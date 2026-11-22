"""Pay approved bills: decide, per bill, whether it is ready to sign or held, with evidence."""
import hashlib
from datetime import date, timedelta

from kavach.masking import mask_account

DUPLICATE_WINDOW_DAYS = 30


def account_hash(account: str) -> str:
    return hashlib.sha256(account.encode()).hexdigest()[:16]


def fingerprint(row: dict) -> str:
    raw = row["raw"]
    parts = [row["item_ref"], raw["amount"], raw["currency"], account_hash(raw["account_number"]), raw["ifsc"],
             str(row["display"].get("beneficiary_version", ""))]
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def evaluate_bills(rows: list[dict], records: dict, sources, today: date) -> list[dict]:
    carriers = records.get("carriers", {})
    history = records.get("payment_history", [])
    seen_in_file: dict[tuple, str] = {}
    out = []
    for row in rows:
        row = {**row, "evidence": [], "decision": {}}
        if row["outcome"] == "cannot_verify":
            row["decision"] = {"owner": "AP lead", "next_step": "Supply the missing value and upload again."}
            out.append(row)
            continue
        raw = row["raw"]
        carrier = carriers.get(raw["carrier_id"])
        if carrier is None:
            out.append(_set(row, "cannot_verify", missing=["carrier record for " + raw["carrier_id"]],
                            reason="No client record for this carrier.", owner="AP lead",
                            next_step="Add the carrier to client records before paying."))
            continue
        row["display"]["carrier"] = carrier["name"]

        active = next((b for b in carrier["beneficiaries"] if b["status"] == "active"), None)
        retired = [b for b in carrier["beneficiaries"] if b["status"] != "active"]
        if active:
            row["display"]["beneficiary_version"] = active["version"]
            row["display"]["approved_destination"] = mask_account(active["account_number"])
        row["evidence"].append({
            "source_type": "client_record", "source_ref": f"carrier {raw['carrier_id']} beneficiary v{active['version'] if active else '-'}",
            "field_or_passage": f"approved account {mask_account(active['account_number']) if active else 'none'}, IFSC {active['ifsc'] if active else '-'}",
            "record_date": active.get("authorized_at") if active else None, "retrieved_at": None,
        })

        key = (raw["carrier_id"], raw["amount"], raw["currency"])
        paid = next((h for h in history if h["bill_id"] == row["item_ref"]), None)
        dup = next((h for h in history if (h["carrier_id"], h["amount"], h["currency"]) == key
                    and date.fromisoformat(h["paid_on"]) >= today - timedelta(days=DUPLICATE_WINDOW_DAYS)), None)
        contact = carrier.get("trusted_contact")
        contact_text = (f"{contact['role']} (client record {contact['record_id']}, enrolled {contact['enrolled_at']})"
                        if contact else None)

        if paid:
            out.append(_set(row, "hold_already_paid", reason=f"Bill {paid['bill_id']} was already paid on {paid['paid_on']}.",
                            owner="AP lead", next_step="Do not pay again. Check why it was re-submitted.",
                            ev=("payment_history", f"bill {paid['bill_id']}", f"paid on {paid['paid_on']}", paid["paid_on"])))
            continue
        if not active or raw["account_number"] != active["account_number"] or raw["ifsc"] != active["ifsc"]:
            is_retired = any(raw["account_number"] == b["account_number"] for b in retired)
            approved = mask_account(active["account_number"]) if active else "none"
            requested = mask_account(raw["account_number"])
            why = "a retired account" if is_retired else "a new account"
            nxt = (f"AP lead: confirm through the trusted contact, {contact_text}, before the client cutoff. "
                   "A separate authorizer must approve the beneficiary update." if contact_text
                   else "No trusted contact is on record. Enrol one before this change can be confirmed.")
            also = (f" It also has the same carrier and amount as {seen_in_file[key]}." if key in seen_in_file else "")
            sender = raw.get("sender_email", "")
            domain = sender.partition("@")[2].lower().strip() if "@" in sender else ""
            if domain and carrier.get("domain") and domain != carrier["domain"]:
                corroborated = sources.company_domain(carrier["domain"])
                if corroborated.get("call"):
                    row.setdefault("calls", []).append(corroborated["call"])
                if corroborated.get("status") != "budget_exceeded":
                    row["evidence"].append({
                        "source_type": "api_response" if corroborated.get("primary_domain") else "client_record",
                        "source_ref": corroborated.get("source_ref", f"carrier {raw['carrier_id']} record"),
                        "field_or_passage": f"primary_domain={corroborated.get('primary_domain') or carrier['domain']} (sender used {domain})",
                        "record_date": None, "retrieved_at": corroborated.get("retrieved_at"),
                    })
            out.append(_set(row, "hold_bank_change",
                            reason=f"Approved account {approved}; the bill requests {requested} ({why}). "
                                   "A bank branch does not prove who owns an account." + also,
                            owner="AP lead", next_step=nxt))
            continue

        if dup or key in seen_in_file:
            earlier = dup["bill_id"] + f" (paid {dup['paid_on']})" if dup else seen_in_file[key]
            out.append(_set(row, "hold_possible_duplicate",
                            reason=f"Same carrier, amount and currency as {earlier}. Possible duplicate, not proven.",
                            owner="AP lead", next_step="Confirm with the carrier statement whether this is a second charge.",
                            ev=("payment_history", f"bill {dup['bill_id']}" if dup else "this upload",
                                f"{raw['currency']} {raw['amount']} to {raw['carrier_id']}", dup["paid_on"] if dup else None)))
            continue
        seen_in_file[key] = row["item_ref"]

        ifsc = sources.ifsc(raw["ifsc"])
        row.setdefault("calls", []).append(ifsc["call"])
        if ifsc["status"] == "invalid":
            out.append(_set(row, "hold_invalid_routing", reason=f"IFSC {raw['ifsc']} is not a valid bank branch code.",
                            owner="AP lead", next_step="Get the correct IFSC from the carrier's approved record.",
                            ev=("api_response", ifsc["call"]["endpoint"], "HTTP 404", None, ifsc["retrieved_at"])))
            continue
        if ifsc["status"] == "ok":
            row["evidence"].append({"source_type": "api_response", "source_ref": ifsc["call"]["endpoint"],
                                    "field_or_passage": f"BANK={ifsc['bank']}, BRANCH={ifsc['branch']} (branch exists; does not prove account owner)",
                                    "record_date": None, "retrieved_at": ifsc["retrieved_at"]})
        else:
            row["evidence"].append({"source_type": "api_response", "source_ref": ifsc["call"]["endpoint"],
                                    "field_or_passage": "IFSC lookup unavailable; routing not re-checked (approved record matches)",
                                    "record_date": None, "retrieved_at": ifsc["retrieved_at"]})

        sender = raw.get("sender_email", "")
        domain = sender.partition("@")[2].lower().strip() if "@" in sender else ""
        if domain and carrier.get("domain") and domain != carrier["domain"]:
            corroborated = sources.company_domain(carrier["domain"])
            if corroborated.get("call"):
                row.setdefault("calls", []).append(corroborated["call"])
            if corroborated.get("status") == "budget_exceeded":
                out.append(_set(row, "cannot_verify",
                                missing=["sender domain corroboration (run allowance reached)"],
                                reason="Run allowance reached before corroborating the carrier domain. Bill is not released.",
                                owner="Controller", next_step="Raise the run allowance or check the sender domain manually."))
                continue
            dist = _edit_distance(domain, carrier["domain"])
            label = "a near-copy of" if dist <= 2 or carrier["domain"].split(".")[0] in domain else "different from"
            out.append(_set(row, "review_sender_domain",
                            reason=f"Sender domain {domain} is {label} the carrier's recorded domain {carrier['domain']}. "
                                   "This needs review; it is not an accusation.",
                            owner="AP lead", next_step="Check the request through the trusted contact before signing.",
                            ev=("api_response" if corroborated.get("primary_domain") else "client_record",
                                corroborated.get("source_ref", f"carrier {raw['carrier_id']} record"),
                                f"primary_domain={corroborated.get('primary_domain') or carrier['domain']}", None,
                                corroborated.get("retrieved_at"))))
            continue

        out.append(_set(row, "ready", reason="Amount, destination and IFSC match the approved beneficiary.",
                        owner="Controller", next_step="Sign in the batch."))
    return out


def _set(row, outcome, missing=None, reason="", owner="", next_step="", ev=None):
    row["outcome"] = outcome
    if missing:
        row["missing"] = missing
    row["decision"] = {"reason": reason, "owner": owner, "next_step": next_step}
    if ev:
        stype, ref, passage, record_date, *rest = ev
        row["evidence"].append({"source_type": stype, "source_ref": ref, "field_or_passage": passage,
                                "record_date": record_date, "retrieved_at": rest[0] if rest else None})
    return row

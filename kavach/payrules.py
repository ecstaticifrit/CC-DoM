"""Pay approved bills: decide, per bill, whether it is ready to sign or held, with evidence."""
import hashlib
import re
from datetime import date, datetime, timedelta, timezone

from kavach.masking import mask_account

DUPLICATE_WINDOW_DAYS = 30
NEWS_WINDOW_DAYS = 90
NEWS_HEADLINES = 3
RESULTS = ("pass", "fail", "warn", "info", "unknown")
SMALL_CARRIER_NOTE = "No company directory record. This is normal for small truck owners."
ALLOWANCE_NOTE = "The run allowance was reached before this check ran."


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


def evidence_item(check, result, source, summary, proves, limits, *, source_type, source_ref, passage,
                  record_date=None, retrieved_at=None, url=None, data=None, cost=0.0) -> dict:
    """One evidence item in the shape the UI renders. data holds display facts (strings and numbers only)."""
    assert result in RESULTS, result
    clean = {k: (v if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v))
             for k, v in (data or {}).items() if v not in (None, "", [])}
    return {"source_type": source_type, "source_ref": source_ref, "field_or_passage": passage,
            "record_date": record_date, "retrieved_at": retrieved_at,
            "check": check, "result": result, "source": source, "summary": summary, "proves": proves,
            "limits": limits, "url": url, "data": clean, "cost_credits": round(float(cost or 0.0), 4)}


def not_run(check, source, res, *, source_ref, cost=0.0, data=None) -> dict:
    """Evidence for a check that did not run: run allowance reached or the source did not answer."""
    budget = res.get("status") == "budget_exceeded"
    summary = ALLOWANCE_NOTE if budget else f"{source} did not answer, so this check did not run."
    return evidence_item(check, "unknown", source, summary, "Nothing. The check did not run.",
                         "A check that did not run proves nothing either way.",
                         source_type="api_response", source_ref=source_ref,
                         passage="run allowance reached" if budget else f"status={(res.get('call') or {}).get('status', 'unavailable')}",
                         retrieved_at=res.get("retrieved_at"), data=data, cost=cost)


def lookup(row: dict, cache: dict, sources, method: str, *args) -> tuple[dict, float]:
    """Call one source adapter once per run. Returns (result, credits this row paid)."""
    key = (method, *args)
    if key in cache:
        return cache[key], 0.0
    fn = getattr(sources, method, None)
    res = fn(*args) if fn else {"status": "unavailable", "call": None}
    if res.get("call"):
        row.setdefault("calls", []).append(res["call"])
    cache[key] = res
    return res, float((res.get("call") or {}).get("cost_credits", 0.0) or 0.0)


def company_facts(company: dict) -> dict:
    return {"Company": company.get("name"), "Domain": company.get("primary_domain"),
            "Founded": company.get("year_founded"), "Size": company.get("employee_count_range"),
            "Type": company.get("company_type"), "Markets": ", ".join(company.get("markets") or []) or None}


def _company_url(company: dict, domain: str) -> str:
    return company.get("website") or f"https://{company.get('primary_domain') or domain}"


def _carrier_record_check(row, raw, carrier, cache, sources) -> dict:
    """Carrier company record: does a company directory own the carrier's recorded domain?"""
    domain = (carrier.get("domain") or "").lower()
    if not domain:
        row["evidence"].append(evidence_item(
            "Carrier company record", "info", "Client record", SMALL_CARRIER_NOTE,
            "The client record has no web domain for this carrier.",
            "A missing directory record says nothing bad about the carrier.",
            source_type="client_record", source_ref=f"carrier {raw['carrier_id']} record", passage="domain: none",
            data={"Carrier": carrier.get("name")}))
        return {"status": "no_domain"}
    res, cost = lookup(row, cache, sources, "company_identify", domain)
    ref = res.get("source_ref", f"Crustdata company_identify domains=[{domain}]")
    status = res.get("status")
    company = res.get("company") or {}
    if status == "ok" and company:
        row["evidence"].append(evidence_item(
            "Carrier company record", "pass", "Crustdata",
            f"Crustdata lists {company.get('name')} as the company that owns {domain}.",
            "A company directory links the carrier's recorded domain to a named company.",
            "A directory record does not prove who owns a bank account or who sent a bill.",
            source_type="api_response", source_ref=ref,
            passage=f"primary_domain={company.get('primary_domain')}, name={company.get('name')}",
            retrieved_at=res.get("retrieved_at"), url=_company_url(company, domain), data=company_facts(company), cost=cost))
    elif status == "not_found":
        row["evidence"].append(evidence_item(
            "Carrier company record", "info", "Crustdata", SMALL_CARRIER_NOTE,
            "The company directory has no company for this domain.",
            "A missing directory record says nothing bad about the carrier.",
            source_type="api_response", source_ref=ref, passage=f"no company owns {domain} (client record domain {domain})",
            retrieved_at=res.get("retrieved_at"), data={"Domain": domain}, cost=cost))
    else:
        row["evidence"].append(not_run("Carrier company record", "Crustdata", res, source_ref=ref, cost=cost,
                                       data={"Domain": domain}))
    return res


def _sender_check(row, raw, carrier, carrier_res, cache, sources) -> None:
    """Sender email domain: evidence only; the outcome rules stay in evaluate_bills."""
    sender = raw.get("sender_email", "")
    domain = sender.partition("@")[2].lower().strip() if "@" in sender else ""
    if not domain:
        return
    recorded = (carrier.get("domain") or "").lower()
    facts = {"Sender domain": domain, "Carrier domain": recorded or "none"}
    ref = f"carrier {raw['carrier_id']} record"
    if not recorded:
        row["evidence"].append(evidence_item(
            "Sender email domain", "info", "Client record",
            "The client record has no domain for this carrier, so Kavach cannot compare the sender domain.",
            "Nothing about the sender.", "A missing domain does not prove the email is false or genuine.",
            source_type="client_record", source_ref=ref, passage=f"sender domain {domain}; carrier domain none", data=facts))
        return
    if domain == recorded:
        row["evidence"].append(evidence_item(
            "Sender email domain", "pass", "Client record",
            f"The sender domain {domain} matches the carrier domain in the client record exactly.",
            "The email came from the domain the client has on record for this carrier.",
            "A matching domain does not prove who sent the email.",
            source_type="client_record", source_ref=ref, passage=f"sender domain {domain} = carrier domain {recorded}",
            data=facts))
        return
    res, cost = lookup(row, cache, sources, "company_identify", domain)
    sref = res.get("source_ref", f"Crustdata company_identify domains=[{domain}]")
    status, owner = res.get("status"), res.get("company") or {}
    carrier_co = (carrier_res or {}).get("company") or {}
    passage = f"sender domain {domain}; carrier domain {recorded}"
    limits = "A directory result does not prove who sent the email."
    if status == "ok" and owner:
        facts["Directory owner"] = owner.get("name")
        same = carrier_co and owner.get("crustdata_company_id") == carrier_co.get("crustdata_company_id")
        if same:
            item = ("info", f"Crustdata lists {domain} as a domain of {owner.get('name')}, but the client record does not list it.",
                    "The sender domain belongs to the same company as the carrier domain.")
        else:
            item = ("warn", f"Crustdata links {domain} to a different company, {owner.get('name')}.",
                    "The sender domain belongs to a different company than the carrier domain.")
        row["evidence"].append(evidence_item(
            "Sender email domain", item[0], "Crustdata", item[1], item[2], limits, source_type="api_response",
            source_ref=sref, passage=passage + f"; directory owner {owner.get('name')}", retrieved_at=res.get("retrieved_at"),
            url=_company_url(owner, domain), data=facts, cost=cost))
    elif status == "not_found":
        row["evidence"].append(evidence_item(
            "Sender email domain", "warn", "Crustdata", "No company in the Crustdata directory owns this domain.",
            "The sender domain is not the carrier's recorded domain and no directory company owns it.", limits,
            source_type="api_response", source_ref=sref, passage=passage + "; no directory owner",
            retrieved_at=res.get("retrieved_at"), data=facts, cost=cost))
    else:
        row["evidence"].append(not_run("Sender email domain", "Crustdata", res, source_ref=sref, cost=cost, data=facts))


def _profile_check(row, raw, carrier, carrier_res, cache, sources) -> None:
    company = (carrier_res or {}).get("company") or {}
    cid = company.get("crustdata_company_id")
    if not cid:
        row["evidence"].append(evidence_item(
            "Carrier company profile", "info", "Crustdata" if carrier.get("domain") else "Client record",
            "No company profile was looked up because the directory has no record for this carrier.",
            "Nothing about the carrier.", "A missing profile does not confirm or reject the bank change.",
            source_type="client_record", source_ref=f"carrier {raw['carrier_id']} record", passage="no directory record"))
        return
    res, cost = lookup(row, cache, sources, "company_enrich", cid)
    ref = res.get("source_ref", f"Crustdata company_enrich crustdata_company_ids=[{cid}]")
    prof = res.get("profile") or {}
    if res.get("status") != "ok" or not prof:
        row["evidence"].append(not_run("Carrier company profile", "Crustdata", res, source_ref=ref, cost=cost,
                                       data={"Company": company.get("name")}))
        return
    place = ", ".join(x for x in (prof.get("city"), prof.get("country")) if x)
    staff = f"about {prof['headcount_total']} employees" if prof.get("headcount_total") else "no headcount figure"
    row["evidence"].append(evidence_item(
        "Carrier company profile", "info", "Crustdata",
        f"Crustdata describes {prof.get('name')} with {staff}" + (f" and a head office in {place}." if place else "."),
        "The carrier is a known company in the directory.",
        "A company profile does not confirm or reject the bank change.",
        source_type="api_response", source_ref=ref,
        passage=f"name={prof.get('name')}, primary_domain={prof.get('primary_domain')}, headcount={prof.get('headcount_total')}",
        retrieved_at=res.get("retrieved_at"), url=_company_url(prof, carrier.get("domain") or ""),
        data={**company_facts(prof), "Employees": prof.get("headcount_total"), "Head office": prof.get("headquarters"),
              "Country": prof.get("country")}, cost=cost))


def news_query(carrier_name: str) -> str:
    name = re.sub(r"\s*\([^)]*\)", "", carrier_name or "").strip()
    return f'"{name}" (merger OR acquisition OR "bank account" OR fraud)'


def _news_check(row, carrier, cache, sources, today: date) -> None:
    query = news_query(carrier.get("name", ""))
    since = today - timedelta(days=NEWS_WINDOW_DAYS)
    start = int(datetime(since.year, since.month, since.day, tzinfo=timezone.utc).timestamp())
    res, cost = lookup(row, cache, sources, "web_search_live", query, start)
    ref = res.get("source_ref", f"Crustdata web_search_live query={query}")
    if res.get("status") != "ok":
        row["evidence"].append(not_run("Carrier news", "Crustdata", res, source_ref=ref, cost=cost, data={"Query": query}))
        return
    hits = [h for h in res.get("results", []) if h.get("title")]
    top = hits[:NEWS_HEADLINES]
    data = {"Query": query, "Since": since.isoformat(), "Results": len(hits)}
    for i, h in enumerate(top, 1):
        data[f"Headline {i}"] = h["title"]
        data[f"Link {i}"] = h.get("url") or ""
    summary = (f"The web search found {len(hits)} results about the carrier since {since.isoformat()}. "
               f"The top {len(top)} are shown as context." if hits
               else f"The web search found no news about the carrier since {since.isoformat()}.")
    row["evidence"].append(evidence_item(
        "Carrier news", "info", "Crustdata", summary,
        "These pages mention the carrier name in the search window.",
        "News is context only. It does not confirm or reject the bank change.",
        source_type="api_response", source_ref=ref, passage="; ".join(h["title"] for h in top) or "no results",
        retrieved_at=res.get("retrieved_at"), url=(top[0].get("url") or None) if top else None, data=data, cost=cost))


def evaluate_bills(rows: list[dict], records: dict, sources, today: date) -> list[dict]:
    carriers = records.get("carriers", {})
    history = records.get("payment_history", [])
    seen_in_file: dict[tuple, str] = {}
    cache: dict[tuple, dict] = {}  # (adapter method, *args) -> result; one call per run
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
                            next_step="Add the carrier to client records before paying.",
                            ev=evidence_item("Approved bank account", "fail", "Client record",
                                             "The client records have no carrier with this ID.",
                                             "Nothing about the carrier.", "A missing record does not mean the bill is false.",
                                             source_type="client_record", source_ref=f"carrier {raw['carrier_id']}",
                                             passage="no carrier record", data={"Carrier ID": raw["carrier_id"]})))
            continue
        row["display"]["carrier"] = carrier["name"]

        active = next((b for b in carrier["beneficiaries"] if b["status"] == "active"), None)
        retired = [b for b in carrier["beneficiaries"] if b["status"] != "active"]
        if active:
            row["display"]["beneficiary_version"] = active["version"]
            row["display"]["approved_destination"] = mask_account(active["account_number"])
        row["evidence"].append(_approved_account_ev(raw, active))
        carrier_res = _carrier_record_check(row, raw, carrier, cache, sources)

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
                            ev=evidence_item("Payment history", "fail", "Payment history",
                                             f"Bill {paid['bill_id']} was already paid on {paid['paid_on']}.",
                                             "The client's payment history shows this bill as paid.",
                                             "The history does not show why the bill came again.",
                                             source_type="payment_history", source_ref=f"bill {paid['bill_id']}",
                                             passage=f"paid on {paid['paid_on']}", record_date=paid["paid_on"],
                                             data={"Bill": paid["bill_id"], "Paid on": paid["paid_on"]})))
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
            _sender_check(row, raw, carrier, carrier_res, cache, sources)
            _profile_check(row, raw, carrier, carrier_res, cache, sources)
            _news_check(row, carrier, cache, sources, today)
            out.append(_set(row, "hold_bank_change",
                            reason=f"Approved account {approved}; the bill requests {requested} ({why}). "
                                   "A bank branch does not prove who owns an account." + also,
                            owner="AP lead", next_step=nxt))
            continue

        if dup or key in seen_in_file:
            earlier = dup["bill_id"] + f" ({dup.get('kind', 'paid')} {dup['paid_on']})" if dup else seen_in_file[key]
            out.append(_set(row, "hold_possible_duplicate",
                            reason=f"Same carrier, amount and currency as {earlier}. Possible duplicate, not proven.",
                            owner="AP lead", next_step="Confirm with the carrier statement whether this is a second charge.",
                            ev=evidence_item("Payment history", "warn", "Payment history",
                                             f"An earlier payment or bill, {earlier}, has the same carrier, amount and currency.",
                                             "Two payments with the same carrier, amount and currency exist close together.",
                                             "A match does not prove that this bill is a second charge.",
                                             source_type="payment_history",
                                             source_ref=f"bill {dup['bill_id']}" if dup else "this upload",
                                             passage=f"{raw['currency']} {raw['amount']} to {raw['carrier_id']}",
                                             record_date=dup["paid_on"] if dup else None,
                                             data={"Earlier": earlier, "Amount": f"{raw['currency']} {raw['amount']}",
                                                   "Window": f"{DUPLICATE_WINDOW_DAYS} days"})))
            continue
        seen_in_file[key] = row["item_ref"]
        row["evidence"].append(evidence_item(
            "Payment history", "pass", "Payment history",
            f"No payment to this carrier for {raw['currency']} {raw['amount']} in the last {DUPLICATE_WINDOW_DAYS} days, "
            "and no earlier bill like it in this file.",
            "The client's payment history has no recent payment like this one.",
            "The history covers only payments the client has recorded.",
            source_type="payment_history", source_ref="payment history and this upload",
            passage=f"no {raw['currency']} {raw['amount']} to {raw['carrier_id']} since "
                    f"{(today - timedelta(days=DUPLICATE_WINDOW_DAYS)).isoformat()}",
            data={"Amount": f"{raw['currency']} {raw['amount']}", "Window": f"{DUPLICATE_WINDOW_DAYS} days"}))

        ifsc = sources.ifsc(raw["ifsc"])
        row.setdefault("calls", []).append(ifsc["call"])
        ifsc_url = ifsc["call"]["endpoint"]
        if ifsc["status"] == "invalid":
            out.append(_set(row, "hold_invalid_routing", reason=f"IFSC {raw['ifsc']} is not a valid bank branch code.",
                            owner="AP lead", next_step="Get the correct IFSC from the carrier's approved record.",
                            ev=evidence_item("Bank branch (IFSC)", "fail", "IFSC registry",
                                             f"The IFSC registry has no branch with code {raw['ifsc']}.",
                                             "The bank routing code on the bill is not a real branch.",
                                             "The registry does not say which code is correct.",
                                             source_type="api_response", source_ref=ifsc_url, passage="HTTP 404",
                                             retrieved_at=ifsc["retrieved_at"], url=ifsc_url, data={"IFSC": raw["ifsc"]})))
            continue
        if ifsc["status"] == "ok":
            row["evidence"].append(evidence_item(
                "Bank branch (IFSC)", "pass", "IFSC registry",
                f"IFSC {raw['ifsc']} is a real branch: {ifsc['bank']}, {ifsc['branch']}.",
                "The bank routing code points to a real bank branch.",
                "A real branch does not prove who owns the account.",
                source_type="api_response", source_ref=ifsc_url,
                passage=f"BANK={ifsc['bank']}, BRANCH={ifsc['branch']} (branch exists; does not prove account owner)",
                retrieved_at=ifsc["retrieved_at"], url=ifsc_url,
                data={"IFSC": raw["ifsc"], "Bank": ifsc["bank"], "Branch": ifsc["branch"]}))
        else:
            row["evidence"].append(evidence_item(
                "Bank branch (IFSC)", "unknown", "IFSC registry",
                ALLOWANCE_NOTE if ifsc["status"] == "budget_exceeded"
                else "The IFSC registry did not answer, so the branch was not checked again.",
                "Nothing new. The approved record already matches this IFSC.",
                "A check that did not run proves nothing either way.",
                source_type="api_response", source_ref=ifsc_url,
                passage="IFSC lookup unavailable; routing not re-checked (approved record matches)",
                retrieved_at=ifsc["retrieved_at"], url=ifsc_url, data={"IFSC": raw["ifsc"]}))

        _sender_check(row, raw, carrier, carrier_res, cache, sources)
        sender = raw.get("sender_email", "")
        domain = sender.partition("@")[2].lower().strip() if "@" in sender else ""
        if domain and carrier.get("domain") and domain != carrier["domain"]:
            if carrier_res.get("status") == "budget_exceeded":
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
                            owner="AP lead", next_step="Check the request through the trusted contact before signing."))
            continue

        out.append(_set(row, "ready", reason="Amount, destination and IFSC match the approved beneficiary.",
                        owner="Controller", next_step="Sign in the batch."))
    return out


def _approved_account_ev(raw: dict, active: dict | None) -> dict:
    requested = mask_account(raw["account_number"])
    ref = f"carrier {raw['carrier_id']} beneficiary v{active['version'] if active else '-'}"
    passage = (f"approved account {mask_account(active['account_number']) if active else 'none'}, "
               f"IFSC {active['ifsc'] if active else '-'}")
    if not active:
        return evidence_item("Approved bank account", "fail", "Client record",
                             "The client record has no active approved account for this carrier.",
                             "No account is approved for this carrier.", "A missing record does not mean the bill is false.",
                             source_type="client_record", source_ref=ref, passage=passage, data={"This bill": requested})
    approved = mask_account(active["account_number"])
    data = {"Approved": f"{approved} (v{active['version']})", "This bill": requested,
            "Approved IFSC": active["ifsc"], "Bill IFSC": raw["ifsc"]}
    if raw["account_number"] != active["account_number"]:
        result, summary = "fail", f"The bill requests {requested}, not the approved account {approved}."
    elif raw["ifsc"] != active["ifsc"]:
        result, summary = "fail", f"The bill uses IFSC {raw['ifsc']}, not the approved IFSC {active['ifsc']}."
    else:
        result, summary = "pass", f"The bill pays the approved account {approved} (beneficiary v{active['version']})."
    return evidence_item("Approved bank account", result, "Client record", summary,
                         f"The client approved this account for the carrier on {active.get('authorized_at') or 'a recorded date'}.",
                         "An approved record does not prove the bill itself is genuine.",
                         source_type="client_record", source_ref=ref, passage=passage,
                         record_date=active.get("authorized_at"), data=data)


def _set(row, outcome, missing=None, reason="", owner="", next_step="", ev=None):
    row["outcome"] = outcome
    if missing:
        row["missing"] = missing
    row["decision"] = {"reason": reason, "owner": owner, "next_step": next_step}
    if ev:
        row["evidence"].append(ev)
    return row

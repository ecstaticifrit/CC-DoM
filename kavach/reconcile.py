"""Reconcile payment-file bills against the bank statement by bank reference, amount and currency."""
import re
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

REF = re.compile(r"\bKV[A-Z0-9]{1,16}\b")


def lines_from_csv(rows: list[dict]) -> list[dict]:
    """Statement rows: date, description, amount, currency, reference; optional type (debit or credit).

    Every line is a debit unless `type` says credit (for example, a returned payment). The sign of the
    amount is ignored. The bank reference may be in `reference` or in the description.
    """
    out = []
    for r in rows:
        raw = r["raw"]
        try:
            paise = int((Decimal(raw.get("amount", "")).copy_abs() * 100).to_integral_value())
        except InvalidOperation:
            paise = None
        text = f"{raw.get('reference', '')} {raw.get('description', '')}".upper()
        refs = set(REF.findall(text)) | ({raw["reference"].strip().upper()} if raw.get("reference", "").strip() else set())
        kind = (raw.get("type") or "debit").strip().lower()
        out.append({"line": r["row_number"], "date": raw.get("date", ""), "refs": refs, "amount": paise,
                    "currency": raw.get("currency", "").upper(), "kind": "credit" if kind.startswith("c") else "debit"})
    return out


def match(bills: list[dict], lines: list[dict]):
    """bills: outbox rows with bill_id, reference_id, amount (paise), currency, reconciled_json, returned_json.

    Returns (paid by outbox id, returned by outbox id, open items with reasons, lines not linked to these bills).
    """
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    paid, returned, open_items, used = {}, {}, [], set()
    for b in bills:
        ref = b["reference_id"]
        same = lambda ln: ref in ln["refs"]
        exact = lambda ln: same(ln) and ln["amount"] == b["amount"] and ln["currency"] == b["currency"]
        debits = [ln for ln in lines if ln["kind"] == "debit" and exact(ln)]
        credits = [ln for ln in lines if ln["kind"] == "credit" and exact(ln)]
        used |= {ln["line"] for ln in lines if same(ln)}
        if credits and not b.get("returned_json"):
            returned[b["id"]] = {"line": credits[0]["line"], "date": credits[0]["date"], "at": stamp}
        if b.get("reconciled_json"):
            if len(debits) > 1:
                open_items.append({"bill_id": b["bill_id"], "reason": f"{len(debits)} debits carry reference {ref}. "
                                   "Possible double payment by the bank. Ask the bank to recall one."})
            continue
        if len(debits) == 1:
            paid[b["id"]] = {"line": debits[0]["line"], "date": debits[0]["date"], "matched_on": "bank reference", "at": stamp}
        elif len(debits) > 1:
            open_items.append({"bill_id": b["bill_id"], "reason": f"{len(debits)} debits carry reference {ref}. "
                               "Possible double payment by the bank. Not reconciled."})
        elif any(same(ln) and ln["kind"] == "debit" for ln in lines):
            open_items.append({"bill_id": b["bill_id"], "reason": f"A debit has reference {ref} but a different amount or currency."})
        else:
            open_items.append({"bill_id": b["bill_id"], "reason": f"No debit with reference {ref} yet. The file may not be uploaded."})
    unlinked = [ln["line"] for ln in lines if ln["line"] not in used]
    return paid, returned, open_items, unlinked

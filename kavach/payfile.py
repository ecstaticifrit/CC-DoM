"""Bank payment file: the signed batch as one bulk-transfer CSV for the client's bank portal.

Kavach does not move money. The controller uploads this file to the bank. Each bill gets one bank
reference and appears in exactly one file line, ever. The bank statement then proves what was paid.
"""
import csv
import hashlib
import io
import re

COLUMNS = ["payment_type", "beneficiary_name", "beneficiary_account", "ifsc", "amount", "currency",
           "bank_reference", "narration", "bill_id"]


def bank_ref(bill_id: str) -> str:
    """Deterministic per bill. A bill can be signed only once per client, so the reference is unique."""
    return ("KV" + re.sub(r"[^A-Za-z0-9]", "", bill_id).upper())[:18]


def build(lines: list[dict]) -> bytes:
    """lines: dicts with bill_id, carrier name, full account number, ifsc, amount, currency."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(COLUMNS)
    for ln in lines:
        name = re.sub(r"\s+", " ", re.sub(r"[^A-Za-z0-9 .\-]", " ", ln["name"])).strip()[:35]
        ref = bank_ref(ln["bill_id"])
        w.writerow(["NEFT", name, ln["account_number"], ln["ifsc"], ln["amount"], ln["currency"], ref,
                    f"{ref} {ln['bill_id']}"[:30], ln["bill_id"]])
    return buf.getvalue().encode()


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()

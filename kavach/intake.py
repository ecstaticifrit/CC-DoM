"""Provisional CSV intake. Replace or adapt when the kickoff format is known."""
import csv
import io
from decimal import Decimal, InvalidOperation

from kavach.masking import mask_account, mask_email

MAX_BYTES = 2_000_000
MAX_ROWS = 1000

FORMATS = {
    "pay_bills": {
        "required": ["bill_id", "carrier_id", "carrier_name", "amount", "currency", "account_number", "ifsc"],
        "optional": ["sender_email"],
        "ref": "bill_id",
    },
    "post_lines": {
        "required": ["date", "description", "amount", "currency"],
        "optional": ["reference"],
        "ref": None,
    },
}


class IntakeError(ValueError):
    """A whole-file problem. The message never contains input values."""


def parse(mode: str, data: bytes) -> list[dict]:
    spec = FORMATS.get(mode)
    if spec is None:
        raise IntakeError("Choose a job: Pay approved bills or Post bank lines.")
    if not data.strip():
        raise IntakeError("The file is empty.")
    if len(data) > MAX_BYTES:
        raise IntakeError("The file is larger than 2 MB.")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise IntakeError("The file is not UTF-8 text. Export it as CSV (UTF-8).") from None

    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip() for h in (reader.fieldnames or [])]
    missing_cols = [c for c in spec["required"] if c not in headers]
    if missing_cols:
        raise IntakeError(
            "The file is missing these columns: " + ", ".join(missing_cols)
            + ". Expected columns: " + ", ".join(spec["required"] + spec["optional"]) + "."
        )

    rows = []
    for i, record in enumerate(reader, start=1):
        if i > MAX_ROWS:
            raise IntakeError(f"The file has more than {MAX_ROWS} rows.")
        record = {(k or "").strip(): (v or "").strip() for k, v in record.items()}
        rows.append(_row(mode, spec, i, record))
    if not rows:
        raise IntakeError("The file has a header but no rows.")
    return rows


def _row(mode: str, spec: dict, number: int, record: dict) -> dict:
    missing = [c for c in spec["required"] if not record.get(c)]
    amount = record.get("amount", "")
    try:
        amount_display = f"{Decimal(amount):,.2f}" if amount else ""
    except InvalidOperation:
        amount_display = ""
        if "amount" not in missing:
            missing.append("amount (not a number)")

    display = {"amount": amount_display, "currency": record.get("currency", "")}
    if mode == "pay_bills":
        display |= {
            "carrier": record.get("carrier_name", ""),
            "destination": mask_account(record["account_number"]) if record.get("account_number") else "",
            "ifsc": record.get("ifsc", ""),
            "sender": mask_email(record["sender_email"]) if record.get("sender_email") else "",
        }
        item_ref = record.get("bill_id") or f"row {number}"
    else:
        display |= {
            "date": record.get("date", ""),
            "description": record.get("description", ""),
            "reference": record.get("reference", ""),
        }
        item_ref = f"line {number}"

    return {
        "row_number": number,
        "item_ref": item_ref,
        "outcome": "cannot_verify" if missing else "not_checked",
        "missing": missing,
        "display": display,
        "raw": record,
    }

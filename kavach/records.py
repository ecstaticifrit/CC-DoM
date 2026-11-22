import json
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def load_records(data_dir: Path = DATA_DIR) -> dict:
    """Client records: carriers, beneficiaries, payment history, vendors and ledger rules."""
    merged: dict = {}
    for name in ("client_records.json", "carriers.json"):
        path = Path(data_dir) / name
        if path.exists():
            merged |= json.loads(path.read_text())
    return merged


def apply_changes(records: dict, changes: list[dict]) -> dict:
    """Add each authorized beneficiary change as a new active version and retire the earlier ones."""
    carriers = json.loads(json.dumps(records.get("carriers", {})))
    for ch in changes:
        carrier = carriers.get(ch["carrier_id"])
        if carrier is None:
            continue
        for b in carrier["beneficiaries"]:
            b["status"] = "retired"
        version = max((b["version"] for b in carrier["beneficiaries"]), default=0) + 1
        carrier["beneficiaries"].append({"version": version, "account_number": ch["account_number"], "ifsc": ch["ifsc"],
                                         "status": "active", "authorized_at": ch["authorized_at"],
                                         "authorized_by": ch["authorized_by"]})
    return {**records, "carriers": carriers}

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

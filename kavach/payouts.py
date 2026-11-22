"""Local INR ledger. A transfer records both wallet balances in the approval transaction."""
from decimal import Decimal

OPENING_PAISE = 10_000_000  # Rs 100,000 per fresh demo database.


def as_inr(paise: int) -> str:
    return f"{paise // 100:,}.{paise % 100:02d}"


def treasury_balance(con) -> int:
    last = con.execute("SELECT treasury_after FROM sim_transfers ORDER BY payout_id DESC LIMIT 1").fetchone()
    return last[0] if last else OPENING_PAISE


def transfer(con, payout_id: int, reference: str, raw: dict, beneficiary_version: int) -> None:
    amount = Decimal(raw["amount"])
    treasury = treasury_balance(con)
    if raw["currency"] != "INR" or not amount.is_finite() or amount <= 0 or amount != amount.quantize(Decimal("0.01")):
        reason = "Simulation requires a positive INR amount in whole paise."
    elif amount > Decimal(treasury) / 100:
        reason = "Insufficient demo balance. No simulated funds moved."
    else:
        paise = int(amount * 100)
        wallet = f"{raw['carrier_id']}:v{beneficiary_version}"
        last = con.execute("SELECT beneficiary_after FROM sim_transfers WHERE wallet=? "
                           "ORDER BY payout_id DESC LIMIT 1", (wallet,)).fetchone()
        con.execute("INSERT INTO sim_transfers (payout_id, wallet, paise, treasury_after, beneficiary_after) "
                    "VALUES (?, ?, ?, ?, ?)", (payout_id, wallet, paise, treasury - paise, (last[0] if last else 0) + paise))
        con.execute("UPDATE outbox SET status='submitted', provider_status='processed', provider_id=? WHERE id=?",
                    ("sim_" + reference, payout_id))
        return
    con.execute("UPDATE outbox SET status='failed', provider_status='failed', note=? WHERE id=?", (reason, payout_id))

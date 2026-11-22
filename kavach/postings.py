"""Post bank lines: find the legal payee and ledger account for each statement line.

Pure module. External fetches go through an injected fetch_text(url) -> (text, retrieved_at).
"""
import re
import uuid
from decimal import Decimal, InvalidOperation

NO_DESCRIPTOR_RULE = "legal payee: no client record links this descriptor to a vendor"
SNIPPET_CHARS = 120


def evaluate_lines(rows: list[dict], records: dict, fetch_text) -> list[dict]:
    fetched: dict[str, tuple] = {}  # url -> (text, retrieved_at) or (None, None); one attempt per run
    seen: dict[tuple, str] = {}  # (vendor, amount, currency, date) -> earliest item_ref
    out = []
    for row in rows:
        new = {**row, "missing": list(row.get("missing", [])), "display": dict(row.get("display", {})),
               "evidence": [], "calls": []}
        if row.get("outcome") != "cannot_verify":
            _evaluate(new, records, fetch_text, fetched, seen)
        out.append(new)
    return out


def _evaluate(row, records, fetch_text, fetched, seen):
    raw = row["raw"]
    vendor_id = _match_vendor(raw.get("description", ""), records.get("descriptor_rules", []))
    if vendor_id is None or vendor_id not in records.get("vendors", {}):
        return _cannot(row, NO_DESCRIPTOR_RULE)

    vendor = records["vendors"][vendor_id]
    legal_name = vendor["legal_name"]
    evidence = _legal_name_evidence(row, vendor, fetch_text, fetched)
    if evidence is None:
        return _cannot(row, f"legal payee: vendor legal page unavailable or does not state {legal_name}")
    row["evidence"].append(evidence)
    row["display"]["legal_payee"] = legal_name

    ledger = records.get("ledger_rules", {}).get(vendor_id)
    if not ledger:
        return _cannot(row, f"ledger rule for {legal_name}")
    row["display"]["ledger_account"] = ledger
    row["evidence"].append({
        "source_type": "client_record", "source_ref": f"ledger rule {vendor_id}",
        "field_or_passage": f"{vendor_id} -> {ledger}", "record_date": None, "retrieved_at": None,
    })

    key = (vendor_id, _amount(raw.get("amount", "")), raw.get("currency", "").upper(), raw.get("date", ""))
    if key in seen:
        row["outcome"] = "hold_possible_duplicate"
        row["display"]["reason"] = (f"Same payee, amount and date as {seen[key]}. "
                                    "Held for approval as a possible duplicate charge.")
        return
    seen[key] = row["item_ref"]
    row["outcome"] = "posted"
    row["missing"] = []
    row["posting"] = {"posting_id": "post_" + uuid.uuid4().hex[:12], "legal_payee": legal_name, "ledger_account": ledger}


def _cannot(row, fact):
    row["outcome"] = "cannot_verify"
    row["missing"].append(fact)


def _match_vendor(descriptor, rules):
    text = descriptor.casefold()
    hits = [r for r in rules if r.get("pattern") and r["pattern"].casefold() in text]
    return max(hits, key=lambda r: len(r["pattern"]))["vendor_id"] if hits else None


def _amount(value):
    try:
        return Decimal(value)
    except InvalidOperation:
        return value


def _legal_name_evidence(row, vendor, fetch_text, fetched):
    src, name = vendor["source"], vendor["legal_name"]
    if src["type"] in ("client_record", "registry"):
        return {"source_type": src["type"], "source_ref": src["ref"], "field_or_passage": f"legal_name: {name}",
                "record_date": src.get("record_date"), "retrieved_at": None}
    if src["type"] != "vendor_legal_page":
        return None
    url, needle = src["url"], src.get("must_contain", name)
    if url not in fetched:
        try:
            fetched[url] = fetch_text(url)
            status = "ok"
        except Exception:
            fetched[url] = (None, None)
            status = "error"
        text = fetched[url][0]
        if status == "ok" and (text is None or needle not in " ".join(text.split())):
            status = "error"
        row["calls"].append({"adapter": "web", "endpoint": url, "cost_credits": 0, "status": status})
    text, retrieved_at = fetched[url]
    if not text:
        return None
    flat = " ".join(text.split())
    i = flat.find(needle)
    if i < 0:
        return None
    pad = max(0, (SNIPPET_CHARS - len(needle)) // 2)
    snippet = flat[max(0, i - pad): i + len(needle) + pad].strip()
    return {"source_type": "web_page", "source_ref": url, "field_or_passage": snippet,
            "record_date": None, "retrieved_at": retrieved_at}


def fetch_page_text(url: str) -> tuple[str, str]:
    """Live fetch_text for evaluate_lines: page text with HTML tags removed, and UTC retrieval time."""
    import html
    from datetime import datetime, timezone

    import httpx

    resp = httpx.get(url, timeout=15, follow_redirects=True)
    resp.raise_for_status()
    text = resp.text.replace("\\n", " ").replace('\\"', '"')
    text = html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\xa0", " ")
    return text, datetime.now(timezone.utc).isoformat(timespec="seconds")

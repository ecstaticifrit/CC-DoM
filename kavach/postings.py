"""Post bank lines: find the legal payee and ledger account for each statement line.

Pure module. External fetches go through an injected fetch_text(url) -> (text, retrieved_at).
"""
import re
import uuid
from decimal import Decimal, InvalidOperation

from kavach.payrules import company_facts, evidence_item, lookup, not_run

NO_DESCRIPTOR_RULE = "legal payee: no client record links this descriptor to a vendor"
SNIPPET_CHARS = 120
SUGGESTIONS = 3


def evaluate_lines(rows: list[dict], records: dict, fetch_text, *, sources=None) -> list[dict]:
    """Evaluate statement lines. With sources (a BudgetedSources), add Crustdata checks and display["chain"]."""
    fetched: dict[str, tuple] = {}  # url -> (text, retrieved_at, via) or (None, None, None); one attempt per run
    seen: dict[tuple, str] = {}  # (vendor, amount, currency, date) -> earliest item_ref
    cache: dict[tuple, dict] = {}  # Crustdata calls; one per run
    out = []
    for row in rows:
        new = {**row, "missing": list(row.get("missing", [])), "display": dict(row.get("display", {})),
               "evidence": [], "calls": []}
        chain = _Chain(new) if sources is not None else None
        if row.get("outcome") != "cannot_verify":
            _evaluate(new, records, fetch_text, fetched, seen, sources, cache, chain)
        elif chain:
            chain.fail("Bank text", "The bank line is missing: " + ", ".join(new["missing"] or ["a required value"]) + ".")
        if chain:
            chain.done()
        out.append(new)
    return out


class _Chain:
    """Bank text -> Merchant -> Legal payee -> Ledger rule -> Posting. Stops at the first missing link."""

    def __init__(self, row):
        self.row, self.steps, self.gap = row, [], None

    def add(self, step, value, source, result="pass"):
        self.steps.append({"step": step, "value": value, "source": source, "result": result})

    def fail(self, step, gap):
        self.steps.append({"step": step, "value": None, "source": None, "result": "fail"})
        self.gap = gap

    def done(self):
        self.row["display"]["chain"] = self.steps
        self.row["display"]["chain_gap"] = self.gap


def _evaluate(row, records, fetch_text, fetched, seen, sources, cache, chain):
    raw = row["raw"]
    desc = raw.get("description", "")
    if chain:
        chain.add("Bank text", desc, None)
    rule = _match_rule(desc, records.get("descriptor_rules", []))
    vendor_id = rule["vendor_id"] if rule else None
    if vendor_id is None or vendor_id not in records.get("vendors", {}):
        fact = NO_DESCRIPTOR_RULE
        if sources is not None:
            fact = _merchant_lookup(row, desc, sources, cache)
        if chain:
            chain.fail("Merchant", f"No client record links the bank text {desc} to a merchant, "
                                   "so Kavach cannot name the legal payee.")
        return _cannot(row, fact)

    vendor = records["vendors"][vendor_id]
    legal_name = vendor["legal_name"]
    row["evidence"].append(evidence_item(
        "Merchant", "pass", "Client record", f"The client descriptor rule {rule['pattern']} links this bank text to {vendor_id}.",
        "The client has a rule that names the merchant for this bank text.",
        "A descriptor rule does not prove the legal payee.",
        source_type="client_record", source_ref=f"descriptor rule {rule['pattern']} -> {vendor_id}",
        passage=f"{rule['pattern']} in {desc}", data={"Rule": rule["pattern"], "Vendor": vendor_id}))
    merchant_value, merchant_source = vendor_id, "Client record"
    if sources is not None and vendor.get("domain"):
        company = _merchant_company(row, vendor, sources, cache)
        if company:
            merchant_value, merchant_source = f"{company.get('name')} ({vendor['domain']})", "Crustdata"
    if chain:
        chain.add("Merchant", merchant_value, merchant_source)

    evidence = _legal_name_evidence(row, vendor, fetch_text, fetched, sources, cache)
    if evidence is None:
        row["evidence"].append(evidence_item(
            "Legal payee", "fail", "Web page", f"The vendor legal page is unavailable or does not state {legal_name}.",
            "Nothing about the legal payee.", "A failed fetch does not prove the payee is wrong.",
            source_type="web_page", source_ref=(vendor.get("source") or {}).get("url") or (vendor.get("source") or {}).get("ref", ""),
            passage=f"{legal_name} not found", url=(vendor.get("source") or {}).get("url"), data={"Looked for": legal_name}))
        if chain:
            chain.fail("Legal payee", f"No source states the legal payee {legal_name} for this merchant.")
        return _cannot(row, f"legal payee: vendor legal page unavailable or does not state {legal_name}")
    row["evidence"].append(evidence)
    row["display"]["legal_payee"] = legal_name
    if chain:
        chain.add("Legal payee", legal_name, evidence["source"])

    ledger = records.get("ledger_rules", {}).get(vendor_id)
    if not ledger:
        row["evidence"].append(evidence_item(
            "Ledger rule", "fail", "Client record", f"No ledger rule assigns {legal_name} to a ledger account.",
            "The client has no ledger account for this payee.", "A missing rule does not mean the charge is wrong.",
            source_type="client_record", source_ref=f"ledger rule {vendor_id}", passage=f"{vendor_id} -> none"))
        if chain:
            chain.fail("Ledger rule", f"No ledger rule assigns {legal_name} to a ledger account.")
        return _cannot(row, f"ledger rule for {legal_name}")
    row["display"]["ledger_account"] = ledger
    row["evidence"].append(evidence_item(
        "Ledger rule", "pass", "Client record", f"The client ledger rule assigns {legal_name} to {ledger}.",
        "The client chose this ledger account for this payee.", "A ledger rule does not prove the charge is correct.",
        source_type="client_record", source_ref=f"ledger rule {vendor_id}", passage=f"{vendor_id} -> {ledger}",
        data={"Payee": legal_name, "Ledger account": ledger}))
    if chain:
        chain.add("Ledger rule", ledger, "Client record")

    key = (vendor_id, _amount(raw.get("amount", "")), raw.get("currency", "").upper(), raw.get("date", ""))
    if key in seen:
        row["outcome"] = "hold_possible_duplicate"
        row["display"]["reason"] = (f"Same payee, amount and date as {seen[key]}. "
                                    "Held for approval as a possible duplicate charge.")
        row["evidence"].append(evidence_item(
            "Duplicate charge", "warn", "Payment history", f"An earlier line, {seen[key]}, has the same payee, amount and date.",
            "Two charges with the same payee, amount and date are in this statement.",
            "A match does not prove that the bank charged twice.",
            source_type="payment_history", source_ref="this upload",
            passage=f"{raw.get('currency', '')} {raw.get('amount', '')} to {legal_name} on {raw.get('date', '')}",
            data={"Earlier line": seen[key]}))
        if chain:
            chain.add("Posting", f"Held: possible duplicate of {seen[key]}", "Payment history", "warn")
        return
    seen[key] = row["item_ref"]
    row["evidence"].append(evidence_item(
        "Duplicate charge", "pass", "Payment history", "No earlier line in this statement has the same payee, amount and date.",
        "This charge is not repeated earlier in this statement.", "The check covers only this statement.",
        source_type="payment_history", source_ref="this upload",
        passage=f"{raw.get('currency', '')} {raw.get('amount', '')} to {legal_name} on {raw.get('date', '')}"))
    row["outcome"] = "posted"
    row["missing"] = []
    row["posting"] = {"posting_id": "post_" + uuid.uuid4().hex[:12], "legal_payee": legal_name, "ledger_account": ledger}
    if chain:
        chain.add("Posting", f"Posted to {ledger}", "Client record")


def _merchant_company(row, vendor, sources, cache):
    """Corroborate the vendor with Crustdata company_identify on the vendor's domain."""
    domain = vendor["domain"].lower()
    res, cost = lookup(row, cache, sources, "company_identify", domain)
    ref = res.get("source_ref", f"Crustdata company_identify domains=[{domain}]")
    company = res.get("company") or {}
    if res.get("status") == "ok" and company:
        row["evidence"].append(evidence_item(
            "Merchant company record", "pass", "Crustdata", f"Crustdata lists {company.get('name')} as the company that owns {domain}.",
            "A company directory links the vendor domain to a named company.",
            "A directory record does not prove the legal entity that took this charge.",
            source_type="api_response", source_ref=ref,
            passage=f"primary_domain={company.get('primary_domain')}, name={company.get('name')}",
            retrieved_at=res.get("retrieved_at"), url=company.get("website") or f"https://{domain}",
            data=company_facts(company), cost=cost))
        return company
    if res.get("status") == "not_found":
        row["evidence"].append(evidence_item(
            "Merchant company record", "info", "Crustdata", "No company in the Crustdata directory owns this vendor domain.",
            "Nothing about the merchant.", "A missing directory record does not mean the merchant is wrong.",
            source_type="api_response", source_ref=ref, passage=f"no company owns {domain}",
            retrieved_at=res.get("retrieved_at"), data={"Domain": domain}, cost=cost))
    else:
        row["evidence"].append(not_run("Merchant company record", "Crustdata", res, source_ref=ref, cost=cost,
                                       data={"Domain": domain}))
    return None


def _merchant_lookup(row, desc, sources, cache) -> str:
    """No client rule: search the web for the descriptor. Suggestions only; never a payee."""
    res, cost = lookup(row, cache, sources, "web_search_live", desc, None)
    ref = res.get("source_ref", f"Crustdata web_search_live query={desc}")
    if res.get("status") != "ok":
        row["evidence"].append(not_run("Merchant lookup", "Crustdata", res, source_ref=ref, cost=cost, data={"Searched": desc}))
        return (f"{NO_DESCRIPTOR_RULE}; the web search for {desc} did not run, "
                "and no source links a payee to this charge")
    names = [h["title"] for h in res.get("results", []) if h.get("title")][:SUGGESTIONS]
    data = {"Searched": desc, "Results": len(res.get("results", []))}
    for i, n in enumerate(names, 1):
        data[f"Suggestion {i}"] = n
    row["evidence"].append(evidence_item(
        "Merchant lookup", "unknown", "Crustdata",
        (f"A web search for {desc} gave {len(names)} possible names. They are suggestions only." if names
         else f"A web search for {desc} found no possible names."),
        "Web pages use words like this bank text.",
        "A web result does not link a payee to this charge, so Kavach cannot post the line.",
        source_type="api_response", source_ref=ref, passage="; ".join(names) or "no results",
        retrieved_at=res.get("retrieved_at"), url=next((h.get("url") for h in res.get("results", []) if h.get("url")), None),
        data=data, cost=cost))
    return f"{NO_DESCRIPTOR_RULE}; the web search for {desc} gave suggestions only, and no source links a payee to this charge"


def _cannot(row, fact):
    row["outcome"] = "cannot_verify"
    row["missing"].append(fact)


def _match_rule(descriptor, rules):
    text = descriptor.casefold()
    hits = [r for r in rules if r.get("pattern") and r["pattern"].casefold() in text]
    return max(hits, key=lambda r: len(r["pattern"])) if hits else None


def _match_vendor(descriptor, rules):
    rule = _match_rule(descriptor, rules)
    return rule["vendor_id"] if rule else None


def _amount(value):
    try:
        return Decimal(value)
    except InvalidOperation:
        return value


def _states(text, needle) -> bool:
    return bool(text) and needle in " ".join(text.split())


def _fetch(url, needle, fetch_text, sources, cache, row):
    """Vendor page text: Crustdata web_enrich_live first when sources is given, then the direct fetch."""
    if sources is not None:
        res, _ = lookup(row, cache, sources, "web_enrich_live", url)
        if res.get("status") == "ok" and _states(res.get("text"), needle):
            return res["text"], res.get("retrieved_at"), "Crustdata web_enrich_live"
    try:
        text, retrieved_at = fetch_text(url)
        status = "ok" if _states(text, needle) else "error"
    except Exception:
        text, retrieved_at, status = None, None, "error"
    row["calls"].append({"adapter": "web", "endpoint": url, "cost_credits": 0, "status": status})
    return text, retrieved_at, "direct fetch"


def _legal_name_evidence(row, vendor, fetch_text, fetched, sources=None, cache=None):
    src, name = vendor["source"], vendor["legal_name"]
    if src["type"] in ("client_record", "registry"):
        return evidence_item(
            "Legal payee", "pass", "Client record", f"The client record names the legal payee {name}, from {src['ref']}.",
            "A registry record held by the client names this legal entity.",
            "The registry does not link this charge to the entity; the client descriptor rule does.",
            source_type=src["type"], source_ref=src["ref"], passage=f"legal_name: {name}",
            record_date=src.get("record_date"), data={"Legal payee": name, "Record": src["ref"]})
    if src["type"] != "vendor_legal_page":
        return None
    url, needle = src["url"], src.get("must_contain", name)
    if url not in fetched:
        text, retrieved_at, via = _fetch(url, needle, fetch_text, sources, cache if cache is not None else {}, row)
        fetched[url] = (text, retrieved_at, via)
    text, retrieved_at, via = fetched[url]
    if not text:
        return None
    flat = " ".join(text.split())
    i = flat.find(needle)
    if i < 0:
        return None
    pad = max(0, (SNIPPET_CHARS - len(needle)) // 2)
    snippet = flat[max(0, i - pad): i + len(needle) + pad].strip()
    return evidence_item(
        "Legal payee", "pass", "Web page", f"The vendor legal page states {needle}.",
        "The vendor's own page names this legal entity.",
        "The page does not prove that this charge was paid to that entity.",
        source_type="web_page", source_ref=url if sources is None else f"{url} (via {via})", passage=snippet,
        retrieved_at=retrieved_at, url=url, data={"Legal payee": name, "Fetched by": via})


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

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from kavach import payrules
from kavach.config import load_config
from kavach.intake import IntakeError, parse
from kavach.records import load_records
from kavach.sources import BudgetedSources, LiveSources
from kavach.store import Store

HERE = Path(__file__).parent
MODES = {"pay_bills": "Pay approved bills", "post_lines": "Post bank lines"}
LABELS = {
    "not_checked": "Not checked yet", "cannot_verify": "Cannot verify", "ready": "Ready to sign",
    "hold_bank_change": "Held: bank account changed", "hold_already_paid": "Held: already paid",
    "hold_possible_duplicate": "Held: possible duplicate", "hold_invalid_routing": "Held: invalid IFSC",
    "review_sender_domain": "Review: sender domain", "already_signed": "Already signed earlier",
    "signed": "Signed", "posted": "Posted",
}
ATTENTION_ORDER = ["cannot_verify", "hold_bank_change", "hold_already_paid", "hold_possible_duplicate",
                   "hold_invalid_routing", "review_sender_domain", "already_signed", "not_checked", "ready", "signed", "posted"]


def create_app(db_path: Path, sources=None, today: date | None = None) -> FastAPI:
    config = load_config()
    store = Store(db_path)
    sources = sources or LiveSources()
    app = FastAPI(title="Kavach")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals["LABELS"] = LABELS
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def ctx(**extra):
        return {"modes": MODES, "config": config, "demo_balance": store.demo_balance(), **extra}

    @app.get("/", response_class=HTMLResponse)
    def start(request: Request):
        return templates.TemplateResponse(request, "start.html", ctx())

    @app.get("/samples/{filename}")
    def sample_file(filename: str):
        allowed = {"friday_bills.csv", "public_tariff_bills.csv"}
        if filename not in allowed:
            raise HTTPException(404, "Sample not found")
        path = HERE.parent / "data" / "samples" / filename
        if not path.exists():
            raise HTTPException(404, "Sample not found")
        return FileResponse(path, media_type="text/csv", filename=filename)

    @app.post("/runs")
    async def create_run(request: Request, mode: str = Form("pay_bills"), run_credits: str = Form(""), file: UploadFile | None = None):
        if mode != "pay_bills":
            return templates.TemplateResponse(request, "start.html", ctx(error="Start with approved carrier bills."), status_code=400)
        live_config = load_config()
        data = await file.read() if file else b""
        try:
            rows = parse(mode, data)
        except IntakeError as err:
            return templates.TemplateResponse(request, "start.html", ctx(error=str(err)), status_code=400)
        input_hash = hashlib.sha256(data).hexdigest()
        try:
            cap = float(run_credits) if run_credits.strip() else float(live_config["limits"]["run_credits"])
        except ValueError:
            cap = float(live_config["limits"]["run_credits"])
        budgeted = BudgetedSources(sources, max_credits=max(0.0, cap), max_seconds=float(live_config["limits"]["run_seconds"]))
        records = load_records()
        rows = payrules.evaluate_bills(rows, records, budgeted, today or date.today())
        for row in rows:
            earlier = store.payout_for_bill(row["item_ref"]) if row["outcome"] != "cannot_verify" else None
            if earlier:
                row["outcome"] = "already_signed"
                row["decision"] = {"reason": f"Bill {row['item_ref']} was already signed in {earlier['run_id']} "
                                             f"(reference {earlier['reference_id'][:8]}…). Kavach will not pay it twice.",
                                   "owner": "Controller", "next_step": "Open the earlier run to follow that payout."}
        run_id = store.create_run(mode, live_config["rule_version"], rows, input_hash=input_hash, allowance_credits=cap)
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    def _run_or_404(run_id: str) -> dict:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return run

    def _fingerprints(run: dict) -> dict[int, str]:
        out = {}
        if run["payout_mode"] != "simulation":
            return out
        for r in run["rows"]:
            if r["outcome"] == "ready":
                src = store.raw_row(run["run_id"], r["row_number"])
                out[r["row_number"]] = payrules.fingerprint({"item_ref": r["item_ref"], **src})
        return out

    def _receipt(run: dict) -> dict:
        def total(rows):
            return f"{sum((Decimal(r['raw_amount']) for r in rows), Decimal(0)):,.2f}"
        rows = [{**r, "raw_amount": (r["display"].get("amount") or "0").replace(",", "")} for r in run["rows"]]
        held = [r for r in rows if r["outcome"].startswith(("hold_", "review_", "cannot_verify"))]
        payouts = [r for r in rows if r["payout"]]
        submitted = [r for r in payouts if r["payout"]["status"] == "submitted"]
        processed = [r for r in submitted if r["payout"]["provider_status"] == "processed"]
        credits = sum(c["cost_credits"] for c in run["calls"])
        rate = config["costs"]
        allowance = {**config["limits"]}
        if run.get("allowance_credits") is not None:
            allowance["run_credits"] = run["allowance_credits"]
        return {
            "run_id": run["run_id"], "mode": run["mode"], "payout_mode": run["payout_mode"] or "historical",
            "sandbox": config["sandbox_label"] if run["payout_mode"] else "Historical run; no new transfers.",
            "simulated_transfers": run["transfers"],
            "allowance": allowance,
            "counts": {k: sum(1 for r in rows if r["outcome"] == k) for k in LABELS if any(r["outcome"] == k for r in rows)},
            "ready_total": total([r for r in rows if r["outcome"] == "ready"]),
            "held_total": total(held), "held": len(held),
            "signed": len(payouts), "submitted": len(submitted), "processed": len(processed),
            "submitted_total": total(submitted), "processed_total": total(processed),
            "reconciled": 0, "reconciled_note": "Reconciliation needs a bank statement; none supplied in this run.",
            "posted": sum(1 for r in rows if r["outcome"] == "posted"),
            "cost": {
                "external_calls": len(run["calls"]), "crustdata_credits": round(credits, 2),
                "usd": round(credits * rate["usd_per_credit"], 2),
                "inr": round(credits * rate["usd_per_credit"] * rate["inr_per_usd"], 2),
                "conversion": f"$1 = Rs {rate['inr_per_usd']} ({rate['rate_date']}); 1 credit = ${rate['usd_per_credit']}",
                "model_spend": "None. No LLM is used: inputs are structured and rules decide.",
                "sponsored": "Crustdata credits are hackathon-sponsored; costs shown at list price.",
                "calls": run["calls"],
            },
            "personal_data": {
                "categories": ["carrier bank account numbers", "carrier names", "sender email addresses"] if run["mode"] == "pay_bills"
                              else ["bank statement descriptors", "vendor legal names"],
                "shown_as": "Account numbers show only the last 4 digits. Email addresses show only the domain. Raw input stays on the server.",
                "retention": f"{config['privacy']['retention_days']} days (policy; no deletion has been performed yet)",
                "person_lookups": sum(1 for c in run["calls"] if c["adapter"].startswith("person")),
            },
        }

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_page(request: Request, run_id: str):
        run = _run_or_404(run_id)
        rows = sorted(run["rows"], key=lambda r: (ATTENTION_ORDER.index(r["outcome"]) if r["outcome"] in ATTENTION_ORDER else 99, r["row_number"]))
        return templates.TemplateResponse(request, "run.html", ctx(
            run=run, rows=rows, mode_label=MODES[run["mode"]], receipt=_receipt(run)))

    @app.post("/runs/{run_id}/confirm", response_class=HTMLResponse)
    async def confirm(request: Request, run_id: str):
        run = _run_or_404(run_id)
        form = await request.form()
        chosen = {int(v) for v in form.getlist("row")}
        fps = _fingerprints(run)
        items = [r for r in run["rows"] if r["row_number"] in chosen and r["row_number"] in fps]
        if not items:
            return RedirectResponse(f"/runs/{run_id}", status_code=303)
        total = f"{sum(Decimal(r['display']['amount'].replace(',', '')) for r in items):,.2f}"
        return templates.TemplateResponse(request, "confirm.html", ctx(run=run, items=items, fps=fps, total=total))

    @app.post("/runs/{run_id}/approve")
    async def approve(request: Request, run_id: str):
        run = _run_or_404(run_id)
        form = await request.form()
        items = [(int(v.split(":")[0]), v.split(":")[1]) for v in form.getlist("item")]
        store.approve(run_id, items, _fingerprints(run), signer="controller")
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    @app.get("/runs/{run_id}/result.json")
    def result(run_id: str):
        run = _run_or_404(run_id)
        return {
            "run_id": run["run_id"], "mode": run["mode"], "rule_version": run["rule_version"], "created_at": run["created_at"],
            "payout_mode": run["payout_mode"] or "historical",
            "rows": [{
                "row_number": r["row_number"], "item_ref": r["item_ref"], "outcome": r["outcome"], "missing": r["missing"],
                "display": r["display"], "decision": r["decision"], "evidence": r["evidence"], "posting": r["posting"],
                "payout": {k: r["payout"][k] for k in ("status", "provider_id", "provider_status", "utr", "note")} if r["payout"] else None,
            } for r in run["rows"]],
        }

    @app.get("/runs/{run_id}/receipt.json")
    def receipt(run_id: str):
        return _receipt(_run_or_404(run_id))

    @app.get("/runs/{run_id}/status.json")
    def status(run_id: str):
        run = _run_or_404(run_id)
        return {"run_id": run["run_id"], "updated_at": run["updated_at"], "rows": len(run["rows"])}

    return app

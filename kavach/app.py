import hashlib
import time
from datetime import date
from decimal import Decimal
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from kavach import payrules, reconcile
from kavach.config import load_config
from kavach.intake import FORMATS, IntakeError, _row, parse
from kavach.masking import mask_account
from kavach.records import apply_changes, load_records
from kavach.sources import BudgetedSources, LiveSources
from kavach.store import Store

HERE = Path(__file__).parent
MODES = {"pay_bills": "Pay approved bills", "post_lines": "Post bank lines"}
LABELS = {
    "not_checked": "Not checked yet", "cannot_verify": "Cannot verify", "ready": "Ready to sign",
    "hold_bank_change": "Held: bank account changed", "hold_already_paid": "Held: already paid",
    "hold_possible_duplicate": "Held: possible duplicate", "hold_invalid_routing": "Held: invalid IFSC",
    "review_sender_domain": "Review: sender domain", "already_signed": "Already signed earlier",
    "signed": "Signed: in payment file", "posted": "Posted", "reopened_reversed": "Reopened: payment returned",
}
ATTENTION = ("hold_", "review_", "cannot_verify", "reopened_reversed")
ATTENTION_ORDER = ["reopened_reversed", "cannot_verify", "hold_bank_change", "hold_already_paid", "hold_possible_duplicate",
                   "hold_invalid_routing", "review_sender_domain", "already_signed", "not_checked", "ready", "signed", "posted"]


def create_app(db_path: Path, sources=None, today: date | None = None) -> FastAPI:
    config = load_config()
    store = Store(db_path)
    sources = sources or LiveSources()

    def current_records() -> dict:
        return apply_changes(load_records(), store.authorized_changes())

    def stale_bills(file_id: str) -> list[str]:
        """Bills in a frozen file whose destination is no longer the carrier's active beneficiary."""
        carriers = current_records().get("carriers", {})
        out = []
        for ln in store.file_lines(file_id):
            active = next((b for b in carriers.get(ln["raw"].get("carrier_id"), {}).get("beneficiaries", [])
                           if b["status"] == "active"), None)
            if not active or (active["account_number"], active["ifsc"]) != (ln["raw"]["account_number"], ln["raw"]["ifsc"]):
                out.append(ln["bill_id"])
        return out

    app = FastAPI(title="Kavach")
    templates = Jinja2Templates(directory=HERE / "templates")
    templates.env.globals["LABELS"] = LABELS
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    def ctx(**extra):
        return {"modes": MODES, "config": config, **extra}

    @app.get("/", response_class=HTMLResponse)
    def start(request: Request):
        return templates.TemplateResponse(request, "start.html", ctx())

    @app.get("/samples/{filename}")
    def sample_file(filename: str):
        allowed = {"friday_bills.csv", "friday_bank_statement.csv", "public_tariff_bills.csv"}
        if filename not in allowed:
            raise HTTPException(404, "Sample not found")
        path = HERE.parent / "data" / "samples" / filename
        if not path.exists():
            raise HTTPException(404, "Sample not found")
        return FileResponse(path, media_type="text/csv", filename=filename)

    @app.post("/runs")
    async def create_run(request: Request, mode: str = Form("pay_bills"), run_credits: str = Form(""), file: UploadFile | None = None):
        if mode != "pay_bills":
            return templates.TemplateResponse(request, "start.html", ctx(error="Start with approved carrier bills. To check a bank statement, open its signed run."), status_code=400)
        live_config = load_config()
        data = await file.read() if file else b""
        try:
            rows = parse(mode, data)
        except IntakeError as err:
            return templates.TemplateResponse(request, "start.html", ctx(error=str(err)), status_code=400)
        input_hash = hashlib.sha256(data).hexdigest()
        try:
            cap = min(float(live_config["limits"]["run_credits"]), float(run_credits)) if run_credits.strip() else float(live_config["limits"]["run_credits"])
        except ValueError:
            cap = float(live_config["limits"]["run_credits"])
        budgeted = BudgetedSources(sources, max_credits=max(0.0, cap), max_seconds=float(live_config["limits"]["run_seconds"]))
        started = time.monotonic()
        rows = evaluate_bills(rows, budgeted)
        run_id = store.create_run(mode, live_config["rule_version"], rows, input_hash=input_hash, allowance_credits=cap,
                                  eval_ms=int((time.monotonic() - started) * 1000))
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    def evaluate_bills(rows: list[dict], budgeted) -> list[dict]:
        records = current_records()
        records["payment_history"] = [*records.get("payment_history", []), *store.signed_history()]
        rows = payrules.evaluate_bills(rows, records, budgeted, today or date.today())
        for row in rows:
            earlier = store.payout_for_bill(row["item_ref"]) if row["outcome"] != "cannot_verify" else None
            if earlier:
                row["outcome"] = "already_signed"
                row["decision"] = {"reason": f"Bill {row['item_ref']} was already signed in {earlier['run_id']} "
                                             f"(reference {earlier['reference_id'][:8]}…). Kavach will not pay it twice.",
                                   "owner": "Controller", "next_step": "Open the earlier run to follow that payment."}
        return rows

    def reevaluate_row(run: dict, row_number: int) -> None:
        """Re-run the bill rules for one row in its file context, after a client record changed."""
        fresh = [_row("pay_bills", FORMATS["pay_bills"], r["row_number"], r["raw"]) for r in store.raw_rows(run["run_id"])]
        spent = sum(c["cost_credits"] for c in run["calls"])
        cap = run.get("allowance_credits") if run.get("allowance_credits") is not None else float(config["limits"]["run_credits"])
        budgeted = BudgetedSources(sources, max_credits=max(0.0, cap - spent), max_seconds=float(config["limits"]["run_seconds"]))
        evaluated = evaluate_bills(fresh, budgeted)
        target = next(r for r in evaluated if r["row_number"] == row_number)
        store.set_row(run["run_id"], row_number, outcome=target["outcome"], decision=target["decision"],
                      display=target["display"], evidence=target["evidence"], missing=target["missing"])
        store.add_calls(run["run_id"], [c for r in evaluated for c in r.get("calls", [])])

    def _run_or_404(run_id: str) -> dict:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return run

    def _fingerprints(run: dict) -> dict[int, str]:
        out = {}
        for r in run["rows"]:
            if r["outcome"] == "ready":
                src = store.raw_row(run["run_id"], r["row_number"])
                out[r["row_number"]] = payrules.fingerprint({"item_ref": r["item_ref"], **src})
        return out

    def _receipt(run: dict) -> dict:
        def total(rows):
            return f"{sum((Decimal(r['raw_amount']) for r in rows), Decimal(0)):,.2f}"
        rows = [{**r, "raw_amount": (r["display"].get("amount") or "0").replace(",", "")} for r in run["rows"]]
        held = [r for r in rows if r["outcome"].startswith(ATTENTION)]
        signed = [r for r in rows if r["payout"]]
        paid = [r for r in signed if r["payout"]["status"] == "paid"]
        returned = [r for r in signed if r["payout"]["status"] == "returned"]
        refs = [r["payout"]["reference_id"] for r in signed]
        count = lambda *names: sum(1 for r in rows if r["outcome"] in names)
        recon = run.get("reconciliation")
        return {
            "run_id": run["run_id"], "mode": run["mode"], "sandbox": config["sandbox_label"],
            "counts": {k: sum(1 for r in rows if r["outcome"] == k) for k in LABELS if any(r["outcome"] == k for r in rows)},
            "ready_total": total([r for r in rows if r["outcome"] == "ready"]),
            "held_total": total(held), "held": len(held),
            "signed": len(signed), "signed_total": total(signed), "files": run["files"],
            "paid": len(paid), "paid_total": total(paid), "returned": len(returned),
            "waiting_for_bank": len(signed) - len(paid) - len(returned),
            "reconciled_note": (f"Last checked against {recon['source']} at {recon['at']}." if recon
                                else "No bank statement checked yet."),
            "reconciliation": recon,
            "this_run": {
                "rows": len(rows), "check_time": (f"{(run.get('eval_ms') or 0) / 1000:.1f} s" if (run.get("eval_ms") or 0) >= 100 else f"{run.get('eval_ms') or 0} ms"),
                "ready": count("ready", "signed"), "ready_total": total([r for r in rows if r["outcome"] in ("ready", "signed")]),
                "bank_changes": count("hold_bank_change"), "duplicates": count("hold_possible_duplicate", "hold_already_paid", "already_signed"),
                "other_holds": count("hold_invalid_routing", "review_sender_domain", "cannot_verify", "reopened_reversed"),
                "held_total": total(held),
                "with_owner": sum(1 for r in held if (r.get("decision") or {}).get("owner") and (r.get("decision") or {}).get("next_step")),
                "bank_refs": len(refs), "distinct_bank_refs": len(set(refs)), "bills_signed": len(signed),
                "double_debits": sum(1 for o in (recon or {}).get("open", []) if "double payment" in o["reason"]),
                "live_checks": [{"adapter": c["adapter"], "status": c["status"]} for c in run["calls"] if c["status"] == "ok"],
            },
            "posted": sum(1 for r in rows if r["outcome"] == "posted"),
            "personal_data": {
                "categories": ["carrier bank account numbers", "carrier names", "sender email addresses"] if run["mode"] == "pay_bills"
                              else ["bank statement descriptors", "vendor legal names"],
                "shown_as": "Account numbers show only the last 4 digits. Email addresses show only the domain. Raw input stays on the server.",
                "payment_file": ("The bank payment file holds full account numbers, because the bank needs them. "
                                 "Only the signed bills are in it. Each download is counted: "
                                 + (", ".join(f"{f['file_id']} downloaded {f['downloads']} time(s)" for f in run["files"]) or "no file yet") + ".")
                                if run["mode"] == "pay_bills" else None,
                "retention": f"{config['privacy']['retention_days']} days (policy; no deletion has been performed yet)",
                "person_lookups": sum(1 for c in run["calls"] if c["adapter"].startswith("person")),
            },
        }

    def _bank_change_context(run: dict) -> dict[int, dict]:
        """Masked facts the bank-change dialog needs for each held bank-change bill."""
        if run["mode"] != "pay_bills":
            return {}
        carriers = current_records().get("carriers", {})
        out = {}
        for r in run["rows"]:
            change = run["changes"].get(r["row_number"])
            if r["outcome"] != "hold_bank_change" and not change:
                continue
            raw = store.raw_row(run["run_id"], r["row_number"])["raw"]
            carrier = carriers.get(raw.get("carrier_id"), {})
            active = next((b for b in carrier.get("beneficiaries", []) if b["status"] == "active"), None)
            out[r["row_number"]] = {"contact": carrier.get("trusted_contact"), "carrier": carrier.get("name") or r["display"].get("carrier"),
                                    "approved": mask_account(active["account_number"]) if active else "none",
                                    "approved_version": active["version"] if active else None,
                                    "requested": mask_account(raw.get("account_number", "")), "change": change}
        return out

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_page(request: Request, run_id: str):
        run = _run_or_404(run_id)
        rows = sorted(run["rows"], key=lambda r: (ATTENTION_ORDER.index(r["outcome"]) if r["outcome"] in ATTENTION_ORDER else 99, r["row_number"]))
        groups: dict[str, list[str]] = {}
        for r in rows:
            if r["outcome"].startswith(ATTENTION):
                groups.setdefault(r["outcome"], []).append(r["item_ref"])
        return templates.TemplateResponse(request, "run.html", ctx(
            run=run, rows=rows, mode_label=MODES[run["mode"]], receipt=_receipt(run),
            fps=_fingerprints(run) if run["mode"] == "pay_bills" else {},
            contacts=_bank_change_context(run),
            done=request.query_params.get("done", ""), done_n=request.query_params.get("n", ""),
            change_error=request.query_params.get("change_error", ""),
            hold_groups=[{"outcome": k, "label": LABELS.get(k, k), "refs": v} for k, v in groups.items()],
            stale={f["file_id"]: stale_bills(f["file_id"]) for f in run["files"]},
            recon_error=request.query_params.get("recon_error", "")[:160]))

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
        queued, file_id = store.approve(run_id, items, _fingerprints(run), signer="controller")
        return RedirectResponse(f"/runs/{run_id}?done=signed&n={len(queued)}" + ("#payment-file" if file_id else ""), status_code=303)

    @app.get("/runs/{run_id}/files/{file_id}.csv")
    def payment_file(run_id: str, file_id: str):
        content = store.file_content(run_id, file_id)
        if content is None:
            raise HTTPException(404, "Payment file not found")
        return Response(content, media_type="text/csv", headers={
            "Content-Disposition": f'attachment; filename="{file_id}.csv"', "Cache-Control": "no-store"})

    def _bank_change_row(run: dict, row_number: int) -> tuple[dict, dict, dict]:
        row = next((r for r in run["rows"] if r["row_number"] == row_number), None)
        if row is None or run["mode"] != "pay_bills":
            raise HTTPException(404, "Bill not found")
        raw = store.raw_row(run["run_id"], row_number)["raw"]
        carrier = current_records().get("carriers", {}).get(raw.get("carrier_id"), {})
        return row, raw, carrier

    def _change_back(run_id: str, row_number: int, via: str):
        """Where a bank-change form returns: the dialog on the run page, or the full change page."""
        def to(error: str, done: str = "") -> str:
            if via == "dialog":
                query = f"?change_error={error}" if error else (f"?done={done}" if done else "")
                return f"/runs/{run_id}{query}#change-{row_number}"
            return f"/runs/{run_id}/rows/{row_number}/change" + (f"?error={error}" if error else "")
        return to

    @app.get("/runs/{run_id}/rows/{row_number}/change", response_class=HTMLResponse)
    def change_page(request: Request, run_id: str, row_number: int, error: str = ""):
        run = _run_or_404(run_id)
        row, raw, carrier = _bank_change_row(run, row_number)
        active = next((b for b in carrier.get("beneficiaries", []) if b["status"] == "active"), None)
        return templates.TemplateResponse(request, "change.html", ctx(
            run=run, row=row, carrier=carrier, change=run["changes"].get(row_number), error=error,
            approved=mask_account(active["account_number"]) if active else "none",
            approved_version=active["version"] if active else None, requested=mask_account(raw["account_number"])))

    @app.post("/runs/{run_id}/rows/{row_number}/callback")
    def record_callback(run_id: str, row_number: int, callback_by: str = Form(""), outcome: str = Form(""), via: str = Form("")):
        run = _run_or_404(run_id)
        row, raw, carrier = _bank_change_row(run, row_number)
        back = _change_back(run_id, row_number, via)
        contact = carrier.get("trusted_contact")
        if row["outcome"] != "hold_bank_change" or not contact:
            return RedirectResponse(back("no_contact" if not contact else ""), status_code=303)
        if not callback_by.strip() or outcome not in ("confirmed", "denied"):
            return RedirectResponse(back("callback_fields"), status_code=303)
        store.record_callback(run_id, row_number, raw["carrier_id"], raw["account_number"], raw["ifsc"],
                              contact["record_id"], callback_by.strip(), outcome == "confirmed")
        decision = ({"reason": f"{row['decision'].get('reason', '')} Callback through {contact['record_id']} confirmed the change "
                               f"(recorded by {callback_by.strip()}). A recorded callback alone does not release the bill.",
                     "owner": "Authorizer", "next_step": "A different person from the AP lead must authorize the beneficiary update."}
                    if outcome == "confirmed" else
                    {"reason": f"The carrier's trusted contact ({contact['record_id']}) did not confirm the new bank account. "
                               "Treat the request as a possible fraud attempt.",
                     "owner": "Controller", "next_step": "Do not pay to the requested account. Pay only to the approved beneficiary."})
        store.set_row(run_id, row_number, decision=decision)
        return RedirectResponse(back("", done="callback"), status_code=303)

    @app.post("/runs/{run_id}/rows/{row_number}/authorize")
    def authorize_change(run_id: str, row_number: int, authorized_by: str = Form(""), via: str = Form("")):
        run = _run_or_404(run_id)
        _bank_change_row(run, row_number)
        back = _change_back(run_id, row_number, via)
        change = run["changes"].get(row_number)
        who = authorized_by.strip()
        if not change or change["status"] != "callback_confirmed":
            return RedirectResponse(back("no_callback"), status_code=303)
        if not who:
            return RedirectResponse(back("authorizer_name"), status_code=303)
        if who.casefold() == (change["callback_by"] or "").casefold():
            return RedirectResponse(back("same_person"), status_code=303)
        if store.authorize_change(run_id, row_number, who):
            reevaluate_row(_run_or_404(run_id), row_number)
        return RedirectResponse(f"/runs/{run_id}?done=approved#why-{row_number}" if via == "dialog" else f"/runs/{run_id}", status_code=303)

    @app.post("/runs/{run_id}/reconcile")
    async def reconcile_upload(request: Request, run_id: str, file: UploadFile | None = None):
        run = _run_or_404(run_id)
        if run["mode"] != "pay_bills" or not run["files"]:
            raise HTTPException(409, "Sign a carrier payment file before checking the bank statement.")
        data = await file.read() if file else b""
        try:
            rows = parse("post_lines", data)
        except IntakeError as err:
            return RedirectResponse(f"/runs/{run_id}?recon_error={err}#reconcile", status_code=303)
        bills = []
        for o in store.payouts_for_run(run_id):
            raw = store.raw_row(run_id, o["row_number"])["raw"]
            bills.append({**o, "amount": int((Decimal(raw["amount"]) * 100).to_integral_value()), "currency": raw["currency"].upper()})
        lines = reconcile.lines_from_csv(rows)
        paid, returned, open_items, unlinked = reconcile.match(bills, lines)
        store.save_reconciliation(run["run_id"], "uploaded bank statement", hashlib.sha256(data).hexdigest(), {
            "lines": len(lines), "paid": len(paid), "returned": len(returned), "open": open_items,
            "unlinked_lines": len(unlinked)}, paid, returned)
        return RedirectResponse(f"/runs/{run_id}#reconcile", status_code=303)

    @app.get("/runs/{run_id}/result.json")
    def result(run_id: str):
        run = _run_or_404(run_id)
        return {
            "run_id": run["run_id"], "mode": run["mode"], "rule_version": run["rule_version"], "created_at": run["created_at"],
            "payment_files": run["files"],
            "rows": [{
                "row_number": r["row_number"], "item_ref": r["item_ref"], "outcome": r["outcome"], "missing": r["missing"],
                "display": r["display"], "decision": r["decision"],
                "evidence": [{k: v for k, v in ev.items() if k != "cost_credits"} for ev in r["evidence"]], "posting": r["posting"],
                "payout": {k: r["payout"].get(k) for k in ("status", "reference_id", "file_id", "reconciled", "returned")} if r["payout"] else None,
                "beneficiary_change": run["changes"].get(r["row_number"]),
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

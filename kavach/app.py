from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from kavach.config import load_config
from kavach.intake import IntakeError, parse
from kavach.store import Store

HERE = Path(__file__).parent
MODES = {"pay_bills": "Pay approved bills", "post_lines": "Post bank lines"}


def create_app(db_path: Path) -> FastAPI:
    config = load_config()
    store = Store(db_path)
    app = FastAPI(title="Kavach")
    templates = Jinja2Templates(directory=HERE / "templates")
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    @app.get("/", response_class=HTMLResponse)
    def start(request: Request):
        return templates.TemplateResponse(
            request, "start.html", {"modes": MODES, "config": config}
        )

    @app.post("/runs")
    async def create_run(request: Request, mode: str = Form(""), file: UploadFile | None = None):
        data = await file.read() if file else b""
        try:
            rows = parse(mode, data)
        except IntakeError as err:
            return templates.TemplateResponse(
                request, "start.html",
                {"modes": MODES, "config": config, "error": str(err)},
                status_code=400,
            )
        run_id = store.create_run(mode, config["rule_version"], rows)
        return RedirectResponse(f"/runs/{run_id}", status_code=303)

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    def run_page(request: Request, run_id: str):
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        order = {"cannot_verify": 0, "not_checked": 1}
        rows = sorted(run["rows"], key=lambda r: (order.get(r["outcome"], 2), r["row_number"]))
        return templates.TemplateResponse(
            request, "run.html",
            {"run": run, "rows": rows, "mode_label": MODES[run["mode"]], "config": config},
        )

    def _run_or_404(run_id: str) -> dict:
        run = store.get_run(run_id)
        if run is None:
            raise HTTPException(404, "Run not found")
        return run

    @app.get("/runs/{run_id}/result.json")
    def result(run_id: str):
        run = _run_or_404(run_id)
        return {
            "run_id": run["run_id"],
            "mode": run["mode"],
            "rule_version": run["rule_version"],
            "created_at": run["created_at"],
            "rows": [
                {
                    "row_number": r["row_number"],
                    "item_ref": r["item_ref"],
                    "outcome": r["outcome"],
                    "missing": r["missing"],
                    "display": r["display"],
                }
                for r in run["rows"]
            ],
        }

    @app.get("/runs/{run_id}/status.json")
    def status(run_id: str):
        run = _run_or_404(run_id)
        return {"run_id": run["run_id"], "updated_at": run["updated_at"], "rows": len(run["rows"])}

    return app

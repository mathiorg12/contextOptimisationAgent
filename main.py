"""
Main FastAPI application — Context Optimisation Agent.

Endpoints:
  GET  /              — dashboard UI
  POST /run_task      — submit a task (returns task_id)
  GET  /task_status/{task_id}  — poll status + results
  GET  /logs          — tail the live agent_run.log
"""

import asyncio
import os
import time
from typing import Dict, Any

from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from models.provider import ModelProvider
from agents.baseline_agent import BaselineAgent
from agents.dual_agent import DualAgent
from utils.logger import get_logger, read_recent_logs

log = get_logger(__name__)

# ── App setup ──────────────────────────────────────────────────────────────────
app = FastAPI(title="Context Optimisation Agent")

os.makedirs("frontend/static", exist_ok=True)
os.makedirs("output/baseline", exist_ok=True)
os.makedirs("output/optimised", exist_ok=True)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend")

# ── Global task state ──────────────────────────────────────────────────────────
task_registry: Dict[str, Dict[str, Any]] = {}


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/run_task")
async def run_task(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    task_desc = data.get("task", "").strip()

    if not task_desc:
        return JSONResponse({"error": "Task description is required."}, status_code=400)

    task_id = str(int(time.time() * 1000))  # ms timestamp as ID
    task_registry[task_id] = {
        "status": "queued",
        "task": task_desc,
        "results": None,
        "started_at": time.time(),
    }
    log.info("[API] /run_task — task_id=%s  task=%s", task_id, task_desc)

    background_tasks.add_task(_run_comparison, task_id, task_desc)
    return {"task_id": task_id}


@app.get("/task_status/{task_id}")
async def get_task_status(task_id: str):
    entry = task_registry.get(task_id)
    if entry is None:
        return JSONResponse({"error": "Task not found."}, status_code=404)
    return entry


@app.get("/logs", response_class=PlainTextResponse)
async def get_logs():
    """Return the last 300 lines of agent_run.log for live debugging."""
    return read_recent_logs(n_lines=300)


# ── Background task ────────────────────────────────────────────────────────────
async def _run_comparison(task_id: str, task_desc: str):
    """
    Run both agents sequentially and store results in task_registry.
    Both approaches create real local files under output/baseline/ and output/optimised/.
    """
    log.info("[Comparison] ═══ Starting comparison for task_id=%s ═══", task_id)

    results = []

    # ── Approach 1: Baseline (Large Only) ──────────────────────────────────────
    task_registry[task_id]["status"] = "running: approach 1 (large-only)"
    log.info("[Comparison] Starting Approach 1 — Baseline (Large Only)")

    provider_a1 = ModelProvider()
    agent_a1 = BaselineAgent(provider_a1)

    try:
        result_a1 = await asyncio.to_thread(agent_a1.run_task, task_desc)
        metrics_a1 = provider_a1.get_metrics()
        log.info(
            "[Comparison] Approach 1 done — success=%s  tokens=%d  wall=%.1fs",
            result_a1["success"],
            metrics_a1["large"]["total"] + metrics_a1["small"]["total"],
            result_a1["wall_time_s"],
        )
        results.append({
            "mode": "Approach 1 — Large Only",
            "approach": "baseline",
            "output": result_a1["output"],
            "metrics": metrics_a1,
            "created_files": [os.path.relpath(f) for f in result_a1["created_files"]],
            "missing_files": result_a1["missing_files"],
            "step_count": result_a1["step_count"],
            "success": result_a1["success"],
            "wall_time_s": result_a1["wall_time_s"],
        })
    except Exception as e:
        log.error("[Comparison] Approach 1 FAILED: %s", e, exc_info=True)
        results.append({
            "mode": "Approach 1 — Large Only",
            "approach": "baseline",
            "error": str(e),
            "success": False,
        })

    # ── Pause between runs (free-tier quota) ───────────────────────────────────
    log.info("[Comparison] Pausing 60 s between runs to respect free-tier quota...")
    task_registry[task_id]["status"] = "pausing between runs (60 s)"
    await asyncio.sleep(60)

    # ── Approach 2: Dual Agent (Planner + Executor) ────────────────────────────
    task_registry[task_id]["status"] = "running: approach 2 (planner + executor)"
    log.info("[Comparison] Starting Approach 2 — Dual Agent (Planner + Executor)")

    provider_a2 = ModelProvider()
    agent_a2 = DualAgent(provider_a2)

    try:
        result_a2 = await asyncio.to_thread(agent_a2.run_task, task_desc)
        metrics_a2 = provider_a2.get_metrics()
        log.info(
            "[Comparison] Approach 2 done — success=%s  tokens_large=%d  tokens_small=%d  wall=%.1fs",
            result_a2["success"],
            metrics_a2["large"]["total"],
            metrics_a2["small"]["total"],
            result_a2["wall_time_s"],
        )
        results.append({
            "mode": "Approach 2 — Planner + Executor",
            "approach": "dual",
            "output": result_a2["output"],
            "metrics": metrics_a2,
            "created_files": [os.path.relpath(f) for f in result_a2["created_files"]],
            "missing_files": result_a2["missing_files"],
            "step_count": result_a2["step_count"],
            "success": result_a2["success"],
            "wall_time_s": result_a2["wall_time_s"],
        })
    except Exception as e:
        log.error("[Comparison] Approach 2 FAILED: %s", e, exc_info=True)
        results.append({
            "mode": "Approach 2 — Planner + Executor",
            "approach": "dual",
            "error": str(e),
            "success": False,
        })

    task_registry[task_id]["status"] = "completed"
    task_registry[task_id]["results"] = results
    log.info("[Comparison] ═══ Comparison complete for task_id=%s ═══", task_id)


# ── Entry point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    log.info("Starting Context Optimisation Agent server on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)

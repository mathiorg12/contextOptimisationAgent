import os
import asyncio
import json
from typing import Dict, Any, List
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from models.provider import ModelProvider
from agent import LargeModelAgent

app = FastAPI()

# Setup directories
os.makedirs("frontend", exist_ok=True)
os.makedirs("frontend/static", exist_ok=True)

app.mount("/static", StaticFiles(directory="frontend/static"), name="static")
templates = Jinja2Templates(directory="frontend")

# Global state to track tasks
task_status = {}

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/run_task")
async def run_task(request: Request, background_tasks: BackgroundTasks):
    data = await request.json()
    task_desc = data.get("task")
    if not task_desc:
        return JSONResponse({"error": "Task description required"}, status_code=400)
    
    task_id = str(len(task_status) + 1)
    task_status[task_id] = {
        "status": "starting",
        "task": task_desc,
        "results": None
    }
    
    background_tasks.add_task(execute_agent_comparison, task_id, task_desc)
    return {"task_id": task_id}

@app.get("/task_status/{task_id}")
async def get_task_status(task_id: str):
    return task_status.get(task_id, {"error": "Task not found"})

async def execute_agent_comparison(task_id: str, task_desc: str):
    provider = ModelProvider()
    results = []
    
    # Run Baseline
    task_status[task_id]["status"] = "running baseline"
    provider.reset_metrics()
    baseline_agent = LargeModelAgent(provider)
    baseline_agent.file_tool.optimized = False
    
    try:
        baseline_output = await asyncio.to_thread(baseline_agent.run_task, task_desc)
        baseline_metrics = provider.get_metrics()
        results.append({
            "mode": "Baseline",
            "output": baseline_output,
            "metrics": baseline_metrics,
            "success": "FINAL_ANSWER" in baseline_output
        })
    except Exception as e:
        results.append({"mode": "Baseline", "error": str(e)})

    # Wait a bit between runs to refresh quota
    await asyncio.sleep(5)

    # Run Optimised
    task_status[task_id]["status"] = "running optimised"
    provider.reset_metrics()
    optimised_agent = LargeModelAgent(provider)
    optimised_agent.file_tool.optimized = True
    optimised_agent.file_tool.threshold_chars = 500
    
    try:
        optimised_output = await asyncio.to_thread(optimised_agent.run_task, task_desc)
        optimised_metrics = provider.get_metrics()
        results.append({
            "mode": "Optimised",
            "output": optimised_output,
            "metrics": optimised_metrics,
            "success": "FINAL_ANSWER" in optimised_output
        })
    except Exception as e:
        results.append({"mode": "Optimised", "error": str(e)})

    task_status[task_id]["status"] = "completed"
    task_status[task_id]["results"] = results

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

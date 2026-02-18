import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from db import DB
from llm import chat_completion

DB_PATH = os.getenv("DB_PATH", "/data/bench.db")
RESULTS_JSONL = os.getenv("RESULTS_JSONL", "/data/results.jsonl")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://llama:8000/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen25")
LLM_TIMEOUT_S = float(os.getenv("LLM_TIMEOUT_S", "180"))

DEFAULT_TEMPERATURE = float(os.getenv("DEFAULT_TEMPERATURE", "0.2"))
DEFAULT_MAX_TOKENS = int(os.getenv("DEFAULT_MAX_TOKENS", "256"))
DEFAULT_STREAM = os.getenv("DEFAULT_STREAM", "true").lower() in ("1", "true", "yes")

MAX_QUEUE_SIZE = int(os.getenv("MAX_QUEUE_SIZE", "1000"))
WORKERS = int(os.getenv("WORKERS", "1"))

queue: "asyncio.Queue[Dict[str, Any]]" = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
db = DB(DB_PATH)

app = FastAPI(title="bench-api", version="0.1")

class BatchReq(BaseModel):
    run_id: Optional[str] = None
    prompts: List[str] = Field(min_length=1)
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None
    sleep_s: Optional[float] = 0.0

class AskReq(BaseModel):
    prompt: str
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    stream: Optional[bool] = None

@app.on_event("startup")
async def startup():
    Path("/data").mkdir(parents=True, exist_ok=True)
    await db.init()
    for _ in range(max(1, WORKERS)):
        asyncio.create_task(worker_loop())

@app.get("/health")
async def health():
    return {
        "ok": True,
        "llm_base_url": LLM_BASE_URL,
        "model": LLM_MODEL,
        "queue_max": MAX_QUEUE_SIZE,
        "workers": WORKERS,
    }

@app.post("/ask")
async def ask(req: AskReq):
    run_id = f"ask_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
    temperature = req.temperature if req.temperature is not None else DEFAULT_TEMPERATURE
    max_tokens = req.max_tokens if req.max_tokens is not None else DEFAULT_MAX_TOKENS
    stream = req.stream if req.stream is not None else DEFAULT_STREAM

    params = {"temperature": temperature, "max_tokens": max_tokens, "stream": stream}
    await db.create_run(run_id=run_id, total=1, model=LLM_MODEL, params_json=json.dumps(params, ensure_ascii=False))

    res = await chat_completion(
        base_url_v1=LLM_BASE_URL,
        model=LLM_MODEL,
        prompt=req.prompt,
        temperature=float(temperature),
        max_tokens=int(max_tokens),
        stream=bool(stream),
        timeout_s=LLM_TIMEOUT_S,
    )

    usage_json = json.dumps(res.usage, ensure_ascii=False) if res.usage else None
    await db.add_result(
        run_id=run_id, idx=1, prompt=req.prompt, response=res.text, ok=res.ok,
        error=res.error, status_code=res.status_code,
        latency_ms=res.latency_ms, ttft_ms=res.ttft_ms, usage_json=usage_json
    )
    await db.mark_finished(run_id)
    _append_jsonl(run_id, 1, req.prompt, res, params)

    return {
        "run_id": run_id,
        "ok": res.ok,
        "latency_ms": res.latency_ms,
        "ttft_ms": res.ttft_ms,
        "response": res.text,
        "error": res.error,
    }

@app.post("/batch")
async def batch(req: BatchReq):
    run_id = req.run_id or f"run_{datetime.utcnow().strftime('%Y%m%d_%H%M%S_%f')}"
    temperature = req.temperature if req.temperature is not None else DEFAULT_TEMPERATURE
    max_tokens = req.max_tokens if req.max_tokens is not None else DEFAULT_MAX_TOKENS
    stream = req.stream if req.stream is not None else DEFAULT_STREAM
    sleep_s = float(req.sleep_s or 0.0)

    params = {"temperature": float(temperature), "max_tokens": int(max_tokens), "stream": bool(stream), "sleep_s": sleep_s}
    await db.create_run(run_id=run_id, total=len(req.prompts), model=LLM_MODEL, params_json=json.dumps(params, ensure_ascii=False))

    for i, p in enumerate(req.prompts, start=1):
        await queue.put({"run_id": run_id, "idx": i, "prompt": p, "params": params})

    return {"run_id": run_id, "total": len(req.prompts), "queued": len(req.prompts)}

@app.get("/runs/{run_id}")
async def run_status(run_id: str):
    r = await db.get_run(run_id)
    if not r:
        raise HTTPException(404, "run_id no existe")
    return r

@app.get("/runs/{run_id}/results")
async def run_results(run_id: str, limit: int = 1000):
    r = await db.get_run(run_id)
    if not r:
        raise HTTPException(404, "run_id no existe")
    results = await db.get_results(run_id, limit=limit)
    return {"run": r, "results": results}

def _append_jsonl(run_id: str, idx: int, prompt: str, res: Any, params: Dict[str, Any]):
    row = {
        "run_id": run_id,
        "idx": idx,
        "prompt": prompt,
        "response": res.text,
        "ok": res.ok,
        "error": res.error,
        "status_code": res.status_code,
        "latency_ms": res.latency_ms,
        "ttft_ms": res.ttft_ms,
        "usage": res.usage,
        "params": params,
        "utc": datetime.utcnow().isoformat() + "Z",
    }
    with open(RESULTS_JSONL, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")

async def worker_loop():
    while True:
        job = await queue.get()
        try:
            run_id = job["run_id"]
            idx = job["idx"]
            prompt = job["prompt"]
            params = job["params"]

            res = await chat_completion(
                base_url_v1=LLM_BASE_URL,
                model=LLM_MODEL,
                prompt=prompt,
                temperature=float(params["temperature"]),
                max_tokens=int(params["max_tokens"]),
                stream=bool(params["stream"]),
                timeout_s=LLM_TIMEOUT_S,
            )

            usage_json = json.dumps(res.usage, ensure_ascii=False) if res.usage else None
            await db.add_result(
                run_id=run_id, idx=idx, prompt=prompt, response=res.text, ok=res.ok,
                error=res.error, status_code=res.status_code,
                latency_ms=res.latency_ms, ttft_ms=res.ttft_ms, usage_json=usage_json
            )
            _append_jsonl(run_id, idx, prompt, res, params)

            sleep_s = float(params.get("sleep_s", 0.0) or 0.0)
            if sleep_s > 0:
                await asyncio.sleep(sleep_s)

            r = await db.get_run(run_id)
            if r and int(r["done"]) >= int(r["total"]) and r.get("finished_utc") is None:
                await db.mark_finished(run_id)

        finally:
            queue.task_done()

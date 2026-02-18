import json
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import httpx

@dataclass
class LLMResp:
    ok: bool
    text: str
    latency_ms: float
    ttft_ms: Optional[float]
    status_code: Optional[int]
    error: Optional[str]
    usage: Optional[Dict[str, Any]]

async def chat_completion(
    base_url_v1: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    stream: bool,
    timeout_s: float,
) -> LLMResp:
    """Call llama-server OpenAI-compatible endpoint: POST {base_url_v1}/chat/completions"""
    url = base_url_v1.rstrip("/") + "/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": bool(stream),
    }

    start = time.perf_counter()
    status_code = None
    ttft_ms = None
    usage = None
    parts: List[str] = []

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            if stream:
                first_chunk_t = None
                async with client.stream("POST", url, json=payload) as r:
                    status_code = r.status_code
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        data = line[len("data:"):].strip()
                        if data == "[DONE]":
                            break
                        obj = json.loads(data)
                        if "usage" in obj:
                            usage = obj["usage"]
                        choices = obj.get("choices") or []
                        if choices:
                            delta = choices[0].get("delta") or {}
                            chunk = delta.get("content")
                            if chunk:
                                if first_chunk_t is None:
                                    first_chunk_t = time.perf_counter()
                                    ttft_ms = (first_chunk_t - start) * 1000.0
                                parts.append(chunk)
            else:
                r = await client.post(url, json=payload)
                status_code = r.status_code
                r.raise_for_status()
                obj = r.json()
                choices = obj.get("choices") or []
                if choices:
                    parts.append((choices[0].get("message") or {}).get("content") or "")
                if "usage" in obj:
                    usage = obj["usage"]

        end = time.perf_counter()
        return LLMResp(True, "".join(parts), (end - start) * 1000.0, ttft_ms, status_code, None, usage)

    except Exception as e:
        end = time.perf_counter()
        return LLMResp(False, "".join(parts), (end - start) * 1000.0, ttft_ms, status_code, str(e), usage)

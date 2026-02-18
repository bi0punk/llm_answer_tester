#!/usr/bin/env python3
import argparse
import time
from pathlib import Path
import httpx

def read_prompts(path: Path):
    out = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            out.append(s)
    if not out:
        raise SystemExit("prompts vacío")
    return out

def main():
    ap = argparse.ArgumentParser(description="Cliente batch para bench-api")
    ap.add_argument("--server", default="http://api:8080", help="URL del bench-api")
    ap.add_argument("--prompts", required=True, help="Archivo prompts.txt")
    ap.add_argument("--temperature", type=float, default=None)
    ap.add_argument("--max-tokens", type=int, default=None)
    ap.add_argument("--stream", action="store_true")
    ap.add_argument("--sleep-s", type=float, default=0.0)
    ap.add_argument("--poll-s", type=float, default=1.0)
    args = ap.parse_args()

    prompts = read_prompts(Path(args.prompts))

    payload = {
        "prompts": prompts,
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
        "stream": True if args.stream else None,
        "sleep_s": args.sleep_s,
    }

    with httpx.Client(timeout=60) as c:
        r = c.post(f"{args.server}/batch", json=payload)
        r.raise_for_status()
        j = r.json()
        run_id = j["run_id"]
        total = j["total"]
        print(f"[client] run_id={run_id} total={total}")

        while True:
            s = c.get(f"{args.server}/runs/{run_id}").json()
            done = int(s["done"])
            ok = int(s["ok"])
            err = int(s["errors"])
            print(f"[client] progress {done}/{total} ok={ok} err={err}", end="\r", flush=True)
            if done >= total:
                print()
                break
            time.sleep(args.poll_s)

        out = c.get(f"{args.server}/runs/{run_id}/results").json()
        results = out["results"]
        print(f"[client] results={len(results)}")
        for row in results:
            idx = row["idx"]
            latency = row["latency_ms"]
            ttft = row["ttft_ms"]
            preview = (row["response"] or "").replace("\n"," ")[:140]
            print(f"#{idx} latency={latency:.1f}ms ttft={ttft if ttft is not None else '-'} :: {preview}")

if __name__ == "__main__":
    main()

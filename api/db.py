import aiosqlite
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  run_id TEXT PRIMARY KEY,
  created_utc TEXT NOT NULL,
  finished_utc TEXT,
  total INTEGER NOT NULL,
  done INTEGER NOT NULL DEFAULT 0,
  ok INTEGER NOT NULL DEFAULT 0,
  errors INTEGER NOT NULL DEFAULT 0,
  model TEXT NOT NULL,
  params_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS results (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  idx INTEGER NOT NULL,
  prompt TEXT NOT NULL,
  response TEXT NOT NULL,
  ok INTEGER NOT NULL,
  error TEXT,
  status_code INTEGER,
  latency_ms REAL NOT NULL,
  ttft_ms REAL,
  usage_json TEXT,
  created_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_run_idx ON results(run_id, idx);
"""

class DB:
    def __init__(self, path: str):
        self.path = path

    async def init(self):
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self.path) as con:
            await con.executescript(SCHEMA)
            await con.commit()

    async def create_run(self, run_id: str, total: int, model: str, params_json: str):
        async with aiosqlite.connect(self.path) as con:
            await con.execute(
                "INSERT INTO runs(run_id, created_utc, total, done, ok, errors, model, params_json) VALUES (?,?,?,?,?,?,?,?)",
                (run_id, now_utc_iso(), total, 0, 0, 0, model, params_json),
            )
            await con.commit()

    async def mark_finished(self, run_id: str):
        async with aiosqlite.connect(self.path) as con:
            await con.execute(
                "UPDATE runs SET finished_utc=? WHERE run_id=?",
                (now_utc_iso(), run_id),
            )
            await con.commit()

    async def add_result(
        self,
        run_id: str,
        idx: int,
        prompt: str,
        response: str,
        ok: bool,
        error: Optional[str],
        status_code: Optional[int],
        latency_ms: float,
        ttft_ms: Optional[float],
        usage_json: Optional[str],
    ):
        async with aiosqlite.connect(self.path) as con:
            await con.execute(
                """
                INSERT INTO results(run_id, idx, prompt, response, ok, error, status_code,
                                    latency_ms, ttft_ms, usage_json, created_utc)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    run_id, idx, prompt, response,
                    1 if ok else 0,
                    error, status_code,
                    float(latency_ms),
                    float(ttft_ms) if ttft_ms is not None else None,
                    usage_json,
                    now_utc_iso(),
                ),
            )

            if ok:
                await con.execute("UPDATE runs SET done = done + 1, ok = ok + 1 WHERE run_id=?", (run_id,))
            else:
                await con.execute("UPDATE runs SET done = done + 1, errors = errors + 1 WHERE run_id=?", (run_id,))

            await con.commit()

    async def get_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as con:
            con.row_factory = aiosqlite.Row
            cur = await con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,))
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_results(self, run_id: str, limit: int = 1000) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.path) as con:
            con.row_factory = aiosqlite.Row
            cur = await con.execute(
                "SELECT * FROM results WHERE run_id=? ORDER BY idx ASC LIMIT ?",
                (run_id, limit),
            )
            rows = await cur.fetchall()
            return [dict(r) for r in rows]

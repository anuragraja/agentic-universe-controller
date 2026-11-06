"""Persistent SQLite storage layer for the Outcome-First Controller.

Provides crash safety, idempotent event processing, and audit trails.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class Storage:
    def __init__(self, db_path: str | Path = "controller.db"):
        self.db_path = Path(db_path)
        self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        with self.conn:
            self.conn.execute("PRAGMA journal_mode = WAL;")
            self.conn.execute("PRAGMA synchronous = NORMAL;")
            self.conn.execute("PRAGMA temp_store = MEMORY;")

            # Key-value state store for checkpoints & metadata
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS meta_state (
                    key TEXT PRIMARY KEY,
                    val TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Ingested chunks watermark
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS ingested_chunks (
                    chunk_id INTEGER PRIMARY KEY,
                    kind TEXT NOT NULL,
                    events_count INTEGER NOT NULL,
                    first_event_id INTEGER,
                    last_event_id INTEGER,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Lead feature table: enables join with call events
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS leads (
                    lead_id TEXT PRIMARY KEY,
                    person_id TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    campaign_id TEXT NOT NULL,
                    lang TEXT NOT NULL,
                    city_tier TEXT NOT NULL,
                    age_band TEXT NOT NULL,
                    value_band TEXT NOT NULL
                );
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_person ON leads (person_id);")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_leads_workflow ON leads (workflow_id);")

            # Person hourly stats for call-time learning
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS person_hours (
                    person_id TEXT NOT NULL,
                    hour INTEGER NOT NULL,
                    dials INTEGER DEFAULT 0,
                    connected INTEGER DEFAULT 0,
                    PRIMARY KEY (person_id, hour)
                );
            """)

            # Variant aggregated performance per workflow and cohort
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS call_stats (
                    workflow_id TEXT NOT NULL,
                    cohort_id TEXT NOT NULL,
                    welcome_message TEXT NOT NULL,
                    voice TEXT NOT NULL,
                    caller_id TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    dials INTEGER DEFAULT 0,
                    connected INTEGER DEFAULT 0,
                    engaged INTEGER DEFAULT 0,
                    halluc_flags INTEGER DEFAULT 0,
                    PRIMARY KEY (workflow_id, cohort_id, welcome_message, voice, caller_id, prompt_version)
                );
            """)

            # Sliding window stats for decay detection (aggregated by day/hour bucket)
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS time_window_stats (
                    workflow_id TEXT NOT NULL,
                    cohort_id TEXT NOT NULL,
                    dim TEXT NOT NULL,
                    val TEXT NOT NULL,
                    bucket_day INTEGER NOT NULL,
                    dials INTEGER DEFAULT 0,
                    connected INTEGER DEFAULT 0,
                    engaged INTEGER DEFAULT 0,
                    PRIMARY KEY (workflow_id, cohort_id, dim, val, bucket_day)
                );
            """)

            # Proposals & Governance lifecycle
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS proposals (
                    proposal_id TEXT PRIMARY KEY,
                    workflow_id TEXT NOT NULL,
                    base_version INTEGER NOT NULL,
                    proposed_config TEXT NOT NULL,
                    change_summary TEXT NOT NULL,
                    diff_json TEXT NOT NULL,
                    affected_leads INTEGER NOT NULL,
                    dry_run_json TEXT NOT NULL,
                    impact_score REAL NOT NULL,
                    rationale TEXT NOT NULL,
                    evidence_json TEXT,
                    status TEXT NOT NULL,
                    approval_id TEXT,
                    applied_version INTEGER,
                    created_minute INTEGER NOT NULL,
                    decided_minute INTEGER,
                    apply_by_minute INTEGER,
                    rejection_reasons TEXT
                );
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_proposals_wf ON proposals (workflow_id, status);")

            # Immutable audit trail
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_trail (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sim_minute INTEGER NOT NULL,
                    ts TEXT NOT NULL,
                    workflow_id TEXT NOT NULL,
                    actor TEXT NOT NULL,
                    action TEXT NOT NULL,
                    version INTEGER,
                    summary TEXT NOT NULL,
                    details_json TEXT NOT NULL
                );
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_wf ON audit_trail (workflow_id, sim_minute);")

    # -------------------------------------------------------------
    # State & Checkpoint
    # -------------------------------------------------------------
    def get_state(self, key: str, default: Any = None) -> Any:
        cur = self.conn.cursor()
        cur.execute("SELECT val FROM meta_state WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            return default
        try:
            return json.loads(row["val"])
        except Exception:
            return row["val"]

    def set_state(self, key: str, val: Any):
        s = json.dumps(val) if not isinstance(val, str) else val
        with self.conn:
            self.conn.execute("""
                INSERT INTO meta_state (key, val, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET val = excluded.val, updated_at = CURRENT_TIMESTAMP;
            """, (key, s))

    def is_chunk_ingested(self, chunk_id: int) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM ingested_chunks WHERE chunk_id = ?", (chunk_id,))
        return cur.fetchone() is not None

    def record_chunk_ingested(self, chunk_id: int, kind: str, count: int, first_id: int, last_id: int):
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO ingested_chunks (chunk_id, kind, events_count, first_event_id, last_event_id)
                VALUES (?, ?, ?, ?, ?);
            """, (chunk_id, kind, count, first_id, last_id))

    def get_last_chunk_id(self, kind: Optional[str] = None) -> int:
        cur = self.conn.cursor()
        if kind:
            cur.execute("SELECT MAX(chunk_id) as m FROM ingested_chunks WHERE kind = ?", (kind,))
        else:
            cur.execute("SELECT MAX(chunk_id) as m FROM ingested_chunks")
        row = cur.fetchone()
        return row["m"] if row and row["m"] is not None else -1

    # -------------------------------------------------------------
    # Lead Features
    # -------------------------------------------------------------
    def insert_leads_batch(self, leads: List[Tuple[str, str, str, str, str, str, str, str]]):
        """Batch insert leads: (lead_id, person_id, workflow_id, campaign_id, lang, city_tier, age_band, value_band)"""
        if not leads:
            return
        with self.conn:
            self.conn.executemany("""
                INSERT OR IGNORE INTO leads (lead_id, person_id, workflow_id, campaign_id, lang, city_tier, age_band, value_band)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, leads)

    def get_lead(self, lead_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM leads WHERE lead_id = ?", (lead_id,))
        row = cur.fetchone()
        return dict(row) if row else None

    def get_active_leads_sample(self, workflow_id: str, limit: int = 5000) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT lang, city_tier, age_band, value_band
            FROM leads WHERE workflow_id = ?
            ORDER BY ROWID DESC LIMIT ?
        """, (workflow_id, limit))
        return [dict(r) for r in cur.fetchall()]

    # -------------------------------------------------------------
    # Call Stats Aggregation
    # -------------------------------------------------------------
    def update_call_stats_batch(self, rows: List[Tuple[str, str, str, str, str, str, int, int, int, int]]):
        """Batch update call_stats:
        (workflow_id, cohort_id, welcome, voice, caller_id, prompt_version, dials, conn, eng, halluc)
        """
        if not rows:
            return
        with self.conn:
            self.conn.executemany("""
                INSERT INTO call_stats (workflow_id, cohort_id, welcome_message, voice, caller_id, prompt_version, dials, connected, engaged, halluc_flags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id, cohort_id, welcome_message, voice, caller_id, prompt_version) DO UPDATE SET
                    dials = dials + excluded.dials,
                    connected = connected + excluded.connected,
                    engaged = engaged + excluded.engaged,
                    halluc_flags = halluc_flags + excluded.halluc_flags;
            """, rows)

    def update_window_stats_batch(self, rows: List[Tuple[str, str, str, str, int, int, int, int]]):
        """Batch update time_window_stats:
        (workflow_id, cohort_id, dim, val, bucket_day, dials, conn, eng)
        """
        if not rows:
            return
        with self.conn:
            self.conn.executemany("""
                INSERT INTO time_window_stats (workflow_id, cohort_id, dim, val, bucket_day, dials, connected, engaged)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(workflow_id, cohort_id, dim, val, bucket_day) DO UPDATE SET
                    dials = dials + excluded.dials,
                    connected = connected + excluded.connected,
                    engaged = engaged + excluded.engaged;
            """, rows)

    def update_person_hours_batch(self, rows: List[Tuple[str, int, int, int]]):
        """(person_id, hour, dials, connected)"""
        if not rows:
            return
        with self.conn:
            self.conn.executemany("""
                INSERT INTO person_hours (person_id, hour, dials, connected)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(person_id, hour) DO UPDATE SET
                    dials = dials + excluded.dials,
                    connected = connected + excluded.connected;
            """, rows)

    def get_cohort_dim_stats(self, workflow_id: str, cohort_id: str, dim: str) -> Dict[str, Dict[str, int]]:
        """Returns {val: {'dials': ..., 'connected': ..., 'engaged': ...}} for given dim."""
        cur = self.conn.cursor()
        dim_col = dim
        if dim not in ("welcome_message", "voice", "caller_id", "prompt_version"):
            raise ValueError(f"Invalid dimension {dim}")
        
        cur.execute(f"""
            SELECT {dim_col} as val,
                   SUM(dials) as dials,
                   SUM(connected) as connected,
                   SUM(engaged) as engaged,
                   SUM(halluc_flags) as halluc_flags
            FROM call_stats
            WHERE workflow_id = ? AND (cohort_id = ? OR ? = '*')
            GROUP BY {dim_col}
        """, (workflow_id, cohort_id, cohort_id))
        
        out = {}
        for r in cur.fetchall():
            out[r["val"]] = {
                "dials": r["dials"],
                "connected": r["connected"],
                "engaged": r["engaged"],
                "halluc_flags": r["halluc_flags"],
            }
        return out

    def get_did_stats(self, workflow_id: str) -> Dict[str, Dict[str, int]]:
        """Returns {did: {'dials': ..., 'connected': ...}}"""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT caller_id,
                   SUM(dials) as dials,
                   SUM(connected) as connected
            FROM call_stats
            WHERE workflow_id = ?
            GROUP BY caller_id
        """, (workflow_id,))
        return {r["caller_id"]: {"dials": r["dials"], "connected": r["connected"]} for r in cur.fetchall()}

    def get_recent_did_stats(self, workflow_id: str, min_day: int) -> Dict[str, Dict[str, int]]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT val as caller_id,
                   SUM(dials) as dials,
                   SUM(connected) as connected
            FROM time_window_stats
            WHERE workflow_id = ? AND dim = 'caller_id' AND bucket_day >= ?
            GROUP BY val
        """, (workflow_id, min_day))
        return {r["caller_id"]: {"dials": r["dials"], "connected": r["connected"]} for r in cur.fetchall()}

    def get_recent_dim_stats(self, workflow_id: str, cohort_id: str, dim: str, min_day: int) -> Dict[str, Dict[str, int]]:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT val,
                   SUM(dials) as dials,
                   SUM(connected) as connected,
                   SUM(engaged) as engaged
            FROM time_window_stats
            WHERE workflow_id = ? AND dim = ? AND (cohort_id = ? OR ? = '*') AND bucket_day >= ?
            GROUP BY val
        """, (workflow_id, dim, cohort_id, cohort_id, min_day))
        return {r["val"]: {"dials": r["dials"], "connected": r["connected"], "engaged": r["engaged"]} for r in cur.fetchall()}

    def get_prompt_qa_stats(self, workflow_id: str, prompt_version: str, min_day: Optional[int] = None) -> Dict[str, int]:
        cur = self.conn.cursor()
        if min_day is not None:
            cur.execute("""
                SELECT SUM(dials) as dials,
                       SUM(connected) as connected,
                       SUM(engaged) as engaged
                FROM time_window_stats
                WHERE workflow_id = ? AND dim = 'prompt_version' AND val = ? AND bucket_day >= ?
            """, (workflow_id, prompt_version, min_day))
            row = cur.fetchone()
            dials = row["dials"] or 0
            connected = row["connected"] or 0
            engaged = row["engaged"] or 0
            # for halluc flags, query call_stats
            cur.execute("""
                SELECT SUM(halluc_flags) as halluc_flags
                FROM call_stats
                WHERE workflow_id = ? AND prompt_version = ?
            """, (workflow_id, prompt_version))
            r2 = cur.fetchone()
            halluc = r2["halluc_flags"] or 0
            return {"dials": dials, "connected": connected, "engaged": engaged, "halluc_flags": halluc}
        else:
            cur.execute("""
                SELECT SUM(dials) as dials,
                       SUM(connected) as connected,
                       SUM(engaged) as engaged,
                       SUM(halluc_flags) as halluc_flags
                FROM call_stats
                WHERE workflow_id = ? AND prompt_version = ?
            """, (workflow_id, prompt_version))
            r = cur.fetchone()
            return {
                "dials": r["dials"] or 0,
                "connected": r["connected"] or 0,
                "engaged": r["engaged"] or 0,
                "halluc_flags": r["halluc_flags"] or 0,
            }

    # -------------------------------------------------------------
    # Governance & Proposals
    # -------------------------------------------------------------
    def save_proposal(self, prop: Dict[str, Any]):
        with self.conn:
            self.conn.execute("""
                INSERT OR REPLACE INTO proposals (
                    proposal_id, workflow_id, base_version, proposed_config,
                    change_summary, diff_json, affected_leads, dry_run_json,
                    impact_score, rationale, evidence_json, status, approval_id,
                    applied_version, created_minute, decided_minute, apply_by_minute,
                    rejection_reasons
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
            """, (
                prop["proposal_id"],
                prop["workflow_id"],
                prop["base_version"],
                json.dumps(prop["proposed_config"]),
                prop["change_summary"],
                json.dumps(prop["diff"]),
                prop["affected_leads"],
                json.dumps(prop["dry_run"]),
                prop["impact_score"],
                prop["rationale"],
                json.dumps(prop.get("evidence")) if prop.get("evidence") else None,
                prop["status"],
                prop.get("approval_id"),
                prop.get("applied_version"),
                prop["created_minute"],
                prop.get("decided_minute"),
                prop.get("apply_by_minute"),
                json.dumps(prop.get("reasons", []))
            ))

    def update_proposal_status(self, proposal_id: str, status: str, **kwargs):
        updates = ["status = ?"]
        params = [status]
        for k, v in kwargs.items():
            if k in ("approval_id", "applied_version", "decided_minute", "apply_by_minute"):
                updates.append(f"{k} = ?")
                params.append(v)
            elif k == "rejection_reasons":
                updates.append("rejection_reasons = ?")
                params.append(json.dumps(v))
        params.append(proposal_id)
        with self.conn:
            self.conn.execute(f"UPDATE proposals SET {', '.join(updates)} WHERE proposal_id = ?", params)

    def get_proposal(self, proposal_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM proposals WHERE proposal_id = ?", (proposal_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d["proposed_config"] = json.loads(d["proposed_config"])
        d["diff"] = json.loads(d["diff_json"])
        d["dry_run"] = json.loads(d["dry_run_json"])
        if d.get("evidence_json"):
            d["evidence"] = json.loads(d["evidence_json"])
        if d.get("rejection_reasons"):
            d["reasons"] = json.loads(d["rejection_reasons"])
        return d

    def get_pending_proposals(self, workflow_id: Optional[str] = None) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        if workflow_id:
            cur.execute("SELECT proposal_id FROM proposals WHERE workflow_id = ? AND status IN ('pending', 'approved')", (workflow_id,))
        else:
            cur.execute("SELECT proposal_id FROM proposals WHERE status IN ('pending', 'approved')")
        pids = [r["proposal_id"] for r in cur.fetchall()]
        return [self.get_proposal(pid) for pid in pids if pid]

    def count_proposals_in_last_24h(self, workflow_id: str, current_minute: int) -> int:
        cur = self.conn.cursor()
        cur.execute("""
            SELECT COUNT(*) as c FROM proposals
            WHERE workflow_id = ? AND created_minute >= ?
        """, (workflow_id, current_minute - 1440))
        return cur.fetchone()["c"]

    # -------------------------------------------------------------
    # Audit Trail
    # -------------------------------------------------------------
    def log_audit(self, sim_minute: int, ts: str, workflow_id: str, actor: str,
                  action: str, summary: str, version: Optional[int] = None,
                  details: Optional[Dict[str, Any]] = None):
        with self.conn:
            self.conn.execute("""
                INSERT INTO audit_trail (sim_minute, ts, workflow_id, actor, action, version, summary, details_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?);
            """, (sim_minute, ts, workflow_id, actor, action, version, summary, json.dumps(details or {})))

    def query_audit_trail(self, workflow_id: Optional[str] = None, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        if workflow_id:
            cur.execute("""
                SELECT * FROM audit_trail WHERE workflow_id = ?
                ORDER BY sim_minute DESC, id DESC LIMIT ?
            """, (workflow_id, limit))
        else:
            cur.execute("""
                SELECT * FROM audit_trail
                ORDER BY sim_minute DESC, id DESC LIMIT ?
            """, (limit,))
        out = []
        for r in cur.fetchall():
            d = dict(r)
            d["details"] = json.loads(d["details_json"])
            out.append(d)
        return out

    def explain_change(self, workflow_id: str, version: int) -> Dict[str, Any]:
        """Answering: Why did workflow X change at version/time T, who approved it, what happened?"""
        cur = self.conn.cursor()
        cur.execute("""
            SELECT * FROM audit_trail
            WHERE workflow_id = ? AND version = ?
            ORDER BY id ASC
        """, (workflow_id, version))
        rows = [dict(r) for r in cur.fetchall()]
        
        # Check proposals matching this version
        cur.execute("""
            SELECT * FROM proposals
            WHERE workflow_id = ? AND applied_version = ?
        """, (workflow_id, version))
        p_row = cur.fetchone()
        prop = dict(p_row) if p_row else None
        if prop:
            prop["proposed_config"] = json.loads(prop["proposed_config"])
            prop["diff"] = json.loads(prop["diff_json"])

        return {
            "workflow_id": workflow_id,
            "version": version,
            "audit_records": rows,
            "proposal": prop
        }

    def close(self):
        self.conn.close()

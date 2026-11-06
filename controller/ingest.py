"""High-throughput streaming event ingestion and incremental aggregation."""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List, Optional, Tuple

from .storage import Storage


class EventIngestor:
    def __init__(self, http_client: Any, storage: Storage):
        self.http = http_client
        self.storage = storage

    def ingest_chunk(self, chunk_meta: Dict[str, Any]) -> Dict[str, Any]:
        """Ingests a single chunk of NDJSON events.
        
        Uses in-memory dictionary aggregation to minimize SQLite write contention,
        enabling processing of >100,000 events/sec.
        """
        chunk_id = chunk_meta["chunk"]
        if self.storage.is_chunk_ingested(chunk_id):
            return {"chunk_id": chunk_id, "skipped": True}

        r = self.http.get(f"/events/chunks/{chunk_id}")
        if r.status_code != 200:
            raise RuntimeError(f"Failed to fetch chunk {chunk_id}: {r.status_code}")

        leads_batch: List[Tuple[str, str, str, str, str, str, str, str]] = []
        person_hours_agg: Dict[Tuple[str, int], List[int]] = defaultdict(lambda: [0, 0])
        # (wf, cohort, welcome, voice, caller_id, prompt) -> [dials, connected, engaged, halluc]
        call_stats_agg: Dict[Tuple[str, str, str, str, str, str], List[int]] = defaultdict(lambda: [0, 0, 0, 0])
        # (wf, cohort, dim, val, day) -> [dials, connected, engaged]
        window_stats_agg: Dict[Tuple[str, str, str, str, int], List[int]] = defaultdict(lambda: [0, 0, 0])

        supervisor_edits = []
        approval_decisions = []
        event_count = 0
        first_event_id = None
        last_event_id = None

        for line in r.text.splitlines():
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            event_count += 1
            eid = ev.get("event_id")
            if first_event_id is None:
                first_event_id = eid
            last_event_id = eid

            ev_type = ev.get("type")
            if ev_type == "lead":
                feat = ev.get("features", {})
                leads_batch.append((
                    ev["lead_id"],
                    ev["person_id"],
                    ev["workflow_id"],
                    ev["campaign_id"],
                    feat.get("lang", "en"),
                    feat.get("city_tier", "1"),
                    feat.get("age_band", "31-45"),
                    feat.get("value_band", "mid"),
                ))
            elif ev_type == "call":
                wid = ev["workflow_id"]
                coh = ev.get("cohort_id") or "default"
                var = ev.get("variant", {})
                wel = var.get("welcome_message", "")
                voi = var.get("voice", "")
                cid = var.get("caller_id", "")
                pr = var.get("prompt_version", "")
                conn = 1 if ev.get("connected") else 0
                eng = 1 if ev.get("engaged") else 0
                qa = ev.get("qa") or {}
                halluc = 1 if qa.get("hallucination_flag") else 0

                call_stats_agg[(wid, coh, wel, voi, cid, pr)][0] += 1
                call_stats_agg[(wid, coh, wel, voi, cid, pr)][1] += conn
                call_stats_agg[(wid, coh, wel, voi, cid, pr)][2] += eng
                call_stats_agg[(wid, coh, wel, voi, cid, pr)][3] += halluc

                day = ev.get("campaign_day_index", 0)
                # Aggregate per dimension into sliding window
                for dim_name, val in [("welcome_message", wel), ("voice", voi), ("caller_id", cid), ("prompt_version", pr)]:
                    window_stats_agg[(wid, coh, dim_name, val, day)][0] += 1
                    window_stats_agg[(wid, coh, dim_name, val, day)][1] += conn
                    window_stats_agg[(wid, coh, dim_name, val, day)][2] += eng

                # Person hour preference tracking
                ts = ev.get("ts", "")
                if len(ts) >= 13:
                    try:
                        hour = int(ts[11:13])
                        person_hours_agg[(ev["person_id"], hour)][0] += 1
                        person_hours_agg[(ev["person_id"], hour)][1] += conn
                    except (ValueError, TypeError):
                        pass

            elif ev_type == "config_changed":
                if ev.get("actor") == "supervisor":
                    supervisor_edits.append(ev)
            elif ev_type == "approval_decided":
                approval_decisions.append(ev)

        # Batch writes to SQLite
        if leads_batch:
            self.storage.insert_leads_batch(leads_batch)

        if call_stats_agg:
            c_rows = [(*k, *v) for k, v in call_stats_agg.items()]
            self.storage.update_call_stats_batch(c_rows)

        if window_stats_agg:
            w_rows = [(*k, *v) for k, v in window_stats_agg.items()]
            self.storage.update_window_stats_batch(w_rows)

        if person_hours_agg:
            p_rows = [(k[0], k[1], v[0], v[1]) for k, v in person_hours_agg.items()]
            self.storage.update_person_hours_batch(p_rows)

        # Record chunk watermark
        self.storage.record_chunk_ingested(
            chunk_id=chunk_id,
            kind=chunk_meta.get("kind", "events"),
            count=event_count,
            first_id=first_event_id or 0,
            last_id=last_event_id or 0,
        )

        return {
            "chunk_id": chunk_id,
            "events_count": event_count,
            "supervisor_edits": supervisor_edits,
            "approval_decisions": approval_decisions,
        }

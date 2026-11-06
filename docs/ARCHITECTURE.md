# Controller Architecture & Technical Design

## 1. System Overview

The **Outcome-First Controller** is an autonomous orchestrator designed to optimize outbound telephony performance across workflows without human micromanagement. It operates against the Formi closed-loop simulator over HTTP, adhering to strict business, governance, and regulatory constraints.

```mermaid
flowchart TD
    subgraph External [Simulator Environment]
        API_EV[/events/chunks]
        API_ST[/sim/state]
        API_ADV[/sim/advance]
        API_WF[/workflows]
        API_APP[/approvals]
        API_CFG[PUT /workflows/:id/config]
        API_VAL[/validation/runs]
        API_LLM[/llm/suggest-fixes]
    end

    subgraph ControllerLoop [Autonomous Control Loop]
        ING[Streaming NDJSON Ingest Engine]
        DB[(Embedded SQLite Store WAL)]
        COH[Canonical Cohort Evaluator]
        STAT[Bayesian Beta-Binomial Inference]
        DECAY[EWMA Variant Decay Detector]
        SCH[Call-Time & DID Health Engine]
        INC[Incident Hallucination Detector]
        GOV[Governance & Policy Engine]
    end

    API_EV -->|NDJSON Chunks| ING
    ING -->|Aggregated Dials / Pickups / Engagements| DB
    DB --> COH
    DB --> STAT
    DB --> DECAY
    DB --> SCH
    DB --> INC

    STAT -->|Winner P win >= 0.95| GOV
    DECAY -->|Rollback Flagged Variant| GOV
    SCH -->|DID Weight Adjustments| GOV
    INC -->|QA Hallucination Spike > 3%| API_LLM
    API_LLM -->|Candidate Fix Prompts| API_VAL
    API_VAL -->|Validation Pass Rate >= 0.97| GOV

    GOV -->|Auto-Apply Allowed Dims| API_CFG
    GOV -->|Customer-Facing Dims| API_APP
    API_APP -->|Approval Polling & State Tracking| GOV
    GOV -->|Sim Advance 15m/24h| API_ADV
```

---

## 2. Core Modules

### 2.1 Storage & State Persistence (`controller/storage.py`)
- **Engine**: SQLite 3 with Write-Ahead Logging (`PRAGMA journal_mode=WAL`), `PRAGMA synchronous=NORMAL`, and foreign key support.
- **Tables**:
  - `meta_state`: Checkpoint state storing `last_chunk_id`, `sim_minute`, and run flags.
  - `leads`: Lead demographic attributes (`lang`, `city_tier`, `age_band`, `value_band`) indexed by `lead_id` and `person_id`.
  - `person_hours`: Per-person historical call connection records by hour of day for personalized call-time learning.
  - `call_stats`: Aggregated variant performance per workflow and cohort `(workflow_id, cohort_id, welcome, voice, caller_id, prompt)`.
  - `time_window_stats`: Rolling calendar-day telemetry buckets for decay and trend detection.
  - `proposals`: Proposal lifecycle tracking (`proposal_id`, `workflow_id`, diff, impact score, dry run, status, approver decisions).
  - `audit_trail`: Append-only immutable regulatory log capturing all actions, timestamps, actors, and version transitions.

### 2.2 Canonical Cohort Engine (`controller/cohort.py`)
- Evaluates workflow `where` conditions against lead metadata deterministically.
- Supports canonical operators: `==`, `!=`, `in`, `not in`, `>`, `<`, `>=`, `<=`.
- Enforces sample gating: cohorts must accumulate $\ge 500$ dials before variant lift is considered statistically valid, preventing traffic fragmentation.

### 2.3 Statistical Inference & Decay Detection (`controller/stats.py`)
- **Bayesian Posterior Updates**: Uses Beta-Binomial conjugacy.
  $$\theta \sim \text{Beta}(\alpha_0 + \text{successes}, \beta_0 + \text{failures})$$
  Evaluates posterior probability $P(\theta_{\text{candidate}} > \theta_{\text{control}}) \ge 0.95$ using Monte Carlo sampling.
- **Frequentist Verification**: Evaluates two-sample pooled z-test with Bonferroni correction for multiple hypothesis testing ($p < \alpha / K$).
- **Decay Detection**: Tracks variant engagement across true calendar days using Exponentially Weighted Moving Averages (EWMA). Triggers permanent rollback when a statistically significant decline ($\ge 5.0\%$, $z > 1.96$) is detected.

### 2.4 Call-Time & DID Health Management (`controller/scheduler.py`, `controller/did_manager.py`)
- **Call-Time Optimization**: Extracts preferred connection hours per person using historical dial records with Laplace smoothing; computes normalized cohort-level dispatch weights.
- **Caller-ID Reputation**: Online monitoring of per-DID pickup health. Detects carrier spam flagging ($< 0.65 \times \text{mean}$) and rotates traffic exclusively across verified healthy DIDs.

### 2.5 Incident Remediation Loop (`controller/incident.py`)
- Continuously calculates rolling QA hallucination rate over 500-call windows.
- If flag rate exceeds $3.0\%$, declares an emergency incident:
  1. Requests prompt repair suggestions from `/llm/suggest-fixes` (2 credits).
  2. Runs candidates through the isolated validation sandbox via `/validation/runs` (5 credits per run).
  3. Filters candidate prompts: rejects strict verbatim scripts ($P5$) that pass validation but destroy conversational engagement (0.86 engagement multiplier); selects grounded prompts ($P1$ or $P3$).
  4. Dispatches emergency approval proposal with attached validation evidence.

### 2.6 Governance & Policy Engine (`controller/governance.py`)
- **Approval Window Gating**: Restricts non-emergency proposals to approver business hours (e.g., 10:00–18:00).
- **Fatigue Protection**: Enforces rolling 24-hour limits on supervisor requests ($\le \text{max\_requests\_per\_24h}$).
- **Auto-Apply Path**: Applies operational changes (`schedule`, healthy `caller_id`) without human intervention only when explicitly permitted by tenant policy (`auto_apply.allowed_dims`).
- **Conflict Handling**: Detects out-of-band supervisor edits; marks conflicting proposals as stale (`apply_stale_conflict`) without stomping supervisor configurations.


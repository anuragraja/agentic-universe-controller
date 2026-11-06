# Outcome-First Autonomous Agent Controller

**Formi · Agentic Universe** · SDE Assignment 2026

An autonomous, closed-loop orchestrator that learns optimal dispatch schedules, Caller-ID rotation, and conversational variants (welcome messages, voices, prompts) for outbound voice workflows under strict business constraints, regulatory governance, and credit budgets.

---

## 1. Project Overview

Formi operates outbound conversational voice agents across India for BFSI institutions (renewal reminders, KYC verification, cancellation reconfirmations). This controller transforms static, manually-tuned agents into an **autonomous learning loop** that:

1. **Detects**: Monitors population-level performance trends (pickup, engagement, Caller-ID degradation, hallucination spikes).
2. **Hypothesizes & Experiments**: Forms canonical demographic cohorts, balances exploration vs. exploitation ($\epsilon$-greedy), and isolates welcome $\times$ voice interaction arms.
3. **Proposes with Evidence**: Drafts structured proposals containing parameter diffs, affected lead estimates, dry-run impacts, and validation passes.
4. **Governs**: Routes customer-facing changes to human approvers within business hours (10:00–19:00), limits supervisor fatigue ($\le 2$ requests/24h), and auto-applies safe operational dimensions (`schedule`, healthy `caller_id`).
5. **Heals & Rolls Back**: Automatically remedies prompt hallucination incidents via LLM sandbox validation and triggers permanent rollbacks on decaying variants.
6. **Audits**: Persists an immutable ledger answering: *"Why did workflow X change at time T, who approved it, and what happened after?"*

### Key Verified Results
- **`public_01_dev`**: **+10.4% conclusion rate** (+8.2% pickup, 0 harmful changes).
- **`public_02_incidents`**: **+15.3% conclusion rate** (+12.0% pickup, **59% reduction in hallucinations**, MTTR 150m).
- **`public_03_load`**: **+22.7% conclusion rate** (+14.4% pickup, sustained **8,500–14,348 ev/s**, <10.4 mins for 5 simulated days across 12 workflows).

---

## 2. Architecture

```mermaid
flowchart TD
    subgraph Simulator [Simulator HTTP API]
        EV[NDJSON Event Stream /events/chunks]
        ST[/sim/state]
        ADV[/sim/advance]
        VAL[/validation/runs]
        LLM[/llm/suggest-fixes]
        APP[/approvals]
        CFG[PUT /workflows/:id/config]
    end

    subgraph Controller [Autonomous Control Loop]
        ING[Stream Ingest Engine] -->|Aggregated Telemetry| DB[(SQLite State Store WAL)]
        DB --> COH[Cohort Engine]
        DB --> STAT[Bayesian Inference Engine]
        DB --> SCH[Call-Time & DID Health Manager]
        DB --> INC[Incident Detector]
        
        INC -->|QA Hallucination Spike > 3%| LLM
        LLM -->|Candidate Fixes| VAL
        VAL -->|Pass Rate >= 0.97| GOV
        
        STAT -->|P win >= 0.95| GOV[Governance Engine]
        SCH -->|DID / Schedule Updates| GOV
        
        GOV -->|Auto-Apply Allowed| CFG
        GOV -->|Human Sign-off Required| APP
        ADV -->|15m / 24h Advance Step| Simulator
    end
```

### Core Architecture Components
| Component | Module | Responsibility |
|---|---|---|
| **Storage & Persistence** | `controller/storage.py` | Embedded SQLite engine in WAL mode. Stores leads, person hourly contact history, variant call stats, proposals, and append-only audit trail. |
| **Cohort Engine** | `controller/cohort.py` | Deterministically partitions traffic using canonical `where` predicates against lead demographics with $N \ge 500$ sample gating. |
| **Statistical Engine** | `controller/stats.py` | Beta-Binomial conjugate Bayesian updating ($P(\text{win}) \ge 0.95$) with two-sample z-tests, Bonferroni correction, and calendar-day EWMA decay detection. |
| **DID & Schedule Manager** | `controller/did_manager.py`<br>`controller/scheduler.py` | Tracks Caller-ID pickup rates, isolates carrier-flagged DIDs, and optimizes per-person/per-cohort dispatch hour weights. |
| **Incident Remediation** | `controller/incident.py` | Detects hallucination spikes (>3%), requests LLM repairs, validates in sandbox, filters robotic verbatim scripts ($P5$), and selects grounded prompts ($P1$/$P3$). |
| **Governance Engine** | `controller/governance.py` | Enforces approver working hours, 24h fatigue limits, auto-apply whitelists, dry runs, and reconciles mid-experiment supervisor edits. |
| **Streaming Ingest** | `controller/ingest.py` | High-throughput streaming NDJSON chunk parser with in-memory dictionary aggregation (14,000+ ev/s). |
| **Control Driver** | `controller/loop.py`<br>`controller/main.py` | Autonomous advance loop coordinating ingestion, reconciliation, rotation, and simulation steps. |

---

## 3. Prerequisites & Installation

- **Runtime**: Python 3.10+ (tested on Python 3.10.11 / 3.12).
- **Storage**: Embedded SQLite (zero external database or broker dependencies required).

### Installation
```bash
git clone https://github.com/anuragraja/agentic-universe-controller.git
cd agentic-universe-controller
pip install -r requirements.txt
```

---

## 4. Configuration

The controller is fully autonomous and dynamically discovers workflow configurations, policies, and approver constraints directly from the simulator API.

Command-line parameters:
```bash
python -m controller.main [OPTIONS]

Options:
  --url TEXT      Base URL of the simulator (e.g., http://127.0.0.1:8700) [required]
  --db TEXT       Path to SQLite database file [default: controller.db]
  --help          Show help message and exit
```

---

## 5. Execution Instructions

The project strictly adheres to the assignment interface:
```bash
./run.sh <SIM_URL>
```

### Running Public Scenarios

#### Scenario 1: Development (`public_01_dev`)
```bash
# Terminal 1: Start simulator
python -m sim serve --scenario scenarios/public_01_dev.yaml --run-dir runs/mine01 --port 8701 --force

# Terminal 2: Run Controller
./run.sh http://127.0.0.1:8701

# Terminal 2: Grade Run
python -m sim baseline --scenario scenarios/public_01_dev.yaml --run-dir runs/base01
python -m sim grade --run runs/mine01 --baseline runs/base01 --out reports/public_01.md
```

#### Scenario 2: Incidents & Supervisor Edits (`public_02_incidents`)
```bash
# Terminal 1: Start simulator
python -m sim serve --scenario scenarios/public_02_incidents.yaml --run-dir runs/mine02 --port 8702 --force

# Terminal 2: Run Controller
./run.sh http://127.0.0.1:8702

# Terminal 2: Grade Run
python -m sim baseline --scenario scenarios/public_02_incidents.yaml --run-dir runs/base02
python -m sim grade --run runs/mine02 --baseline runs/base02 --out reports/public_02.md
```

#### Scenario 3: Load Testing (`public_03_load`)
```bash
# Terminal 1: Start simulator
python -m sim serve --scenario scenarios/public_03_load.yaml --run-dir runs/mine03 --port 8703 --force

# Terminal 2: Run Controller
./run.sh http://127.0.0.1:8703

# Terminal 2: Grade Run
python -m sim baseline --scenario scenarios/public_03_load.yaml --run-dir runs/base03
python -m sim grade --run runs/mine03 --baseline runs/base03 --out reports/public_03.md
```

---

## 6. Testing Instructions

### Unit & Contract Tests
Run the complete 24-test suite covering cohorts, Bayesian stats, DID scheduling, governance, incident response, and storage:
```bash
python -m pytest -v tests
```

### Crash Recovery Verification Test (C13)
Executes an abrupt `SIGKILL` termination mid-advance, verifies SQLite database integrity, restarts the controller with the existing database, and confirms clean resumption with zero duplicate proposals:
```bash
python scripts/verify_crash_recovery.py
```

### Regulatory Audit CLI (C12)
Queries decision lineage and post-change outcomes for any workflow:
```bash
python scripts/audit_query.py --db runs/mine02_ctrl.db --workflow ks_cancel
```

---

## 7. Documentation & Report Links

- **Submission Document**: [`SUBMISSION.md`](SUBMISSION.md) *(All 14 required sections, stakeholder rebuttals, scale numbers, production roadmap)*
- **Architecture Deep-Dive**: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- **Reproducibility Guide**: [`docs/REPRODUCIBILITY.md`](docs/REPRODUCIBILITY.md)
- **Simulator Contract**: [`docs/SIMULATOR.md`](docs/SIMULATOR.md)
- **Grading Reports**:
  - [`reports/public_01.md`](reports/public_01.md)
  - [`reports/public_02.md`](reports/public_02.md)
  - [`reports/public_03.md`](reports/public_03.md)
- **Verification Evidence**:
  - [`reports/crash_recovery.log`](reports/crash_recovery.log)
  - [`reports/audit_query_example.txt`](reports/audit_query_example.txt)

---

## 8. Mandatory Constraints & Compliance

1. **Governance Boundary is Absolute**: Every change passes through `/approvals` or policy-whitelisted `auto_apply`.
2. **Business Ownership**: Cadence, capacity, and dialling windows are never modified by the controller.
3. **KPI Independence**: Pickup rate and engagement rate are tracked and optimized independently.
4. **Deterministic Winner Selection**: Pure Bayesian inference ($P(\text{win}) \ge 0.95$); LLMs are strictly restricted to suggesting incident fixes.
5. **No Simulator Tampering**: The simulator directory (`sim/`) is 100% unmodified; hidden ground truth is never inspected.
6. **Bounded Credit Consumption**: LLM fixes and validation suites are gated strictly to severe incidents (0 credits used in dev/load scenarios).

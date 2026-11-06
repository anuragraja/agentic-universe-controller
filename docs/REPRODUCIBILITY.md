# Reproducibility & Execution Guide

This document provides exact, verified commands to run unit tests, execute public scenarios, run the crash recovery test harness, and query the audit trail.

---

## 1. Environment Setup

Requirements: Python 3.10+ (standard dependencies in `requirements.txt`).

```bash
pip install -r requirements.txt
```

Verify the installation and test suite:
```bash
python -m pytest -v tests
```

---

## 2. Public Scenario Execution

### Scenario 1: Development Baseline (`public_01_dev`)
```bash
# Terminal 1: Start simulator
python -m sim serve --scenario scenarios/public_01_dev.yaml --run-dir runs/mine01 --port 8701 --force

# Terminal 2: Run Controller
./run.sh http://127.0.0.1:8701

# Terminal 2: Grade Run against baseline
python -m sim baseline --scenario scenarios/public_01_dev.yaml --run-dir runs/base01
python -m sim grade --run runs/mine01 --baseline runs/base01 --out reports/public_01.md
```

### Scenario 2: Incidents & Supervisor Edits (`public_02_incidents`)
```bash
# Terminal 1: Start simulator
python -m sim serve --scenario scenarios/public_02_incidents.yaml --run-dir runs/mine02 --port 8702 --force

# Terminal 2: Run Controller
./run.sh http://127.0.0.1:8702

# Terminal 2: Grade Run against baseline
python -m sim baseline --scenario scenarios/public_02_incidents.yaml --run-dir runs/base02
python -m sim grade --run runs/mine02 --baseline runs/base02 --out reports/public_02.md
```

### Scenario 3: Load Testing (`public_03_load`)
```bash
# Terminal 1: Start simulator
python -m sim serve --scenario scenarios/public_03_load.yaml --run-dir runs/mine03 --port 8703 --force

# Terminal 2: Run Controller
./run.sh http://127.0.0.1:8703

# Terminal 2: Grade Run against baseline
python -m sim baseline --scenario scenarios/public_03_load.yaml --run-dir runs/base03
python -m sim grade --run runs/mine03 --baseline runs/base03 --out reports/public_03.md
```

---

## 3. Crash Recovery Verification (C13)

Executes an abrupt `SIGKILL` mid-run, verifies SQLite database integrity, restarts the controller with the same state store, and ensures the simulation completes with zero duplicate actions or state loss:

```bash
python scripts/verify_crash_recovery.py
```

Output log is saved to `reports/crash_recovery.log`.

---

## 4. Regulatory Audit CLI (C12)

Answers the compliance question: *"Why did workflow X change at time T, who approved it, and what happened after?"*

```bash
python scripts/audit_query.py --db runs/mine02_ctrl.db --workflow ks_cancel
```

Output includes:
1. Event timeline with actors, actions, versions, and proposal IDs.
2. Proposal lineage with diffs, impact scores, dry runs, and human approval status.
3. Verified subsequent call outcomes (pickup %, engagement %, QA flags).


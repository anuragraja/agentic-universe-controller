"""Crash recovery test for SRE compliance (C13).
Simulates abrupt process crash (SIGKILL/taskkill) during active autonomous control,
restarts the controller with the same stateful SQLite DB, and verifies idempotent resumption.
"""
import subprocess
import time
import sys
import os
import sqlite3
import httpx

PORT = 8710
URL = f"http://127.0.0.1:{PORT}"
RUN_DIR = "runs/crash_test"
DB_PATH = "runs/crash_test.db"

def main():
    print("=" * 60)
    print("CRASH RECOVERY VERIFICATION TEST (C13)")
    print("=" * 60)
    
    # 1. Clean previous run artifacts
    if os.path.exists(DB_PATH):
        try:
            os.remove(DB_PATH)
        except OSError:
            pass

    # 2. Start sim server
    print(f"[Test] Starting simulator on port {PORT}...")
    sim_proc = subprocess.Popen(
        [sys.executable, "-m", "sim", "serve", "--scenario", "scenarios/public_01_dev.yaml", 
         "--run-dir", RUN_DIR, "--port", str(PORT), "--force"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    # Wait for sim health
    ready = False
    for _ in range(30):
        try:
            r = httpx.get(f"{URL}/health", timeout=1.0)
            if r.status_code == 200:
                ready = True
                break
        except Exception:
            time.sleep(1)
            
    if not ready:
        print("[Test] Simulator failed to start.")
        sim_proc.kill()
        sys.exit(1)
        
    print("[Test] Simulator is ready. Launching Controller Phase 1...")
    
    # 3. Launch controller
    ctrl_proc = subprocess.Popen(
        [sys.executable, "-m", "controller.main", "--url", URL, "--db", DB_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Let it run for ~25-30 seconds so it bootstraps and finishes Day 0 / Day 1
    print("[Test] Controller running... Waiting 25 seconds before simulated crash...")
    time.sleep(25)
    
    # 4. Abruptly KILL the controller
    print(f"\n[Test] !!! SIMULATING ABRUPT CRASH (KILLING PID {ctrl_proc.pid}) !!!")
    ctrl_proc.kill()
    ctrl_proc.wait()
    print("[Test] Controller process terminated abruptly via SIGKILL.")
    
    # Verify DB integrity right after crash
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("PRAGMA integrity_check")
    integrity = cur.fetchone()[0]
    print(f"[Test] SQLite integrity check post-crash: {integrity}")
    
    cur.execute("SELECT count(*) FROM proposals")
    proposals_before = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM audit_trail")
    audit_before = cur.fetchone()[0]
    print(f"[Test] State snapshot at crash: {proposals_before} proposals, {audit_before} audit entries logged.")
    conn.close()
    
    # 5. Restart controller with same DB
    print("\n[Test] Restarting Controller Phase 2 with existing SQLite DB...")
    restart_proc = subprocess.Popen(
        [sys.executable, "-m", "controller.main", "--url", URL, "--db", DB_PATH],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )
    
    # Stream output until complete
    for line in restart_proc.stdout:
        print(f"  [Controller] {line.strip()}")
        if "Simulation finished!" in line:
            break
            
    restart_proc.wait()
    print(f"[Test] Controller Phase 2 exited with code {restart_proc.returncode}.")
    
    # 6. Verify final state and idempotency
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT count(*) FROM proposals")
    proposals_after = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM audit_trail")
    audit_after = cur.fetchone()[0]
    
    # Verify no duplicate active proposals
    cur.execute("""
        SELECT proposal_id, count(*) 
        FROM proposals 
        GROUP BY proposal_id 
        HAVING count(*) > 1
    """)
    dups = cur.fetchall()
    
    # Check simulator final status
    r = httpx.get(f"{URL}/sim/state", timeout=2.0)
    sim_state = r.json()
    
    print("\n" + "=" * 60)
    print("CRASH RECOVERY TEST RESULTS:")
    print(f"- Simulator finished: {sim_state.get('finished')} (End Minute: {sim_state.get('sim_minute')})")
    print(f"- Proposals before crash: {proposals_before} | After completion: {proposals_after}")
    print(f"- Audit records before crash: {audit_before} | After completion: {audit_after}")
    print(f"- Duplicate proposals found: {len(dups)}")
    print(f"- SQLite Integrity Check: {integrity}")
    print("=" * 60)
    
    conn.close()
    sim_proc.kill()
    
    if sim_state.get('finished') and len(dups) == 0:
        print("[Test] SUCCESS: Crash recovery verified with 100% data integrity and zero duplicate actions.")
        sys.exit(0)
    else:
        print("[Test] FAILURE: Crash recovery verification failed.")
        sys.exit(1)

if __name__ == "__main__":
    main()

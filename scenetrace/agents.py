"""Bounded local workflow automation; no autonomous person identity decisions."""
import json
import threading

from . import store, service, vision

LOCK = threading.Lock()
RECHECK_ACTIVE = False


def settings():
    return {row["key"]: row["value"] == "true" for row in store.query("SELECT * FROM settings")}


def recover():
    service.recover_interrupted_jobs()
    store.execute("UPDATE agent_runs SET status='interrupted',message='Server stopped before this task finished.' WHERE status IN ('queued','running')")
    store.execute("UPDATE exports SET status='interrupted',message='Export stopped when the server closed. Create the video again.' WHERE status IN ('queued','processing')")
    if settings().get("auto_resume"):
        rows = store.query("""SELECT r.id FROM recordings r WHERE status='interrupted' AND resume_attempts<1
            AND NOT EXISTS(SELECT 1 FROM tracks t WHERE t.recording_id=r.id)""")
        for row in rows:
            with store.connect() as db:
                db.execute("UPDATE recordings SET resume_attempts=resume_attempts+1 WHERE id=?", (row["id"],))
                store.audit(db, "agent_resume", row["id"], {"reason": "interrupted during previous run", "max_attempts": 1})
            service.submit(row["id"])


def queue_recheck(reason="manual"):
    global RECHECK_ACTIVE
    with LOCK:
        if RECHECK_ACTIVE:
            return None
        RECHECK_ACTIVE = True
    run_id = store.new_id("agent")
    try:
        store.execute("INSERT INTO agent_runs(id,kind,status,message) VALUES(?,?,?,?)",
                      (run_id, "location_recheck", "queued", "Waiting to recheck unresolved locations"))
        service.EXECUTOR.submit(recheck, run_id, reason)
    except Exception:
        with LOCK:
            RECHECK_ACTIVE = False
        raise
    return run_id


def queue_quality_refresh():
    existing=store.query("SELECT id FROM agent_runs WHERE kind='evidence_quality' AND status IN ('queued','running')")
    if existing:return existing[0]['id']
    run_id=store.new_id("agent")
    store.execute("INSERT INTO agent_runs(id,kind,status,message) VALUES(?,?,?,?)",
        (run_id,"evidence_quality","queued","Waiting to refresh original-resolution crops and face evidence"))
    service.EXECUTOR.submit(refresh_evidence,run_id)
    return run_id


def refresh_evidence(run_id):
    try:
        store.execute("UPDATE agent_runs SET status='running' WHERE id=?",(run_id,))
        rows=store.query("SELECT id FROM recordings WHERE status='complete'")
        count=0
        for index,row in enumerate(rows):
            store.execute("UPDATE agent_runs SET message=? WHERE id=?",(f"Checking evidence from recording {index+1} of {len(rows)}",run_id))
            count+=service.refresh_quality(row["id"])
        store.execute("UPDATE agent_runs SET status='complete',message=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
            (f"Refreshed {count} original-resolution crops. Blurred or small faces stay unavailable for photo matching.",run_id))
    except Exception as error:
        store.execute("UPDATE agent_runs SET status='failed',message=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",(str(error)[:300],run_id))


def recheck(run_id, reason):
    global RECHECK_ACTIVE
    checked = recognized = 0
    try:
        store.execute("UPDATE agent_runs SET status='running',message=? WHERE id=?", ("Checking saved references against unresolved recordings", run_id))
        references = store.query("SELECT * FROM reference_views")
        recordings = store.query("SELECT id,path FROM recordings WHERE status='complete' AND location_status IN ('unknown','uncertain')")
        for row in recordings:
            try:
                frames, _ = vision.sample_video(row["path"])
                result = vision.recognize(frames, references)
                with store.connect() as db:
                    change = db.execute("""UPDATE recordings SET location_id=?,location_status=?,scene_scores=?
                        WHERE id=? AND status='complete' AND location_status IN ('unknown','uncertain')""",
                        (result["location_id"], result["status"], json.dumps(result["scores"]), row["id"]))
                    if change.rowcount:
                        checked += 1
                        recognized += int(result["status"] == "recognized")
                        store.audit(db, "agent_location_recheck", row["id"], {
                            "reason": reason, "status": result["status"], "location_id": result["location_id"],
                            "model": vision.SCENE_VERSION})
            except Exception as error:
                with store.connect() as db:
                    store.audit(db, "agent_recheck_error", row["id"], {"error": str(error)[:300]})
        store.execute("UPDATE agent_runs SET status='complete',message=?,finished_at=CURRENT_TIMESTAMP WHERE id=?",
                      (f"Checked {checked} recordings; recognized {recognized} locations. Confirmed labels and person associations were preserved.", run_id))
    except Exception as error:
        store.execute("UPDATE agent_runs SET status='failed',message=?,finished_at=CURRENT_TIMESTAMP WHERE id=?", (str(error)[:300], run_id))
    finally:
        with LOCK:
            RECHECK_ACTIVE = False

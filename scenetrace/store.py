from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"


def new_id(prefix):
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


@contextmanager
def connect():
    DATA.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DATA / "scenetrace.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init():
    for folder in ("videos", "references", "thumbnails", "exports"):
        (DATA / folder).mkdir(parents=True, exist_ok=True)
    with connect() as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS locations (
            id TEXT PRIMARY KEY, label TEXT NOT NULL UNIQUE,
            camera_label TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS reference_views (
            id TEXT PRIMARY KEY, location_id TEXT NOT NULL REFERENCES locations(id),
            features_path TEXT NOT NULL, preview_path TEXT NOT NULL, filename TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS recordings (
            id TEXT PRIMARY KEY, filename TEXT NOT NULL, path TEXT NOT NULL,
            sha256 TEXT NOT NULL UNIQUE, status TEXT NOT NULL DEFAULT 'queued',
            progress REAL NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
            duration REAL NOT NULL DEFAULT 0, recorded_at TEXT,
            location_id TEXT REFERENCES locations(id), location_status TEXT DEFAULT 'unknown',
            scene_scores TEXT DEFAULT '[]', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS people (
            id TEXT PRIMARY KEY, label TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS tracks (
            id TEXT PRIMARY KEY, recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
            local_id INTEGER NOT NULL, person_id TEXT NOT NULL REFERENCES people(id),
            first_seen REAL NOT NULL, last_seen REAL NOT NULL,
            thumbnail TEXT NOT NULL, appearance TEXT NOT NULL,
            match_status TEXT DEFAULT 'provisional', sample_count INTEGER NOT NULL,
            UNIQUE(recording_id, local_id));
        CREATE TABLE IF NOT EXISTS candidates (
            id TEXT PRIMARY KEY, track_id TEXT NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
            target_person_id TEXT NOT NULL REFERENCES people(id), score REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending');
        CREATE TABLE IF NOT EXISTS audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT, action TEXT NOT NULL,
            target TEXT NOT NULL, detail TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS exports (
            id TEXT PRIMARY KEY, person_id TEXT NOT NULL, status TEXT NOT NULL,
            progress REAL DEFAULT 0,message TEXT DEFAULT '',path TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS export_sources (
            export_id TEXT REFERENCES exports(id) ON DELETE CASCADE,
            recording_id TEXT REFERENCES recordings(id) ON DELETE CASCADE);
        CREATE TABLE IF NOT EXISTS detections (
            recording_id TEXT NOT NULL REFERENCES recordings(id) ON DELETE CASCADE,
            local_id INTEGER NOT NULL, offset REAL NOT NULL, box TEXT NOT NULL,
            confidence REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS detection_recording_idx ON detections(recording_id,offset);
        CREATE TABLE IF NOT EXISTS agent_runs (
            id TEXT PRIMARY KEY, kind TEXT NOT NULL, status TEXT NOT NULL,
            message TEXT NOT NULL DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            finished_at TEXT);
        """)
        columns = {row[1] for row in db.execute("PRAGMA table_info(recordings)")}
        if "resume_attempts" not in columns:
            db.execute("ALTER TABLE recordings ADD COLUMN resume_attempts INTEGER NOT NULL DEFAULT 0")
        for name, definition in (("detector_version", "TEXT"), ("processed_frames", "INTEGER DEFAULT 0")):
            if name not in columns:
                db.execute(f"ALTER TABLE recordings ADD COLUMN {name} {definition}")
        track_columns = {row[1] for row in db.execute("PRAGMA table_info(tracks)")}
        for name, definition in (("face_embeddings", "TEXT DEFAULT '[]'"), ("crop_sharpness", "REAL DEFAULT 0"),
                                 ("thumbnail_offset", "REAL DEFAULT 0"), ("quality_status", "TEXT DEFAULT 'not_checked'")):
            if name not in track_columns:
                db.execute(f"ALTER TABLE tracks ADD COLUMN {name} {definition}")
        detection_columns = {row[1] for row in db.execute("PRAGMA table_info(detections)")}
        if "face_box" not in detection_columns:
            db.execute("ALTER TABLE detections ADD COLUMN face_box TEXT")
        if not db.execute("SELECT 1 FROM counters WHERE key='face_match_migration'").fetchone():
            db.execute("DELETE FROM candidates WHERE status='pending'")
            db.execute("INSERT INTO counters(key,value) VALUES('face_match_migration',1)")
            audit(db,"replace_clothing_matcher","workspace",{"replacement":"quality-gated face candidates; no clothing fallback"})
        for key in ("auto_recheck", "auto_resume"):
            db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?, 'true')", (key,))
        for person in db.execute("SELECT id FROM people WHERE label=upper(id) ORDER BY created_at,id").fetchall():
            db.execute("UPDATE people SET label=? WHERE id=?", (next_person_label(db), person[0]))


def next_person_label(db):
    row = db.execute("INSERT INTO counters(key,value) VALUES('person',1) ON CONFLICT(key) DO UPDATE SET value=value+1 RETURNING value").fetchone()
    return f"Person {row[0]:04d}"


def query(sql, params=()):
    with connect() as db:
        return [dict(row) for row in db.execute(sql, params).fetchall()]


def execute(sql, params=()):
    with connect() as db:
        db.execute(sql, params)


def audit(db, action, target, detail):
    db.execute("INSERT INTO audit(action,target,detail) VALUES(?,?,?)",
               (action, target, json.dumps(detail)))


def update_recording(recording_id, **fields):
    allowed = {"status", "progress", "message", "duration", "location_id", "location_status", "scene_scores", "detector_version", "processed_frames"}
    if not fields or not set(fields).issubset(allowed):
        raise ValueError("Invalid recording update")
    execute(f"UPDATE recordings SET {','.join(k + '=?' for k in fields)} WHERE id=?",
            (*fields.values(), recording_id))


def assign_location(recording_id, location_id):
    with connect() as db:
        old = db.execute("SELECT location_id FROM recordings WHERE id=?", (recording_id,)).fetchone()
        if not old or not db.execute("SELECT 1 FROM locations WHERE id=?", (location_id,)).fetchone():
            raise ValueError("Recording or location does not exist")
        db.execute("UPDATE recordings SET location_id=?, location_status='confirmed' WHERE id=?",
                   (location_id, recording_id))
        audit(db, "confirm_location", recording_id, {"before": old[0], "after": location_id})


def review(track_id, person_id=None):
    with connect() as db:
        track = db.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
        if not track:
            raise ValueError("Track does not exist")
        target = person_id or track["person_id"]
        if not db.execute("SELECT 1 FROM people WHERE id=?", (target,)).fetchone():
            raise ValueError("Person group does not exist")
        conflict = db.execute("""SELECT 1 FROM tracks WHERE recording_id=? AND person_id=? AND id<>?
            AND first_seen < ? AND last_seen > ?""",
            (track["recording_id"], target, track_id, track["last_seen"], track["first_seen"])).fetchone()
        if conflict:
            raise ValueError("This group already has an overlapping track in this recording. Review those tracks first.")
        db.execute("UPDATE tracks SET person_id=?, match_status='confirmed' WHERE id=?", (target, track_id))
        db.execute("UPDATE candidates SET status=CASE WHEN target_person_id=? THEN 'accepted' ELSE 'rejected' END WHERE track_id=?",
                   (target, track_id))
        audit(db, "confirm_person_group", track_id, {"before": track["person_id"], "after": target})


def split_track(track_id):
    with connect() as db:
        track = db.execute("SELECT person_id FROM tracks WHERE id=?", (track_id,)).fetchone()
        if not track:
            raise ValueError("Track does not exist")
        person_id = new_id("P")
        db.execute("INSERT INTO people(id,label) VALUES(?,?)", (person_id, next_person_label(db)))
        db.execute("UPDATE tracks SET person_id=?,match_status='provisional' WHERE id=?", (person_id, track_id))
        db.execute("UPDATE candidates SET status='rejected' WHERE track_id=?", (track_id,))
        audit(db, "split_person_group", track_id, {"before": track[0], "after": person_id})


def delete_recording(recording_id):
    with connect() as db:
        recording = db.execute("SELECT path,status FROM recordings WHERE id=?", (recording_id,)).fetchone()
        if not recording:
            return
        if recording["status"] in ("queued", "processing"):
            raise ValueError("Wait for processing to finish before deleting this recording.")
        exports=db.execute("SELECT e.id,e.path,e.status FROM exports e JOIN export_sources s ON s.export_id=e.id WHERE s.recording_id=?",(recording_id,)).fetchall()
        if any(export["status"] in ("queued","processing") for export in exports):
            raise ValueError("Wait for the tracked-video export to finish before deleting its source recording.")
        paths = [row[0] for row in db.execute("SELECT thumbnail FROM tracks WHERE recording_id=?", (recording_id,))]
        paths.extend(export["path"] for export in exports)
        for export in exports:
            db.execute("DELETE FROM exports WHERE id=?",(export["id"],))
        db.execute("DELETE FROM recordings WHERE id=?", (recording_id,))
        db.execute("DELETE FROM candidates WHERE target_person_id IN (SELECT p.id FROM people p WHERE NOT EXISTS(SELECT 1 FROM tracks t WHERE t.person_id=p.id))")
        db.execute("DELETE FROM people WHERE NOT EXISTS(SELECT 1 FROM tracks WHERE tracks.person_id=people.id)")
        audit(db, "delete_recording", recording_id, {})
    for path in [recording["path"], *paths]:
        resolved = Path(path).resolve()
        if resolved.is_relative_to(DATA.resolve()):
            resolved.unlink(missing_ok=True)

from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO, StringIO
from pathlib import Path
import csv
import json
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.concurrency import run_in_threadpool
from . import store, service, agents, vision


@asynccontextmanager
async def lifespan(app):
    store.init()
    agents.recover()
    yield


app = FastAPI(title="SceneTrace Local API", lifespan=lifespan)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])


@app.middleware("http")
async def local_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and urlparse(origin).netloc != request.headers.get("host"):
        return JSONResponse({"detail": "Open the local workspace to make changes."}, status_code=403)
    return await call_next(request)


@app.exception_handler(ValueError)
async def invalid_request(request, error):
    return JSONResponse({"detail": str(error)}, status_code=400)


def get_recording(recording_id):
    rows = store.query("SELECT r.*,l.label AS location_label,l.camera_label FROM recordings r LEFT JOIN locations l ON l.id=r.location_id WHERE r.id=?", (recording_id,))
    if not rows:
        raise HTTPException(404, "Recording not found")
    return rows[0]


def public_recording(row):
    return {key: value for key, value in row.items() if key not in {"path", "sha256"}} | {
        "media_url": f"/api/recordings/{row['id']}/media", "scene_scores": json.loads(row["scene_scores"])}


def public_track(row):
    return {key: value for key, value in row.items() if key not in {"appearance", "face_embeddings", "thumbnail", "path"}} | {
        "thumbnail_url": f"/api/tracks/{row['id']}/thumbnail?v={round(row.get('crop_sharpness',0))}"}


def location_rows():
    rows = store.query("SELECT l.*,COUNT(v.id) AS reference_count FROM locations l LEFT JOIN reference_views v ON v.location_id=l.id GROUP BY l.id ORDER BY l.created_at")
    for row in rows:
        references = store.query("SELECT id FROM reference_views WHERE location_id=?", (row["id"],))
        row["preview_url"] = f"/api/references/{references[0]['id']}/preview" if references else None
    return rows


async def incoming(upload):
    contents = bytearray()
    try:
        while chunk := await upload.read(1024 * 1024):
            contents.extend(chunk)
            if len(contents) > 250 * 1024 * 1024:
                raise ValueError("Choose a video under 250 MB.")
    finally:
        await upload.close()
    buffer = BytesIO(contents)
    buffer.name = upload.filename or "video.mp4"
    return buffer


@app.get("/api/health")
def health():
    return {"status": "ok", "name": "SceneTrace"}


@app.get("/api/overview")
def overview():
    return {
        "locations": len(location_rows()),
        "recordings": store.query("SELECT COUNT(*) AS n FROM recordings")[0]["n"],
        "people": store.query("SELECT COUNT(DISTINCT person_id) AS n FROM tracks")[0]["n"],
        "reviews": store.query("SELECT COUNT(*) AS n FROM tracks WHERE match_status='provisional'")[0]["n"],
        "active_jobs": store.query("SELECT COUNT(*) AS n FROM recordings WHERE status IN ('queued','processing')")[0]["n"],
    }


@app.get("/api/locations")
def locations():
    return location_rows()


@app.post("/api/references")
async def reference(file: UploadFile = File(...), label: str = Form(...), camera_label: str = Form(...), location_id: str | None = Form(None)):
    result = await run_in_threadpool(service.register_reference, await incoming(file), label, camera_label, location_id or None)
    run_id = agents.queue_recheck("reference_added") if agents.settings().get("auto_recheck") else None
    return {"location_id": result, "agent_run_id": run_id}


class RenameLocation(BaseModel):
    label: str = Field(min_length=1, max_length=100)


@app.patch("/api/locations/{location_id}")
def rename_location(location_id: str, payload: RenameLocation):
    label = payload.label.strip()
    if not label:
        raise ValueError("Enter a location name.")
    if not store.query("SELECT id FROM locations WHERE id=?", (location_id,)):
        raise HTTPException(404, "Location not found")
    if store.query("SELECT id FROM locations WHERE lower(label)=lower(?) AND id<>?", (label, location_id)):
        raise ValueError("That label is already used by another view.")
    with store.connect() as db:
        db.execute("UPDATE locations SET label=? WHERE id=?", (label, location_id))
        store.audit(db, "rename_location", location_id, {"label": label})
    return {"ok": True}


@app.get("/api/references/{reference_id}/preview")
def reference_preview(reference_id: str):
    rows = store.query("SELECT preview_path FROM reference_views WHERE id=?", (reference_id,))
    if not rows or not Path(rows[0]["preview_path"]).exists():
        raise HTTPException(404, "Reference preview not found")
    return FileResponse(rows[0]["preview_path"], media_type="image/jpeg")


@app.post("/api/recordings")
async def upload_recording(file: UploadFile = File(...), recorded_at: str | None = Form(None)):
    if recorded_at:
        try:
            parsed = datetime.fromisoformat(recorded_at)
        except ValueError:
            raise ValueError("Enter a valid recording start time.")
        if parsed.tzinfo is None:
            raise ValueError("Recording time requires a UTC offset.")
        recorded_at = parsed.isoformat()
    result, duplicate = await run_in_threadpool(service.add_recording, await incoming(file), recorded_at)
    return {"id": result, "duplicate": duplicate}


@app.get("/api/recordings")
def recordings():
    rows = store.query("SELECT r.*,l.label AS location_label,l.camera_label FROM recordings r LEFT JOIN locations l ON l.id=r.location_id ORDER BY r.created_at DESC")
    return [public_recording(row) for row in rows]


@app.get("/api/recordings/{recording_id}")
def recording(recording_id: str):
    row = public_recording(get_recording(recording_id))
    row["tracks"] = [public_track(track) for track in store.query("SELECT t.*,p.label FROM tracks t JOIN people p ON p.id=t.person_id WHERE recording_id=? ORDER BY first_seen", (recording_id,))]
    return row


@app.get("/api/recordings/{recording_id}/media")
def media(recording_id: str):
    row = get_recording(recording_id)
    if not Path(row["path"]).exists():
        raise HTTPException(404, "Source file is missing")
    return FileResponse(row["path"])


class LocationAssignment(BaseModel):
    location_id: str


@app.patch("/api/recordings/{recording_id}/location")
def assign_location(recording_id: str, assignment: LocationAssignment):
    get_recording(recording_id)
    store.assign_location(recording_id, assignment.location_id)
    return {"ok": True}


@app.post("/api/recordings/{recording_id}/teach-location")
def teach_recording_location(recording_id: str, assignment: LocationAssignment):
    recording=get_recording(recording_id)
    if recording["status"] in ("queued","processing"):
        raise ValueError("Wait for processing to finish before teaching this view.")
    locations=store.query("SELECT * FROM locations WHERE id=?",(assignment.location_id,))
    if not locations:
        raise ValueError("Choose one of your saved locations.")
    source=locations[0]
    upload=BytesIO(Path(recording["path"]).read_bytes())
    upload.name=recording["filename"]
    service.register_reference(upload,source["label"],source["camera_label"],source["id"])
    store.assign_location(recording_id,source["id"])
    run_id=agents.queue_recheck("additional_view_taught")
    return {"ok":True,"agent_run_id":run_id}


@app.post("/api/recordings/{recording_id}/retry")
def retry(recording_id: str):
    row = get_recording(recording_id)
    if row["status"] not in ("failed", "interrupted"):
        raise ValueError("Only failed or interrupted recordings can be retried.")
    service.submit(recording_id)
    return {"ok": True}


@app.post("/api/recordings/{recording_id}/reanalyze")
def reanalyze(recording_id: str):
    row = get_recording(recording_id)
    if row["status"] in ("queued", "processing"):
        raise ValueError("This recording is already being analyzed.")
    if store.query("SELECT id FROM tracks WHERE recording_id=? AND match_status='confirmed'", (recording_id,)):
        raise ValueError("Reviewed associations were preserved. Split any confirmed tracks before replacing this analysis.")
    service.submit(recording_id, replace=True)
    return {"ok": True}


@app.get("/api/recordings/{recording_id}/detections")
def detections(recording_id: str):
    get_recording(recording_id)
    rows = store.query("""SELECT d.local_id,d.offset,d.box,d.face_box,d.confidence,t.person_id,p.label
        FROM detections d JOIN tracks t ON t.recording_id=d.recording_id AND t.local_id=d.local_id
        JOIN people p ON p.id=t.person_id WHERE d.recording_id=? ORDER BY d.offset""", (recording_id,))
    return [{**row,"box":json.loads(row["box"]),"face_box":json.loads(row["face_box"]) if row["face_box"] else None} for row in rows]


@app.get("/api/recordings/{recording_id}/frame")
def appearance_frame(recording_id: str, at: float = 0):
    import cv2
    import math
    row = get_recording(recording_id)
    if not math.isfinite(at) or at < 0 or at > row["duration"]:
        raise ValueError("Choose a playback time inside this recording.")
    cap = cv2.VideoCapture(row["path"])
    try:
        cap.set(cv2.CAP_PROP_POS_MSEC, at * 1000)
        ok, frame = cap.read()
        if not ok:
            raise ValueError("The video frame could not be decoded.")
        frame = vision.resize(frame)
        rows = store.query("""SELECT d.box,d.confidence,p.label FROM detections d JOIN tracks t
            ON t.recording_id=d.recording_id AND t.local_id=d.local_id JOIN people p ON p.id=t.person_id
            WHERE d.recording_id=? AND abs(d.offset-?)<0.09""", (recording_id, at))
        for detection in rows:
            x, y, w, h = json.loads(detection["box"])
            x, w = int(x * frame.shape[1]), int(w * frame.shape[1])
            y, h = int(y * frame.shape[0]), int(h * frame.shape[0])
            cv2.rectangle(frame, (x, y), (x+w, y+h), (95, 240, 130), 2)
            cv2.putText(frame, detection["label"], (x, max(18,y-8)), cv2.FONT_HERSHEY_SIMPLEX, .55, (95, 240, 130), 2)
        ok, encoded = cv2.imencode(".jpg", frame)
        if not ok:
            raise ValueError("Unable to render the appearance frame.")
        return Response(encoded.tobytes(), media_type="image/jpeg")
    finally:
        cap.release()


@app.delete("/api/recordings/{recording_id}")
def delete_recording(recording_id: str):
    get_recording(recording_id)
    store.delete_recording(recording_id)
    return {"ok": True}


@app.get("/api/tracks/{track_id}/thumbnail")
def thumbnail(track_id: str, enhance: bool = False):
    rows = store.query("SELECT thumbnail FROM tracks WHERE id=?", (track_id,))
    if not rows or not Path(rows[0]["thumbnail"]).exists():
        raise HTTPException(404, "Person preview not found")
    if enhance:
        import cv2
        from .identity import enhance_preview
        original = cv2.imread(rows[0]["thumbnail"])
        if original is None:
            raise ValueError("The original crop is unavailable.")
        ok,encoded = cv2.imencode('.jpg',enhance_preview(original),[cv2.IMWRITE_JPEG_QUALITY,96])
        if not ok:
            raise ValueError("Unable to enhance this preview.")
        return Response(encoded.tobytes(),media_type="image/jpeg")
    return FileResponse(rows[0]["thumbnail"], media_type="image/jpeg")


@app.get("/api/people")
def people():
    rows = store.query("SELECT p.*,COUNT(t.id) AS appearances FROM people p JOIN tracks t ON t.person_id=p.id GROUP BY p.id ORDER BY p.created_at DESC")
    for row in rows:
        track = store.query("SELECT id FROM tracks WHERE person_id=? ORDER BY sample_count DESC LIMIT 1", (row["id"],))[0]
        row["thumbnail_url"] = f"/api/tracks/{track['id']}/thumbnail"
    return rows


def person_observations(person_id):
    rows = store.query("""SELECT t.*,r.filename,r.recorded_at,r.location_status,
        l.label AS location_label,l.camera_label FROM tracks t JOIN recordings r ON t.recording_id=r.id
        LEFT JOIN locations l ON l.id=r.location_id WHERE t.person_id=?""", (person_id,))
    result = []
    for row in rows:
        item = public_track(row)
        item["first_observed"] = service.observation_time(row["recorded_at"], row["first_seen"])
        item["last_observed"] = service.observation_time(row["recorded_at"], row["last_seen"])
        result.append(item)
    return result


@app.get("/api/people/{person_id}")
def person(person_id: str):
    return {"id":person_id,"observations":person_observations(person_id),
        "videos":store.query("SELECT id,status,progress,message FROM exports WHERE person_id=? ORDER BY created_at DESC LIMIT 5",(person_id,))}


@app.post("/api/people/{person_id}/tracked-video")
def create_tracked_video(person_id: str):
    from .video_export import queue
    return {"id":queue(person_id)}


@app.get("/api/exports/{export_id}")
def tracked_video_status(export_id: str):
    rows=store.query("SELECT id,person_id,status,progress,message FROM exports WHERE id=?",(export_id,))
    if not rows:raise HTTPException(404,"Tracked video not found")
    return rows[0] | {"media_url":f"/api/exports/{export_id}/media"}


@app.get("/api/exports/{export_id}/media")
def tracked_video_media(export_id: str):
    rows=store.query("SELECT path,status FROM exports WHERE id=?",(export_id,))
    if not rows or rows[0]['status']!='complete' or not Path(rows[0]['path']).exists():
        raise HTTPException(404,"Tracked video is not ready")
    return FileResponse(rows[0]['path'],media_type='video/mp4')


@app.get("/api/people/{person_id}/export")
def export_person(person_id: str):
    output = StringIO()
    writer = csv.writer(output)
    fields = ["person_id", "filename", "location_label", "camera_label", "first_observed", "last_observed", "recorded_at", "match_status", "location_status"]
    writer.writerow(fields)
    for row in person_observations(person_id):
        values = [str(row.get(key) or "") for key in fields]
        writer.writerow(["'" + value if value.startswith(("=", "+", "-", "@")) else value for value in values])
    return Response(output.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="person-timeline.csv"'})


@app.get("/api/reviews")
def reviews():
    tracks = store.query("SELECT t.*,r.filename,p.label FROM tracks t JOIN recordings r ON r.id=t.recording_id JOIN people p ON p.id=t.person_id WHERE t.match_status='provisional' ORDER BY r.created_at DESC,t.first_seen")
    result = []
    for row in tracks:
        item = public_track(row)
        candidates = store.query("SELECT c.*,p.label FROM candidates c JOIN people p ON p.id=c.target_person_id WHERE c.track_id=? AND c.status='pending' ORDER BY c.score DESC", (row["id"],))
        for candidate in candidates:
            others = store.query("SELECT id FROM tracks WHERE person_id=? ORDER BY sample_count DESC LIMIT 1", (candidate["target_person_id"],))
            candidate["thumbnail_url"] = f"/api/tracks/{others[0]['id']}/thumbnail" if others else None
        item["candidates"] = candidates
        result.append(item)
    return result


class ReviewDecision(BaseModel):
    action: str
    person_id: str | None = None
    candidate_id: str | None = None


@app.post("/api/tracks/{track_id}/review")
def review(track_id: str, decision: ReviewDecision):
    if not store.query("SELECT id FROM tracks WHERE id=?", (track_id,)):
        raise HTTPException(404, "Track not found")
    if decision.action == "split":
        store.split_track(track_id)
    elif decision.action == "reject":
        if not store.query("SELECT id FROM candidates WHERE id=? AND track_id=?", (decision.candidate_id, track_id)):
            raise ValueError("Candidate not found for this track.")
        with store.connect() as db:
            db.execute("UPDATE candidates SET status='rejected' WHERE id=? AND track_id=?", (decision.candidate_id, track_id))
            store.audit(db, "reject_match", track_id, {"candidate": decision.candidate_id})
    elif decision.action in ("accept", "keep"):
        if decision.action == "accept" and not decision.person_id:
            raise ValueError("Select a target person group.")
        store.review(track_id, decision.person_id if decision.action == "accept" else None)
    else:
        raise ValueError("Unknown review action.")
    return {"ok": True}


@app.get("/api/search/people")
def search_people(q: str = "", location_id: str | None = None):
    term = q.strip().lower()[:100]
    rows = store.query("""SELECT t.*,p.label,r.filename,r.recorded_at,r.location_status,
        l.label AS location_label,l.camera_label FROM tracks t JOIN people p ON p.id=t.person_id
        JOIN recordings r ON r.id=t.recording_id LEFT JOIN locations l ON l.id=r.location_id
        WHERE (instr(lower(p.id),?)>0 OR instr(lower(p.label),?)>0 OR instr(lower(t.id),?)>0)
        AND (? IS NULL OR r.location_id=?) ORDER BY r.created_at DESC,t.first_seen LIMIT 100""",
        (term, term, term, location_id, location_id))
    return {"matches": [public_track(row) | {
        "first_observed": service.observation_time(row["recorded_at"], row["first_seen"]),
        "last_observed": service.observation_time(row["recorded_at"], row["last_seen"])} for row in rows]}


@app.post("/api/search/photo")
async def search_photo(file: UploadFile = File(...), location_id: str | None = Form(None), recording_id: str | None = Form(None)):
    from .search import photo_matches
    try:
        contents = await file.read(10 * 1024 * 1024 + 1)
    finally:
        await file.close()
    if recording_id:
        get_recording(recording_id)
    results = await run_in_threadpool(photo_matches, contents, location_id or None, recording_id or None)
    return {"method":"quality_gated_face_similarity","identity_verified":False,
            "message":"Face candidates only; confirm against source evidence. No result means insufficient matching evidence, not proof of absence. No clothing-color fallback is used.",
            "matches": [public_track(row) | {
                "first_observed": service.observation_time(row["recorded_at"], row["first_seen"]),
                "last_observed": service.observation_time(row["recorded_at"], row["last_seen"])} for row in results]}


@app.get("/api/agents")
def agent_center():
    return {"settings": agents.settings(),
            "runs": store.query("SELECT * FROM agent_runs ORDER BY created_at DESC,id DESC LIMIT 30"),
            "activity": store.query("SELECT * FROM audit ORDER BY id DESC LIMIT 40"),
            "attention": {
                "unassigned_locations": store.query("SELECT COUNT(*) AS n FROM recordings WHERE status='complete' AND location_status IN ('unknown','uncertain')")[0]["n"],
                "provisional_tracks": store.query("SELECT COUNT(*) AS n FROM tracks WHERE match_status='provisional'")[0]["n"],
                "failed_jobs": store.query("SELECT COUNT(*) AS n FROM recordings WHERE status IN ('failed','interrupted')")[0]["n"],
            }}


class AgentSettings(BaseModel):
    auto_recheck: bool
    auto_resume: bool


@app.patch("/api/agents/settings")
def update_agent_settings(payload: AgentSettings):
    with store.connect() as db:
        for key, value in payload.model_dump().items():
            db.execute("UPDATE settings SET value=? WHERE key=?", ("true" if value else "false", key))
        store.audit(db, "update_agent_settings", "workspace", payload.model_dump())
    return {"ok": True}


@app.post("/api/agents/recheck")
def recheck_locations():
    return {"run_id": agents.queue_recheck(), "message": "Location recheck queued, or an existing recheck is already active."}


@app.post("/api/agents/quality-refresh")
def refresh_evidence_quality():
    return {"run_id":agents.queue_quality_refresh()}


app.mount("/", StaticFiles(directory=store.ROOT / "frontend", html=True), name="frontend")

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import json
import threading

import cv2
import numpy as np

from . import store, vision, identity, quality

EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="scenetrace")
LOCK = threading.Lock()
ACTIVE = set()


def recover_interrupted_jobs():
    store.execute("UPDATE recordings SET status='interrupted', message='Processing stopped when the app closed. Retry this recording.' WHERE status IN ('queued','processing')")


def write_upload(upload, folder):
    suffix = Path(upload.name).suffix.lower()
    if suffix not in {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}:
        raise ValueError("Choose a supported video file.")
    contents = upload.getbuffer()
    if len(contents) > 250 * 1024 * 1024 or not len(contents):
        raise ValueError("Choose a non-empty video under 250 MB.")
    digest = hashlib.sha256(contents).hexdigest()
    path = store.DATA / folder / f"{store.new_id('video')}{suffix}"
    path.write_bytes(contents)
    return path, digest


def register_reference(upload, label, camera_label, location_id=None):
    label = label.strip()[:100]
    camera_label = camera_label.strip()[:80]
    if not label or not camera_label:
        raise ValueError("Enter a location name and camera label.")
    if not location_id and store.query("SELECT id FROM locations WHERE lower(label)=lower(?)", (label,)):
        raise ValueError("That location is already saved. Add another reference to it instead.")
    path, _ = write_upload(upload, "references")
    reference_id = store.new_id("ref")
    feature_path = store.DATA / "references" / f"{reference_id}.npz"
    preview_path = store.DATA / "references" / f"{reference_id}.jpg"
    try:
        frames, _ = vision.sample_video(path)
        if max(len(vision.describe(frame)[1]) for frame in frames) < 20:
            raise ValueError("This view has too little background detail. Use clearer footage showing doors, walls, or furniture.")
        vision.save_reference(frames, feature_path)
        cv2.imwrite(str(preview_path), frames[0])
        with store.connect() as db:
            if location_id:
                if not db.execute("SELECT id FROM locations WHERE id=?", (location_id,)).fetchone():
                    raise ValueError("Saved location no longer exists.")
            else:
                location_id = store.new_id("loc")
                db.execute("INSERT INTO locations(id,label,camera_label) VALUES(?,?,?)", (location_id, label, camera_label))
            db.execute("INSERT INTO reference_views VALUES(?,?,?,?,?)",
                       (reference_id, location_id, str(feature_path), str(preview_path), Path(upload.name).name))
            store.audit(db, "register_reference", location_id, {"reference_id": reference_id, "model": vision.SCENE_VERSION})
        return location_id
    except Exception:
        feature_path.unlink(missing_ok=True)
        preview_path.unlink(missing_ok=True)
        raise
    finally:
        path.unlink(missing_ok=True)


def add_recording(upload, recorded_at=None):
    path, digest = write_upload(upload, "videos")
    existing = store.query("SELECT id FROM recordings WHERE sha256=?", (digest,))
    if existing:
        path.unlink(missing_ok=True)
        return existing[0]["id"], True
    try:
        _, duration = vision.sample_video(path, count=1)
        recording_id = store.new_id("rec")
        store.execute("INSERT INTO recordings(id,filename,path,sha256,duration,recorded_at) VALUES(?,?,?,?,?,?)",
                      (recording_id, Path(upload.name).name, str(path), digest, duration, recorded_at))
        submit(recording_id)
        return recording_id, False
    except Exception:
        path.unlink(missing_ok=True)
        raise


def submit(recording_id, replace=False):
    with LOCK:
        if recording_id in ACTIVE:
            return
        ACTIVE.add(recording_id)
    store.update_recording(recording_id, status="queued", progress=0, message="Waiting to analyze")
    EXECUTOR.submit(process, recording_id, replace)


def appearance_candidates(appearance, recording_id):
    # A face descriptor is required. Clothing color is never used for identity suggestions.
    if not appearance:
        return []
    rows = store.query("SELECT t.face_embeddings,t.person_id FROM tracks t WHERE t.recording_id<>?", (recording_id,))
    ranked = {}
    for row in rows:
        scores = [identity.face_similarity(sample["feature"],json.loads(row["face_embeddings"])) for sample in appearance]
        supported = [score for score in scores if score is not None]
        if supported:
            ranked[row["person_id"]] = max(ranked.get(row["person_id"],0),max(supported))
    return sorted(ranked.items(), key=lambda pair: pair[1], reverse=True)[:3]


def process(recording_id, replace=False):
    cap = None
    thumbnail_paths = []
    old_thumbnails = []
    try:
        row = store.query("SELECT * FROM recordings WHERE id=?", (recording_id,))[0]
        previous = store.query("SELECT * FROM tracks WHERE recording_id=?", (recording_id,))
        old_detections=store.query("SELECT * FROM detections WHERE recording_id=?",(recording_id,)) if replace else []
        if previous and not replace:
            raise ValueError("This recording already has results. Existing reviewed results were preserved.")
        if replace and any(track["match_status"] == "confirmed" for track in previous):
            raise ValueError("This recording has reviewed person associations. Reanalysis will not overwrite those decisions.")
        store.update_recording(recording_id, status="processing", message="Recognizing the saved viewpoint", progress=.03)
        frames, duration = vision.sample_video(row["path"])
        result = vision.recognize(frames, store.query("SELECT * FROM reference_views"))
        if row["location_status"] == "confirmed":
            result.update(location_id=row["location_id"], status="confirmed")
        store.update_recording(recording_id, location_id=result["location_id"], location_status=result["status"],
                               scene_scores=json.dumps(result["scores"]), progress=.12, duration=duration,
                               message="Loading the person-only neural detector")
        cap = cv2.VideoCapture(row["path"])
        fps = cap.get(cv2.CAP_PROP_FPS)
        total = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        stride = max(1, int(fps / 5))
        detector = vision.PedestrianDetector()
        face_engine = identity.FaceEngine()
        tracker = vision.TrackManager()
        index = 0
        observations = []
        processed_frames = 0
        while cap.isOpened():
            ok, frame = cap.read()
            if not ok:
                break
            if index % stride == 0:
                timestamp = cap.get(cv2.CAP_PROP_POS_MSEC) / 1000
                # For codecs without presentation timestamps only, use the frame offset.
                if timestamp <= 0 and index > 0:
                    timestamp = index / fps
                native = frame
                frame = vision.resize(frame)
                boxes = detector.detect(frame)
                faces=face_engine.detect(native)
                face_only=set()
                for face in faces:
                    fx,fy,fw,fh=face[:4]
                    center=((fx+fw/2)*frame.shape[1]/native.shape[1],(fy+fh/2)*frame.shape[0]/native.shape[0])
                    if any(x<=center[0]<=x+w and y<=center[1]<=y+h for x,y,w,h in boxes):continue
                    clipped=(max(0,int(fx*frame.shape[1]/native.shape[1])),max(0,int(fy*frame.shape[0]/native.shape[0])),
                        int(fw*frame.shape[1]/native.shape[1]),int(fh*frame.shape[0]/native.shape[0]))
                    boxes.append(clipped);detector.scores.append(float(face[14]));face_only.add(clipped)
                current = tracker.update(boxes,timestamp,frame,face_only=face_only)
                processed_frames += 1
                for track in current:
                    box = track["box"]
                    box_index = boxes.index(box)
                    confidence = detector.scores[box_index] if box_index < len(detector.scores) else 1.0
                    track["max_confidence"] = max(track.get("max_confidence", 0), confidence)
                    normalized = [box[0]/frame.shape[1],box[1]/frame.shape[0],box[2]/frame.shape[1],box[3]/frame.shape[0]]
                    evidence_box=normalized
                    if box in face_only:
                        x,y,w,h=normalized
                        evidence_box=[max(0,x-w*.25),max(0,y-h*.25),w*1.5,h*1.5]
                    face_box = quality.gather(track,native,evidence_box,timestamp,face_engine)
                    if face_box is None:
                        for face in faces:
                            fx,fy,fw,fh=face[:4]
                            nx,ny=(fx+fw/2)/native.shape[1],(fy+fh/2)/native.shape[0]
                            if normalized[0]<=nx<=normalized[0]+normalized[2] and normalized[1]<=ny<=normalized[1]+normalized[3]:
                                face_box=[float(fx/native.shape[1]),float(fy/native.shape[0]),float(fw/native.shape[1]),float(fh/native.shape[0])];break
                    observations.append((track["local_id"],timestamp,normalized,confidence,face_box))
                if index % (stride * 2) == 0:
                    store.update_recording(recording_id, progress=min(.96, .12 + .84 * index / max(1, total)),
                                           message=f"Person detection · {timestamp:.1f}s / {duration:.1f}s · {len(current)} visible", processed_frames=processed_frames)
            index += 1
        pending_tracks = []
        for track in tracker.tracks.values():
            if track["samples"] < 3 or track["last_seen"]-track["first_seen"] < .35:
                continue
            track_id = store.new_id("track")
            person_id = store.new_id("P")
            thumbnail = store.DATA / "thumbnails" / f"{track_id}.jpg"
            if not cv2.imwrite(str(thumbnail), track["thumbnail"], [cv2.IMWRITE_JPEG_QUALITY,96]):
                raise ValueError("Could not save the person preview. Check free disk space.")
            thumbnail_paths.append(thumbnail)
            pending_tracks.append((track, track_id, person_id, thumbnail,
                                   appearance_candidates(track.get("face_embeddings",[]), recording_id)))
        reused=set()
        old_boxes={(sample['local_id'],round(sample['offset'],3)):json.loads(sample['box']) for sample in old_detections}
        for track,*_ in pending_tracks:
            new_samples=[sample for sample in observations if sample[0]==track['local_id']]
            ranks=[]
            for old in previous:
                if old['person_id'] in reused:continue
                scores=[vision.overlap(sample[2],old_boxes[(old['local_id'],round(sample[1],3))])
                    for sample in new_samples if (old['local_id'],round(sample[1],3)) in old_boxes]
                if len(scores)>=3:ranks.append((float(np.mean(scores)),old['person_id']))
            if ranks and max(ranks)[0]>=.75:
                track['reuse_person_id']=max(ranks)[1];reused.add(track['reuse_person_id'])
        with store.connect() as db:
            if replace:
                # Commit replacement only after inference succeeds. Keep old results on failure.
                if db.execute("SELECT 1 FROM tracks WHERE recording_id=? AND match_status='confirmed'", (recording_id,)).fetchone():
                    raise ValueError("A reviewer confirmed a track during analysis; previous results were preserved.")
                old_thumbnails = [track["thumbnail"] for track in previous]
                db.execute("DELETE FROM tracks WHERE recording_id=?", (recording_id,))
                db.execute("DELETE FROM detections WHERE recording_id=?", (recording_id,))
            for track, track_id, person_id, thumbnail, candidates in pending_tracks:
                auto_match = bool(candidates and candidates[0][1]>=.75 and
                    (len(candidates)==1 or candidates[0][1]-candidates[1][1]>=.12))
                if auto_match and db.execute("SELECT 1 FROM tracks WHERE recording_id=? AND person_id=? AND first_seen<? AND last_seen>?",
                    (recording_id,candidates[0][0],track['last_seen'],track['first_seen'])).fetchone():
                    auto_match=False
                if auto_match:
                    person_id=candidates[0][0]
                    store.audit(db,"automatic_person_association",track_id,{"person_id":person_id,"face_score":candidates[0][1],"model":identity.VERSION})
                else:
                    if track.get('reuse_person_id'):
                        person_id=track['reuse_person_id']
                    else:
                        db.execute("INSERT INTO people(id,label) VALUES(?,?)", (person_id, store.next_person_label(db)))
                db.execute("""INSERT INTO tracks(id,recording_id,local_id,person_id,first_seen,last_seen,thumbnail,
                    appearance,sample_count,face_embeddings,crop_sharpness,thumbnail_offset,quality_status) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    track_id, recording_id, track["local_id"], person_id, track["first_seen"], track["last_seen"],
                    str(thumbnail),json.dumps(track["appearance"].tolist()),track["samples"],json.dumps(track.get("face_embeddings",[])),
                    track.get("crop_sharpness",0),track.get("thumbnail_offset",track["first_seen"]),track.get("quality_status","not_checked")))
                if auto_match:
                    db.execute("UPDATE tracks SET match_status='automatic' WHERE id=?",(track_id,))
                for target, score in candidates:
                    db.execute("INSERT INTO candidates(id,track_id,target_person_id,score) VALUES(?,?,?,?)",
                               (store.new_id("candidate"), track_id, target, score))
            retained = {track["local_id"] for track, *_ in pending_tracks}
            db.executemany("INSERT INTO detections(recording_id,local_id,offset,box,confidence,face_box) VALUES(?,?,?,?,?,?)",
                [(recording_id,local_id,timestamp,json.dumps(box),confidence,json.dumps(face_box) if face_box else None)
                 for local_id,timestamp,box,confidence,face_box in observations if local_id in retained])
            if replace:
                db.execute("DELETE FROM candidates WHERE target_person_id IN (SELECT p.id FROM people p WHERE NOT EXISTS(SELECT 1 FROM tracks t WHERE t.person_id=p.id))")
                db.execute("DELETE FROM people WHERE NOT EXISTS(SELECT 1 FROM tracks WHERE tracks.person_id=people.id)")
            message = f"Analysis complete · {len(pending_tracks)} person tracks · {processed_frames} frames analyzed"
            db.execute("UPDATE recordings SET status='complete',progress=1,message=?,detector_version=?,processed_frames=? WHERE id=?", (message, vision.DETECTOR_VERSION, processed_frames, recording_id))
            store.audit(db, "analysis_complete", recording_id, {"scene_model": vision.SCENE_VERSION,
                        "detector": vision.DETECTOR_VERSION, "person_matcher": identity.VERSION})
        for old_path in old_thumbnails:
            resolved = Path(old_path).resolve()
            if resolved.is_relative_to(store.DATA.resolve()):
                resolved.unlink(missing_ok=True)
    except Exception as error:
        for path in thumbnail_paths:
            path.unlink(missing_ok=True)
        store.update_recording(recording_id, status="failed", message=str(error)[:500])
    finally:
        if cap is not None:
            cap.release()
        with LOCK:
            ACTIVE.discard(recording_id)


def observation_time(recording_start, offset):
    if not recording_start:
        minutes, seconds = divmod(float(offset), 60)
        return f"{int(minutes):02d}:{seconds:05.2f} into recording"
    return (datetime.fromisoformat(recording_start) + timedelta(seconds=offset)).isoformat(timespec="seconds")


def refresh_quality(recording_id):
    row = store.query("SELECT * FROM recordings WHERE id=? AND status='complete'",(recording_id,))
    if not row:
        return 0
    tracks = store.query("SELECT * FROM tracks WHERE recording_id=?",(recording_id,))
    by_local = {track["local_id"]:{"source":track} for track in tracks}
    cap = cv2.VideoCapture(row[0]["path"])
    engine = identity.FaceEngine()
    try:
        detections = store.query("SELECT * FROM detections WHERE recording_id=? ORDER BY offset",(recording_id,))
        for sample in detections:
            cap.set(cv2.CAP_PROP_POS_MSEC,sample["offset"]*1000)
            ok,frame = cap.read()
            if not ok or sample["local_id"] not in by_local:
                continue
            track = by_local[sample["local_id"]]
            face_box = quality.gather(track,frame,json.loads(sample["box"]),sample["offset"],engine)
            store.execute("UPDATE detections SET face_box=? WHERE recording_id=? AND local_id=? AND offset=?",
                          (json.dumps(face_box) if face_box else None,recording_id,sample["local_id"],sample["offset"]))
        updated = 0
        for track in by_local.values():
            if "thumbnail" not in track:
                continue
            source = track["source"]
            cv2.imwrite(source["thumbnail"],track["thumbnail"],[cv2.IMWRITE_JPEG_QUALITY,96])
            store.execute("UPDATE tracks SET face_embeddings=?,crop_sharpness=?,thumbnail_offset=?,quality_status=? WHERE id=?",
                (json.dumps(track.get("face_embeddings",[])),track["crop_sharpness"],track["thumbnail_offset"],track["quality_status"],source["id"]))
            updated += 1
        with store.connect() as db:
            store.audit(db,"quality_agent_refresh",recording_id,{"tracks_refreshed":updated,"face_model":identity.VERSION,"source_resolution":"native"})
        return updated
    finally:
        cap.release()

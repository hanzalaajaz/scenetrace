from datetime import datetime
from io import BytesIO
from pathlib import Path
import json

import cv2
import numpy as np
import pytest

from scenetrace import service, store, vision


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "DATA", tmp_path / "data")
    store.init()
    return store.DATA


def textured(seed=10):
    image = np.random.default_rng(seed).integers(0, 256, (360, 640, 3), dtype=np.uint8)
    return cv2.GaussianBlur(image, (3, 3), 0)


def clip(path, image=None):
    image = textured() if image is None else image
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (640, 360))
    assert writer.isOpened()
    for _ in range(12):
        writer.write(image)
    writer.release()
    return path


def upload(path):
    result = BytesIO(path.read_bytes())
    result.name = path.name
    return result


def test_scene_recognizes_saved_view_and_rejects_unknown(workspace):
    path = workspace / "reference.npz"
    frame = textured()
    vision.save_reference([frame], path)
    references = [{"location_id": "entrance", "features_path": str(path)}]
    known = vision.recognize([frame, frame, frame], references)
    assert known["status"] == "recognized"
    assert known["location_id"] == "entrance"
    unknown = vision.recognize([textured(55)], references)
    assert unknown["status"] == "unknown"
    assert unknown["location_id"] is None


def test_similar_location_candidates_do_not_force_match(workspace):
    path = workspace / "reference.npz"
    frame = textured()
    vision.save_reference([frame], path)
    result = vision.recognize([frame], [
        {"location_id": "room_a", "features_path": str(path)},
        {"location_id": "room_b", "features_path": str(path)}])
    assert result["status"] == "uncertain"
    assert result["location_id"] is None


def test_register_persists_and_discards_reference_source(workspace):
    path = clip(workspace / "source.avi")
    location_id = service.register_reference(upload(path), "Entrance", "CAM-01")
    assert store.query("SELECT label FROM locations WHERE id=?", (location_id,))[0]["label"] == "Entrance"
    reference = store.query("SELECT * FROM reference_views")[0]
    assert Path(reference["features_path"]).exists()
    assert len(list((workspace / "references").glob("*.avi"))) == 0
    with pytest.raises(ValueError, match="already saved"):
        service.register_reference(upload(path), "entrance", "CAM-02")


def test_invalid_upload_does_not_create_records(workspace):
    invalid = BytesIO(b"this is not a real video")
    invalid.name = "video.mp4"
    with pytest.raises(ValueError):
        service.add_recording(invalid)
    assert not store.query("SELECT * FROM recordings")
    assert not list((workspace / "videos").iterdir())


def seed_recording(path, recording_id="r1", status="queued"):
    store.execute("INSERT INTO recordings(id,filename,path,sha256,status) VALUES(?,?,?,?,?)",
                  (recording_id, path.name, str(path), recording_id, status))


def seed_track(workspace, track_id="t1", person_id="p1", first=1, last=3):
    store.execute("INSERT OR IGNORE INTO people(id,label) VALUES(?,?)", (person_id, person_id))
    thumbnail = workspace / "thumbnails" / f"{track_id}.jpg"
    cv2.imwrite(str(thumbnail), textured())
    store.execute("""INSERT INTO tracks(id,recording_id,local_id,person_id,first_seen,last_seen,
        thumbnail,appearance,sample_count) VALUES(?,?,?,?,?,?,?,?,?)""",
        (track_id, "r1", len(store.query("SELECT id FROM tracks")) + 1, person_id, first, last, str(thumbnail), "[]", 3))


def test_review_overlap_guard_split_and_audit(workspace):
    seed_recording(clip(workspace / "video.avi"), status="complete")
    seed_track(workspace)
    seed_track(workspace, "t2", "p2", 2, 4)
    with pytest.raises(ValueError, match="overlapping"):
        store.review("t1", "p2")
    store.execute("UPDATE tracks SET first_seen=5,last_seen=6 WHERE id='t2'")
    store.review("t1", "p2")
    assert store.query("SELECT person_id FROM tracks WHERE id='t1'")[0]["person_id"] == "p2"
    store.split_track("t1")
    result = store.query("SELECT * FROM tracks WHERE id='t1'")[0]
    assert result["person_id"] != "p2"
    assert result["match_status"] == "provisional"
    assert len(store.query("SELECT * FROM audit WHERE action<>'replace_clothing_matcher'")) == 2


def test_location_correction_and_recording_deletion(workspace):
    source = clip(workspace / "videos" / "video.avi")
    seed_recording(source, status="complete")
    seed_track(workspace)
    thumbnail = Path(store.query("SELECT thumbnail FROM tracks")[0]["thumbnail"])
    store.execute("INSERT INTO locations(id,label,camera_label) VALUES('loc1','Room','CAM-01')")
    store.assign_location("r1", "loc1")
    assert store.query("SELECT location_status FROM recordings")[0]["location_status"] == "confirmed"
    store.delete_recording("r1")
    assert not source.exists() and not thumbnail.exists()
    assert not store.query("SELECT * FROM tracks")
    assert store.query("SELECT * FROM locations")
    assert len(store.query("SELECT * FROM audit WHERE action<>'replace_clothing_matcher'")) == 2


def test_pipeline_real_scene_matching_with_controlled_detections(workspace, monkeypatch):
    frame = textured()
    reference_source = clip(workspace / "ref.avi", frame)
    location_id = service.register_reference(upload(reference_source), "Entrance", "CAM-01")
    source = clip(workspace / "videos" / "recording.avi", frame)
    seed_recording(source)
    monkeypatch.setattr(vision.PedestrianDetector, "detect", lambda self, frame: [(100, 50, 70, 160)])
    service.process("r1")
    row = store.query("SELECT * FROM recordings")[0]
    assert row["status"] == "complete", row["message"]
    assert row["location_id"] == location_id
    tracks = store.query("SELECT * FROM tracks")
    assert len(tracks) == 1
    assert tracks[0]["first_seen"] <= tracks[0]["last_seen"]
    assert tracks[0]["match_status"] == "provisional"
    assert Path(tracks[0]["thumbnail"]).exists()
    assert tracks[0]["person_id"].startswith("P-")
    assert store.query("SELECT label FROM people")[0]["label"] == "Person 0001"
    samples = store.query("SELECT * FROM detections")
    assert len(samples) == tracks[0]["sample_count"]
    assert all(0 <= value <= 1 for value in json.loads(samples[0]["box"]))


def test_time_offsets_are_not_upload_dates():
    assert service.observation_time(None, 83.4) == "01:23.40 into recording"
    assert service.observation_time("2026-10-29T09:00:00+05:00", 83.4) == "2026-10-29T09:01:23+05:00"


def test_tracking_gap_creates_new_local_track():
    frame = textured()
    tracker = vision.TrackManager(max_gap=1)
    assert tracker.update([(10, 10, 80, 160)], 0, frame)[0]["local_id"] == 1
    assert tracker.update([(12, 10, 80, 160)], .2, frame)[0]["local_id"] == 1
    assert tracker.update([(12, 10, 80, 160)], 3, frame)[0]["local_id"] == 2


def test_restart_marks_pending_work_retryable(workspace):
    seed_recording(workspace / "video.avi", status="processing")
    service.recover_interrupted_jobs()
    assert store.query("SELECT status FROM recordings")[0]["status"] == "interrupted"


def test_api_workspace_and_persistent_results(workspace):
    from fastapi.testclient import TestClient
    from scenetrace.api import app
    source = clip(workspace / "videos" / "source.avi")
    seed_recording(source, status="complete")
    seed_track(workspace)
    with TestClient(app) as client:
        assert client.get("/").status_code == 200
        assert client.get("/api/health").json()["status"] == "ok"
        assert client.get("/api/overview").json()["people"] == 1
        assert "path" not in client.get("/api/recordings/r1").json()
        assert len(client.get("/api/recordings/r1").json()["tracks"]) == 1
        assert client.get("/api/tracks/t1/thumbnail").status_code == 200
        assert client.get("/api/recordings/r1/media", headers={"Range": "bytes=0-99"}).status_code == 206
        assert len(client.get("/api/reviews").json()) == 1
        assert client.post("/api/tracks/t1/review", json={"action": "keep"}).status_code == 200
        assert not client.get("/api/reviews").json()
        timeline = client.get("/api/people/p1").json()["observations"]
        assert timeline[0]["first_observed"].endswith("into recording")
        assert client.get("/api/people/p1/export").headers["content-type"].startswith("text/csv")
    with TestClient(app) as client:
        assert client.get("/api/recordings/r1").json()["tracks"][0]["match_status"] == "confirmed"


def test_api_rejects_invalid_input_and_cross_origin_mutation(workspace):
    from fastapi.testclient import TestClient
    from scenetrace.api import app
    with TestClient(app) as client:
        invalid = client.post("/api/recordings", files={"file": ("bad.mp4", b"invalid")})
        assert invalid.status_code == 400
        naive_time = client.post("/api/recordings", files={"file": ("bad.mp4", b"invalid")}, data={"recorded_at": "2026-10-29T10:00:00"})
        assert naive_time.status_code == 400
        cross_origin = client.post("/api/recordings", headers={"Origin": "https://example.com"})
        assert cross_origin.status_code == 403
        assert client.get("/api/recordings/missing").status_code == 404


def test_person_id_and_photo_search_return_source_evidence(workspace, monkeypatch):
    from fastapi.testclient import TestClient
    from scenetrace.api import app
    source = clip(workspace / "videos" / "source.avi")
    seed_recording(source, status="complete")
    seed_track(workspace)
    red = np.zeros((160, 80, 3), dtype=np.uint8)
    red[:, :] = (0, 0, 220)
    vector = vision.person_appearance(red)
    from scenetrace.identity import FaceEngine
    monkeypatch.setattr(FaceEngine,"describe",lambda self,image,min_size=40:{"feature":[1.,0.],"reason":"test face","box":None,"quality":100})
    store.execute("UPDATE tracks SET face_embeddings=? WHERE id='t1'", (json.dumps([{"feature":[1.,0.],"model":"yunet-sface-quality-v2"}]),))
    store.execute("UPDATE tracks SET appearance=? WHERE id='t1'", (json.dumps(vector.tolist()),))
    ok, encoded = cv2.imencode(".png", red)
    assert ok
    with TestClient(app) as client:
        result = client.get("/api/search/people", params={"q": "P1"}).json()["matches"]
        assert len(result) == 1
        assert result[0]["recording_id"] == "r1"
        assert result[0]["first_observed"].endswith("into recording")
        assert not client.get("/api/search/people?q=missing").json()["matches"]
        photo = client.post("/api/search/photo", files={"file": ("person.png", encoded.tobytes(), "image/png")})
        assert photo.status_code == 200
        response = photo.json()
        assert response["identity_verified"] is False
        assert response["matches"][0]["person_id"] == "p1"
        assert response["matches"][0]["similarity"] > .99
        assert "appearance" not in response["matches"][0]
        invalid = client.post("/api/search/photo", files={"file": ("bad.png", b"not an image")})
        assert invalid.status_code == 400


def test_agent_recheck_resolves_unknown_but_preserves_confirmed(workspace):
    from scenetrace import agents
    frame = textured()
    source = clip(workspace / "videos" / "source.avi", frame)
    service.register_reference(upload(source), "Entrance", "CAM-01")
    seed_recording(source, status="complete")
    seed_recording(source, recording_id="r2", status="complete")
    store.execute("INSERT INTO locations(id,label,camera_label) VALUES('manual','Other room','CAM-02')")
    store.assign_location("r2", "manual")
    store.execute("INSERT INTO agent_runs(id,kind,status) VALUES('a1','location_recheck','queued')")
    agents.recheck("a1", "test")
    assert store.query("SELECT location_status FROM recordings WHERE id='r1'")[0]["location_status"] == "recognized"
    assert store.query("SELECT location_id FROM recordings WHERE id='r2'")[0]["location_id"] == "manual"
    assert store.query("SELECT status FROM agent_runs WHERE id='a1'")[0]["status"] == "complete"


def test_agent_settings_persist_and_resume_is_bounded(workspace, monkeypatch):
    from scenetrace import agents
    from fastapi.testclient import TestClient
    from scenetrace.api import app
    seed_recording(workspace / "video.avi", status="processing")
    resumed = []
    monkeypatch.setattr(service, "submit", resumed.append)
    agents.recover()
    assert resumed == ["r1"]
    agents.recover()
    assert resumed == ["r1"]
    with TestClient(app) as client:
        assert client.patch("/api/agents/settings", json={"auto_recheck": False, "auto_resume": False}).status_code == 200
        assert client.get("/api/agents").json()["settings"] == {"auto_recheck": False, "auto_resume": False}
    assert agents.settings()["auto_resume"] is False


def test_detector_rejects_nonperson_class_and_low_confidence():
    detector = vision.PedestrianDetector.__new__(vision.PedestrianDetector)
    detector.grid = np.zeros((3, 2))
    detector.strides = np.full((3, 1), 8)
    raw = np.zeros((3, 85), np.float32)
    raw[:, :4] = [10, 15, 2.2, 3]
    raw[:, 4] = .95
    raw[0, 5] = .3  # Person score below threshold.
    raw[1, 5] = .8
    raw[1, 6] = .99  # Highest class is not person.
    raw[2, 5] = .95  # Genuine person-class candidate.
    boxes = detector.decode(raw, 1, 640, 640)
    assert len(boxes) == 1
    assert detector.scores[0] > .8


def test_neural_detector_empty_image_does_not_assign_ids():
    if not vision.MODEL_PATH.exists():
        pytest.skip("Run setup_model.py to install the neural detector")
    detector = vision.PedestrianDetector()
    assert detector.detect(np.zeros((360, 640, 3), np.uint8)) == []


def test_reanalysis_replaces_only_provisional_results(workspace, monkeypatch):
    source = clip(workspace / "videos" / "source.avi")
    seed_recording(source, status="complete")
    seed_track(workspace)
    previous_thumbnail = Path(store.query("SELECT thumbnail FROM tracks WHERE id='t1'")[0]["thumbnail"])
    monkeypatch.setattr(vision.PedestrianDetector, "detect", lambda self, frame: [])
    service.process("r1", replace=True)
    assert store.query("SELECT status FROM recordings")[0]["status"] == "complete"
    assert not store.query("SELECT * FROM tracks")
    assert not previous_thumbnail.exists()
    seed_track(workspace, "reviewed", "reviewed-person")
    store.review("reviewed")
    service.process("r1", replace=True)
    assert store.query("SELECT id FROM tracks")[0]["id"] == "reviewed"
    assert "reviewed" in store.query("SELECT message FROM recordings")[0]["message"]


def test_recording_scoped_photo_search_and_captured_frames(workspace, monkeypatch):
    from fastapi.testclient import TestClient
    from scenetrace.api import app
    source = clip(workspace / "videos" / "source.avi")
    seed_recording(source, status="complete")
    seed_recording(source, recording_id="r2", status="complete")
    seed_track(workspace)
    store.update_recording("r1", duration=1.2)
    crop = cv2.imread(store.query("SELECT thumbnail FROM tracks")[0]["thumbnail"])
    appearance = vision.person_appearance(crop)
    store.execute("UPDATE tracks SET appearance=? WHERE id='t1'", (json.dumps(appearance.tolist()),))
    store.execute("INSERT INTO detections(recording_id,local_id,offset,box,confidence) VALUES('r1',1,1.0,'[0.1,0.1,0.2,0.5]',0.9)")
    from scenetrace.identity import FaceEngine
    monkeypatch.setattr(FaceEngine,"describe",lambda self,image,min_size=40:{"feature":[1.,0.],"reason":"test face","box":None,"quality":100})
    store.execute("UPDATE tracks SET face_embeddings=? WHERE id='t1'",(json.dumps([{"feature":[1.,0.],"model":"yunet-sface-quality-v2"}]),))
    monkeypatch.setattr(vision.PedestrianDetector, "detect", lambda self, frame: [])
    _, encoded = cv2.imencode('.png',crop)
    with TestClient(app) as client:
        match = client.post('/api/search/photo', files={'file':('person.png',encoded.tobytes())},data={'recording_id':'r1'})
        assert len(match.json()['matches']) == 1
        other = client.post('/api/search/photo', files={'file':('person.png',encoded.tobytes())},data={'recording_id':'r2'})
        assert other.json()['matches'] == []
        samples = client.get('/api/recordings/r1/detections').json()
        assert samples[0]['label'] == 'p1'
        assert samples[0]['box'] == [.1,.1,.2,.5]
        frame = client.get('/api/recordings/r1/frame?at=1')
        assert frame.status_code == 200
        assert frame.headers['content-type'].startswith('image/jpeg')
        assert client.get('/api/recordings/r1/frame?at=-1').status_code == 400


def test_color_only_or_blurred_photo_cannot_match_identity(workspace, monkeypatch):
    from scenetrace import identity,search
    source=clip(workspace/'videos'/'source.avi');seed_recording(source,status='complete');seed_track(workspace)
    image=np.full((160,100,3),130,np.uint8)
    store.execute("UPDATE tracks SET appearance=? WHERE id='t1'",(json.dumps(vision.person_appearance(image).tolist()),))
    monkeypatch.setattr(identity.FaceEngine,'describe',lambda self,image,min_size=40:{'feature':None,'reason':'Face is too blurred','box':None,'quality':0})
    _,encoded=cv2.imencode('.png',image)
    with pytest.raises(ValueError,match='blurred'):
        search.photo_matches(encoded.tobytes())
    assert identity.face_similarity([1,0],[{'feature':[0,1],'model':identity.VERSION}]) is None
    assert identity.face_similarity([1,0],[{'feature':[1,0],'model':'old-unsafe-model'}]) is None


def test_quality_agent_chooses_sharper_native_frame_and_keeps_original():
    from scenetrace import quality,identity
    class NoFace:
        def describe(self,image):return {'feature':None,'box':None,'quality':0}
    sharp=textured();blur=cv2.GaussianBlur(sharp,(25,25),10)
    track={}
    quality.gather(track,blur,[0,0,1,1],0,NoFace())
    quality.gather(track,sharp,[0,0,1,1],1,NoFace())
    assert track['thumbnail_offset']==1
    assert track['thumbnail'].shape==sharp.shape
    before=track['thumbnail'].copy()
    enhanced=identity.enhance_preview(track['thumbnail'])
    assert enhanced.shape==before.shape
    assert np.array_equal(track['thumbnail'],before)


def test_confident_face_match_reuses_global_person_id(workspace,monkeypatch):
    from scenetrace import identity
    source=clip(workspace/'videos'/'source.avi')
    seed_recording(source,status='complete');seed_track(workspace)
    store.execute("UPDATE tracks SET face_embeddings=? WHERE id='t1'",(json.dumps([{'feature':[1.,0.],'model':identity.VERSION}]),))
    seed_recording(source,recording_id='r2')
    monkeypatch.setattr(vision.PedestrianDetector,'detect',lambda self,frame:[(100,50,70,160)])
    monkeypatch.setattr(identity.FaceEngine,'describe',lambda self,image,min_size=40:{'feature':[1.,0.],'box':None,'quality':100})
    service.process('r2')
    assert store.query("SELECT status FROM recordings WHERE id='r2'")[0]['status']=='complete'
    track=store.query("SELECT * FROM tracks WHERE recording_id='r2'")[0]
    assert track['person_id']=='p1' and track['match_status']=='automatic'
    assert len(store.query('SELECT * FROM people'))==1


def test_short_fragments_are_not_assigned_person_ids(workspace,monkeypatch):
    source=clip(workspace/'videos'/'source.avi');seed_recording(source)
    calls=[]
    def brief_detection(self,frame):
        calls.append(1)
        return [(100,50,70,160)] if len(calls)<=2 else []
    monkeypatch.setattr(vision.PedestrianDetector,'detect',brief_detection)
    service.process('r1')
    assert store.query('SELECT status FROM recordings')[0]['status']=='complete'
    assert not store.query('SELECT * FROM tracks')


def test_tiny_handle_sized_boxes_do_not_get_person_ids():
    detector=vision.PedestrianDetector.__new__(vision.PedestrianDetector)
    detector.grid=np.zeros((1,2));detector.strides=np.full((1,1),8)
    raw=np.zeros((1,85),np.float32);raw[0,:4]=[10,10,.5,1.4];raw[0,4]=.99;raw[0,5]=.99
    assert detector.decode(raw,1,640,640)==[]


def test_tracked_video_export_is_playable_and_deleted_with_source(workspace):
    from scenetrace import video_export
    source=clip(workspace/'videos'/'source.avi');seed_recording(source,status='complete');seed_track(workspace)
    store.update_recording('r1',duration=1.2)
    store.execute("UPDATE tracks SET first_seen=.2,last_seen=.8 WHERE id='t1'")
    store.execute("INSERT INTO detections(recording_id,local_id,offset,box,confidence) VALUES('r1',1,.5,'[0.1,0.1,0.2,0.5]',.9)")
    target=workspace/'exports'/'test.mp4'
    store.execute("INSERT INTO exports(id,person_id,status,path) VALUES('e1','p1','queued',?)",(str(target),))
    store.execute("INSERT INTO export_sources VALUES('e1','r1')")
    video_export.build('e1')
    result=store.query("SELECT * FROM exports WHERE id='e1'")[0]
    assert result['status']=='complete',result['message']
    cap=cv2.VideoCapture(str(target));ok,frame=cap.read();cap.release()
    assert ok and frame.shape[:2]==(540,960)
    store.delete_recording('r1')
    assert not target.exists() and not store.query('SELECT * FROM exports')


def test_teaching_additional_angle_preserves_saved_label(workspace,monkeypatch):
    from fastapi.testclient import TestClient
    from scenetrace.api import app
    from scenetrace import agents
    source=clip(workspace/'videos'/'source.avi');seed_recording(source,status='complete')
    store.execute("INSERT INTO locations(id,label,camera_label) VALUES('loc1','Room','CAM-01')")
    monkeypatch.setattr(agents,'queue_recheck',lambda reason='manual':None)
    with TestClient(app) as client:
        response=client.post('/api/recordings/r1/teach-location',json={'location_id':'loc1'})
        assert response.status_code==200,response.text
        assert client.get('/api/recordings/r1').json()['location_status']=='confirmed'
    assert store.query('SELECT label FROM locations')[0]['label']=='Room'
    assert store.query('SELECT location_id FROM reference_views')[0]['location_id']=='loc1'


def test_face_only_video_still_creates_a_track(workspace,monkeypatch):
    from scenetrace import identity
    source=clip(workspace/'videos'/'source.avi');seed_recording(source)
    monkeypatch.setattr(vision.PedestrianDetector,'detect',lambda self,frame:[])
    face=np.array([50,50,60,80,65,75,95,75,80,90,68,110,92,110,.99],dtype=np.float32)
    monkeypatch.setattr(identity.FaceEngine,'detect',lambda self,image,min_size=24:[face])
    monkeypatch.setattr(identity.FaceEngine,'describe',lambda self,image,min_size=40:{'feature':None,'box':None,'quality':0,'reason':'test'})
    service.process('r1')
    assert store.query('SELECT status FROM recordings')[0]['status']=='complete'
    assert len(store.query('SELECT * FROM tracks'))==1
    assert store.query('SELECT face_box FROM detections')[0]['face_box'] is not None


def test_reanalysis_preserves_id_for_same_observation_geometry(workspace,monkeypatch):
    from scenetrace import identity
    source=clip(workspace/'videos'/'source.avi');seed_recording(source)
    monkeypatch.setattr(vision.PedestrianDetector,'detect',lambda self,frame:[(100,50,70,160)])
    monkeypatch.setattr(identity.FaceEngine,'detect',lambda self,image,min_size=24:[])
    service.process('r1')
    person_id=store.query('SELECT person_id FROM tracks')[0]['person_id']
    service.process('r1',replace=True)
    assert store.query('SELECT person_id FROM tracks')[0]['person_id']==person_id


def test_face_to_body_handoff_keeps_local_id():
    tracker=vision.TrackManager();frame=textured()
    face=(100,50,30,40)
    first=tracker.update([face],0,frame,face_only={face})[0]['local_id']
    body=(80,30,90,250)
    assert tracker.update([body],.2,frame)[0]['local_id']==first


def test_frontend_javascript_parses_without_syntax_errors():
    from tree_sitter import Language,Parser
    import tree_sitter_javascript
    parser=Parser(Language(tree_sitter_javascript.language()))
    source=(store.ROOT/'frontend'/'app.js').read_bytes()
    tree=parser.parse(source)
    assert not tree.root_node.has_error,'Frontend JavaScript contains a parse error'


def test_double_click_launcher_reuses_existing_server(monkeypatch):
    import launcher
    opened=[]
    monkeypatch.setattr(launcher,'server_running',lambda:True)
    monkeypatch.setattr(launcher.webbrowser,'open',lambda url,new=0:opened.append(url))
    monkeypatch.setattr(launcher,'prepare_environment',lambda:pytest.fail('Existing servers must not run setup again'))
    assert launcher.main(['--no-browser'])==0
    assert not opened
    assert launcher.main([])==0
    assert opened==[launcher.URL]


def test_double_click_launcher_refuses_unrelated_occupied_port(monkeypatch):
    import launcher
    monkeypatch.setattr(launcher,'server_running',lambda:False)
    monkeypatch.setattr(launcher,'port_occupied',lambda:True)
    with pytest.raises(RuntimeError,match='another application'):
        launcher.main(['--no-browser'])

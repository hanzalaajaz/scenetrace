# SceneTrace — Complete Explanation of the Implemented Project

**Status:** local working prototype. **Document date:** 29 October 2026.

This document describes work already implemented. Planned capabilities and validation gaps are listed separately. The research abstract and literature review are in [RESEARCH_ABSTRACT_LITERATURE_REVIEW.md](RESEARCH_ABSTRACT_LITERATURE_REVIEW.md).

## 1. Project purpose

SceneTrace organizes observations of people across uploaded camera recordings. It detects people and faces, maintains local tracks, compares usable face evidence with a shared person gallery, and builds a record of where and when each associated appearance was observed.

The intended journey is:

```text
Person 0001
  -> Camera 1 / entrance / observation time
  -> Camera 2 / outside / observation time
  -> Camera 3 / room entrance / observation time
```

This is an illustration, not an assertion that those observations exist in the current database. Recorded observations establish last-seen evidence, not somebody's exact present location.

The project works with uploaded videos. Physical campus cameras, CCTV access, and direct camera-to-camera communication are not required. Each recording worker consults the same local database and person gallery.

## 2. What is implemented

| Area | Implemented capability |
|---|---|
| Interface | Custom browser application on localhost; no Streamlit |
| Location setup | Labeled reference videos, multiple views per location, reference previews, location rename |
| View matching | Multi-frame ORB/SIFT matching with geometric verification and an unknown state |
| Additional angles | Teach an existing recording's view to a saved location |
| Video input | Upload validation, decoding, duplicate-file detection, processing progress |
| Detection | Person-only YOLOX-S plus YuNet face detection |
| Tracking | Motion-assisted local box association and face/body handoff logic |
| Identity gallery | Readable person labels, face descriptors, supported global-ID reuse |
| Evidence | Native-resolution crops, sharpness selection, face-quality checks |
| Playback | Person and face boxes synchronized with sampled observation times |
| Search | Person/track ID search; clear-face photo search in selected or all analyzed recordings |
| New-video search | Analyze a newly supplied recording before running the photo comparison |
| Histories | Captured images, location/camera, observation intervals, source links |
| Corrections | Confirm/reject candidate associations, manual grouping, split mistaken groups, audited changes |
| Reports | CSV history export and playable H.264 tracked-person highlight videos |
| Automation | Serial processing queue, location rechecks, quality refresh, limited interrupted-job recovery |
| Deletion | Recording removal with dependent observations, crops, and derived tracked videos |

## 3. Technology stack and architecture

| Layer | Current implementation |
|---|---|
| Frontend | HTML, CSS, JavaScript |
| Backend | Python and FastAPI |
| Server | Uvicorn, bound to 127.0.0.1:8000 |
| Database | SQLite |
| Media and features | Managed files under data/ |
| Computer vision | OpenCV DNN, image processing, ORB/SIFT |
| Array processing | NumPy |
| Image decoding | Pillow |
| Video export | FFmpeg supplied through imageio-ffmpeg |
| Processing execution | One background ThreadPoolExecutor worker |
| Tests | pytest, FastAPI test client, generated media, JavaScript syntax parsing |

```text
Browser interface
       |
Local FastAPI application
       |
Background processing controller
       |
View recognition -> body/face detection -> local tracking
       |
Quality checks -> face descriptors -> global person association
       |
SQLite + source videos + reference features + captured crops
       |
Histories / photo search / correction tools / tracked-video exports
```

Models run locally through OpenCV. GPU execution is not configured in this implementation.

## 4. Models, datasets, and what "training" means

| Task | Model or algorithm | Dataset/reference relationship |
|---|---|---|
| Person detection | YOLOX-S | Uses the downloaded pretrained COCO detector; only the person class is retained |
| Face detection | YuNet | The original YuNet training project documents WIDER Face |
| Face comparison | MobileFaceNet with SFace loss | Uses a pretrained OpenCV Zoo checkpoint |
| Location matching | ORB and SIFT | Uses features extracted from the user's labeled reference videos |
| Local tracking | Custom motion-assisted overlap association | No independently trained tracking model |

The original SFace research reports experiments on CASIA-WebFace, VGGFace2, and MS-Celeb-1M. The exact training-data mixture for our downloaded checkpoint has not been established from its model documentation. It should not be described as definitively trained on all those datasets.

The application downloads model weights, not the complete original training datasets. It does not currently retrain YOLOX, YuNet, or SFace on the user's recordings.

The menu named **Train locations** registers reference features and labels. It does not run neural-network backpropagation. Likewise, adding face examples updates a retrieval gallery rather than retraining the face network.

The model downloader checks SHA256 values. Model origins and licenses are documented in [models/ATTRIBUTION.md](models/ATTRIBUTION.md).

## 5. Location registration and recognition

### Registration

1. The user supplies a reference video, location name, and camera/view label.
2. OpenCV samples up to nine frames across the clip.
3. ORB and SIFT extract local keypoints and descriptors.
4. Descriptors, a preview image, and the location association are saved.
5. Temporary reference-video copies are removed after feature extraction; the extracted features and preview persist.

Several reference sets can share a location. This supports different learned angles or lighting conditions.

### Recognition on later uploads

1. Sample frames from the new recording.
2. Compare their descriptors with stored reference descriptors.
3. Use geometric verification to reject inconsistent feature matches.
4. Aggregate evidence across frames and rank saved locations.
5. Assign a view only when its score, frame support, and separation from alternatives satisfy the current thresholds.

The outcomes are recognized, uncertain, or unknown. Human-confirmed assignments are preserved by automatic rechecks.

The system recognizes visual viewpoints. It cannot know that an unseen grey wall is named OUTSIDE merely because an OUTSIDE label exists. **Teach this angle** lets the user connect that angle to the existing label once and reuse it later. This capability was used to register additional OUTSIDE/CAM2 views in the local demonstration.

## 6. Uploading and processing a recording

Uploads are checked for supported file extensions, size, and actual decoding. A content hash detects exact duplicate files. Managed storage filenames are generated internally rather than derived from user-supplied paths.

The prototype accepts nonempty supported recordings up to 250 MB and rejects recordings longer than one hour. Browser playback and OpenCV decoding have different codec support; H.264 MP4 is the preferred playback format.

Source frames are decoded, while inference samples roughly five frames per second depending on frame rate. Observation offsets come from decoder timestamps where available, with a frame-rate fallback when the codec does not provide usable timestamps.

Processing runs outside the request/UI path. Persisted progress and error messages let the browser show queued, processing, completed, failed, or interrupted work.

## 7. Person detection and face detection

YOLOX-S predicts object classes and bounding boxes. Only person-class candidates are considered. Score filtering, nonmaximum suppression, minimum box dimensions, and sustained observations reduce false IDs on small background objects.

YuNet independently detects faces and facial landmarks. Faces outside existing body detections can provide face-only tracks. Faces inside a tracked body are associated with that observation.

The browser draws person boxes and face boxes using persisted normalized coordinates. Boxes represent sampled detection evidence; the system does not run detection on every playback frame.

Current conservative filtering reduces handle-like detections and very short fragments, but cannot eliminate all false positives. It can also miss distant, small, occluded, or briefly visible people.

## 8. Local tracks and global person IDs

A local track belongs to one recording. A global person group can contain supported appearances from several recordings.

Within a video, the custom tracker uses overlap, predicted movement, elapsed time, and face/body containment. It is not a complete ByteTrack, Deep SORT, or BoT-SORT implementation.

For global association, the worker compares clear face descriptors with the existing gallery. A strong match can reuse the existing person ID. A runner-up margin and same-recording overlap checks constrain automatic associations. Such decisions are labeled automatic and logged.

When no supported match exists, a provisional group is created. That does not establish that the observation belongs to a genuinely new real-world person. Users can correct or split groups.

Reanalysis compares observation geometry to preserve IDs for corresponding tracks in the same source. Reviewed associations are protected from automatic replacement.

## 9. Face evidence and photo matching

The face pipeline is:

```text
Face detection -> size/landmark/sharpness checks -> alignment
      -> SFace embedding -> normalized cosine comparison
```

The query photo must contain one usable face. Recorded face evidence must also pass quality checks. Missing, small, clipped, blurred, or unreliable faces are rejected for identity comparison.

The gallery retains up to three high-quality face examples per track, along with model version, source offset, and quality information. Comparisons exclude incompatible descriptor versions.

Photo search returns supported candidates from retained observations, including the captured image, person ID, recording, camera/location, source time, and similarity. It does not establish a name, intent, or other personal facts.

The old clothing-color identity matcher has been disabled. A similar shirt does not provide an identity fallback. If a person was missed by detection or their face was never usable, photo search may not find them.

## 10. Current thresholds and their meaning

| Check | Current rule |
|---|---|
| Person candidate | Model score at least 0.60, followed by size/NMS checks |
| Retained local track | At least three observations spanning at least 0.35 seconds |
| Face tracking candidate | YuNet score at least 0.90, with visible face-size filtering |
| Face evidence | Size, sharpness, pose/landmark, and clipping checks |
| Query photo face | Minimum face dimension of 64 pixels before other checks |
| Recorded identity face | Minimum face dimension of 40 pixels before other checks |
| Photo candidate | Best face cosine at least 0.60; additional saved examples must provide support when available |
| Automatic global association | Best face score at least 0.75 and margin of at least 0.12 when a competing group exists |
| Saved-view assignment | Median score, frame-support fraction, and competing-view margin |

These are implementation heuristics, not calibrated accuracy probabilities. A score of 0.75 must not be presented as a 75% probability that two observations belong to the same person. Thresholds need validation on held-out, representative footage.

## 11. Captures and image enhancement

The quality module considers sharpness, crop size, and usable face evidence when choosing representative images. Captures come from original-resolution video frames, avoiding unnecessary enlargement during storage.

Optional enhanced previews apply nonlocal-means denoising, local contrast adjustment, and mild unsharp masking. The original remains available. Enhanced previews are not used to manufacture identity evidence, and filters cannot recover detail absent from the source recording.

## 12. User workflow

1. **Train locations:** register labeled reference footage once; add views as needed.
2. **Analyze video:** upload footage and optionally supply its actual start date/time and UTC offset.
3. **Recordings:** inspect processing, location, boxes, IDs, and detected tracks.
4. **View appearances:** open captured images with camera/location and observation intervals.
5. **Find person:** provide a clear face photo and choose one recording, all analyzed recordings, or a new recording to process before searching.
6. **People:** inspect the shared-ID history and source evidence.
7. **Create tracked video:** generate an annotated highlight movie from that group's associated observations.
8. **Advanced corrections:** inspect uncertain candidates or correct grouping when necessary.

Normal search does not require the user to process a review queue first.

## 13. Time and location records

When the recording start is known:

```text
Absolute observation time = recording start + playback offset
```

When it is unknown, the application reports playback offsets and keeps undated recordings separate. Upload time and file modification time are not treated as recording time.

Locations are saved labels/view associations, not GPS coordinates. Missing coverage cannot reveal a person's path between cameras or establish their current whereabouts.

## 14. Tracked-video export

The exporter collects the selected person's associated observation intervals, orders dated observations where possible, reads source frames, and renders the person ID, boxes, camera/location, and source time.

FFmpeg encodes a 960x540 H.264 MP4 at 12 frames per second. The export omits audio and is limited to 600 seconds of observation excerpts. Undated recordings are not presented as a verified chronological journey.

The output is a compilation of associated evidence, not generated footage of unobserved travel. Source links and association quality remain important when interpreting it.

## 15. Agent-style automation

Implemented automation includes:

- Queuing uploaded recordings and updating progress.
- Rechecking unresolved locations after new references are supplied.
- Refreshing native-resolution evidence and face descriptors.
- Resuming eligible interrupted analysis once after restart.
- Rendering tracked-video exports.
- Recording automatic actions and manual corrections.

These are bounded background services. There is no LLM reasoning agent, and the application should not be described as a fully autonomous decision-making system.

## 16. Database and storage

| Record | Purpose |
|---|---|
| locations | Saved names and camera/view labels |
| reference_views | Descriptor and preview references |
| recordings | Source files, processing status, time basis, view assignment |
| tracks | Camera-local tracks, global group links, captures, face evidence |
| people | Persistent anonymous global labels |
| detections | Source offsets, person boxes, face boxes, detection scores |
| candidates | Proposed group associations and review state |
| audit | Automatic and manual decision history |
| agent_runs/settings | Task state and persistent automation settings |
| exports/export_sources | Generated-video state and source provenance |

The database and media remain in the local data/ folder. Face descriptors are excluded from public API response objects but are stored in the local database. The prototype does not encrypt the database or provide a complete multi-user authentication system.

Query images are processed in memory by the current photo-search path. Newly uploaded recordings are retained as managed recording sources. Use footage and images you are permitted to process.

## 17. Deletion behavior

Delete recording is visible in the library and recording detail. It removes the source, dependent tracks/detections, associated thumbnails, and derived tracked videos that used that recording. Shared person groups with other observations remain as appropriate. Reference assets are separate and remain saved.

Active processing or export jobs must finish before their source can be deleted. Deletion is confirmed in the interface and recorded in the audit trail.

## 18. Code organization

```text
app.py                         Local server entry point
launcher.py                    Automatic setup/startup helper
run.bat                        Double-click Windows launcher
setup_model.py                 Model download and checksum checks
frontend/                      Browser pages, styling, and interactions
scenetrace/api.py              HTTP routes and application lifecycle
scenetrace/vision.py           View descriptors, person detection, tracking
scenetrace/identity.py         Face detection, quality gates, embeddings
scenetrace/quality.py          Native-resolution evidence selection
scenetrace/search.py           Face-photo candidate retrieval
scenetrace/service.py          Recording-processing pipeline
scenetrace/agents.py           Background automation and recovery
scenetrace/video_export.py     Tracked-video rendering
scenetrace/store.py            Database schema, persistence, corrections
models/ATTRIBUTION.md          Model sources and license information
tests/test_workspace.py        Functional and source-validation checks
```

## 19. Running and verification

On Windows, double-click **run.bat** after installing Python 3.11 or newer. The launcher handles the local environment, requirements, model checks, server startup, and opening the browser. First setup needs internet access.

Manual startup is also available:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_model.py
.\.venv\Scripts\python.exe app.py
```

Open http://127.0.0.1:8000. The server binds to localhost.

Development tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

At the documented checkpoint, 32 checks passed, including launcher reuse and occupied-port behavior. Coverage includes scene rejection, extra-view teaching, ID persistence, controlled global-ID matching, face-only tracks, false small-object rejection, native evidence selection, photo rejection, deletion, playable exports, and JavaScript syntax parsing.

Several identity tests use controlled descriptors to test software behavior. They do not establish real-world recognition accuracy. Automated browser visual/click testing remained blocked by the browser origin permission policy, so it must not be reported as completed.

## 20. Work not completed

- Evaluated learned body re-identification when faces are unavailable.
- A stronger established multi-object tracker and crowded-scene evaluation.
- Held-out benchmarks for detection, face matching, ID switches, and view recognition.
- Multi-view clip segmentation and foreground masking for reference extraction.
- Live webcam sessions or real-time CCTV/RTSP integration.
- Full reference deletion/retention administration, authenticated multi-user access, and encryption at rest.
- Complete browser accessibility, navigation, and playback QA.

The implemented system is a prototype supporting the intended workflow with explicit evidence and uncertainty. It is not a guarantee that every person is detected, every camera handoff is correctly linked, or every unfamiliar view is recognized.

## 21. Documentation and primary sources

- [Current project scope](PROJECT.md)
- [Milestones and remaining work](MILESTONES.md)
- [Research abstract and literature review](RESEARCH_ABSTRACT_LITERATURE_REVIEW.md)
- [YOLOX original implementation](https://github.com/Megvii-BaseDetection/YOLOX)
- [YuNet original training project](https://github.com/ShiqiYu/libfacedetection.train)
- [OpenCV SFace model documentation](https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface)
- [SFace original research implementation](https://github.com/zhongyy/SFace)

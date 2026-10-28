# SceneTrace

**A local computer-vision workspace for finding people in camera recordings and building source-linked location histories.**

Register camera views once, upload recordings, and inspect person/face detections, captured appearances, shared person IDs, and camera-by-camera observations. Search with a clear face photo or a saved ID, then export the associated evidence as CSV or a tracked highlight video.

> Working prototype. Cross-camera identity matching depends on usable face evidence. Recognition accuracy has not been established on a representative benchmark. The application does not infer someone's exact current location.

## Start with a double-click

On Windows, install **Python 3.11 or newer**, then double-click **[run.bat](run.bat)**.

The launcher will:

1. Create a local `.venv` environment when needed.
2. Install or check the application requirements.
3. Download/check the three computer-vision models and verify their SHA256 values.
4. Start the local server and open the application in your browser.
5. Reuse an already-running SceneTrace server instead of starting a duplicate.

Open **http://127.0.0.1:8000** if the browser does not open automatically. Keep the server window open; press **Ctrl+C** there to stop it. First setup needs internet access and downloads approximately 75 MB of model weights in addition to Python packages. Later runs use the local files.

Python must already be installed. No Node.js, Docker, Streamlit, or cloud AI account is required.

## Typical workflow

1. **Train locations:** upload reference footage and enter its location and camera/view label. Several views can share a label.
2. **Analyze video:** upload a single-view recording. Add its actual recording start time and UTC offset if known.
3. **Recordings:** inspect progress, recognized location, person/face boxes, readable IDs, and captured appearances.
4. **Teach this angle:** when a different viewpoint is not recognized, save that recording as another reference for an existing location.
5. **Find person:** upload a clear face photo and choose one recording, all analyzed recordings, or a new recording to analyze first. ID search is also available.
6. **People:** open captured images and the group's source-linked camera/location/time history.
7. **Create tracked video:** generate a playable H.264 highlight video from that group's associated observations, or download its CSV history.

Advanced corrections support grouping, splitting, and reviewing uncertain connections. They are optional in the normal search flow.

## Implemented features

- Saved camera/location references with multi-frame ORB/SIFT matching and geometric verification.
- Person-only YOLOX-S detection and YuNet face detection, including face-only observations.
- Custom motion-assisted local tracking and face/body handoff logic.
- Quality-gated SFace comparison and supported reuse of global person IDs across recordings.
- Native-resolution captures selected using sharpness and usable face evidence.
- Original/enhanced preview comparison using denoising, contrast adjustment, and mild sharpening.
- Photo and ID search with captured results, camera/location, source times, and original-video links.
- Synchronized person and face boxes during playback.
- CSV histories and tracked-video exports with labels and source timestamps.
- Background processing, progress reporting, view rechecks, evidence refresh, and limited restart recovery.
- Persistent SQLite records, correction history, and recording deletion with dependent export cleanup.

Clothing-color-only identity matching is disabled. A similar shirt is not treated as evidence that two people share an identity. Enhanced previews do not change the original or supply matching evidence.

## How it works

```text
Labeled reference videos -> saved view features
                                   |
Uploaded recording -> automatic view recognition
                                   |
                    person + face detection
                                   |
                    local tracks + sharp captures
                                   |
              face comparison with shared person gallery
                                   |
              camera/location/time observations in SQLite
                                   |
          photo/ID search -> histories -> CSV / tracked video
```

Cameras do not directly message one another. Processing workers consult a common gallery. Strong supported matches may reuse an existing ID; unclear evidence stays provisional. A provisional ID is not proof of a new real-world person.

The controller automates bounded CV workflows. There is no LLM reasoning agent in this implementation.

## Technology

| Layer | Implementation |
|---|---|
| Interface | HTML, CSS, JavaScript |
| API/server | Python, FastAPI, Uvicorn |
| Detection/recognition | OpenCV DNN, YOLOX-S, YuNet, SFace |
| View matching | ORB, SIFT, geometric verification |
| Local tracking | Custom motion-assisted overlap association |
| Storage | SQLite and managed local media |
| Video export | FFmpeg via imageio-ffmpeg |
| Testing | pytest, API tests, generated clips, JavaScript parser |

Models run locally on CPU. See [model attribution](models/ATTRIBUTION.md) for sources, licenses, and checksums.

## Models and training data

- **YOLOX-S:** pretrained COCO detector, restricted to its person class.
- **YuNet:** associated with WIDER Face training/evaluation in the original project.
- **SFace/MobileFaceNet:** pretrained OpenCV checkpoint. The original research studies CASIA-WebFace, VGGFace2, and MS-Celeb-1M; the exact training mixture of the downloaded checkpoint is not established here.
- **Location references:** supplied by the user. "Train locations" registers reference features; it does not retrain a neural network.

Only pretrained weights are downloaded, not the full research datasets. No model is currently fine-tuned on uploaded recordings.

## Limits to understand

- Cross-camera linking currently relies on usable faces. Learned full-body re-identification when faces are unavailable remains future work.
- The custom tracker is not ByteTrack, Deep SORT, or BoT-SORT. Occlusion, crowds, and fast camera movement can cause misses, switches, or fragmented tracks.
- Conservative thresholds reduce small-object and brief-fragment false IDs but may miss distant or briefly visible people.
- The application recognizes reference viewpoints, not arbitrary locations or physical camera hardware. New angles may need an additional reference.
- Inference samples roughly five frames per second; it does not analyze every playback frame.
- Use continuous single-view videos up to **250 MB** and no longer than **one hour**. Edited multi-view videos are not segmented in this build.
- OpenCV decoding and browser codec support differ. H.264 MP4 is preferred for playback.
- Actual chronology requires a known recording start time. Unknown dates remain video offsets rather than upload timestamps.
- Tracked exports contain at most **ten minutes** of associated excerpts, use H.264 at 12 fps, omit audio, and do not invent travel through coverage gaps.
- Display filters cannot restore facial detail that was never recorded.
- Live webcam/RTSP integration and production multi-user administration are not implemented.

## Data and repository contents

Source code is separate from local data:

```text
frontend/                  Browser interface
scenetrace/                API, CV, storage, workers, and export modules
models/ATTRIBUTION.md       Model origins and licenses
app.py                     Server entry point
launcher.py                Automatic environment/startup helper
run.bat                    Double-click Windows launcher
setup_model.py             Verified model downloader
requirements*.txt          Runtime/development dependencies
PROJECT_EXPLAINED.md        Complete implementation explanation
RESEARCH_ABSTRACT_LITERATURE_REVIEW.md
MILESTONES.md               Delivery checklist and remaining work
tests/                     Regression checks
```

The repository excludes videos, query/evidence data, SQLite databases, face descriptors, model binaries, local environments, diagnostics, and local tooling. Each installation keeps its own files under `data/`.

The prototype stores local data without database encryption and has no complete multi-user authentication system. Keep it on localhost and use footage you are permitted to process. Face descriptors are not returned in public API response objects.

Recording deletion removes dependent observations, crops, and derived tracking videos; saved location-reference assets remain separate. Stop the app before backing up the entire `data/` folder.

## Developer setup

A manual setup is available if needed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe setup_model.py
.\.venv\Scripts\python.exe app.py
```

For a read-only launcher check:

```powershell
run.bat --check
```

Run regression checks:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
```

Tests verify selected software behaviors, including ID persistence, scene rejection, extra-view teaching, face-only tracking, quality selection, photo rejection, deletion, playable export, and JavaScript syntax. Controlled identity tests do not establish real-world recognition accuracy. Browser visual/click QA is not fully verified.

## Documentation

- [Complete project explanation](PROJECT_EXPLAINED.md)
- [250-word abstract and 250-word literature review](RESEARCH_ABSTRACT_LITERATURE_REVIEW.md)
- [Current scope](PROJECT.md)
- [Milestones](MILESTONES.md)
- [Model sources and third-party licenses](models/ATTRIBUTION.md)

The third-party model licenses do not determine the license of the project's application source. No application-source license has been selected in this repository.

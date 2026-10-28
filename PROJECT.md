# SceneTrace — cross-camera person history from videos

## Core idea

Register each camera/location view once. Upload camera recordings. Detect each visible person and face, maintain a camera-local track, and link supported appearances to a shared global person ID. Build a source-linked history showing camera, location, and observation time. A photo or ID search checks saved recordings, or first analyzes a newly uploaded recording, then returns matching captured evidence and a tracked highlight video.

Example: Person 0001 -> Camera 1 / entrance at 10:02 -> Camera 2 / corridor at 10:05 -> Camera 3 / room at 10:08. Actual clock times require a known recording start date, time, and UTC offset. Without them, show video playback offsets and keep different recordings' dates unknown.

Cameras do not need to message one another. Each processing worker uses the same local identity gallery and observation database. No campus CCTV access is required; uploaded video files are the primary input.

## Main menus

1. Analyze video: upload a camera recording and optionally supply its real recording start time.
2. Train locations: upload labeled reference views once; add multiple angles or lighting conditions per saved location.
3. Recordings: original playback with person/face boxes, readable IDs, captured appearances, reanalysis, and visible deletion controls.
4. People: shared-ID profiles, captured images, source-linked location timeline, CSV, and tracked-video generation.
5. Find person: clear face photo plus selected recording, all analyzed recordings, or a new video that is analyzed before searching. ID search is also available.
6. Agent center: processing activity, unresolved-view rechecks, quality refresh, and persistent automation settings.
7. Advanced corrections: inspect uncertain connections, correct groups, and split mistaken associations. This is not a mandatory step in the normal search flow.

## Recognition and ID rules

- Person detection uses official OpenCV Zoo YOLOX-S, restricted to the person class. Tiny detections, low-confidence candidates, and short fragments are filtered to reduce background-object IDs; this conservative filtering can miss small or briefly visible people.
- YuNet detects faces, including face-only appearances without a full body. A motion-assisted tracker associates consecutive observations. Face/body handoffs attempt to retain a local ID.
- Native-resolution crops are selected using sharpness and face quality. Originals remain available; optional denoising, contrast, and mild sharpening affect display only.
- Clear faces use SFace descriptors. Small, blurred, clipped, or uncertain faces do not supply identity evidence. Clothing-color-only identity matching is disabled.
- Strong returning-person face matches can reuse a global ID automatically, subject to a runner-up margin and overlap checks. The association is labeled automatic and can be corrected.
- Weak or unavailable evidence stays provisional. A provisional ID is not proof that somebody is a new real-world person. Cross-camera identity is not guaranteed when a face is unavailable; learned body re-identification remains future work.
- Reanalysis attempts to preserve IDs for the same observation geometry. Reviewed associations are protected. A corrected false detection is not kept merely to preserve an ID.
- Location recognition uses multi-frame ORB/SIFT and geometric verification. It recognizes learned viewpoints, not arbitrary physical locations or camera hardware. An unlearned angle may remain unassigned. Teach this angle adds that recording as another reference to an existing saved label and rechecks unresolved recordings.

## Search results

Photo search requires a clear single-person face photo and compares original evidence, not enhanced images. Results contain captured person crops, saved person ID, source recording, camera/location, observed interval, and face similarity. These are evidence-backed candidates, not proof of identity or a person's name. No result means no supported match, rather than proof that the person never appeared.

View appearances opens captured images and locations instead of autoplaying a video. Full history provides the chronological record where dates are known. A tracked-video export compiles associated observation intervals with boxes, ID, camera/location, and source times. It does not invent travel through camera gaps. Exports use H.264, omit audio, and are limited to ten minutes of selected observation intervals.

## CV and agent workflow

The local controller queues ingestion, view recognition, body/face detection, tracking, evidence selection, face matching, and result persistence. It can recheck unknown locations after references are added, refresh sharp crops/face evidence, resume interrupted video jobs once, and generate tracked-video exports. Tasks and corrections are logged. This is bounded workflow automation, not an LLM reasoning agent.

## Technical structure

- Browser: custom HTML/CSS/JavaScript interface, served on localhost; no Streamlit.
- API: FastAPI; one background processing executor.
- Storage: SQLite plus managed local media under data/.
- CV: OpenCV DNN (YOLOX-S), YuNet, SFace, ORB/SIFT, motion-assisted overlap association, quality scoring, conservative preview filtering.
- Video export: local FFmpeg encoder supplied by imageio-ffmpeg.
- Models: downloaded once from official OpenCV Zoo sources; setup_model.py checks SHA256 values. See models/ATTRIBUTION.md and the model license files.

Tracklets, global person groups, detections, face evidence, location references, export provenance, and audit entries are separate records. Face descriptors are excluded from API response objects. They are stored locally and are not encrypted in this prototype. Use recordings you are permitted to process.

## Remaining validation and scope

See MILESTONES.md. Test on consented footage with known camera labels and ground truth. Measure false detections, missed people/faces, ID switches, false cross-camera links, view assignment errors, and timestamp accuracy. Unit tests and checks on a few clips do not establish deployment accuracy.

Important remaining work: evaluated learned body re-identification for nonfrontal/no-face views, stronger multi-object tracking, multi-view clip segmentation, foreground masking for location matching, live webcam sessions, broader retention/reference deletion controls, and browser accessibility/playback QA. Do not advertise exact current location or guaranteed identity recognition.

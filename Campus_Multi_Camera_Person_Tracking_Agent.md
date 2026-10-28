> Current scope: see [PROJECT.md](PROJECT.md) and [MILESTONES.md](MILESTONES.md). They supersede the earlier delivery order below and include automatic view recognition and the requested custom browser interface.

# Video and Webcam Person Tracking Assistant

## 1. Project idea

Build a local application that detects and tracks people in uploaded videos or a live webcam feed. It draws bounding boxes and temporary IDs, counts visible people, and produces a timeline of events such as entering a user-defined area or crossing a line.

This project works with an ordinary webcam and recorded videos. Campus cameras, CCTV access, and a campus map are not required.

**Example:** upload a walking video, draw a counting line, run processing, and view annotated playback plus a table of crossing times. Then run the same detection and tracking pipeline on your webcam.

## 2. Goal and first deliverable

The first deliverable is a working demo with:

- Upload and playback of one recorded video.
- Live processing from a connected webcam.
- Person detection, bounding boxes, and temporary tracking IDs.
- Current visible-person count.
- A configurable line for counting directional crossings.
- A searchable event table and CSV export.
- Start, stop, and reset controls.

Track IDs describe observations within a processing session. They do not identify people by name and may change after long occlusion or leaving and returning.

## 3. Available inputs

### Recorded videos

Accept locally selected video files supported by the decoding backend. Validate each file and show a useful error when its format cannot be decoded.

Process one video first. Add a queue for several files later. Keep each file's tracks separate unless the user explicitly configures a related recording experiment.

A video's event timestamp is its playback offset, for example `00:01:23.400`. Do not assume the file creation time is the recording time. If a user supplies the recording start time, retain its source and timezone separately.

### Webcam

Let the user select an available webcam, start the preview, and stop capture. Show a clear active-camera indicator. Report unavailable devices and disconnections without crashing.

Use elapsed session time for event ordering and optionally record the actual capture time. Release the webcam when processing stops. Webcam frames need not be saved by default.

## 4. Core workflow

1. Select a video file or webcam.
2. Create a processing session with its own source ID.
3. Decode frames and preserve their source timing.
4. Detect people in each processed frame.
5. Track detections across frames and assign temporary IDs.
6. Draw boxes, IDs, the current count, and configured lines or zones.
7. Detect line crossings or zone entry/exit events.
8. Save event metadata and show it in the dashboard.
9. Stop processing, review results, and optionally export events or annotated video.

A detected person and a unique visitor are different concepts. Label counts precisely: visible people, crossing events, and distinct track IDs. Distinct track IDs are not a reliable count of unique real-world people.

## 5. Features and scope

### First version

- Single uploaded video or single webcam per active session.
- Person-only detection and per-source tracking.
- Live bounding boxes and temporary IDs.
- Current visible-person count.
- One user-drawn counting line with two directions.
- Event timeline containing source, track ID, event type, and time.
- CSV export and session deletion.

### Second version

- User-drawn polygon zones.
- Zone entry, exit, and observed time inside a zone.
- Saved session summaries and filtering by track ID or event type.
- Optional annotated-video export.
- Video processing progress, cancellation, and configurable processing rate.
- A batch queue for multiple independent videos.

Only calculate observed zone duration from available observations. Mark interrupted observations when tracking is lost rather than inventing an exit time.

### Optional advanced experiment

Use two related recorded videos, or record two views sequentially with volunteers, to study possible matches between sources. Sequential recordings demonstrate appearance matching, not a real simultaneous camera handoff. Do not present unrelated clips as a continuous journey.

Cross-source matching requires its own labeled evaluation, timing assumptions, and review interface. Keep possible matches provisional. It is not required to complete this project.

### Outside the initial scope

- Named-person identification or facial recognition.
- Campus-wide monitoring, CCTV integrations, or indoor positioning.
- Automatic conclusions about intent, suspicious behavior, or attendance.
- Guaranteed recovery of the same ID after a person leaves the frame.

## 6. Application design

Start with one local application and a background processing worker. The responsibilities below can be ordinary modules; separate autonomous AI agents are optional.

| Module | Responsibility |
|---|---|
| Source manager | Open uploaded files or a webcam, validate inputs, release resources |
| Detection module | Find people and return boxes and detection confidence |
| Tracking module | Maintain temporary IDs within the current source/session |
| Event module | Calculate counts, line crossings, and later zone events |
| Storage module | Save session settings and event metadata |
| Dashboard | Display preview, controls, results, and exports |

Suggested code layout:

```text
app/
  sources/        # Video and webcam capture
  perception/     # Detection and tracking
  events/         # Crossing and zone rules
  storage/        # Sessions and observations
  ui/             # Controls, preview, and results
  config/         # Processing settings
exports/          # User-requested output files
```

Python can handle the video pipeline. Choose a person detector and a compatible multi-object tracker after checking their installation requirements, licensing, and performance on your machine. A simple local UI and SQLite event store are enough for the first prototype. A browser frontend and separate API can be added when needed.

A server-side webcam capture library opens a camera attached to the server computer. If the application later runs remotely, browser webcam capture and an explicit frame-streaming path will be needed to use the user's camera.

## 7. Event and session records

Keep these basic entities:

- `Session`: ID, source type, display name, processing settings, status, start/end times.
- `Track`: session ID, temporary track ID, first/last observed offsets.
- `CountingLine`: session ID, normalized endpoints, direction labels.
- `Zone`: optional polygon and label.
- `Event`: session ID, track ID, event type, source offset, confidence/provenance fields.

Example event:

```json
{
  "event_id": "evt_001",
  "session_id": "session_001",
  "source_type": "uploaded_video",
  "source_name": "walking_demo.mp4",
  "track_id": "track_12",
  "event_type": "line_crossing",
  "line_id": "line_1",
  "direction": "A_to_B",
  "source_offset_ms": 83400,
  "detection_confidence": 0.91,
  "detector_version": "configured-model-version"
}
```

Detection confidence is not an identity-match probability or a calibrated confidence in the crossing event. Record those concepts separately if they are introduced later.

## 8. Counting and tracking rules

- Use a consistent point on each tracked box, such as bottom center, for line and zone calculations.
- Require a confirmed transition across a line; add a small dead band to reduce jitter-induced crossings.
- Record direction and debounce the same transition so one crossing produces one event.
- Allow a later genuine return crossing to create another event.
- Keep IDs scoped to a source and session to avoid collisions between uploads.
- Handle track loss explicitly; do not assume a person disappeared from the physical scene.
- Store line and zone coordinates normalized to frame dimensions so preview scaling does not change the rules.

## 9. Dashboard

The main screen should contain:

- Input selector: upload a video or select a webcam.
- Preview with detection boxes, IDs, and an active-processing indicator.
- Start, stop, and reset buttons.
- Visible-person count and directional crossing totals.
- Line-drawing controls; zone controls can follow later.
- Event table with time, track ID, event type, and direction.
- Export and delete-session actions.

Show file processing progress for videos. For webcams, show elapsed time and measured processing speed. Display incomplete or cancelled sessions honestly.

## 10. Data handling

Use your own recordings or footage you are permitted to process. Use consenting volunteers for staged tests.

Keep processing local for the prototype. Store event metadata by default; make saving webcam footage or annotated videos an explicit option. Let the user delete session records and exported artifacts through clear controls. Do not store names or infer identity from appearance.

If the app becomes shared or publicly accessible, add authentication, per-user data access, upload size limits, safe file handling, and retention enforcement before deployment.

## 11. Evaluation

Create a small test set with manually recorded ground truth:

1. One person crosses a line in each direction.
2. Two people cross close together.
3. A person stands near the line without crossing.
4. A person crosses, returns, and crosses again.
5. A person is briefly hidden behind another person or object.
6. A person leaves and re-enters the frame.
7. A video ends or the webcam disconnects during processing.

Measure:

- Missed detections and false detections on labeled frames.
- ID switches and fragmented tracks.
- Crossing precision and recall against manually checked events.
- Event timing error and count error.
- Processing speed and preview delay on the actual machine.
- Correct cleanup of webcam handles and cancelled jobs.

Do not claim a target frame rate or tracking accuracy until it has been measured on your hardware and videos.

## 12. Implementation milestones

1. **Video input:** open a file and display frames with correct playback offsets.
2. **Person detection:** draw person boxes and show visible-person counts.
3. **Tracking:** add temporary IDs and inspect ID switches on a short clip.
4. **Event counting:** implement one counting line and verify it with staged crossings.
5. **Webcam:** reuse the pipeline with start/stop controls and device cleanup.
6. **Results:** save sessions/events and export a CSV.
7. **Polish:** handle invalid files, cancellation, disconnections, and session deletion.
8. **Optional extensions:** polygon zones, annotated export, batch videos, then reviewed cross-source matching.

Finish each milestone with a working demonstration before adding the next feature.

## 13. Definition of done

The first version is complete when a user can upload a video or start a webcam, see people tracked with temporary IDs, configure a counting line, inspect correctly timed crossing events, export the results, and stop or delete a session cleanly. Known tracking limitations and measured performance must be documented.

## 14. One-sentence pitch

**A local video and webcam assistant that tracks people with temporary IDs, counts line crossings, and turns recordings into an easy-to-review event timeline.**

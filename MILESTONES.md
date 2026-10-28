# SceneTrace milestones and task checklist

The current scope is defined in [PROJECT.md](PROJECT.md). Checkmarks indicate implemented code, not validated real-world accuracy.

## M0 â€” Project foundation

- [x] Update the idea for uploaded videos, saved labels, automatic view recognition, and a custom frontend on localhost.
- [x] Separate UI, persistence, and computer-vision modules.
- [x] Validate 30 isolated backend/source tests, including scene rejection, corrections, timestamp handling, and API behavior.
- [x] Add isolated dependency setup, local server settings, and storage exclusions.
- [ ] Prepare permitted footage from two known views and one unregistered view, with manually checked people and recording times.
- [ ] Agree on acceptable false view assignments, missed detections, and person-match errors using this footage.

Acceptance: documented startup works and the evaluation dataset has independent test clips. Implementation can start before user footage arrives; accuracy acceptance cannot.

## M1 â€” Clean UI and persistent workspace

Depends on M0.

- [x] Overview with actual totals, upload entry point, and recent recordings.
- [x] Locations, Recordings, People, and Review matches pages.
- [x] SQLite schema, local media storage, correction audit records.
- [x] Clear empty/loading/error states and no fabricated results.
- [ ] Validate responsive layout and keyboard use in a real browser. Automated browser preview was blocked by the localhost origin permission gate; HTTP page and health checks passed.
- [ ] Verify persistence with the user's reference footage after full server restart.

Acceptance: saved locations and completed observations survive restart and the interface supports the primary journey.

## M2 â€” One-time location/reference setup

Depends on M1.

- [x] Label a location and its view/camera once.
- [x] Extract and persist representative frames and scene descriptors.
- [x] Add multiple reference sets to a saved view.
- [x] Preview references and rename locations.
- [ ] Add explicit reference removal/replacement and camera-label editing.
- [ ] Mask foreground people and filter blurred/redundant frames.

Acceptance: future uploads can reuse stored references without another camera prompt; unclear references get useful feedback.

## M3 â€” Upload, time, and background processing

Depends on M1; independent of M2.

- [x] Validate size, extension, and actual decoding; reject empty/invalid files.
- [x] Generated storage names and duplicate-content detection.
- [x] Persist job state, process outside the UI, expose progress and retry interrupted work.
- [x] Keep source playback offsets separate from upload time.
- [x] Optional recording start date/time/UTC offset.
- [x] Open original videos at an observation's playback offset.
- [ ] Add cancellation, configurable processing limits, and accurate variable-frame-rate evaluation.
- [ ] Detect and split multi-view/edit boundaries; until then require single-view clips.

Acceptance: a valid upload reaches a completed/failed state, invalid media cannot become a completed analysis, and unknown dates stay unknown.

## M4 â€” Automatic saved-view recognition

Depends on M2 and M3.

- [x] Compare multiple frames against stored references using ORB and geometric verification.
- [x] Aggregate scores and require sufficient support plus a margin over other locations.
- [x] Recognized / uncertain / unknown results, candidate suggestions, and manual correction.
- [x] Persist scores, model version, and correction provenance.
- [ ] Evaluate held-out known views, similar rooms, night scenes, crops, and moved cameras.
- [ ] Calibrate thresholds from evidence rather than treating default scores as probabilities.
- [ ] Add scene segmentation and per-segment assignments before supporting multi-view uploads.

Acceptance: measured strong matches auto-assign without a camera selector; unseen and ambiguous views are allowed to remain unassigned.

## M5 â€” Person detection and within-video tracking

Depends on M3; may develop independently of M4.

- [x] Person-only YOLOX-S, YuNet face detection, motion-assisted overlap tracking, and conservative fragment filtering.
- [x] Per-recording track IDs, first/last detection offsets, representative thumbnails, provisional person groups.
- [x] Quality-gated SFace matching; clothing-only identity suggestions removed; strong supported face matches can reuse a global ID.
- [ ] Integrate and evaluate a stronger detector and multi-object tracker, such as the detector/tracker options in the supplied brief, after compatibility and licensing checks.
- [ ] Persist frame-level boxes and add synchronized overlays or annotated-video output.
- [ ] Measure misses, false detections, ID switches, fragmentation, and throughput on real footage.

Acceptance: real person observations are source-linked, ID limitations are visible, and the detector/tracker meets the agreed evaluation targets. The baseline alone is not accuracy acceptance.

## M6 â€” Reviewed returning people and correction

Depends on M4 and M5.

- [x] Side-by-side candidate crops and accept/reject/separate-group actions.
- [x] Manual assignment to an existing group.
- [x] Prevent conflicting overlapping tracks from joining the same group in one recording.
- [x] Split a mistaken association into a new provisional group.
- [x] Persist decisions and audit changes.
- [ ] Integrate evaluated learned body descriptors; test same clothes, changed clothes, and look-alikes.
- [ ] Add gallery-consistency checks, cross-recording timing constraints where timestamps are known, and richer evidence comparison.
- [ ] Measure false merges and missed associations using held-out volunteers.

Acceptance: person suggestions stay provisional until reviewed; false group associations can be corrected without losing source observations.

## M7 â€” Location histories, search, and reports

Depends on M4â€“M6.

- [x] Person profiles with location, camera label, match states, and source-video links.
- [x] Chronological dated observations; separate unknown-date recording offsets.
- [x] Latest dated observation rather than an unsupported current-location claim.
- [x] CSV export with time basis and match state.
- [ ] Add location/date/recording filters and a graphical timeline.
- [ ] Add recording-time correction with audit history.
- [ ] Complete end-to-end checks that location/group corrections update every derived view.

Acceptance: users can answer where and when a group was observed and open the corresponding source evidence, including uncertainty and coverage gaps.

## M8 â€” Webcam and local release hardening

Depends on the recording MVP, M1â€“M7.

- [ ] Add bounded webcam sessions with explicit start/stop and resource cleanup.
- [ ] Reuse saved-view matching and observation persistence; handle a moved webcam.
- [ ] Display visible now only while a recent live observation supports it.
- [x] Bind the server to localhost by default.
- [x] Delete completed recordings and dependent source media/results.
- [ ] Add configurable retention, disk-capacity checks, and backup/restore workflow.
- [ ] Run real-video evaluation, restart/recovery tests, and browser accessibility checks.
- [ ] Package a repeatable demo and measured limitations report.

Acceptance: recording and webcam workflows meet documented targets, stop cleanly, and recover without silently losing or inventing observations.

## Delivery order

### Added search and automation tasks

- [x] Separate Search person menu with person/track ID lookup, location filtering, and source-video evidence.
- [x] Face-photo search within selected, all analyzed, or newly uploaded recordings; unclear evidence does not fall back to clothing colors.
- [x] Agent center with task runs, audit history, attention counts, and persisted settings.
- [x] Recheck completed unresolved locations automatically when reference footage is added; preserve confirmed labels.
- [x] Resume interrupted analysis at most once when no track results have been saved.
- [ ] Upgrade photo search to an evaluated learned body-appearance model before claiming robust re-identification.

1. Foundation and UI: M0â€“M1.
2. Saved references and uploads: M2â€“M3.
3. Automatic view assignment and within-video tracking: M4â€“M5.
4. Reviewed person history MVP: M6â€“M7.
5. Webcam and verified local release: M8.

Zone counting, dwell summaries, PDF reports, remote hosting, and automatic person merging are deferred. Avoid fixed completion dates until actual footage and machine performance are measured.


## Implemented core workflow update

- [x] Shared global person gallery, with strong face-match reuse across recordings and an explicit automatic association state.
- [x] Face-only observations, face/body handoff, face boxes, full-person boxes, and stable IDs on matching reanalysis geometry.
- [x] Tiny-object and short-fragment rejection to reduce gate-handle and brief background false IDs.
- [x] Sharpest native-resolution crop selection; original/enhanced preview comparison without changing matching evidence.
- [x] Simplified Find person flow that can analyze a new recording before searching.
- [x] Captured-appearance gallery and source-linked camera/location/time history.
- [x] H.264 tracked-person highlight video, with source times and location labels; tested decoding and deletion provenance.
- [x] Visible recording deletion controls and dependent export cleanup.
- [x] ORB/SIFT location verification and Teach this angle for additional views of an existing saved location.
- [x] Thirty regression checks including photo rejection, ID reuse, capture quality, source deletion, teaching views, export playback, and JavaScript syntax parsing.
- [ ] Browser visual/click QA: still blocked by the saved origin permission policy despite the user's conversational approval.
- [ ] Validate identity and view accuracy on held-out real footage. Unit tests do not establish deployment accuracy.
- [ ] Learned body re-identification for supported handoffs when faces are unavailable; do not substitute clothing-color guesses.

## Repository and startup delivery

- [x] Complete implementation explanation and referenced research draft.
- [x] A 250-word abstract and a 250-word literature review.
- [x] Double-click Windows launcher with automatic dependency/model setup and existing-server reuse.
- [x] Thirty-two regression checks passed after launcher integration.
- [x] Prepare the initial source tree and authenticate GitHub publication for the requested repository.

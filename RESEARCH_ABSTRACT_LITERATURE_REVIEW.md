# SceneTrace: Cross-Camera Person Observation and Retrieval

Research draft based on the implemented prototype as of 29 October 2026.

## Abstract

SceneTrace is a locally deployed computer vision prototype designed to organize person observations across uploaded camera recordings. The project addresses manual video review by combining camera-view registration, person detection, face comparison, persistent identifiers, and searchable location histories. Users register labeled reference footage for each camera view, after which later recordings are compared against stored background features using ORB, SIFT, and geometric verification. YOLOX-S detects people, while YuNet detects faces, including appearances where the full body is unavailable. A motion-assisted tracker associates observations within recordings. Clear faces are aligned and represented through SFace embeddings, enabling supported appearances to reuse an identifier across recordings. Face size, sharpness, landmark visibility, similarity thresholds, and competing matches constrain automatic associations. Unclear evidence remains provisional, and clothing color is not used as an identity fallback. The system stores original-resolution captures, observation intervals, camera labels, location assignments, and correction history in SQLite and local storage. A browser interface supports video analysis, person searches using photographs or identifiers, captured-image galleries, and annotated tracking-video exports. Background workers automate processing, evidence-quality refresh, unresolved-location rechecks, and limited recovery of interrupted jobs. Thirty-two functional tests verify software workflows, including identifier persistence, view registration, source deletion, and playable exports. These checks do not establish recognition accuracy on representative populations or camera conditions. Remaining work includes rigorous evaluation, stronger multi-object tracking, body-based re-identification when faces are unavailable, and broader operational controls. The prototype therefore provides an auditable implementation foundation for camera-based observation retrieval while explicitly separating recorded evidence from unsupported identity or location claims.

## Literature Review

Person retrieval across cameras combines object detection, temporal association, identity representation, and scene interpretation. Ge et al. introduced YOLOX, an anchor-free detector incorporating a decoupled head and SimOTA assignment [1]. Its pretrained COCO model supports SceneTrace's person-detection stage, but detector confidence alone cannot establish identity.

Wu et al. presented YuNet as a compact face detector suitable for efficient deployment [2]. Face localization and landmarks support alignment before comparison. Zhong et al. proposed SFace loss to balance identity separation with robustness to noisy training samples [3]. SceneTrace uses pretrained SFace embeddings, while rejecting faces with insufficient resolution, sharpness, or landmark visibility. Published model results do not directly establish performance on the project's recordings.

Wojke et al. extended SORT with a learned appearance metric, demonstrating the value of visual descriptors for maintaining identities through occlusion [4]. ByteTrack instead associates lower-confidence detections with existing tracks to reduce fragmentation [5]. These approaches motivate stronger future tracking; SceneTrace currently implements a simpler motion-assisted overlap tracker rather than either algorithm.

Lowe's SIFT research established distinctive local features for matching image content across changes in scale and orientation [6]. Such features support registered-view comparison, although they cannot identify an unseen room from an arbitrary angle.

Together, this literature motivates separating detection, identity association, and location recognition. SceneTrace integrates these tasks with persistent records, quality checks, correction history, and evidence-linked retrieval. Its research contribution should therefore be investigated through evaluation, measuring false associations, missed observations, identity switches, and viewpoint rejection, rather than claiming improvements from functional tests alone.

## References

1. Ge, Z., Liu, S., Wang, F., Li, Z., and Sun, J. (2021). **YOLOX: Exceeding YOLO Series in 2021.** [Original paper](https://arxiv.org/abs/2107.08430).
2. Wu, W., Peng, H., and Yu, S. (2023). **YuNet: A Tiny Millisecond-Level Face Detector.** Machine Intelligence Research. [Original paper](https://doi.org/10.1007/s11633-023-1423-y).
3. Zhong, Y., Deng, W., Hu, J., Zhao, D., Li, X., and Wen, D. (2021). **SFace: Sigmoid-Constrained Hypersphere Loss for Robust Face Recognition.** IEEE Transactions on Image Processing. [Original paper](https://doi.org/10.1109/TIP.2020.3048632).
4. Wojke, N., Bewley, A., and Paulus, D. (2017). **Simple Online and Realtime Tracking with a Deep Association Metric.** [Original paper](https://arxiv.org/abs/1703.07402).
5. Zhang, Y., et al. (2022). **ByteTrack: Multi-Object Tracking by Associating Every Detection Box.** [Original paper](https://arxiv.org/abs/2110.06864).
6. Lowe, D. G. (2004). **Distinctive Image Features from Scale-Invariant Keypoints.** International Journal of Computer Vision. [Original paper](https://doi.org/10.1023/B:VISI.0000029664.99615.94).

## Word-count and research notes

- Abstract: 250 words.
- Literature review: 250 words, excluding numbered citation markers.
- Titles, references, and these notes are outside the word counts. Counts use whitespace-separated words; hyphenated terms count as one word.
- This document describes a prototype. It does not claim a completed recognition-accuracy study, superiority to published trackers, or production readiness.
- Deep SORT and ByteTrack are reviewed as related work; the current application does not implement either complete tracker.

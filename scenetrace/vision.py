"""ORB scene verification and person-only YOLOX detection.

These baselines are intentionally separate from the UI so stronger models can
replace them without changing persisted observations or review semantics.
"""
from pathlib import Path
import cv2
import numpy as np

SCENE_VERSION = "orb-sift-ransac-v2"
DETECTOR_VERSION = "yolox-s-person-v2"
MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / "person-yolox.onnx"


def resize(frame, width=720):
    h, w = frame.shape[:2]
    return cv2.resize(frame, (width, max(1, round(h * width / w))))


def sample_video(path, count=9):
    cap = cv2.VideoCapture(str(path))
    try:
        fps = cap.get(cv2.CAP_PROP_FPS)
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        if not cap.isOpened() or not np.isfinite(fps) or fps <= 0 or frames < 1:
            raise ValueError("This video cannot be decoded. Try an MP4 recording with a supported codec.")
        duration = frames / fps
        if duration > 3600:
            raise ValueError("Use a clip under one hour for this prototype.")
        samples = []
        for index in np.linspace(0, max(0, frames - 2), min(count, int(frames))).astype(int):
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(index))
            ok, frame = cap.read()
            if ok:
                samples.append(resize(frame))
        if not samples:
            raise ValueError("No readable video frames were found.")
        return samples, float(duration)
    finally:
        cap.release()


def describe(frame):
    gray = cv2.cvtColor(resize(frame), cv2.COLOR_BGR2GRAY)
    points, descriptors = cv2.ORB_create(nfeatures=1400).detectAndCompute(gray, None)
    xy = np.asarray([point.pt for point in points], dtype=np.float32).reshape(-1, 2)
    return xy, descriptors if descriptors is not None else np.empty((0, 32), np.uint8)


def save_reference(frames, path):
    payload = {}
    for index, frame in enumerate(frames):
        points, descriptors = describe(frame)
        payload[f"p{index}"] = points
        payload[f"d{index}"] = descriptors
        points,descriptors=describe_sift(frame)
        payload[f"s{index}"]=points
        payload[f"t{index}"]=descriptors
    np.savez_compressed(path, **payload)


def describe_sift(frame):
    gray=cv2.cvtColor(resize(frame),cv2.COLOR_BGR2GRAY)
    points,descriptors=cv2.SIFT_create(nfeatures=1600).detectAndCompute(gray,None)
    return np.asarray([point.pt for point in points],dtype=np.float32).reshape(-1,2), descriptors if descriptors is not None else np.empty((0,128),np.float32)


def read_reference(path, kind="orb"):
    with np.load(path, allow_pickle=False) as archive:
        a,b=("p","d") if kind=="orb" else ("s","t")
        count=sum(key.startswith(a) and key[1:].isdigit() for key in archive.files)
        return [(archive[f"{a}{i}"],archive[f"{b}{i}"]) for i in range(count)]


def scene_similarity(first, second):
    points_a, descriptors_a = first
    points_b, descriptors_b = second
    if min(len(descriptors_a), len(descriptors_b)) < 12:
        return 0.0
    norm=cv2.NORM_L2 if descriptors_a.dtype.kind=="f" else cv2.NORM_HAMMING
    neighbors = cv2.BFMatcher(norm).knnMatch(descriptors_a, descriptors_b, k=2)
    good = [pair[0] for pair in neighbors if len(pair) == 2 and pair[0].distance < .72 * pair[1].distance]
    if len(good) < 10:
        return 0.0
    source = np.float32([points_a[m.queryIdx] for m in good])
    target = np.float32([points_b[m.trainIdx] for m in good])
    _, mask = cv2.findHomography(source, target, cv2.RANSAC, 4.0)
    if mask is None:
        return 0.0
    inliers = int(mask.sum())
    if inliers < 10:
        return 0.0
    # Evidence score, not a probability. Reject small, localized matching patches.
    hull_area = cv2.contourArea(cv2.convexHull(source[mask.ravel().astype(bool)]))
    coverage = min(1.0, hull_area / (720 * 120))
    return float(min(1.0, inliers / 55) * (inliers / len(good)) * coverage)


def recognize(frames, references):
    if not references:
        return {"status": "unknown", "location_id": None, "scores": []}
    descriptions = [describe(frame) for frame in frames]
    sift_descriptions=[describe_sift(frame) for frame in frames]
    by_location = {}
    for reference in references:
        saved = read_reference(reference["features_path"])
        scores = [max((scene_similarity(frame, ref) for ref in saved), default=0) for frame in descriptions]
        sift_saved=read_reference(reference["features_path"],"sift")
        if not sift_saved and reference.get("preview_path"):
            preview=cv2.imread(reference["preview_path"])
            if preview is not None:
                sift_saved=[describe_sift(preview)]
        sift_scores=[max((scene_similarity(frame,ref) for ref in sift_saved),default=0) for frame in sift_descriptions]
        scores=np.maximum(scores,sift_scores)
        location_id = reference["location_id"]
        previous = by_location.get(location_id, np.zeros(len(frames)))
        by_location[location_id] = np.maximum(previous, scores)
    ranked = sorted(({
        "location_id": key, "score": round(float(np.median(values)), 3),
        "support": round(float(np.mean(values >= .5)), 3)
    } for key, values in by_location.items()), key=lambda row: row["score"], reverse=True)
    best = ranked[0]
    margin = best["score"] - (ranked[1]["score"] if len(ranked) > 1 else 0)
    # Conservative defaults, still requiring validation against the user's footage.
    accepted = best["score"] >= .55 and best["support"] >= .75 and margin >= .15
    status = "recognized" if accepted else "uncertain" if best["score"] >= .15 else "unknown"
    return {"status": status, "location_id": best["location_id"] if accepted else None, "scores": ranked[:3]}


def person_appearance(crop):
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    histogram = cv2.calcHist([hsv], [0, 1], None, [16, 8], [0, 180, 0, 256]).flatten()
    norm = np.linalg.norm(histogram)
    return histogram / max(norm, 1e-9)


class PedestrianDetector:
    def __init__(self):
        if not MODEL_PATH.exists():
            raise ValueError("The person detector model is missing. Run python setup_model.py, then retry analysis.")
        self.net = cv2.dnn.readNetFromONNX(str(MODEL_PATH))
        self.net.setPreferableBackend(cv2.dnn.DNN_BACKEND_OPENCV)
        self.net.setPreferableTarget(cv2.dnn.DNN_TARGET_CPU)
        grids, strides = [], []
        for stride in (8, 16, 32):
            x, y = np.meshgrid(np.arange(640 // stride), np.arange(640 // stride))
            grid = np.stack((x, y), axis=2).reshape(-1, 2)
            grids.append(grid)
            strides.append(np.full((len(grid), 1), stride))
        self.grid = np.concatenate(grids)
        self.strides = np.concatenate(strides)
        self.scores = []

    def detect(self, frame):
        h, w = frame.shape[:2]
        ratio = min(640 / w, 640 / h)
        image = np.full((640, 640, 3), 114, dtype=np.float32)
        resized = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB), (int(w * ratio), int(h * ratio)))
        image[:resized.shape[0], :resized.shape[1]] = resized
        self.net.setInput(image.transpose(2, 0, 1)[None])
        raw = self.net.forward()[0]
        return self.decode(raw, ratio, w, h)

    def decode(self, raw, ratio, width, height):
        # COCO class 0 is person. Background/non-person classes never get IDs.
        scores = raw[:, 4] * raw[:, 5]
        is_person = np.argmax(raw[:, 5:], axis=1) == 0
        mask = is_person & (scores >= .60)
        if not mask.any():
            self.scores = []
            return []
        selected = raw[mask]
        centers = (selected[:, :2] + self.grid[mask]) * self.strides[mask]
        sizes = np.exp(np.clip(selected[:, 2:4], -10, 10)) * self.strides[mask]
        corners = np.concatenate((centers - sizes / 2, centers + sizes / 2), axis=1) / ratio
        boxes, confidence = [], []
        for corner, score in zip(corners, scores[mask]):
            x1, y1, x2, y2 = corner
            x1, x2 = np.clip([x1, x2], 0, width)
            y1, y2 = np.clip([y1, y2], 0, height)
            if x2-x1 < max(16,width*.035) or y2-y1 < max(36,height*.10):
                continue
            boxes.append([int(x1), int(y1), int(x2 - x1), int(y2 - y1)])
            confidence.append(float(score))
        indices = np.asarray(cv2.dnn.NMSBoxes(boxes, confidence, .60, .45)).ravel() if boxes else []
        self.scores = [confidence[i] for i in indices]
        return [tuple(boxes[i]) for i in indices]


def overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    intersection = max(0, min(ax + aw, bx + bw) - max(ax, bx)) * max(0, min(ay + ah, by + bh) - max(ay, by))
    return intersection / max(1e-9, aw * ah + bw * bh - intersection)


class TrackManager:
    def __init__(self, max_gap=1.2):
        self.tracks = {}
        self.next_id = 1
        self.max_gap = max_gap

    def update(self, boxes, timestamp, frame, face_only=None):
        face_only=face_only or set()
        available = {key for key, track in self.tracks.items() if timestamp - track["last_seen"] <= self.max_gap}
        current = []
        for box in boxes:
            def match_score(key):
                old = self.tracks[key]
                delta = timestamp - old["last_seen"]
                predicted = np.asarray(old["box"], dtype=float).copy()
                predicted[:2] += old.get("velocity", np.zeros(2)) * delta
                iou = overlap(box, predicted)
                if old.get('face_only') or box in face_only:
                    small,large=(box,predicted) if box[2]*box[3]<predicted[2]*predicted[3] else (predicted,box)
                    cx,cy=small[0]+small[2]/2,small[1]+small[3]/2
                    if delta<=.45 and large[2]*large[3]>small[2]*small[3]*3 and large[0]<=cx<=large[0]+large[2] and large[1]<=cy<=large[1]+large[3]*.45:
                        iou=max(iou,.4)
                return iou
            candidates = sorted(((match_score(key), key) for key in available), reverse=True)
            if candidates and candidates[0][0] >= .15:
                key = candidates[0][1]
                available.remove(key)
                track = self.tracks[key]
            else:
                key = self.next_id
                self.next_id += 1
                track = {"local_id": key, "first_seen": timestamp, "samples": 0}
                self.tracks[key] = track
            x, y, w, h = box
            crop = frame[max(0, y):max(0, y) + h, max(0, x):max(0, x) + w]
            if crop.size == 0:
                continue
            descriptor = person_appearance(crop)
            count = track["samples"]
            track["appearance"] = (track["appearance"] * count + descriptor) / (count + 1) if count else descriptor
            if count:
                delta = max(.001, timestamp - track["last_seen"])
                measured = (np.asarray(box[:2]) - np.asarray(track["box"][:2])) / delta
                track["velocity"] = .5 * track.get("velocity", measured) + .5 * measured
            track.update(box=box,last_seen=timestamp,samples=count+1,face_only=box in face_only)
            if count == 0:
                track["thumbnail"] = crop.copy()
            current.append(track)
        return current

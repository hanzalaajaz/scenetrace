"""Local face evidence with quality gates; no clothing-based identity fallback."""
from pathlib import Path
import cv2
import numpy as np

MODELS = Path(__file__).resolve().parents[1] / "models"
VERSION = "yunet-sface-quality-v2"


def sharpness(image):
    if image.size == 0:
        return 0.0
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


class FaceEngine:
    def __init__(self):
        if not (MODELS / "face-yunet.onnx").exists() or not (MODELS / "face-sface.onnx").exists():
            raise ValueError("Face comparison models are missing. Run python setup_model.py first.")
        self.detector = cv2.FaceDetectorYN.create(str(MODELS / "face-yunet.onnx"), "", (320, 320), .85, .3, 100)
        self.recognizer = cv2.FaceRecognizerSF.create(str(MODELS / "face-sface.onnx"), "")

    def detect(self,image,min_size=24):
        height,width=image.shape[:2]
        if min(height,width)<20:return []
        self.detector.setInputSize((width,height))
        _,faces=self.detector.detect(image)
        if faces is None:return []
        valid=[]
        for face in faces:
            x,y,w,h=face[:4]
            visible_w=min(width,x+w)-max(0,x)
            visible_h=min(height,y+h)-max(0,y)
            if min(visible_w,visible_h)>=min_size and face[14]>=.90:
                valid.append(face)
        return valid

    def describe(self, image, min_size=40):
        height, width = image.shape[:2]
        if min(height, width) < 20:
            return {"feature": None, "box": None, "reason": "Face is too small", "quality": 0.0}
        faces=self.detect(image,min_size=20)
        if not len(faces):
            return {"feature": None, "box": None, "reason": "No clear face detected", "quality": 0.0}
        if len(faces) != 1:
            return {"feature": None, "box": None, "reason": "Several faces detected; use a single-person image", "quality": 0.0}
        face = faces[0]
        x, y, w, h = face[:4]
        x1, y1 = max(0, int(x)), max(0, int(y))
        x2, y2 = min(width, int(x+w)), min(height, int(y+h))
        crop = image[y1:y2, x1:x2]
        quality = sharpness(crop)
        result = {"feature": None, "box": [x1, y1, max(0,x2-x1), max(0,y2-y1)], "quality": quality}
        if min(w,h,x2-x1,y2-y1) < min_size:
            return result | {"reason": "Face resolution is too low for reliable comparison"}
        landmarks=face[4:14].reshape(5,2)
        if np.any(landmarks[:,0]<0) or np.any(landmarks[:,0]>=width) or np.any(landmarks[:,1]<0) or np.any(landmarks[:,1]>=height):
            return result | {"reason":"Face landmarks are clipped or unreliable"}
        eye_distance=np.linalg.norm(landmarks[0]-landmarks[1])
        if eye_distance<w*.20 or eye_distance>w*.8:
            return result | {"reason":"Face pose is too uncertain for comparison"}
        if quality < 45:
            return result | {"reason": "Face is too blurred for reliable comparison"}
        if face[14] < .9:
            return result | {"reason": "Face detection is uncertain"}
        aligned = self.recognizer.alignCrop(image, face)
        vector = self.recognizer.feature(aligned).flatten().astype(float)
        vector /= max(np.linalg.norm(vector), 1e-9)
        return result | {"feature": vector.tolist(), "reason": "Clear face evidence available"}


def face_similarity(query, examples):
    vector = np.asarray(query, dtype=float)
    scores = []
    for sample in examples:
        if sample.get("model")!=VERSION:
            continue
        other = np.asarray(sample.get("feature", []), dtype=float)
        if other.shape == vector.shape and len(other) and np.isfinite(other).all():
            scores.append(float(np.dot(vector, other) / max(1e-9,np.linalg.norm(vector)*np.linalg.norm(other))))
    scores.sort(reverse=True)
    # Stricter than the upstream demo threshold; still candidates, never identity proof.
    if not scores or scores[0] < .60:
        return None
    if len(scores) > 1 and scores[1] < .50:
        return None
    return scores[0]


def enhance_preview(image):
    """Conservative display filtering. Never used to manufacture matching evidence."""
    denoised = cv2.fastNlMeansDenoisingColored(image, None, 3, 3, 7, 21)
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    lab[:,:,0] = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8,8)).apply(lab[:,:,0])
    contrast = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    blurred = cv2.GaussianBlur(contrast, (0,0), 1)
    return cv2.addWeighted(contrast, 1.25, blurred, -.25, 0)

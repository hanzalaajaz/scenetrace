"""Download the official OpenCV Zoo YOLOX ONNX model and verify its SHA256."""
from pathlib import Path
import hashlib
import urllib.request

URL = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx"
SHA256 = "c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063"
DIRECTORY = Path(__file__).resolve().parent / "models"
MODELS = [
    ("person-yolox.onnx",URL,SHA256),
    ("face-yunet.onnx","https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx","8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    ("face-sface.onnx","https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx","0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
]

if __name__ == "__main__":
    DIRECTORY.mkdir(exist_ok=True)
    for name,url,checksum in MODELS:
        target=DIRECTORY/name
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest()==checksum:
            print(f"{name}: installed and verified")
            continue
        temporary=target.with_suffix('.part')
        try:
            urllib.request.urlretrieve(url,temporary)
            if hashlib.sha256(temporary.read_bytes()).hexdigest()!=checksum:
                raise RuntimeError(f"{name}: checksum mismatch; download was not installed")
            temporary.replace(target)
            print(f"{name}: installed and verified")
        finally:
            temporary.unlink(missing_ok=True)

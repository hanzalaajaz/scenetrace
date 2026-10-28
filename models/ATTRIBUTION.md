# Person detector

Model: `object_detection_yolox_2022nov.onnx`, YOLOX-S, from the official OpenCV Zoo.

- Upstream: https://github.com/opencv/opencv_zoo/tree/main/models/object_detection_yolox
- Download: https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models/object_detection_yolox/object_detection_yolox_2022nov.onnx
- SHA256: `c5c2d13e59ae883e6af3b45daea64af4833a4951c92d116ec270d9ddbe998063`
- Model size: 35,858,002 bytes.
- License: Apache 2.0; see LICENSE-YOLOX.

SceneTrace uses the model through OpenCV DNN, with RGB top-left letterboxing, stride/grid output decoding, person-class filtering, a score threshold, and nonmaximum suppression. The supplied upstream preprocessing reference is kept in this folder for attribution; it is not executed by the app.

## Face detection and comparison

YuNet: https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet

- `face_detection_yunet_2023mar.onnx`; SHA256 `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`.
- MIT license; see LICENSE-YUNET.

SFace: https://github.com/opencv/opencv_zoo/tree/main/models/face_recognition_sface

- `face_recognition_sface_2021dec.onnx`; SHA256 `0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79`.
- Apache 2.0 license; see LICENSE-SFACE.

Models run locally through OpenCV. Face size, sharpness, clipped landmarks, and model version are checked before descriptors can support matching. Conservative matching thresholds still require real-world evaluation; similarity scores are not probabilities.

"""Choose original-resolution evidence and retain clear-face descriptors only."""
import math
import numpy as np
from .identity import sharpness,VERSION


def gather(track, frame, box, timestamp, engine):
    height, width = frame.shape[:2]
    x,y,w,h = box
    x1,y1 = int(max(0,x)*width), int(max(0,y)*height)
    x2,y2 = int(min(1,x+w)*width), int(min(1,y+h)*height)
    crop = frame[y1:y2,x1:x2]
    if not crop.size:
        return None
    focus = sharpness(crop)
    face = engine.describe(crop)
    evidence_score = math.log1p(focus)*10 + min(crop.shape[0]*crop.shape[1]/10000,25)
    if face["feature"] is not None:
        evidence_score += 100 + math.log1p(face["quality"])*10
        examples = track.setdefault("face_embeddings",[])
        examples.append({"feature":face["feature"],"offset":timestamp,"quality":face["quality"],"model":VERSION})
        examples.sort(key=lambda example:example["quality"],reverse=True)
        del examples[3:]
    if evidence_score > track.get("evidence_score",-1):
        track.update(thumbnail=crop.copy(),thumbnail_offset=timestamp,crop_sharpness=focus,evidence_score=evidence_score,
            quality_status="clear_face" if face["feature"] is not None else "blurred" if focus<40 else "body_only")
    if face["box"]:
        fx,fy,fw,fh=face["box"]
        return [(x1+fx)/width,(y1+fy)/height,fw/width,fh/height]
    return None

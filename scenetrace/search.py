"""Search recorded observations; photo retrieval is appearance evidence only."""
from io import BytesIO
import json
import warnings

import cv2
import numpy as np
from PIL import Image, UnidentifiedImageError

from . import store, identity


def photo_matches(contents, location_id=None, recording_id=None):
    if not contents or len(contents) > 10 * 1024 * 1024:
        raise ValueError("Choose a person photo under 10 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contents)) as image:
                if image.width * image.height > 20_000_000 or min(image.size) < 32:
                    raise ValueError("Use a clear crop at least 32 pixels wide and under 20 megapixels.")
                from PIL import ImageOps
                rgb = np.asarray(ImageOps.exif_transpose(image).convert("RGB"))
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("This image cannot be read. Use a JPG, PNG, or WebP photo.")
    frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    evidence = identity.FaceEngine().describe(frame,min_size=64)
    if evidence["feature"] is None:
        raise ValueError(evidence["reason"] + ". Upload a clear, single-person face photo. Clothing colors will not be used as a fallback.")
    rows = store.query("""SELECT t.*,p.label,r.filename,r.recorded_at,r.location_status,
        l.label AS location_label,l.camera_label FROM tracks t JOIN people p ON p.id=t.person_id
        JOIN recordings r ON r.id=t.recording_id LEFT JOIN locations l ON l.id=r.location_id
        WHERE (? IS NULL OR r.location_id=?) AND (? IS NULL OR r.id=?)""", (location_id, location_id, recording_id, recording_id))
    results = []
    for row in rows:
        score = identity.face_similarity(evidence["feature"],json.loads(row["face_embeddings"]))
        if score is not None:
            results.append(row | {"similarity": round(score,4),"result_status":"face_candidate"})
    return sorted(results, key=lambda row: row["similarity"], reverse=True)[:20]

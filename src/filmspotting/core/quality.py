"""Frame quality heuristics: pick a sharp frame from the same shot as the target."""

import cv2
import numpy as np

SAME_SHOT_THRESHOLD = 0.7


def sharpness(frame: np.ndarray) -> float:
    """Variance of the Laplacian: higher means more in-focus detail, less motion blur."""
    gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def _histogram(frame: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(frame, cv2.COLOR_RGB2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
    return cv2.normalize(hist, hist).flatten()


def same_shot(a: np.ndarray, b: np.ndarray) -> bool:
    return cv2.compareHist(_histogram(a), _histogram(b), cv2.HISTCMP_CORREL) >= SAME_SHOT_THRESHOLD


def best_frame_index(frames: list[np.ndarray], target_index: int) -> int:
    """Index of the sharpest frame that belongs to the same shot as ``frames[target_index]``.

    Frames further from the target are slightly penalised so we stay close to the requested moment.
    """
    target = frames[target_index]
    span = max(target_index, len(frames) - 1 - target_index, 1)
    best, best_score = target_index, -1.0
    for i, frame in enumerate(frames):
        if i != target_index and not same_shot(frame, target):
            continue
        score = sharpness(frame) * (1 - 0.3 * abs(i - target_index) / span)
        if score > best_score:
            best, best_score = i, score
    return best

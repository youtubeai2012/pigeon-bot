"""Blur the burned-in white captions in a Zack D. Films source video."""

import subprocess

import cv2
import numpy as np


def caption_mask(frame):
    """Return a mask following caption glyphs, or an empty mask if none are found."""
    height, width = frame.shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    x0, x1 = int(width * 0.10), int(width * 0.90)
    y0, y1 = int(height * 0.65), int(height * 0.88)
    roi = frame[y0:y1, x0:x1]
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    brightest = roi.max(axis=2).astype(np.int16)
    darkest = roi.min(axis=2).astype(np.int16)
    white = ((gray >= 185) & ((brightest - darkest) <= 55)).astype(np.uint8)
    dark = (gray <= 90).astype(np.uint8)
    near_dark = cv2.dilate(dark, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))

    count, labels, stats, centroids = cv2.connectedComponentsWithStats(white, 8)
    letters = []
    for index in range(1, count):
        x, y, w, h, area = stats[index]
        if not (height * 0.009 <= h <= height * 0.055):
            continue
        if not (width * 0.002 <= w <= width * 0.07):
            continue
        if not (height * width * 0.00002 <= area <= height * width * 0.003):
            continue
        component = labels[y:y+h, x:x+w] == index
        if np.count_nonzero(component & (near_dark[y:y+h, x:x+w] != 0)) < area * 0.08:
            continue
        letters.append((index, x, y, w, h, area, centroids[index][1]))

    # Text forms a row of similarly sized components spanning the centre.
    groups = []
    for letter in sorted(letters, key=lambda item: item[6]):
        match = next((group for group in groups if abs(group[0][6] - letter[6]) <= height * 0.022), None)
        if match is None:
            groups.append([letter])
        else:
            match.append(letter)

    for group in groups:
        left = min(item[1] for item in group) + x0
        right = max(item[1] + item[3] for item in group) + x0
        if len(group) < 4 or right - left < width * 0.12:
            continue
        if not (left < width * 0.58 and right > width * 0.42):
            continue
        for index, x, y, w, h, _, _ in group:
            patch = mask[y0+y:y0+y+h, x0+x:x0+x+w]
            patch[labels[y:y+h, x:x+w] == index] = 255

    if not mask.any():
        return mask
    radius = max(4, round(height * 0.015))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (radius * 2 + 1, radius * 2 + 1))
    return cv2.dilate(mask, kernel)


def blur_caption_frame(frame):
    mask = caption_mask(frame)
    if not mask.any():
        return frame
    height = frame.shape[0]
    blurred = cv2.GaussianBlur(frame, (0, 0), sigmaX=max(12, height * 0.03))
    alpha = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.5, height * 0.0025))
    alpha = alpha.astype(np.float32)[:, :, None] / 255.0
    return np.uint8(np.clip(frame * (1 - alpha) + blurred * alpha, 0, 255))


def blur_caption_video(source, output):
    capture = cv2.VideoCapture(str(source))
    if not capture.isOpened():
        raise RuntimeError(f"Could not read source video: {source}")
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = capture.get(cv2.CAP_PROP_FPS) or 30
    command = ["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo",
               "-pix_fmt", "bgr24", "-s", f"{width}x{height}", "-r", str(fps),
               "-i", "-", "-an", "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "18", "-pix_fmt", "yuv420p", str(output)]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            process.stdin.write(blur_caption_frame(frame).tobytes())
        process.stdin.close()
        error = process.stderr.read().decode(errors="replace")
        if process.wait() != 0:
            raise RuntimeError(f"Caption blur failed: {error[-2000:]}")
    finally:
        capture.release()
        if process.poll() is None:
            process.kill()
            process.wait()

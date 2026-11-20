"""DWPose для Fooocus-sud: найти позы людей на картинке и нарисовать скелет OpenPose для ControlNet.

Модели (ONNX, качаются при первом использовании в models/controlnet):
  yolox_l.onnx          — детектор людей
  dw-ll_ucoco_384.onnx  — DWPose: 133 точки (тело, кисти, лицо)
Код детектора/позы — extras/dwpose/cv_ox_*.py из Fannovel16/comfyui_controlnet_aux (Apache-2.0),
сборка и отрисовка — по мотивам того же проекта (DWposeDetector / draw_poses).

detect(img_rgb) → (картинка скелета HxWx3 uint8, позы в долях 0..1 — для будущего редактора).
"""

import colorsys
import math

import cv2
import numpy as np

from extras.dwpose.cv_ox_det import inference_detector
from extras.dwpose.cv_ox_pose import inference_pose

POSE_INPUT_SIZE = (288, 384)   # dw-ll_ucoco_384: ширина, высота
THRESHOLD = 0.3
EPS = 0.01

_sessions = None


def _load(det_path, pose_path):
    global _sessions
    if _sessions is None or _sessions[0] != (det_path, pose_path):
        import onnxruntime as ort
        avail = ort.get_available_providers()
        providers = [p for p in ('CUDAExecutionProvider', 'CPUExecutionProvider') if p in avail] or avail
        try:
            det = ort.InferenceSession(det_path, providers=providers)
            pose = ort.InferenceSession(pose_path, providers=providers)
        except Exception as e:
            print(f'[DWPose] {providers} не завёлся ({e}), считаю на CPU')
            det = ort.InferenceSession(det_path, providers=['CPUExecutionProvider'])
            pose = ort.InferenceSession(pose_path, providers=['CPUExecutionProvider'])
        print(f'[DWPose] onnxruntime: {det.get_providers()[0]}')
        _sessions = ((det_path, pose_path), det, pose)
    return _sessions[1], _sessions[2]


def _keypoints(img_rgb, det, pose):
    """→ массив [людей, 134, 3] (x, y, score) в пикселях, порядок точек тела — OpenPose-18."""
    bgr = np.ascontiguousarray(img_rgb[:, :, ::-1])
    boxes = inference_detector(det, bgr, detect_classes=[0])
    if boxes is None or len(boxes) == 0:
        return None
    kps, scores = inference_pose(pose, boxes, bgr, POSE_INPUT_SIZE)
    info = np.concatenate((kps, scores[..., None]), axis=-1)
    # шея = середина плеч; перестановка mmpose → openpose
    neck = np.mean(info[:, [5, 6]], axis=1)
    neck[:, 2:4] = np.logical_and(info[:, 5, 2:4] > THRESHOLD, info[:, 6, 2:4] > THRESHOLD).astype(int)
    info = np.insert(info, 17, neck, axis=1)
    mmpose_idx = [17, 6, 8, 10, 7, 9, 12, 14, 16, 13, 15, 2, 1, 4, 3]
    openpose_idx = [1, 2, 3, 4, 6, 7, 8, 9, 10, 12, 13, 14, 15, 16, 17]
    info[:, openpose_idx] = info[:, mmpose_idx]
    return info


def _part(points, W, H):
    out = [(float(x) / W, float(y) / H) if s >= THRESHOLD else None for x, y, s in points]
    return None if all(p is None for p in out) else out


def to_poses(info, W, H):
    poses = []
    if info is None:
        return poses
    for person in info:
        poses.append({
            'body': _part(person[:18], W, H) or [None] * 18,
            'left_hand': _part(person[92:113], W, H),
            'right_hand': _part(person[113:134], W, H),
            'face': _part(person[24:92], W, H),
        })
    return poses


LIMBS = [[2, 3], [2, 6], [3, 4], [4, 5], [6, 7], [7, 8], [2, 9], [9, 10], [10, 11], [2, 12], [12, 13],
         [13, 14], [2, 1], [1, 15], [15, 17], [1, 16], [16, 18]]
COLORS = [[255, 0, 0], [255, 85, 0], [255, 170, 0], [255, 255, 0], [170, 255, 0], [85, 255, 0], [0, 255, 0],
          [0, 255, 85], [0, 255, 170], [0, 255, 255], [0, 170, 255], [0, 85, 255], [0, 0, 255], [85, 0, 255],
          [170, 0, 255], [255, 0, 255], [255, 0, 170], [255, 0, 85]]
HAND_EDGES = [[0, 1], [1, 2], [2, 3], [3, 4], [0, 5], [5, 6], [6, 7], [7, 8], [0, 9], [9, 10], [10, 11], [11, 12],
              [0, 13], [13, 14], [14, 15], [15, 16], [0, 17], [17, 18], [18, 19], [19, 20]]


def draw(poses, W, H, hands=True, face=True, xinsir=True):
    """Скелет на чёрном фоне. xinsir=True — толще палки на больших картинках (как советует xinsir)."""
    canvas = np.zeros((H, W, 3), dtype=np.uint8)
    side = max(W, H)
    scale = (1 if side < 500 else min(2 + side // 1000, 7)) if xinsir else 1
    for p in poses:
        body = p['body']
        for (a, b), color in zip(LIMBS, COLORS):
            k1, k2 = body[a - 1], body[b - 1]
            if k1 is None or k2 is None:
                continue
            Y = np.array([k1[0], k2[0]]) * W
            X = np.array([k1[1], k2[1]]) * H
            length = ((X[0] - X[1]) ** 2 + (Y[0] - Y[1]) ** 2) ** 0.5
            angle = math.degrees(math.atan2(X[0] - X[1], Y[0] - Y[1]))
            poly = cv2.ellipse2Poly((int(np.mean(Y)), int(np.mean(X))), (int(length / 2), 4 * scale), int(angle), 0, 360, 1)
            cv2.fillConvexPoly(canvas, poly, [int(c * 0.6) for c in color])
        for k, color in zip(body, COLORS):
            if k is not None:
                cv2.circle(canvas, (int(k[0] * W), int(k[1] * H)), 4, color, thickness=-1)
        if hands:
            for hand in (p['left_hand'], p['right_hand']):
                if not hand:
                    continue
                for i, (a, b) in enumerate(HAND_EDGES):
                    k1, k2 = hand[a], hand[b]
                    if k1 is None or k2 is None:
                        continue
                    x1, y1, x2, y2 = int(k1[0] * W), int(k1[1] * H), int(k2[0] * W), int(k2[1] * H)
                    if min(x1, y1, x2, y2) > EPS:
                        rgb = [int(c * 255) for c in colorsys.hsv_to_rgb(i / len(HAND_EDGES), 1.0, 1.0)]
                        cv2.line(canvas, (x1, y1), (x2, y2), rgb, thickness=2)
                for k in hand:
                    if k is not None and k[0] * W > EPS and k[1] * H > EPS:
                        cv2.circle(canvas, (int(k[0] * W), int(k[1] * H)), 4, (0, 0, 255), thickness=-1)
        if face and p['face']:
            for k in p['face']:
                if k is not None and k[0] * W > EPS and k[1] * H > EPS:
                    cv2.circle(canvas, (int(k[0] * W), int(k[1] * H)), 3, (255, 255, 255), thickness=-1)
    return canvas


def detect(img_rgb, det_path, pose_path, hands=True, face=True):
    """→ (скелет HxWx3 uint8, позы в долях). Людей не нашлось — чёрная картинка и []."""
    det, pose = _load(det_path, pose_path)
    H, W = img_rgb.shape[:2]
    poses = to_poses(_keypoints(img_rgb, det, pose), W, H)
    print(f'[DWPose] Людей найдено: {len(poses)}')
    return draw(poses, W, H, hands=hands, face=face), poses

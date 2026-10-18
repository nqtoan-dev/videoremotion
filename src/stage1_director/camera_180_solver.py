import math
import numpy as np
from typing import Tuple, Dict, List

def compute_blender_look_at_euler(cam_xyz: np.ndarray, target_xyz: np.ndarray) -> List[float]:
    """
    Tính góc xoay Euler [rx, ry, rz] (đơn vị: độ) theo hệ tọa độ Z-up của Blender.
    Mặc định Camera của Blender khi góc xoay (0, 0, 0) sẽ nhìn thẳng xuống trục -Z, đỉnh máy hướng theo +Y.
    Khi rx = 90 độ, rz = 0 độ, Camera nhìn dọc theo trục +Y.
    """
    delta = target_xyz - cam_xyz
    dist_xy = math.hypot(float(delta[0]), float(delta[1]))

    # Góc quay quanh trục Z (Pan) và trục X (Tilt)
    rz_rad = math.atan2(float(delta[1]), float(delta[0])) - (math.pi / 2.0)
    rz_rad = math.atan2(math.sin(rz_rad), math.cos(rz_rad))
    rx_rad = (math.pi / 2.0) + math.atan2(float(delta[2]), max(dist_xy, 1e-6))

    return [
        round(math.degrees(rx_rad), 2),
        0.0,
        round(math.degrees(rz_rad), 2)
    ]

def compute_actor_facing_z_deg(actor_xyz: List[float], target_xyz: List[float]) -> float:
    """Tính góc xoay Z (độ) để nhân vật đứng ở actor_xyz quay mặt nhìn thẳng vào target_xyz."""
    dx = target_xyz[0] - actor_xyz[0]
    dy = target_xyz[1] - actor_xyz[1]
    angle_rad = math.atan2(dy, dx) - (math.pi / 2.0)
    angle_rad = math.atan2(math.sin(angle_rad), math.cos(angle_rad))
    return round(math.degrees(angle_rad), 2)

def solve_180_degree_camera_rig(
    speaker_xyz: List[float],
    listener_xyz: List[float],
    speaker_height_m: float = 1.72,
    shot_style: str = "OTS_CLOSE_UP",
    locked_side: str = "SIDE_A"
) -> Dict:
    """
    Định vị Camera 3D tự động tuân thủ nghiêm ngặt Quy tắc 180 độ (180-Degree Rule):
    1. Cố định vector trục hành động (Line of Action) từ nhân vật có tọa độ X nhỏ hơn sang nhân vật có X lớn hơn
       để dù đổi vai người nói/người nghe thì pháp tuyến bán cầu `SIDE_A` KHÔNG BAO GIỜ bị đảo chiều.
    2. Đặt tiêu cự từ 50mm đến 85mm cho các cảnh cận/trung cận.
    """
    p_spk = np.array(speaker_xyz, dtype=float)
    p_lst = np.array(listener_xyz, dtype=float)

    # Cố định điểm neo Trái -> Phải trong không gian thế giới để giữ nguyên bán cầu máy quay
    if (p_spk[0], p_spk[1]) <= (p_lst[0], p_lst[1]):
        p_left, p_right = p_spk, p_lst
    else:
        p_left, p_right = p_lst, p_spk

    line_of_action = p_right - p_left
    loa_len = float(np.linalg.norm(line_of_action[:2]))
    loa_unit = line_of_action / loa_len if loa_len > 1e-5 else np.array([1.0, 0.0, 0.0])

    # Pháp tuyến vuông góc với Trục hành động trên mặt phẳng ngang XY
    side_multiplier = -1.0 if locked_side == "SIDE_A" else 1.0
    normal_side_unit = np.array([-loa_unit[1] * side_multiplier, loa_unit[0] * side_multiplier, 0.0])

    eye_z = float(p_spk[2]) + (speaker_height_m * 0.91)
    speaker_eye_pos = np.array([p_spk[0], p_spk[1], eye_z])

    vec_spk_to_lst = p_lst - p_spk
    dist_spk_to_lst = float(np.linalg.norm(vec_spk_to_lst[:2]))
    unit_spk_to_lst = vec_spk_to_lst / max(dist_spk_to_lst, 1e-5)

    if shot_style == "ESTABLISHING_WIDE":
        midpoint = (p_spk + p_lst) * 0.5
        cam_pos = midpoint + (normal_side_unit * 2.8)
        cam_pos[2] = eye_z + 0.12
        look_target = np.array([midpoint[0], midpoint[1], eye_z - 0.08])
        lens_mm = 50.0
        fstop = 2.8
    elif shot_style == "OTS_CLOSE_UP":
        # Đặt máy qua vai người nghe (Over-The-Shoulder), lệch về bán cầu SIDE_A 0.45m
        cam_pos = p_lst - (unit_spk_to_lst * 0.45) + (normal_side_unit * 0.48)
        cam_pos[2] = eye_z
        look_target = speaker_eye_pos
        lens_mm = 75.0
        fstop = 2.0
    else:  # CLOSE_UP (Cận mặt đặc tả cảm xúc)
        cam_pos = p_spk + (unit_spk_to_lst * 1.25) + (normal_side_unit * 0.52)
        cam_pos[2] = eye_z
        look_target = speaker_eye_pos
        lens_mm = 85.0
        fstop = 2.0

    rotation_deg = compute_blender_look_at_euler(cam_pos, look_target)

    return {
        "lens_mm": float(lens_mm),
        "aperture_fstop": float(fstop),
        "line_of_action_side": locked_side,
        "location_xyz": [round(float(c), 3) for c in cam_pos],
        "rotation_euler_deg": rotation_deg
    }

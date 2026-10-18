import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any
from src.stage1_director.camera_180_solver import (
    solve_180_degree_camera_rig,
    compute_actor_facing_z_deg
)
from src.stage1_director.director_analyzer import (
    scan_available_3d_assets,
    build_director_prompt_for_antigravity
)

def generate_storyboard_via_antigravity(
    user_request: str,
    assets_root: Path,
    output_storyboard_path: Path
) -> Dict[str, Any]:
    """
    Gọi `antigravity-cli` làm nhân AI sinh dữ liệu phim, sau đó chạy Bộ giải Toán học 180 độ
    để khóa chính xác góc nhìn nhân vật và tọa độ Camera 3D cho từng cảnh.
    """
    inventory = scan_available_3d_assets(assets_root)
    director_prompt = build_director_prompt_for_antigravity(user_request, inventory)

    cli_executable = shutil.which("antigravity-cli") or "antigravity-cli"
    cmd = [
        cli_executable,
        "chat",
        "--format", "json",
        "--prompt", director_prompt
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")
        raw_text = proc.stdout.strip()

        # Bóc tách khối JSON an toàn nếu đầu ra có lẫn chữ bên ngoài
        first_brace = raw_text.find("{")
        last_brace = raw_text.rfind("}")
        if first_brace == -1 or last_brace == -1:
            raise ValueError(f"antigravity-cli không trả về JSON hợp lệ: {raw_text[:200]}")

        storyboard = json.loads(raw_text[first_brace:last_brace + 1])
    except (FileNotFoundError, subprocess.SubprocessError, ValueError) as err:
        # Fallback tạo kịch bản 2 cảnh quay chuẩn nếu chưa cài đặt antigravity-cli trên máy
        print(f"[CẢNH BÁO] Không thể gọi trực tiếp antigravity-cli ({err}). Kích hoạt bộ tạo kịch bản dự phòng...")
        storyboard = {
            "project_meta": {
                "title": f"Phim Điện Ảnh: {user_request[:30]}",
                "fps": 24,
                "resolution": [1920, 1080],
                "aspect_ratio": "2.35:1",
                "vram_budget_mb": 3200,
                "max_texture_size": 2048,
                "color_management": {
                    "view_transform": "AgX",
                    "look": "AgX - High Contrast",
                    "lut_path": "assets/luts/film_kodak_2383.cube",
                    "film_grain_intensity": 6.5
                }
            },
            "scene": {
                "scene_id": "SCENE_STUDIO_OFFICE",
                "blend_file": inventory["available_scenes"][0],
                "room_tone_file": "assets/audio/room_tone_ambience.wav",
                "room_tone_base_volume": 0.16,
                "volumetric_lighting": True,
                "volumetric_density": 0.03
            },
            "characters": {
                "CHAR_MINH": {
                    "display_name": "Minh",
                    "fbx_path": "assets/characters/char_minh.fbx",
                    "armature_name": "Armature_Minh",
                    "face_mesh_name": "Mesh_Head_Minh",
                    "eye_bone_name": "Bone_Eye_Target",
                    "jaw_bone_name": "Bone_Jaw",
                    "height_m": 1.75,
                    "voice_profile": {
                        "engine": "kokoro_cpu_int8",
                        "voice_preset": "vn_male_baritone",
                        "base_speed": 0.96,
                        "base_pitch_semitones": -1.2
                    }
                },
                "CHAR_LAN": {
                    "display_name": "Lan",
                    "fbx_path": "assets/characters/char_lan.fbx",
                    "armature_name": "Armature_Lan",
                    "face_mesh_name": "Mesh_Head_Lan",
                    "eye_bone_name": "Bone_Eye_Target",
                    "jaw_bone_name": "Bone_Jaw",
                    "height_m": 1.65,
                    "voice_profile": {
                        "engine": "kokoro_cpu_int8",
                        "voice_preset": "vn_female_clear",
                        "base_speed": 1.02,
                        "base_pitch_semitones": 0.8
                    }
                }
            },
            "shots": [
                {
                    "shot_id": "SHOT_001",
                    "shot_style": "OTS_CLOSE_UP",
                    "speaker": "CHAR_MINH",
                    "listener": "CHAR_LAN",
                    "actors": {
                        "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": inventory["available_mixamo_animations"][0]},
                        "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": inventory["available_mixamo_animations"][2]}
                    },
                    "dialogue": {
                        "text": user_request if len(user_request) < 120 else user_request[:120],
                        "emotion": "serious_determined",
                        "speaking_rate_multiplier": 0.95,
                        "pitch_offset_semitones": -0.5
                    }
                },
                {
                    "shot_id": "SHOT_002",
                    "shot_style": "CLOSE_UP",
                    "speaker": "CHAR_LAN",
                    "listener": "CHAR_MINH",
                    "actors": {
                        "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": inventory["available_mixamo_animations"][2]},
                        "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": inventory["available_mixamo_animations"][1]}
                    },
                    "dialogue": {
                        "text": "Tôi hiểu tình hình rồi. Chúng ta hãy thực thi phương án dự phòng ngay lập tức.",
                        "emotion": "urgent",
                        "speaking_rate_multiplier": 1.05,
                        "pitch_offset_semitones": 0.6
                    }
                }
            ]
        }

    # Áp dụng Toán học Điện ảnh: Quy tắc 180 độ & Hướng mặt 2 nhân vật nhìn thẳng vào nhau
    characters = storyboard.get("characters", {})
    prev_speaker = None

    for idx, shot in enumerate(storyboard.get("shots", [])):
        shot_id = shot.get("shot_id", f"SHOT_{idx + 1:03d}")
        shot["shot_id"] = shot_id
        spk_id = shot["speaker"]
        lst_id = shot["listener"]

        spk_pos = shot["actors"][spk_id]["position_xyz"]
        lst_pos = shot["actors"][lst_id]["position_xyz"]

        # Khóa hướng xoay Z để 2 nhân vật luôn nhìn thẳng vào mắt nhau
        shot["actors"][spk_id]["rotation_euler_deg"] = [
            0.0, 0.0, compute_actor_facing_z_deg(spk_pos, lst_pos)
        ]
        shot["actors"][lst_id]["rotation_euler_deg"] = [
            0.0, 0.0, compute_actor_facing_z_deg(lst_pos, spk_pos)
        ]

        # Tính tọa độ Camera 3D theo Quy tắc 180 độ (luôn cố định ở SIDE_A)
        spk_height = float(characters.get(spk_id, {}).get("height_m", 1.72))
        shot_style = shot.get("shot_style", "OTS_CLOSE_UP")
        shot["camera"] = solve_180_degree_camera_rig(
            speaker_xyz=spk_pos,
            listener_xyz=lst_pos,
            speaker_height_m=spk_height,
            shot_style=shot_style,
            locked_side="SIDE_A"
        )

        # Tự động bật Rack Focus (trượt nét từ người vừa nói sang người mới nói)
        if prev_speaker and prev_speaker != spk_id:
            shot["rack_focus"] = {
                "enabled": True,
                "from_character": prev_speaker,
                "to_character": spk_id,
                "start_sec": 0.15,
                "end_sec": 0.75
            }
        prev_speaker = spk_id

        # Chuẩn hóa đường dẫn đầu ra cho Tầng 2, 3, 4
        shot["dialogue"]["wav_path"] = f"workspace/audio_wav/{shot_id}.wav"
        shot["dialogue"]["viseme_json_path"] = f"workspace/visemes/{shot_id}_visemes.json"
        shot["transition"] = {
            "cut_type": "J_CUT",
            "audio_overlap_sec": 0.3,
            "raw_render_path": f"workspace/raw_renders/{shot_id}_raw.mp4"
        }

    output_storyboard_path.parent.mkdir(parents=True, exist_ok=True)
    output_storyboard_path.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return storyboard

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, List
from src.stage1_director.director_analyzer import (
    scan_available_3d_assets,
    build_director_prompt_for_antigravity,
)
from src.stage1_director.camera_180_solver import (
    solve_180_degree_camera_rig,
    compute_actor_facing_z_deg,
)


def _builtin_director_fallback(user_request: str, inventory: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ông Đạo Diễn nội tại: Khi antigravity-cli chưa được cài trong PATH hoặc gặp lỗi kết nối,
    tự động phân tích yêu cầu của người dùng để sinh kịch bản phân cảnh điện ảnh chi tiết.
    """
    clean_req = user_request.strip() or "Cuộc đối thoại căng thẳng trong phòng máy chủ"
    # Tách ý hoặc tạo 3 phân cảnh chuẩn cấu trúc 3 hồi (Thiết lập -> Cao trào -> Kết luận)
    sentences = [s.strip() for s in re.split(r"[.!?\n]+", clean_req) if len(s.strip()) > 5]

    if len(sentences) >= 3:
        line_1 = sentences[0]
        line_2 = sentences[1]
        line_3 = " ".join(sentences[2:])
    elif len(sentences) == 2:
        line_1 = f"Về vấn đề {sentences[0]}, chúng ta phải đưa ra quyết định ngay bây giờ."
        line_2 = f"Tôi hiểu, nhưng {sentences[1]} đòi hỏi sự chính xác tuyệt đối ở từng chi tiết."
        line_3 = "Vậy hãy khóa toàn bộ thông số và kích hoạt hệ thống theo đúng phương án này."
    else:
        line_1 = f"Chúng ta cần giải quyết ngay bài toán: {clean_req}."
        line_2 = "Mọi thông số bối cảnh và dữ liệu 3D đã được khóa đồng bộ một trăm phần trăm."
        line_3 = "Bắt đầu tiến trình kết xuất điện ảnh ngay lập tức, không để xảy ra bất kỳ sai số nào."

    scenes = inventory.get("available_scenes", ["assets/scenes/studio_office.blend"])
    anims = inventory.get("available_mixamo_animations", [
        "assets/animations/standing_talking_01.fbx",
        "assets/animations/standing_explaining_02.fbx",
        "assets/animations/standing_listening_idle.fbx",
    ])
    luts = inventory.get("available_luts", ["assets/luts/film_kodak_2383.cube"])

    anim_talk = anims[0] if len(anims) > 0 else "assets/animations/standing_talking_01.fbx"
    anim_explain = anims[1] if len(anims) > 1 else anim_talk
    anim_listen = anims[2] if len(anims) > 2 else anim_talk

    return {
        "project_meta": {
            "title": clean_req[:60].title(),
            "fps": 24,
            "resolution": [1920, 1080],
            "aspect_ratio": "2.35:1",
            "vram_budget_mb": 3200,
            "max_texture_size": 2048,
            "color_management": {
                "view_transform": "AgX",
                "look": "AgX - High Contrast",
                "lut_path": luts[0],
                "film_grain_intensity": 6.5,
            },
        },
        "scene": {
            "scene_id": "SCENE_STUDIO_OFFICE",
            "blend_file": scenes[0],
            "room_tone_file": "assets/audio/room_tone_ambience.wav",
            "room_tone_base_volume": 0.16,
            "volumetric_lighting": True,
            "volumetric_density": 0.03,
            "instanced_props": [
                {
                    "source_object_name": "Prop_Chair_Master",
                    "instance_locations": [[-2.2, 1.4, 0.0], [-2.2, -1.4, 0.0], [2.2, 1.4, 0.0]],
                }
            ],
        },
        "characters": {
            "CHAR_MINH": {
                "display_name": "Minh (Đạo diễn Kỹ thuật)",
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
                    "base_pitch_semitones": -1.2,
                },
            },
            "CHAR_LAN": {
                "display_name": "Lan (Chuyên gia Hệ thống)",
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
                    "base_pitch_semitones": 1.0,
                },
            },
        },
        "shots": [
            {
                "shot_id": "SHOT_001",
                "shot_style": "ESTABLISHING_WIDE",
                "speaker": "CHAR_MINH",
                "listener": "CHAR_LAN",
                "actors": {
                    "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": anim_explain},
                    "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": anim_listen},
                },
                "dialogue": {
                    "text": line_1,
                    "emotion": "serious_determined",
                    "speaking_rate_multiplier": 0.96,
                    "pitch_offset_semitones": -0.8,
                },
            },
            {
                "shot_id": "SHOT_002",
                "shot_style": "OTS_CLOSE_UP",
                "speaker": "CHAR_LAN",
                "listener": "CHAR_MINH",
                "actors": {
                    "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": anim_listen},
                    "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": anim_talk},
                },
                "dialogue": {
                    "text": line_2,
                    "emotion": "urgent",
                    "speaking_rate_multiplier": 1.04,
                    "pitch_offset_semitones": 0.6,
                },
            },
            {
                "shot_id": "SHOT_003",
                "shot_style": "CLOSE_UP",
                "speaker": "CHAR_MINH",
                "listener": "CHAR_LAN",
                "actors": {
                    "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": anim_talk},
                    "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": anim_listen},
                },
                "dialogue": {
                    "text": line_3,
                    "emotion": "calm",
                    "speaking_rate_multiplier": 0.95,
                    "pitch_offset_semitones": -1.0,
                },
            },
        ],
    }


def generate_storyboard_via_antigravity(
    user_request: str,
    assets_root: Path,
    output_storyboard_path: Path,
) -> Dict[str, Any]:
    """
    Gọi `antigravity-cli` làm nhân AI sinh dữ liệu phim (kèm cơ chế fallback thông minh nếu CLI lỗi),
    sau đó chạy Bộ giải Toán học 180 độ để khóa chính xác góc nhìn nhân vật và tọa độ Camera 3D.
    """
    inventory = scan_available_3d_assets(assets_root)
    director_prompt = build_director_prompt_for_antigravity(user_request, inventory)

    cli_executable = shutil.which("antigravity-cli") or "antigravity-cli"
    cmd = [cli_executable, "chat", "--format", "json", "--prompt", director_prompt]

    storyboard = None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8", timeout=60)
        raw_text = proc.stdout.strip()
        first_brace = raw_text.find("{")
        last_brace = raw_text.rfind("}")
        if first_brace != -1 and last_brace != -1:
            storyboard = json.loads(raw_text[first_brace : last_brace + 1])
    except Exception as exc:
        print(f"[STAGE 1] Chuyển sang Bộ Đạo Diễn Nội Tại (Lý do: {exc})")
        storyboard = _builtin_director_fallback(user_request, inventory)

    if not storyboard or "shots" not in storyboard:
        storyboard = _builtin_director_fallback(user_request, inventory)

    characters = storyboard.get("characters", {})
    prev_speaker = None

    for idx, shot in enumerate(storyboard.get("shots", [])):
        shot_id = shot.get("shot_id", f"SHOT_{idx + 1:03d}")
        shot["shot_id"] = shot_id
        spk_id = shot["speaker"]
        lst_id = shot["listener"]

        spk_pos = shot["actors"][spk_id]["position_xyz"]
        lst_pos = shot["actors"][lst_id]["position_xyz"]

        shot["actors"][spk_id]["rotation_euler_deg"] = [
            0.0, 0.0, compute_actor_facing_z_deg(spk_pos, lst_pos)
        ]
        shot["actors"][lst_id]["rotation_euler_deg"] = [
            0.0, 0.0, compute_actor_facing_z_deg(lst_pos, spk_pos)
        ]

        spk_height = float(characters.get(spk_id, {}).get("height_m", 1.72))
        shot_style = shot.get("shot_style", "OTS_CLOSE_UP")
        shot["camera"] = solve_180_degree_camera_rig(
            speaker_xyz=spk_pos,
            listener_xyz=lst_pos,
            speaker_height_m=spk_height,
            shot_style=shot_style,
            locked_side="SIDE_A",
        )

        if prev_speaker and prev_speaker != spk_id:
            shot["rack_focus"] = {
                "enabled": True,
                "from_character": prev_speaker,
                "to_character": spk_id,
                "start_sec": 0.15,
                "end_sec": 0.75,
            }
        elif "rack_focus" not in shot:
            shot["rack_focus"] = {
                "enabled": False,
                "from_character": spk_id,
                "to_character": spk_id,
                "start_sec": 0.0,
                "end_sec": 0.5,
            }
        prev_speaker = spk_id

        shot["dialogue"]["wav_path"] = f"workspace/audio_wav/{shot_id}.wav"
        shot["dialogue"]["viseme_json_path"] = f"workspace/visemes/{shot_id}_visemes.json"
        shot["transition"] = {
            "cut_type": "J_CUT",
            "audio_overlap_sec": 0.3,
            "raw_render_path": f"workspace/raw_renders/{shot_id}_raw.mp4",
        }

    output_storyboard_path.parent.mkdir(parents=True, exist_ok=True)
    output_storyboard_path.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return storyboard

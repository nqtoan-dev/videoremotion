import os
import re
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any, Optional, List
from src.stage1_director.director_analyzer import (
    scan_available_3d_assets,
    build_director_prompt_for_antigravity,
)
from src.stage1_director.camera_180_solver import (
    solve_180_degree_camera_rig,
    compute_actor_facing_z_deg,
)


def _get_antigravity_2_candidate_paths() -> List[Path]:
    """
    Danh sách các đường dẫn cấu hình chuẩn nơi Antigravity 2.0 (Desktop IDE & CLI)
    lưu trữ phiên đăng nhập (OAuth Token / Session / Account Info) trên máy người dùng.
    """
    home = Path.home()
    appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
    localappdata = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    xdg_config = Path(os.environ.get("XDG_CONFIG_HOME", str(home / ".config")))

    return [
        # Chuẩn thư mục .antigravity tại HOME
        home / ".antigravity" / "auth.json",
        home / ".antigravity" / "session.json",
        home / ".antigravity" / "credentials.json",
        home / ".antigravity" / "config.json",
        home / ".antigravity-2.0" / "auth.json",
        # Chuẩn Antigravity 2.0 trên Windows (%APPDATA% & %LOCALAPPDATA%)
        appdata / "Antigravity" / "auth.json",
        appdata / "Antigravity" / "session.json",
        appdata / "Antigravity" / "User" / "globalStorage" / "storage.json",
        appdata / "Antigravity 2.0" / "auth.json",
        localappdata / "Antigravity" / "auth.json",
        localappdata / "Antigravity" / "credentials.json",
        # Chuẩn Antigravity 2.0 trên Linux (~/.config)
        xdg_config / "Antigravity" / "auth.json",
        xdg_config / "Antigravity" / "User" / "globalStorage" / "storage.json",
        xdg_config / "antigravity" / "auth.json",
        xdg_config / "antigravity-2.0" / "auth.json",
        # Chuẩn Antigravity 2.0 trên macOS
        home / "Library" / "Application Support" / "Antigravity" / "auth.json",
        home / "Library" / "Application Support" / "Antigravity" / "User" / "globalStorage" / "storage.json",
    ]


def _extract_token_and_account_from_json(data: Any) -> Optional[Dict[str, str]]:
    """
    Đệ quy trích xuất token xác thực (access_token, session_token, api_key, id_token)
    và định danh người dùng (email, account, user, username) từ cấu trúc JSON của Antigravity 2.0.
    """
    if not isinstance(data, dict):
        return None

    token_keys = (
        "access_token",
        "accessToken",
        "session_token",
        "sessionToken",
        "auth_token",
        "authToken",
        "id_token",
        "api_key",
        "apiKey",
        "token",
    )
    user_keys = ("email", "username", "user_email", "account_name", "account", "name", "user")

    found_token = None
    found_user = None

    for tk in token_keys:
        val = data.get(tk)
        if isinstance(val, str) and len(val.strip()) >= 8:
            found_token = val.strip()
            break

    for uk in user_keys:
        val = data.get(uk)
        if isinstance(val, str) and len(val.strip()) >= 2:
            found_user = val.strip()
            break
        elif isinstance(val, dict):
            nested_email = val.get("email") or val.get("name") or val.get("username")
            if isinstance(nested_email, str) and nested_email.strip():
                found_user = nested_email.strip()
                break

    # Tìm trong các khóa lồng nhau của Antigravity 2.0 (ví dụ: "antigravity.auth", "sessions", "account")
    if not found_token:
        for k, v in data.items():
            if isinstance(v, dict):
                sub = _extract_token_and_account_from_json(v)
                if sub and sub.get("token"):
                    found_token = sub["token"]
                    found_user = found_user or sub.get("account")
                    break
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        sub = _extract_token_and_account_from_json(item)
                        if sub and sub.get("token"):
                            found_token = sub["token"]
                            found_user = found_user or sub.get("account")
                            break

    if found_token:
        return {
            "token": found_token,
            "account": found_user or "Antigravity 2.0 Local User",
        }
    return None


def resolve_antigravity_cli_binary() -> Optional[str]:
    """Dò tìm binary của Antigravity CLI (hỗ trợ cả `antigravity-cli` và `antigravity` bản 2.0)."""
    for bin_name in ("antigravity-cli", "antigravity", "ag"):
        found = shutil.which(bin_name)
        if found:
            return found

    # Quét thêm các thư mục cài đặt cục bộ phổ biến của Antigravity 2.0 trên máy người dùng
    home = Path.home()
    localappdata = Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")))
    extra_bins = [
        localappdata / "Programs" / "Antigravity" / "bin" / "antigravity-cli.exe",
        localappdata / "Programs" / "Antigravity" / "bin" / "antigravity.exe",
        home / ".antigravity" / "bin" / "antigravity-cli",
        home / ".local" / "bin" / "antigravity-cli",
    ]
    for p in extra_bins:
        if p.exists():
            return str(p)
    return None


def discover_and_bind_antigravity_2_auth() -> Dict[str, Any]:
    """
    Tự động kiểm tra và kế thừa phiên đăng nhập của người dùng từ Antigravity 2.0 trên máy:
    1. Kiểm tra biến môi trường hoặc file cấu hình Antigravity 2.0 đã đăng nhập.
    2. Nếu tìm thấy phiên của Antigravity 2.0 mà CLI chưa có `~/.antigravity/auth.json`,
       tự động đồng bộ sang `~/.antigravity/auth.json` để `antigravity-cli` tự động đăng nhập.
    3. Kiểm tra thêm lệnh `auth status` của CLI nếu có.
    """
    # 1. Kiểm tra biến môi trường sẵn có trên máy
    for env_key in ("ANTIGRAVITY_TOKEN", "ANTIGRAVITY_ACCESS_TOKEN", "ANTIGRAVITY_API_KEY"):
        env_val = os.environ.get(env_key, "").strip()
        if env_val:
            return {
                "authenticated": True,
                "method": f"Environment ({env_key})",
                "account": os.environ.get("ANTIGRAVITY_USER", "Local Logged-in User"),
                "token": env_val,
                "source_path": "os.environ",
            }

    # 2. Quét các file lưu phiên đăng nhập của Antigravity 2.0 trên máy người dùng
    for candidate_path in _get_antigravity_2_candidate_paths():
        if not candidate_path.exists():
            continue
        try:
            raw_content = candidate_path.read_text(encoding="utf-8", errors="ignore")
            json_data = json.loads(raw_content)
            extracted = _extract_token_and_account_from_json(json_data)
            if extracted and extracted.get("token"):
                # Tự động đồng bộ sang ~/.antigravity/auth.json cho antigravity-cli nếu chưa tồn tại
                cli_auth_file = Path.home() / ".antigravity" / "auth.json"
                if candidate_path.resolve() != cli_auth_file.resolve() and not cli_auth_file.exists():
                    try:
                        cli_auth_file.parent.mkdir(parents=True, exist_ok=True)
                        cli_auth_file.write_text(
                            json.dumps(
                                {
                                    "access_token": extracted["token"],
                                    "account": extracted["account"],
                                    "synced_from": str(candidate_path),
                                    "version": "2.0",
                                },
                                ensure_ascii=False,
                                indent=2,
                            ),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass

                return {
                    "authenticated": True,
                    "method": "Antigravity 2.0 Local Session (Auto-SSO)",
                    "account": extracted["account"],
                    "token": extracted["token"],
                    "source_path": str(candidate_path),
                }
        except Exception:
            continue

    # 3. Kiểm tra trực tiếp qua CLI `auth status` (nếu Antigravity 2.0 lưu trong OS Keychain / Credential Manager)
    cli_bin = resolve_antigravity_cli_binary()
    if cli_bin:
        try:
            proc = subprocess.run(
                [cli_bin, "auth", "status"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
            )
            out = (proc.stdout + "\n" + proc.stderr).strip()
            if proc.returncode == 0 and out and "not logged in" not in out.lower():
                return {
                    "authenticated": True,
                    "method": "Antigravity 2.0 OS Keychain",
                    "account": out.splitlines()[0][:60],
                    "token": "KEYCHAIN_MANAGED",
                    "source_path": cli_bin,
                }
        except Exception:
            pass

    return {
        "authenticated": False,
        "method": "Built-in Director Core (Offline Ready)",
        "account": "Chưa phát hiện phiên Antigravity 2.0",
        "token": None,
        "source_path": None,
    }


def _build_authenticated_subprocess_env(auth_info: Dict[str, Any]) -> Dict[str, str]:
    """Tạo môi trường thực thi kế thừa đầy đủ phiên đăng nhập Antigravity 2.0 cho tiến trình con."""
    env = os.environ.copy()
    token = auth_info.get("token")
    if token and token != "KEYCHAIN_MANAGED":
        env["ANTIGRAVITY_TOKEN"] = token
        env["ANTIGRAVITY_ACCESS_TOKEN"] = token
        env["ANTIGRAVITY_API_KEY"] = token
    if auth_info.get("source_path") and auth_info["source_path"] != "os.environ":
        env["ANTIGRAVITY_AUTH_FILE"] = str(auth_info["source_path"])
    return env


def _builtin_director_fallback(user_request: str, inventory: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ông Đạo Diễn nội tại: Khi antigravity-cli chưa được cài trong PATH hoặc gặp lỗi kết nối,
    tự động phân tích yêu cầu của người dùng để sinh kịch bản phân cảnh điện ảnh chi tiết.
    """
    clean_req = user_request.strip() or "Cuộc đối thoại căng thẳng trong phòng máy chủ"
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
    Tự động nạp phiên đăng nhập từ Antigravity 2.0 trên máy người dùng,
    gọi `antigravity-cli` sinh dữ liệu phim và khóa góc máy theo Quy tắc 180 độ.
    """
    inventory = scan_available_3d_assets(assets_root)
    director_prompt = build_director_prompt_for_antigravity(user_request, inventory)

    # Tự động phát hiện và kế thừa tài khoản Antigravity 2.0 đã đăng nhập trên máy
    auth_info = discover_and_bind_antigravity_2_auth()
    auth_env = _build_authenticated_subprocess_env(auth_info)

    cli_executable = resolve_antigravity_cli_binary() or "antigravity-cli"
    cmd = [cli_executable, "chat", "--format", "json", "--prompt", director_prompt]

    storyboard = None
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True,
            encoding="utf-8",
            timeout=60,
            env=auth_env,
        )
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

    # Lưu thông tin xác thực Antigravity 2.0 vào project_meta để hiển thị trên UI
    storyboard.setdefault("project_meta", {})["antigravity_auth"] = {
        "authenticated": auth_info["authenticated"],
        "method": auth_info["method"],
        "account": auth_info["account"],
    }

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

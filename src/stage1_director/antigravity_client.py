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
    """Use a known story or the user's supplied script, never generic demo dialogue."""
    from src.stage1_director.director_analyzer import (
        generate_thach_sanh_storyboard, generate_thanh_giong_storyboard,
    )
    request = user_request.strip()
    normalized = request.casefold()
    source = "local_story"
    explicit_script = re.search(r"(?:kịch bản|lời kể|lời thoại|script)\s*:\s*(.+)", request, re.I | re.S)
    if not explicit_script and ("thánh gióng" in normalized or "thanh giong" in normalized):
        story = generate_thanh_giong_storyboard()
    elif not explicit_script and ("thạch sanh" in normalized or "thach sanh" in normalized):
        story = generate_thach_sanh_storyboard(request)
    else:
        source = "user_script"
        # A supplied script can be narrated verbatim. A topic requires an AI director.
        if not explicit_script:
            raise RuntimeError(
                "Chưa kết nối bộ viết kịch bản AI cho chủ đề này. Kết nối Antigravity CLI "
                "hoặc nhập 'Kịch bản:' kèm nội dung đầy đủ. Hiện hỗ trợ bản kể Thánh Gióng và Thạch Sanh."
            )
        paragraphs = [line.strip() for line in re.split(r"\n+|(?<=[.!?])\s+", explicit_script[1]) if line.strip()]
        story = {"project_title": "Kịch bản của bạn", "shots": [
            {"shot_id": f"SHOT_{i:03d}", "scene_title": f"Cảnh {i}",
             "dialogue": line, "visual_theme": "studio_tech"}
            for i, line in enumerate(paragraphs, 1)
        ]}
    scenes = inventory.get("available_scenes") or [""]
    animations = inventory.get("available_mixamo_animations") or [""]
    luts = inventory.get("available_luts") or [""]
    shots = []
    for i, beat in enumerate(story["shots"]):
        shot = dict(beat)
        shot.update({
            "speaker": "NARRATOR", "listener": "LISTENER",
            "shot_style": "ESTABLISHING_WIDE" if i == 0 else "OTS_CLOSE_UP",
            "actors": {
                "NARRATOR": {"position_xyz": [-1.1, 0, 0], "mixamo_animation": animations[0]},
                "LISTENER": {"position_xyz": [1.1, 0, 0], "mixamo_animation": animations[0]},
            },
            "dialogue": {"text": beat["dialogue"], "emotion": "calm", "speaking_rate_multiplier": 1.0},
        })
        shots.append(shot)
    return {
        "project_meta": {
            "title": story["project_title"], "fps": 24, "resolution": [1920, 1080],
            "aspect_ratio": "2.35:1", "director_source": source,
            "render_mode": "illustrated_2d",
            "generation_notice": "Video minh họa 2D có chuyển động và giọng đọc. " + ("Bản kể có sẵn." if source == "local_story" else "Dùng nội dung lời kể bạn đã nhập."),
            "color_management": {"lut_path": luts[0], "film_grain_intensity": 0},
        },
        "scene": {"blend_file": scenes[0], "room_tone_file": "", "room_tone_base_volume": 0.12},
        "characters": {
            "NARRATOR": {"display_name": "Người kể chuyện", "height_m": 1.75,
                         "voice_profile": {"voice_preset": "vi-VN-NamMinhNeural"}},
            "LISTENER": {"display_name": "Người nghe", "height_m": 1.65,
                         "voice_profile": {"voice_preset": "vi-VN-HoaiMyNeural"}},
        },
        "shots": shots,
    }


def validate_storyboard(storyboard: Dict[str, Any]):
    if not isinstance(storyboard, dict) or not isinstance(storyboard.get("project_meta"), dict):
        raise ValueError("Kịch bản thiếu thông tin dự án.")
    if not isinstance(storyboard.get("scene"), dict) or not isinstance(storyboard.get("characters"), dict):
        raise ValueError("Kịch bản thiếu bối cảnh hoặc nhân vật.")
    shots = storyboard.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("Kịch bản chưa có cảnh quay.")
    seen = set()
    for i, shot in enumerate(shots, 1):
        shot_id = shot.get("shot_id", f"SHOT_{i:03d}")
        if not isinstance(shot_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", shot_id) or shot_id in seen:
            raise ValueError("Mã cảnh quay không hợp lệ hoặc trùng nhau.")
        seen.add(shot_id)
        dialogue = shot.get("dialogue")
        text = dialogue.get("text") if isinstance(dialogue, dict) else dialogue
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Cảnh {shot_id} chưa có lời thoại.")
        for role in ("speaker", "listener"):
            actor_id = shot.get(role)
            if actor_id not in storyboard["characters"] or actor_id not in shot.get("actors", {}):
                raise ValueError(f"Cảnh {shot_id} thiếu nhân vật {role}.")
            position = shot["actors"][actor_id].get("position_xyz")
            if not isinstance(position, list) or len(position) != 3:
                raise ValueError(f"Cảnh {shot_id} thiếu vị trí nhân vật.")


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
        validate_storyboard(storyboard)
        storyboard["project_meta"]["director_source"] = "antigravity"
    except Exception as exc:
        print(f"[STAGE 1] Chuyển sang Bộ Đạo Diễn Nội Tại (Lý do: {exc})")
        storyboard = _builtin_director_fallback(user_request, inventory)

    if not storyboard:
        storyboard = _builtin_director_fallback(user_request, inventory)
    validate_storyboard(storyboard)
    storyboard["project_meta"]["user_request"] = user_request

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
        if "scene_title" not in shot:
            shot["scene_title"] = f"Phân Cảnh {idx + 1}"
        if "visual_theme" not in shot:
            shot["visual_theme"] = "studio_tech"
        if "sky_color" not in shot:
            shot["sky_color"] = [0.15, 0.22, 0.32]
        if "ground_color" not in shot:
            shot["ground_color"] = [0.18, 0.16, 0.20]

        if isinstance(shot.get("dialogue"), str):
            shot["dialogue"] = {
                "text": shot["dialogue"],
                "emotion": "serious_determined",
                "speaking_rate_multiplier": 1.0,
                "pitch_offset_semitones": 0.0,
            }

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

        run_dir = output_storyboard_path.parent.resolve()
        shot["status"] = "planned"
        shot["dialogue"]["wav_path"] = (run_dir / "audio_wav" / f"{shot_id}.wav").as_posix()
        shot["dialogue"]["viseme_json_path"] = (run_dir / "visemes" / f"{shot_id}_visemes.json").as_posix()
        shot["transition"] = {
            "cut_type": "J_CUT",
            "audio_overlap_sec": 0.3,
            "raw_render_path": (run_dir / "raw_renders" / f"{shot_id}_raw.mp4").as_posix(),
        }

    from src.stage1_director.director_analyzer import write_storyboard
    write_storyboard(output_storyboard_path, storyboard)
    return storyboard

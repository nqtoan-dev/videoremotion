import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.stage1_director.antigravity_client import (
    generate_storyboard_via_antigravity,
    discover_and_bind_antigravity_2_auth,
)

MOCK_CLI_JSON = {
    "project_meta": {
        "title": "Test Movie",
        "fps": 24,
        "resolution": [1920, 1080],
        "aspect_ratio": "2.35:1",
        "vram_budget_mb": 3200,
        "max_texture_size": 2048,
        "color_management": {
            "view_transform": "AgX",
            "look": "AgX - High Contrast",
            "lut_path": "assets/luts/film_kodak_2383.cube",
            "film_grain_intensity": 6.0
        }
    },
    "scene": {
        "scene_id": "SCENE_01",
        "blend_file": "assets/scenes/studio_office.blend",
        "room_tone_file": "assets/audio/room_tone_ambience.wav",
        "room_tone_base_volume": 0.16
    },
    "characters": {
        "CHAR_MINH": {"height_m": 1.75, "voice_profile": {"engine": "kokoro_cpu_int8"}},
        "CHAR_LAN": {"height_m": 1.65, "voice_profile": {"engine": "kokoro_cpu_int8"}}
    },
    "shots": [
        {
            "shot_id": "SHOT_001",
            "shot_style": "OTS_CLOSE_UP",
            "speaker": "CHAR_MINH",
            "listener": "CHAR_LAN",
            "actors": {
                "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": "a.fbx"},
                "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": "b.fbx"}
            },
            "dialogue": {"text": "Câu thoại số 1.", "emotion": "serious"}
        },
        {
            "shot_id": "SHOT_002",
            "shot_style": "CLOSE_UP",
            "speaker": "CHAR_LAN",
            "listener": "CHAR_MINH",
            "actors": {
                "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": "b.fbx"},
                "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": "a.fbx"}
            },
            "dialogue": {"text": "Câu thoại số 2 đáp lại.", "emotion": "urgent"}
        }
    ]
}

def test_stage1_180_degree_rule_and_manifest(tmp_path: Path):
    out_storyboard = tmp_path / "storyboard.json"
    mock_proc = MagicMock()
    mock_proc.stdout = json.dumps(MOCK_CLI_JSON, ensure_ascii=False)

    with patch("subprocess.run", return_value=mock_proc):
        data = generate_storyboard_via_antigravity(
            user_request="Tạo phim đối thoại 2 kỹ sư",
            assets_root=tmp_path,
            output_storyboard_path=out_storyboard
        )

    assert out_storyboard.exists()
    s1_cam_y = data["shots"][0]["camera"]["location_xyz"][1]
    s2_cam_y = data["shots"][1]["camera"]["location_xyz"][1]

    # Cả 2 cảnh quay phải nằm cùng một phía bán cầu (cùng dấu Y) theo Quy tắc 180 độ
    assert s1_cam_y < 0 and s2_cam_y < 0
    # Tiêu cự ống kính cận cảnh phải nằm trong dải 50mm - 85mm
    assert 50.0 <= data["shots"][0]["camera"]["lens_mm"] <= 85.0
    assert 50.0 <= data["shots"][1]["camera"]["lens_mm"] <= 85.0
    # Cảnh 2 đổi người nói phải tự động kích hoạt Rack Focus
    assert data["shots"][1]["rack_focus"]["enabled"] is True


def test_antigravity_2_auto_login_from_local_machine_session(tmp_path: Path, monkeypatch):
    # Giả lập người dùng đã đăng nhập sẵn vào Antigravity 2.0 trên máy (lưu tại AppData/Antigravity/User/globalStorage/storage.json)
    fake_appdata = tmp_path / "AppData" / "Roaming"
    storage_file = fake_appdata / "Antigravity" / "User" / "globalStorage" / "storage.json"
    storage_file.parent.mkdir(parents=True, exist_ok=True)
    storage_file.write_text(
        json.dumps({
            "antigravity.auth": {
                "accessToken": "ag2_live_session_token_99887766",
                "account": {"email": "director@antigravity2.local"}
            }
        }),
        encoding="utf-8"
    )

    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    monkeypatch.setenv("APPDATA", str(fake_appdata))
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("ANTIGRAVITY_TOKEN", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("ANTIGRAVITY_API_KEY", raising=False)

    auth_info = discover_and_bind_antigravity_2_auth()

    assert auth_info["authenticated"] is True
    assert auth_info["token"] == "ag2_live_session_token_99887766"
    assert auth_info["account"] == "director@antigravity2.local"
    # Kiểm tra file ~/.antigravity/auth.json đã được tự động đồng bộ cho antigravity-cli
    synced_cli_auth = tmp_path / ".antigravity" / "auth.json"
    assert synced_cli_auth.exists()

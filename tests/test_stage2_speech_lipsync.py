import os
import json
from pathlib import Path
from unittest.mock import patch
from src.stage2_speech_lipsync.cpu_tts_generator import synthesize_dialogue_cpu_xeon
from src.stage2_speech_lipsync.rhubarb_lipsync import run_rhubarb_lipsync_on_xeon

def test_stage2_zero_vram_tts_and_rhubarb_mapping(tmp_path: Path):
    # 1. Đảm bảo GPU bị khóa hoàn toàn ở Tầng 2 (0 MB VRAM)
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""

    wav_out = tmp_path / "SHOT_001.wav"
    viseme_out = tmp_path / "SHOT_001_visemes.json"

    dialogue_cfg = {
        "text": "Một bộ phim điện ảnh cần khẩu hình khớp từng phần trăm giây.",
        "emotion": "serious_determined",
        "speaking_rate_multiplier": 1.0,
        "pitch_offset_semitones": -1.0
    }
    voice_profile = {"base_speed": 1.0, "base_pitch_semitones": -0.5}

    with patch("shutil.which", return_value=None):
        synthesize_dialogue_cpu_xeon(dialogue_cfg, voice_profile, wav_out)

    assert wav_out.exists() and wav_out.stat().st_size > 8000

    # 2. Kiểm tra phân tích khẩu hình Rhubarb sang 5 nhóm A, O, E, M, F
    fake_rhubarb_output = {
        "metadata": {"duration": 1.60},
        "mouthCues": [
            {"start": 0.00, "end": 0.18, "value": "A"},  # -> M
            {"start": 0.18, "end": 0.52, "value": "D"},  # -> A
            {"start": 0.52, "end": 0.88, "value": "E"},  # -> O
            {"start": 0.88, "end": 1.22, "value": "C"},  # -> E
            {"start": 1.22, "end": 1.60, "value": "G"}   # -> F
        ]
    }

    def fake_rhubarb_cmd(cmd, check=True):
        out_idx = cmd.index("-o") + 1
        Path(cmd[out_idx]).write_text(json.dumps(fake_rhubarb_output), encoding="utf-8")

    with patch("subprocess.run", side_effect=fake_rhubarb_cmd):
        viseme_data = run_rhubarb_lipsync_on_xeon(wav_out, viseme_out, fps=24)

    shapes = [kf["mouth_shape"] for kf in viseme_data["keyframes"]]
    assert shapes == ["M", "A", "O", "E", "F"]
    assert viseme_data["keyframes"][1]["weights"]["shape_A"] == 1.0
    assert viseme_data["keyframes"][2]["weights"]["shape_O"] == 1.0

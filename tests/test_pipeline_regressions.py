import copy
import json
import math
import shutil
import subprocess
import wave
from array import array
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import HTTPException

from src.main_orchestrator import verify_final_video
from src.stage1_director.antigravity_client import _builtin_director_fallback, generate_storyboard_via_antigravity
from src.stage1_director.director_analyzer import scan_available_3d_assets
from src.stage2_speech_lipsync.cpu_tts_generator import generate_vietnamese_tts, validate_speech_wav
from src.stage4_post_nvenc.ffmpeg_nvenc_editor import assemble_final_cinematic_movie


FFMPEG = pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg required")


def run(*args):
    return subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *map(str, args)], check=True, capture_output=True)


def wav(path, duration=1.2, silent=False):
    samples = array("h", (0 if silent else int(10000 * math.sin(2 * math.pi * 440 * i / 24000)) for i in range(int(24000 * duration))))
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(24000)
        f.writeframes(samples.tobytes())


def test_offline_director_uses_correct_story_and_preserves_all_script_scenes():
    story = _builtin_director_fallback("Tạo truyện Thánh Gióng", {})
    assert len(story["shots"]) == 8
    assert all(s["visual_theme"].startswith("giong_") for s in story["shots"])
    assert "Phù Đổng" in story["shots"][0]["dialogue"]["text"]
    assert "tre" in story["shots"][5]["dialogue"]["text"]
    assert "2D" in story["project_meta"]["generation_notice"]
    script = "Kịch bản:\n" + "\n".join(f"Đây là nội dung cảnh thứ {n}." for n in range(7))
    data = _builtin_director_fallback(script, {})
    assert len(data["shots"]) == 7
    assert data["shots"][-1]["dialogue"]["text"] == "Đây là nội dung cảnh thứ 6."
    custom = _builtin_director_fallback("Kịch bản: Thánh Gióng trong lời kể riêng của tôi.", {})
    assert len(custom["shots"]) == 1
    assert custom["shots"][0]["dialogue"]["text"] == "Thánh Gióng trong lời kể riêng của tôi."
    with pytest.raises(RuntimeError, match="Chưa kết nối"):
        _builtin_director_fallback("Tạo phim về Sao Hỏa", {})


def test_placeholder_assets_are_not_advertised(tmp_path):
    for folder, suffix in [("scenes", ".blend"), ("characters", ".fbx"), ("animations", ".fbx")]:
        root = tmp_path / folder
        root.mkdir()
        (root / ("demo" + suffix)).write_text("CINE_CODE_PLACEHOLDER")
    inventory = scan_available_3d_assets(tmp_path)
    assert inventory["available_scenes"] == []
    assert inventory["available_characters"] == []
    assert inventory["available_mixamo_animations"] == []


def test_storyboard_media_paths_are_scoped_to_current_run(tmp_path):
    auth = {"authenticated": False, "method": "test", "account": "test", "token": None, "source_path": None}
    with patch("src.stage1_director.antigravity_client.discover_and_bind_antigravity_2_auth", return_value=auth), patch("src.stage1_director.antigravity_client.subprocess.run", side_effect=FileNotFoundError):
        data = generate_storyboard_via_antigravity("Thánh Gióng", tmp_path, tmp_path / "job-a" / "storyboard.json")
    for shot in data["shots"]:
        assert Path(shot["dialogue"]["wav_path"]).is_relative_to(tmp_path / "job-a")
        assert Path(shot["transition"]["raw_render_path"]).is_relative_to(tmp_path / "job-a")


def test_tts_provider_failure_does_not_publish_fake_or_stale_speech(tmp_path):
    output = tmp_path / "voice.wav"
    wav(output)
    with patch("src.stage2_speech_lipsync.cpu_tts_generator._edge_tts_save", side_effect=RuntimeError("offline")), patch("gtts.gTTS", side_effect=RuntimeError("offline")), patch("src.stage2_speech_lipsync.cpu_tts_generator._generate_fallback_speech_waveform") as fake:
        with pytest.raises(RuntimeError, match="Không tạo được giọng đọc"):
            generate_vietnamese_tts("Xin chào", output)
        fake.assert_not_called()
    assert not output.exists()
    wav(output, silent=True)
    with pytest.raises(RuntimeError, match="im lặng"):
        validate_speech_wav(output)


def test_tts_cpu_restriction_does_not_disable_video_gpu(tmp_path, monkeypatch):
    from src.stage2_speech_lipsync import cpu_tts_generator as tts
    monkeypatch.setenv("CUDA_VISIBLE_DEVICES", "0")
    model, output = tmp_path / "voice.onnx", tmp_path / "voice.wav"
    model.touch()
    commands = []
    def piper_command(command, **kwargs):
        commands.append((command, kwargs))
        if command[0] == "piper":
            wav(Path(command[command.index("--output_file") + 1]))
        else:
            wav(output)
    with patch.object(tts.shutil, "which", return_value="piper"), patch.object(tts.subprocess, "run", side_effect=piper_command):
        tts.synthesize_dialogue_cpu_xeon({"text": "Xin chào"}, {"model_onnx_path": str(model)}, output)
    assert commands[0][1]["env"]["CUDA_VISIBLE_DEVICES"] == ""
    assert tts.os.environ["CUDA_VISIBLE_DEVICES"] == "0"


@FFMPEG
def test_real_assembly_pads_short_renders_and_keeps_every_scene(tmp_path):
    shots = []
    colors = ["red", "green", "blue"]
    for i, color in enumerate(colors):
        raw, speech = tmp_path / f"{i}.mp4", tmp_path / f"{i}.wav"
        run("-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=24:d=0.5", "-c:v", "libx264", raw)
        wav(speech)
        shots.append({"shot_id": f"SHOT_{i}", "dialogue": {"wav_path": str(speech)}, "transition": {"raw_render_path": str(raw)}})
    storyboard = {"project_meta": {"fps": 24, "color_management": {"film_grain_intensity": 0}}, "scene": {}, "shots": shots}
    manifest = tmp_path / "storyboard.json"
    manifest.write_text(json.dumps(storyboard))
    output = tmp_path / "final.mp4"
    with patch("src.stage4_post_nvenc.ffmpeg_nvenc_editor.is_nvenc_available", return_value=False):
        assemble_final_cinematic_movie(manifest, output)
    report = verify_final_video(output, expected_duration=3.9)
    assert abs(report["video_duration"] - report["audio_duration"]) < 0.1
    for time, channel in [(0.5, 0), (1.7, 1), (3.0, 2)]:
        frame = run("-ss", time, "-i", output, "-vf", "crop=16:16:150:80,scale=1:1", "-frames:v", 1, "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1").stdout
        assert len(frame) == 3
        assert frame[channel] > max(frame[j] for j in range(3) if j != channel) + 25


@FFMPEG
@pytest.mark.parametrize("problem", ["mismatch", "black", "silent", "missing_audio", "truncated"])
def test_verifier_rejects_broken_real_media(tmp_path, problem):
    output = tmp_path / "broken.mp4"
    color = "black" if problem == "black" else "red"
    command = ["-f", "lavfi", "-i", f"color=c={color}:s=320x180:r=24:d=1"]
    if problem != "missing_audio":
        source = "anullsrc=r=24000:cl=mono:d=1" if problem == "silent" else f"sine=frequency=440:duration={2 if problem == 'mismatch' else 1}"
        command += ["-f", "lavfi", "-i", source, "-c:a", "aac"]
    run(*command, "-c:v", "libx264", output)
    with pytest.raises(RuntimeError):
        verify_final_video(output, expected_duration=3 if problem == "truncated" else None)


def test_web_job_state_hides_stale_outputs_and_reserves_job_before_start(tmp_path, monkeypatch):
    from src.stage1_director import web_ui
    state = copy.deepcopy(web_ui.PIPELINE_STATE)
    state.update(status="idle", video_ready=False, job_id=None, storyboard_path=None, video_path=None)
    monkeypatch.setattr(web_ui, "PIPELINE_STATE", state)
    monkeypatch.setattr(web_ui, "WORKSPACE_DIR", tmp_path)
    monkeypatch.setattr(web_ui, "STATE_PATH", tmp_path / "latest_job.json")
    monkeypatch.setattr(web_ui, "discover_and_bind_antigravity_2_auth", lambda: {"authenticated": False, "method": "test", "account": "test"})
    (tmp_path / "storyboard.json").write_text('{"shots":[{"shot_id":"OLD"}]}')
    (tmp_path / "final_cinematic_movie.mp4").write_bytes(b"old movie")
    assert web_ui.get_pipeline_status()["storyboard"] is None
    assert web_ui.get_pipeline_status()["video_ready"] is False
    with pytest.raises(HTTPException):
        web_ui.stream_final_video()
    with patch.object(web_ui.threading, "Thread"):
        result = web_ui.start_render_job(web_ui.RenderJobRequest(prompt="Thánh Gióng"))
        assert web_ui.PIPELINE_STATE["status"] == "running"
        assert result["job_id"] == web_ui.PIPELINE_STATE["job_id"]
        with pytest.raises(HTTPException) as error:
            web_ui.start_render_job(web_ui.RenderJobRequest(prompt="Thạch Sanh"))
        assert error.value.status_code == 409
    with pytest.raises(HTTPException):
        web_ui.stream_shot_audio("SHOT_001", job_id="old-job")

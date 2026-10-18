import sys
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Callable, Optional
from src.stage1_director.antigravity_client import generate_storyboard_via_antigravity
from src.stage1_director.director_analyzer import write_storyboard
from src.stage2_speech_lipsync.cpu_tts_generator import synthesize_dialogue_cpu_xeon
from src.stage2_speech_lipsync.rhubarb_lipsync import run_rhubarb_lipsync_on_xeon
from src.stage3_blender_eevee.blender_runner import render_single_shot_headless
from src.stage4_post_nvenc.ffmpeg_nvenc_editor import assemble_final_cinematic_movie


def verify_final_video(video_path: Path, expected_duration: Optional[float] = None):
    """
    Kiểm tra thực tế file video xuất ra:
    1. Phải có cả video stream và audio stream.
    2. Không được phép là khung hình đen (kiểm tra bằng blackdetect).
    3. Không được phép im lặng hoàn toàn (kiểm tra bằng volumedetect).
    """
    if not video_path.is_file() or video_path.stat().st_size == 0:
        raise RuntimeError(f"LỖI NGHIÊM TRỌNG: File video không tồn tại hoặc quá nhỏ ({video_path})!")

    # 1. Kiểm tra cấu trúc Stream bằng ffprobe
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,duration:format=duration",
        "-of", "json", str(video_path)
    ]
    probe_out = subprocess.check_output(probe_cmd, text=True)
    probe = json.loads(probe_out)
    streams = probe.get("streams", [])
    stream_types = [s.get("codec_type") for s in streams]

    if "video" not in stream_types or "audio" not in stream_types:
        raise RuntimeError(f"LỖI: Video thiếu luồng hình ảnh hoặc âm thanh! Streams hiện có: {stream_types}")
    try:
        video_duration = float(next(s for s in streams if s["codec_type"] == "video")["duration"])
        audio_duration = float(next(s for s in streams if s["codec_type"] == "audio")["duration"])
        container_duration = float(probe["format"]["duration"])
    except (KeyError, ValueError, TypeError):
        raise RuntimeError("Không đo được thời lượng hình ảnh và âm thanh đầu ra.")
    durations = [video_duration, audio_duration, container_duration]
    if not all(math.isfinite(d) and d > 0 for d in durations):
        raise RuntimeError("Video có thời lượng không hợp lệ.")
    if max(durations) - min(durations) > 0.15:
        raise RuntimeError(
            f"Hình ảnh ({video_duration:.2f}s) và âm thanh ({audio_duration:.2f}s) lệch thời lượng."
        )
    if expected_duration is not None and abs(video_duration - expected_duration) > 0.15:
        raise RuntimeError(f"Video thiếu cảnh hoặc bị cắt: cần {expected_duration:.2f}s, có {video_duration:.2f}s.")

    # 2. Kiểm tra độ sáng khung hình (Phát hiện video đen)
    black_cmd = [
        "ffmpeg", "-hide_banner", "-nostdin", "-xerror", "-i", str(video_path),
        "-vf", "blackdetect=d=0.5:pix_th=0.10:pic_th=0.98",
        "-af", "volumedetect", "-f", "null", "-"
    ]
    black_proc = subprocess.run(black_cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    if "black_duration" in black_proc.stderr:
        raise RuntimeError(f"LỖI: Phát hiện khung hình bị đen trong video đầu ra!\n{black_proc.stderr}")

    volumes = re.findall(r"max_volume:\s*(-?inf|[-\d.]+) dB", black_proc.stderr)
    if not volumes or not math.isfinite(float(volumes[-1])) or float(volumes[-1]) < -65:
        raise RuntimeError("Luồng âm thanh không có tiếng nghe được.")

    print(f"[VERIFIED] '{video_path}': {video_duration:.2f}s, hình/tiếng đồng bộ, không đen/câm.")
    return {"video_duration": video_duration, "audio_duration": audio_duration, "max_volume_db": float(volumes[-1])}


def execute_cinematic_pipeline(
    user_prompt: str,
    progress_callback: Optional[Callable[[int, str, int], None]] = None,
    workspace_dir: Optional[Path] = None,
) -> Path:
    """
    Điều phối tuần tự 4 tầng:
    progress_callback(stage_number, log_message, percent_complete)
    """
    def notify(stage: int, msg: str, pct: int):
        print(f"[STAGE {stage} | {pct}%] {msg}")
        if progress_callback:
            progress_callback(stage, msg, pct)

    assets_root = Path("assets")
    workspace = (workspace_dir or Path("workspace")).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    storyboard_path = workspace / "storyboard.json"
    final_movie_path = workspace / "final_cinematic_movie.mp4"

    # --- TẦNG 1 ---
    notify(1, "Ông Đạo Diễn đang phân tích yêu cầu & gọi nhân AI antigravity-cli...", 10)
    storyboard = generate_storyboard_via_antigravity(
        user_request=user_prompt,
        assets_root=assets_root,
        output_storyboard_path=storyboard_path,
    )
    shots = storyboard.get("shots", [])
    fps = int(storyboard["project_meta"].get("fps", 24))
    characters = storyboard["characters"]
    if not shots:
        raise RuntimeError("Không có cảnh quay trong kịch bản.")
    notify(1, f"Đã lập {len(shots)} cảnh. {storyboard['project_meta'].get('generation_notice', '')}", 25)

    # --- TẦNG 2 ---
    notify(2, "Khởi chạy TTS trên CPU Intel Xeon (0MB VRAM) & phân tích khẩu hình Rhubarb...", 30)
    for idx, shot in enumerate(shots):
        shot_id = shot["shot_id"]
        spk_id = shot["speaker"]
        voice_profile = characters[spk_id]["voice_profile"]
        wav_path = Path(shot["dialogue"]["wav_path"])
        viseme_path = Path(shot["dialogue"]["viseme_json_path"])

        synthesize_dialogue_cpu_xeon(
            dialogue_cfg=shot["dialogue"],
            voice_profile=voice_profile,
            output_wav_path=wav_path,
        )
        shot["status"] = "audio_ready"
        write_storyboard(storyboard_path, storyboard)
        run_rhubarb_lipsync_on_xeon(
            wav_path=wav_path,
            viseme_json_output_path=viseme_path,
            fps=fps,
        )
        pct = 30 + int(((idx + 1) / max(1, len(shots))) * 20)
        notify(2, f"Hoàn tất thu âm & tách khẩu hình (A, O, E, M, F) cho {shot_id}.", pct)

    # Ghi lại storyboard cập nhật thời lượng chính xác
    write_storyboard(storyboard_path, storyboard)

    # --- TẦNG 3 ---
    notify(3, "Khởi chạy Bộ Kết Xuất Cảnh Quay (EEVEE / 2.5D Procedural)...", 55)
    for idx, shot in enumerate(shots):
        shot_id = shot["shot_id"]
        shot["status"] = "rendering"
        write_storyboard(storyboard_path, storyboard)
        notify(3, f"Đang kết xuất {shot_id}: {shot['scene_title']}...", 55 + int(idx / len(shots) * 25))
        render_single_shot_headless(storyboard_path, shot_id)
        shot["status"] = "rendered"
        write_storyboard(storyboard_path, storyboard)
        pct = 55 + int(((idx + 1) / max(1, len(shots))) * 25)
        notify(3, f"Đã kết xuất xong cảnh {shot_id}.", pct)

    # --- TẦNG 4 ---
    notify(4, "Đang ghép cảnh, đồng bộ hình ảnh và lời kể...", 88)
    assemble_final_cinematic_movie(storyboard_path, final_movie_path)

    # Kiểm định chất lượng video xuất bản cuối cùng
    notify(4, "Đang kiểm định chất lượng hình ảnh & âm thanh đầu ra...", 96)
    expected_duration = sum(math.ceil((s['dialogue']['duration_sec'] + 0.3) * fps) / fps for s in shots) - 0.3 * (len(shots) - 1)
    report = verify_final_video(final_movie_path, expected_duration=expected_duration)
    final_movie_path.with_suffix(".verified.json").write_text(json.dumps(report), encoding="utf-8")
    notify(4, "Xuất bản bộ phim điện ảnh hoàn chỉnh thành công!", 100)

    return final_movie_path


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Tạo video về truyện cổ tích Thạch Sanh"
    out = execute_cinematic_pipeline(prompt)
    print(f"Hoàn thành xuất sắc: {out}")

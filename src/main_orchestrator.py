import sys
import json
import subprocess
from pathlib import Path
from typing import Callable, Optional
from src.stage1_director.antigravity_client import generate_storyboard_via_antigravity
from src.stage2_speech_lipsync.cpu_tts_generator import synthesize_dialogue_cpu_xeon
from src.stage2_speech_lipsync.rhubarb_lipsync import run_rhubarb_lipsync_on_xeon
from src.stage3_blender_eevee.blender_runner import render_single_shot_headless
from src.stage4_post_nvenc.ffmpeg_nvenc_editor import assemble_final_cinematic_movie


def verify_final_video(video_path: Path):
    """
    Kiểm tra thực tế file video xuất ra:
    1. Phải có cả video stream và audio stream.
    2. Không được phép là khung hình đen (kiểm tra bằng blackdetect).
    3. Không được phép im lặng hoàn toàn (kiểm tra bằng volumedetect).
    """
    if not video_path.exists() or video_path.stat().st_size < 50_000:
        raise RuntimeError(f"LỖI NGHIÊM TRỌNG: File video không tồn tại hoặc quá nhỏ ({video_path})!")

    # 1. Kiểm tra cấu trúc Stream bằng ffprobe
    probe_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "stream=codec_type,duration",
        "-of", "json", str(video_path)
    ]
    probe_out = subprocess.check_output(probe_cmd, text=True)
    streams = json.loads(probe_out).get("streams", [])
    stream_types = [s.get("codec_type") for s in streams]

    if "video" not in stream_types or "audio" not in stream_types:
        raise RuntimeError(f"LỖI: Video thiếu luồng hình ảnh hoặc âm thanh! Streams hiện có: {stream_types}")

    # 2. Kiểm tra độ sáng khung hình (Phát hiện video đen)
    black_cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf", "blackdetect=d=0.5:pix_th=0.10:pic_th=0.98",
        "-an", "-f", "null", "-"
    ]
    black_proc = subprocess.run(black_cmd, stderr=subprocess.PIPE, text=True)
    if "black_duration" in black_proc.stderr:
        raise RuntimeError(f"LỖI: Phát hiện khung hình bị đen trong video đầu ra!\n{black_proc.stderr}")

    # 3. Kiểm tra âm lượng (Phát hiện mất tiếng / audio câm)
    vol_cmd = [
        "ffmpeg", "-i", str(video_path),
        "-af", "volumedetect",
        "-vn", "-f", "null", "-"
    ]
    vol_proc = subprocess.run(vol_cmd, stderr=subprocess.PIPE, text=True)
    if "mean_volume: -91.0 dB" in vol_proc.stderr or "max_volume: -91.0 dB" in vol_proc.stderr:
        raise RuntimeError("LỖI: Luồng âm thanh trong video bị câm hoàn toàn (-91.0 dB)!")

    print(f"[VERIFIED] Video '{video_path}' đạt chuẩn: Có hình ảnh màu sắc rõ nét và có giọng đọc đầy đủ!")


def execute_cinematic_pipeline(
    user_prompt: str,
    progress_callback: Optional[Callable[[int, str, int], None]] = None,
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
    workspace = Path("workspace")
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
    notify(1, f"Đã khóa kịch bản {len(shots)} phân cảnh & tính toán góc máy Quy tắc 180 độ.", 25)

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
        run_rhubarb_lipsync_on_xeon(
            wav_path=wav_path,
            viseme_json_output_path=viseme_path,
            fps=fps,
        )
        pct = 30 + int(((idx + 1) / max(1, len(shots))) * 20)
        notify(2, f"Hoàn tất thu âm & tách khẩu hình (A, O, E, M, F) cho {shot_id}.", pct)

    # Ghi lại storyboard cập nhật thời lượng chính xác
    storyboard_path.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")

    # --- TẦNG 3 ---
    notify(3, "Khởi chạy Bộ Kết Xuất Cảnh Quay (EEVEE / 2.5D Procedural)...", 55)
    for idx, shot in enumerate(shots):
        shot_id = shot["shot_id"]
        lens = shot["camera"]["lens_mm"]
        notify(3, f"Đang kết xuất cảnh {shot_id} (Ống kính {lens}mm f/2.0, AgX, Tiêu đề & Phụ đề)...", 55 + idx * 8)
        render_single_shot_headless(storyboard_path, shot_id)
        pct = 55 + int(((idx + 1) / max(1, len(shots))) * 25)
        notify(3, f"Đã kết xuất xong cảnh {shot_id}.", pct)

    # --- TẦNG 4 ---
    notify(4, "Đang dựng hậu kỳ J-Cut/L-Cut (0.3s), trộn Room Tone, phủ 3D LUT & nén NVENC...", 88)
    assemble_final_cinematic_movie(storyboard_path, final_movie_path)

    # Kiểm định chất lượng video xuất bản cuối cùng
    notify(4, "Đang kiểm định chất lượng hình ảnh & âm thanh đầu ra...", 96)
    verify_final_video(final_movie_path)
    notify(4, "Xuất bản bộ phim điện ảnh hoàn chỉnh thành công!", 100)

    return final_movie_path


if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Tạo video về truyện cổ tích Thạch Sanh"
    out = execute_cinematic_pipeline(prompt)
    print(f"Hoàn thành xuất sắc: {out}")

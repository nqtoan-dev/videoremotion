import json
import subprocess
from pathlib import Path
from typing import List, Dict

def is_nvenc_available() -> bool:
    """Kiểm tra chip phần cứng NVENC trên Quadro P2000 có sẵn sàng trong FFmpeg hay không."""
    try:
        res = subprocess.run(
            ["ffmpeg", "-hide_banner", "-encoders"],
            capture_output=True, text=True, check=True
        )
        return "h264_nvenc" in res.stdout
    except Exception:
        return False

def build_ffmpeg_master_command(
    muxed_clips: List[Path],
    clip_durations: List[float],
    storyboard: Dict,
    output_movie_path: Path,
    use_nvenc: bool = True
) -> List[str]:
    """
    Xây dựng lệnh FFmpeg thực hiện đồng thời:
    1. Cắt nối J-Cut / L-Cut (âm thanh cảnh tiếp theo tràn sớm 0.3 giây).
    2. Trộn Room Tone xuyên suốt + Audio Ducking.
    3. Phủ màu 3D LUT (.cube) + Hạt phim 35mm + Đóng khung CinemaScope 2.35:1.
    4. Mã hóa phần cứng bằng cờ `-c:v h264_nvenc -preset p6 -cq 18`.
    """
    meta = storyboard["project_meta"]
    scene_cfg = storyboard["scene"]
    fps = int(meta.get("fps", 24))
    overlap = 0.30  # 0.3 giây chồng lấn cho kỹ thuật J-Cut / L-Cut

    inputs: List[str] = []
    for clip in muxed_clips:
        inputs.extend(["-i", str(clip.as_posix())])

    room_tone_path = Path(scene_cfg.get("room_tone_file", ""))
    has_room_tone = room_tone_path.exists()
    room_tone_idx = len(muxed_clips)
    if has_room_tone:
        inputs.extend(["-stream_loop", "-1", "-i", str(room_tone_path.as_posix())])

    filters: List[str] = []
    n = len(muxed_clips)

    if n == 1:
        filters.append("[0:v]null[v_joined];[0:a]anull[a_joined]")
    else:
        v_prev = "[0:v]"
        a_prev = "[0:a]"
        timeline_cursor = clip_durations[0]

        for i in range(1, n):
            cut_offset = round(max(0.1, timeline_cursor - overlap), 3)
            v_out = f"[v_jcut_{i}]"
            a_out = f"[a_jcut_{i}]"

            # J-Cut: Âm thanh cảnh i bắt đầu sớm hơn 0.3s qua acrossfade, hình ảnh cắt dứt khoát ở cuối nhịp chồng
            filters.append(f"{v_prev}[{i}:v]xfade=transition=fade:duration=0.04:offset={cut_offset}{v_out}")
            filters.append(f"{a_prev}[{i}:a]acrossfade=d={overlap}:c1=tri:c2=tri{a_out}")

            v_prev = v_out
            a_prev = a_out
            timeline_cursor = round(cut_offset + clip_durations[i], 3)

        filters.append(f"{v_prev}null[v_joined]")
        filters.append(f"{a_prev}anull[a_joined]")

    # Trộn Room Tone chạy xuyên suốt bên dưới lời thoại
    if has_room_tone:
        rt_vol = float(scene_cfg.get("room_tone_base_volume", 0.16))
        filters.append(
            f"[{room_tone_idx}:a]volume={rt_vol}[a_rt];"
            f"[a_joined][a_rt]amix=inputs=2:duration=first:dropout_transition=0[a_master]"
        )
    else:
        filters.append("[a_joined]anull[a_master]")

    # Chuỗi hậu kỳ hình ảnh: 3D LUT (.cube) + Hạt phim 35mm + Khung CinemaScope 2.35:1 (1920x816 trên nền 1920x1080)
    lut_path = Path(meta["color_management"].get("lut_path", ""))
    grain_val = float(meta["color_management"].get("film_grain_intensity", 6.5))

    v_fx = ["format=rgb24"]
    if lut_path.exists():
        v_fx.append(f"lut3d=file='{lut_path.as_posix()}':interp=tetrahedral")
    v_fx.extend([
        "format=yuv420p",
        f"noise=alls={grain_val}:allf=t+u",
        "drawbox=x=0:y=0:w=iw:h=132:color=black:t=fill",
        "drawbox=x=0:y=ih-132:w=iw:h=132:color=black:t=fill"
    ])
    filters.append(f"[v_joined]{','.join(v_fx)}[v_master]")

    video_encoder_flags = (
        ["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "18"]
        if use_nvenc else
        ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]
    )

    return [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[v_master]",
        "-map", "[a_master]",
        "-r", str(fps),
        *video_encoder_flags,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "256k",
        str(output_movie_path.as_posix())
    ]

def assemble_final_cinematic_movie(storyboard_path: Path, output_movie_path: Path) -> Path:
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    shots = storyboard["shots"]
    overlap = 0.30
    use_nvenc = is_nvenc_available()

    temp_mux_dir = output_movie_path.parent / "temp_muxed_shots"
    temp_mux_dir.mkdir(parents=True, exist_ok=True)

    muxed_clips: List[Path] = []
    clip_durations: List[float] = []

    for shot in shots:
        shot_id = shot["shot_id"]
        raw_vid = Path(shot["transition"]["raw_render_path"])
        wav_aud = Path(shot["dialogue"]["wav_path"])
        viseme_json = Path(shot["dialogue"]["viseme_json_path"])

        speech_dur = float(json.loads(viseme_json.read_text(encoding="utf-8"))["duration_sec"])
        total_clip_dur = round(speech_dur + overlap, 3)

        mux_out = temp_mux_dir / f"{shot_id}_muxed.mp4"
        enc_flags = ["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "16"] if use_nvenc else ["-c:v", "libx264", "-crf", "16"]
        cmd_mux = [
            "ffmpeg", "-y",
            "-i", str(raw_vid.as_posix()),
            "-i", str(wav_aud.as_posix()),
            "-filter_complex", f"[1:a]apad=pad_dur={overlap}[a_padded]",
            "-map", "0:v:0", "-map", "[a_padded]",
            "-t", str(total_clip_dur),
            *enc_flags,
            "-c:a", "aac", "-b:a", "192k",
            str(mux_out.as_posix())
        ]
        subprocess.run(cmd_mux, check=True)
        muxed_clips.append(mux_out)
        clip_durations.append(total_clip_dur)

    output_movie_path.parent.mkdir(parents=True, exist_ok=True)
    cmd_master = build_ffmpeg_master_command(
        muxed_clips=muxed_clips,
        clip_durations=clip_durations,
        storyboard=storyboard,
        output_movie_path=output_movie_path,
        use_nvenc=use_nvenc
    )
    subprocess.run(cmd_master, check=True)
    return output_movie_path

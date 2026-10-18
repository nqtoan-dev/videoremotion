import os
import json
import math
import subprocess
import wave
from pathlib import Path
from typing import List, Dict


def is_nvenc_available() -> bool:
    """Kiểm tra thực tế khả năng khởi tạo bộ mã hóa phần cứng h264_nvenc trên Quadro P2000."""
    try:
        res = subprocess.run(
            [
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                "-c:v", "h264_nvenc", "-f", "null", "-"
            ],
            capture_output=True, text=True, timeout=10
        )
        return res.returncode == 0
    except Exception:
        return False


def _sanitize_lut_path_for_ffmpeg(lut_path: Path) -> str:
    """Chuẩn hóa đường dẫn file .cube cho bộ lọc lut3d của FFmpeg (tránh lỗi dấu ':' ổ đĩa trên Windows)."""
    try:
        rel = os.path.relpath(lut_path.resolve(), Path.cwd().resolve())
        return Path(rel).as_posix()
    except Exception:
        return lut_path.as_posix().replace(":", "\\:")


def build_ffmpeg_master_command(
    muxed_clips: List[Path],
    clip_durations: List[float],
    storyboard: Dict,
    output_movie_path: Path,
    use_nvenc: bool = True,
) -> List[str]:
    meta = storyboard["project_meta"]
    scene_cfg = storyboard["scene"]
    fps = int(meta.get("fps", 24))
    overlap = 0.30
    if not muxed_clips or len(muxed_clips) != len(clip_durations):
        raise ValueError("Cần có cảnh quay và thời lượng tương ứng để dựng phim.")
    if any(not math.isfinite(d) or d <= overlap for d in clip_durations):
        raise ValueError("Thời lượng cảnh quay không hợp lệ.")
    total_duration = sum(clip_durations) - overlap * (len(muxed_clips) - 1)

    inputs: List[str] = []
    for clip in muxed_clips:
        inputs.extend(["-i", str(clip.as_posix())])

    room_tone_path = Path(scene_cfg.get("room_tone_file", ""))
    has_room_tone = room_tone_path.is_file() and room_tone_path.stat().st_size > 44
    room_tone_idx = len(muxed_clips)
    if has_room_tone:
        inputs.extend(["-stream_loop", "-1", "-i", str(room_tone_path.as_posix())])

    filters: List[str] = []
    n = len(muxed_clips)
    # Every input must cover its declared duration and use the same clock.
    # A short raw render must never silently truncate the entire xfade chain.
    for i, duration in enumerate(clip_durations):
        filters.append(
            f"[{i}:v]fps={fps},settb=AVTB,setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={duration},trim=duration={duration},"
            f"setsar=1,format=yuv420p[v{i}]"
        )
        filters.append(
            f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,"
            f"asetpts=PTS-STARTPTS,apad,atrim=duration={duration}[a{i}]"
        )

    if n == 1:
        filters.append("[v0]null[v_joined];[a0]anull[a_joined]")
    else:
        v_prev = "[v0]"
        a_prev = "[a0]"
        timeline_cursor = clip_durations[0]

        for i in range(1, n):
            cut_offset = round(max(0.1, timeline_cursor - overlap), 3)
            v_out = f"[v_jcut_{i}]"
            a_out = f"[a_jcut_{i}]"

            filters.append(f"{v_prev}[v{i}]xfade=transition=fade:duration={overlap}:offset={cut_offset}{v_out}")
            filters.append(f"{a_prev}[a{i}]acrossfade=d={overlap}:c1=tri:c2=tri{a_out}")

            v_prev = v_out
            a_prev = a_out
            timeline_cursor = round(cut_offset + clip_durations[i], 3)

        filters.append(f"{v_prev}null[v_joined]")
        filters.append(f"{a_prev}anull[a_joined]")

    if has_room_tone:
        rt_vol = float(scene_cfg.get("room_tone_base_volume", 0.16))
        filters.append(
            f"[{room_tone_idx}:a]volume={rt_vol}[a_rt];"
            f"[a_joined][a_rt]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[a_master]"
        )
    else:
        filters.append("[a_joined]anull[a_master]")

    color = meta.get("color_management", {})
    lut_path = Path(color.get("lut_path", ""))
    grain_val = float(color.get("film_grain_intensity", 6.5))

    v_fx = ["format=rgb24"]
    if lut_path.is_file():
        safe_lut = _sanitize_lut_path_for_ffmpeg(lut_path)
        v_fx.append(f"lut3d=file='{safe_lut}':interp=tetrahedral")
    v_fx.extend([
        "eq=contrast=1.06:brightness=0.02:saturation=1.12",
        "format=yuv420p",
        f"noise=alls={grain_val}:allf=t+u",
        "drawbox=x=0:y=0:w=iw:h=ih*0.1222:color=black:t=fill",
        "drawbox=x=0:y=ih-ih*0.1222:w=iw:h=ih*0.1222:color=black:t=fill",
    ])
    filters.append(f"[v_joined]{','.join(v_fx)}[v_master]")

    video_encoder_flags = (
        ["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "18"]
        if use_nvenc
        else ["-c:v", "libx264", "-preset", "fast", "-crf", "18"]
    )

    return [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-filter_complex_threads", "2",
        *inputs,
        "-filter_complex", ";".join(filters),
        "-map", "[v_master]",
        "-map", "[a_master]",
        "-r", str(fps),
        *video_encoder_flags,
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "256k",
        "-t", str(round(total_duration, 6)),
        "-movflags", "+faststart",
        str(output_movie_path.as_posix()),
    ]


def assemble_final_cinematic_movie(storyboard_path: Path, output_movie_path: Path) -> Path:
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    shots = storyboard["shots"]
    if not shots:
        raise ValueError("Kịch bản chưa có cảnh quay.")
    fps = int(storyboard["project_meta"].get("fps", 24))
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
        if not raw_vid.is_file() or not wav_aud.is_file():
            raise RuntimeError(f"Cảnh {shot_id} thiếu hình ảnh hoặc giọng đọc.")
        with wave.open(str(wav_aud), "rb") as wf:
            speech_dur = wf.getnframes() / float(wf.getframerate())
        total_clip_dur = math.ceil((speech_dur + overlap) * fps) / fps

        mux_out = temp_mux_dir / f"{shot_id}_muxed.mp4"
        enc_flags = (
            ["-c:v", "h264_nvenc", "-preset", "p6", "-cq", "16"]
            if use_nvenc
            else ["-c:v", "libx264", "-preset", "fast", "-crf", "16"]
        )
        cmd_mux = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-i", str(raw_vid.as_posix()),
            "-i", str(wav_aud.as_posix()),
            "-filter_complex", (
                f"[0:v]fps={fps},setpts=PTS-STARTPTS,tpad=stop_mode=clone:stop_duration={total_clip_dur},"
                f"trim=duration={total_clip_dur}[v_padded];"
                f"[1:a]apad,atrim=duration={total_clip_dur}[a_padded]"
            ),
            "-map", "[v_padded]", "-map", "[a_padded]",
            "-t", str(total_clip_dur),
            *enc_flags,
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            str(mux_out.as_posix()),
        ]
        try:
            subprocess.run(cmd_mux, check=True, capture_output=True)
        except subprocess.CalledProcessError:
            if not use_nvenc:
                raise
            start = cmd_mux.index("-c:v")
            cmd_mux[start:start + len(enc_flags)] = ["-c:v", "libx264", "-preset", "fast", "-crf", "16"]
            subprocess.run(cmd_mux, check=True, capture_output=True)

        muxed_clips.append(mux_out)
        clip_durations.append(total_clip_dur)

    output_movie_path.parent.mkdir(parents=True, exist_ok=True)
    cmd_master = build_ffmpeg_master_command(
        muxed_clips=muxed_clips,
        clip_durations=clip_durations,
        storyboard=storyboard,
        output_movie_path=output_movie_path,
        use_nvenc=use_nvenc,
    )
    try:
        subprocess.run(cmd_master, check=True)
    except subprocess.CalledProcessError as exc:
        if not use_nvenc:
            raise
        print(f"[STAGE 4] Lệnh Master với NVENC gặp lỗi ({exc}), chuyển sang CPU libx264...")
        cmd_fallback = build_ffmpeg_master_command(
            muxed_clips=muxed_clips, clip_durations=clip_durations,
            storyboard=storyboard, output_movie_path=output_movie_path, use_nvenc=False,
        )
        subprocess.run(cmd_fallback, check=True)

    return output_movie_path

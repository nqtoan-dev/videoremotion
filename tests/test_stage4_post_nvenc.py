from pathlib import Path
from src.stage4_post_nvenc.ffmpeg_nvenc_editor import build_ffmpeg_master_command

def test_stage4_nvenc_jcut_lut_grain_and_cinemascope_command(tmp_path: Path):
    lut_file = tmp_path / "film_kodak_2383.cube"
    lut_file.write_text("LUT_3D_SIZE 2\n0.0 0.0 0.0\n1.0 1.0 1.0\n", encoding="utf-8")

    room_tone = tmp_path / "room_tone.wav"
    room_tone.write_bytes(b"RIFF0000WAVEfmt ")

    storyboard = {
        "project_meta": {
            "fps": 24,
            "color_management": {
                "lut_path": str(lut_file),
                "film_grain_intensity": 6.5
            }
        },
        "scene": {
            "room_tone_file": str(room_tone),
            "room_tone_base_volume": 0.16
        }
    }

    clips = [tmp_path / "SHOT_001.mp4", tmp_path / "SHOT_002.mp4"]
    cmd = build_ffmpeg_master_command(
        muxed_clips=clips,
        clip_durations=[3.5, 4.0],
        storyboard=storyboard,
        output_movie_path=tmp_path / "final_movie.mp4",
        use_nvenc=True
    )

    cmd_str = " ".join(cmd)
    # 1. Kiểm tra cắt nối J-Cut 0.3 giây
    assert "acrossfade=d=0.3" in cmd_str
    # 2. Kiểm tra Room Tone xuyên suốt
    assert "-stream_loop -1" in cmd_str and "amix=inputs=2" in cmd_str
    # 3. Kiểm tra 3D LUT (.cube) + Hạt phim 35mm + Khung CinemaScope 2.35:1
    assert "lut3d=file=" in cmd_str
    assert "noise=alls=6.5:allf=t+u" in cmd_str
    assert "drawbox=x=0:y=0:w=iw:h=132:color=black:t=fill" in cmd_str
    # 4. Kiểm tra cờ nén phần cứng Quadro P2000 NVENC
    assert "-c:v h264_nvenc -preset p6 -cq 18" in cmd_str

import sys
import subprocess
from pathlib import Path
from src.stage1_director.antigravity_client import generate_storyboard_via_antigravity
from src.stage2_speech_lipsync.cpu_tts_generator import synthesize_dialogue_cpu_xeon
from src.stage2_speech_lipsync.rhubarb_lipsync import run_rhubarb_lipsync_on_xeon
from src.stage4_post_nvenc.ffmpeg_nvenc_editor import assemble_final_cinematic_movie

def execute_cinematic_pipeline(user_prompt: str) -> Path:
    assets_root = Path("assets")
    workspace = Path("workspace")
    storyboard_path = workspace / "storyboard.json"
    final_movie_path = workspace / "final_cinematic_movie.mp4"

    # 1. TẦNG 1: Ông Đạo Diễn + Nhân AI antigravity-cli + Toán học Quy tắc 180 độ
    print("[TẦNG 1] Khởi chạy Đạo Diễn AI, phân tích kịch bản và giải toán 180 độ...")
    storyboard = generate_storyboard_via_antigravity(
        user_request=user_prompt,
        assets_root=assets_root,
        output_storyboard_path=storyboard_path
    )
    fps = int(storyboard["project_meta"].get("fps", 24))
    characters = storyboard["characters"]

    # 2. TẦNG 2: Sinh giọng thoại tự nhiên & Tách khẩu hình Rhubarb trên CPU Xeon (0MB VRAM)
    print("[TẦNG 2] Khởi chạy TTS INT8 & Rhubarb khẩu hình trên CPU Xeon (0 MB VRAM)...")
    for shot in storyboard["shots"]:
        spk_id = shot["speaker"]
        voice_profile = characters[spk_id]["voice_profile"]
        wav_path = Path(shot["dialogue"]["wav_path"])
        viseme_path = Path(shot["dialogue"]["viseme_json_path"])

        synthesize_dialogue_cpu_xeon(
            dialogue_cfg=shot["dialogue"],
            voice_profile=voice_profile,
            output_wav_path=wav_path
        )
        run_rhubarb_lipsync_on_xeon(
            wav_path=wav_path,
            viseme_json_output_path=viseme_path,
            fps=fps
        )

    # 3. TẦNG 3: Kết xuất Đồ họa Điện ảnh bằng Blender EEVEE Headless (Tối ưu P2000 < 3.2GB VRAM)
    print("[TẦNG 3] Khởi chạy Blender EEVEE Headless tuần tự từng cảnh trên Quadro P2000...")
    blend_file = Path(storyboard["scene"]["blend_file"])
    render_script = Path("src/stage3_blender_eevee/render_shot.py")

    for shot in storyboard["shots"]:
        cmd_blender = [
            "blender", "-b", str(blend_file.as_posix()),
            "-P", str(render_script.as_posix()),
            "--",
            "--storyboard", str(storyboard_path.as_posix()),
            "--shot-id", shot["shot_id"]
        ]
        subprocess.run(cmd_blender, check=True)

    # 4. TẦNG 4: Dựng phim J-Cut/L-Cut, LUT, Hạt phim 35mm, CinemaScope 2.35:1 & Xuất h264_nvenc
    print("[TẦNG 4] Hậu kỳ J-Cut/L-Cut, 3D LUT, Film Grain 35mm & nén phần cứng NVENC...")
    return assemble_final_cinematic_movie(storyboard_path, final_movie_path)

if __name__ == "__main__":
    prompt = sys.argv[1] if len(sys.argv) > 1 else "Hai kỹ sư Minh và Lan tranh luận khẩn cấp về việc ngắt kết nối máy chủ trước khi bị tấn công."
    output_movie = execute_cinematic_pipeline(prompt)
    print(f"Hoàn thành xuất sắc bộ phim điện ảnh: {output_movie}")

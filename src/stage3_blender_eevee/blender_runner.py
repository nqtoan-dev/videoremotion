import json
import math
import wave
import shutil
import subprocess
from pathlib import Path
from typing import Dict
from PIL import Image, ImageDraw, ImageFont


def is_valid_blend_file(blend_path: Path) -> bool:
    """Kiểm tra file .blend có phải là file nhị phân thật của Blender (bắt đầu bằng 'BLENDER') hay chỉ là placeholder."""
    if not blend_path.exists() or blend_path.stat().st_size < 12:
        return False
    header = blend_path.read_bytes()[:12]
    return header.startswith(b"BLENDER")


def render_visual_shot_guaranteed(shot: Dict, storyboard: Dict, out_path: Path, fps: int = 24) -> Path:
    """
    Đảm bảo 100% tạo ra video có cảnh nền 2.5D/3D minh họa, hiệu ứng chuyển động camera,
    tiêu đề phân cảnh và phụ đề câu chuyện tiếng Việt rõ nét, tuyệt đối không dùng màn hình đen.
    """
    out_path.parent.mkdir(parents=True, exist_ok=True)
    frames_dir = out_path.parent / f"frames_{shot['shot_id']}"
    frames_dir.mkdir(parents=True, exist_ok=True)

    # Đo thời lượng thực tế từ file âm thanh WAV hoặc cấu hình
    wav_path = Path(shot.get("dialogue", {}).get("wav_path", "")) if isinstance(shot.get("dialogue"), dict) else None
    duration = 5.0
    if wav_path and wav_path.exists():
        try:
            with wave.open(str(wav_path), "rb") as wf:
                duration = wf.getnframes() / float(wf.getframerate())
        except Exception:
            pass
    elif "duration" in shot:
        duration = float(shot["duration"])
    elif isinstance(shot.get("dialogue"), dict) and "duration_sec" in shot["dialogue"]:
        duration = float(shot["dialogue"]["duration_sec"])

    duration = max(2.5, round(duration, 2))
    total_frames = max(int(duration * fps), 24)
    width, height = 1920, 1080

    sky_rgb = [int(c * 255) for c in shot.get("sky_color", [0.15, 0.28, 0.38])]
    ground_rgb = [int(c * 255) for c in shot.get("ground_color", [0.22, 0.18, 0.12])]
    title_text = shot.get("scene_title", "Truyện Cổ Tích: Thạch Sanh")
    dialogue_raw = shot.get("dialogue", "")
    dialogue_text = dialogue_raw.get("text", "") if isinstance(dialogue_raw, dict) else str(dialogue_raw)
    theme = shot.get("visual_theme", "forest_banyan_tree")

    # Tải font hỗ trợ Unicode tiếng Việt trên Windows / Linux / macOS
    font_paths = [
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    font_title = None
    font_sub = None
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font_title = ImageFont.truetype(fp, 46)
                font_sub = ImageFont.truetype(fp, 32)
                break
            except Exception:
                continue
    if font_title is None:
        font_title = font_sub = ImageFont.load_default()

    # Tạo từng khung hình hoạt họa điện ảnh 2.5D
    for f in range(total_frames):
        t = f / float(max(1, total_frames - 1))
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)

        # 1. Bầu trời và mặt đất có gradient màu phong phú
        horizon_y = int(height * 0.62)
        for y in range(0, horizon_y, 2):
            ratio = y / float(horizon_y)
            r = min(255, max(0, int(sky_rgb[0] * (1.1 - ratio * 0.4))))
            g = min(255, max(0, int(sky_rgb[1] * (1.1 - ratio * 0.35))))
            b = min(255, max(0, int(sky_rgb[2] * (1.1 - ratio * 0.3))))
            draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))

        for y in range(horizon_y, height, 2):
            ratio = (y - horizon_y) / float(height - horizon_y)
            r = min(255, max(0, int(ground_rgb[0] * (1.0 - ratio * 0.4))))
            g = min(255, max(0, int(ground_rgb[1] * (1.0 - ratio * 0.4))))
            b = min(255, max(0, int(ground_rgb[2] * (1.0 - ratio * 0.4))))
            draw.rectangle([(0, y), (width, y + 1)], fill=(r, g, b))

        # 2. Thiên thể (Mặt trời hoặc Mặt trăng huyền bí theo chủ đề)
        is_night = "night" in theme or "cave" in theme
        celestial_x = int(width * 0.78 + math.sin(t * math.pi) * 45)
        celestial_y = int(height * 0.22 - math.sin(t * math.pi) * 30)
        c_color = (230, 240, 255) if is_night else (255, 225, 110)
        c_halo = (100, 120, 180) if is_night else (255, 200, 70)
        draw.ellipse([celestial_x - 110, celestial_y - 110, celestial_x + 110, celestial_y + 110], fill=c_halo)
        draw.ellipse([celestial_x - 70, celestial_y - 70, celestial_x + 70, celestial_y + 70], fill=c_color)

        # 3. Dãy núi / Hậu cảnh Parallax
        pan_offset = int(t * 70)
        draw.polygon([(150 - pan_offset, horizon_y), (500 - pan_offset, 290), (880 - pan_offset, horizon_y)], fill=(45, 60, 52))
        draw.polygon([(700 - pan_offset, horizon_y), (1120 - pan_offset, 240), (1540 - pan_offset, horizon_y)], fill=(35, 52, 46))
        draw.polygon([(1300 - pan_offset, horizon_y), (1650 - pan_offset, 310), (1980 - pan_offset, horizon_y)], fill=(42, 58, 50))

        # 4. Chi tiết bối cảnh đặc trưng theo chủ đề truyện Thạch Sanh
        if theme == "forest_banyan_tree":
            # Gốc đa đại thụ: Thân to, rễ chùm và tán lá xum xuê
            tree_x = 450 - int(pan_offset * 0.4)
            draw.rectangle([tree_x - 55, horizon_y - 320, tree_x + 55, horizon_y + 20], fill=(85, 50, 28))
            draw.line([(tree_x - 30, horizon_y - 200), (tree_x - 75, horizon_y + 20)], fill=(75, 42, 22), width=10)
            draw.line([(tree_x + 30, horizon_y - 200), (tree_x + 80, horizon_y + 20)], fill=(75, 42, 22), width=10)
            draw.ellipse([tree_x - 240, horizon_y - 540, tree_x + 240, horizon_y - 210], fill=(28, 105, 42))
            draw.ellipse([tree_x - 160, horizon_y - 480, tree_x + 180, horizon_y - 190], fill=(38, 125, 52))
        elif theme == "temple_night_battle":
            # Miếu thờ cổ kính & hào quang búa thần
            temple_x = 480 - int(pan_offset * 0.4)
            draw.polygon([(temple_x - 180, horizon_y - 140), (temple_x, horizon_y - 280), (temple_x + 180, horizon_y - 140)], fill=(95, 45, 35))
            draw.rectangle([temple_x - 130, horizon_y - 140, temple_x + 130, horizon_y], fill=(70, 35, 30))
            # Hào quang chiến trận
            draw.line([(width * 0.5 - 50, horizon_y - 120), (width * 0.5 + 80, horizon_y - 220)], fill=(255, 100, 50), width=6)
        elif theme == "deep_cave_rescue":
            # Hang đá sâu thẳm & thạch nhũ
            for sx in range(100, width, 220):
                draw.polygon([(sx, 0), (sx + 70, 0), (sx + 35, 180 + (sx % 90))], fill=(50, 40, 35))
            draw.line([(width * 0.5 - 60, horizon_y - 100), (width * 0.5 + 140, horizon_y - 260)], fill=(255, 215, 0), width=5)
        elif theme == "royal_palace_victory":
            # Cung điện hoàng gia nguy nga & niêu cơm thần
            draw.rectangle([250, horizon_y - 360, 420, horizon_y], fill=(160, 120, 50))
            draw.polygon([(220, horizon_y - 360), (335, horizon_y - 480), (450, horizon_y - 360)], fill=(210, 50, 40))
            draw.rectangle([width - 450, horizon_y - 360, width - 280, horizon_y], fill=(160, 120, 50))
            draw.polygon([(width - 480, horizon_y - 360), (width - 365, horizon_y - 480), (width - 250, horizon_y - 360)], fill=(210, 50, 40))
            # Niêu cơm thần tỏa khói thơm
            draw.ellipse([width * 0.5 - 45, horizon_y - 40, width * 0.5 + 45, horizon_y + 15], fill=(50, 50, 55))
            draw.ellipse([width * 0.5 - 35, horizon_y - 35, width * 0.5 + 35, horizon_y - 15], fill=(245, 245, 240))

        # 5. Nhân vật chính (Thạch Sanh) có chuyển động nhịp nhàng
        bob_y = math.sin(t * 3 * math.pi) * 8
        hero_x = int(width * 0.52 + math.sin(t * 1.5 * math.pi) * 20)
        hero_y = int(horizon_y + 25 + bob_y)

        # Đầu và khăn quấn
        draw.ellipse([hero_x - 38, hero_y - 200, hero_x + 38, hero_y - 124], fill=(240, 195, 155))
        draw.ellipse([hero_x - 40, hero_y - 212, hero_x + 40, hero_y - 175], fill=(130, 75, 40))
        # Thân áo nâu dân dã / chiến binh
        draw.rectangle([hero_x - 48, hero_y - 124, hero_x + 48, hero_y], fill=(115, 68, 38))
        draw.rectangle([hero_x - 46, hero_y - 45, hero_x + 46, hero_y - 25], fill=(50, 45, 40))
        # Chân
        draw.rectangle([hero_x - 35, hero_y, hero_x - 10, hero_y + 90], fill=(95, 55, 32))
        draw.rectangle([hero_x + 10, hero_y, hero_x + 35, hero_y + 90], fill=(95, 55, 32))

        # Vũ khí (Búa thần hoặc Cung tên vàng)
        draw.line([(hero_x + 45, hero_y - 110), (hero_x + 85, hero_y + 40)], fill=(80, 50, 30), width=7)
        draw.rectangle([hero_x + 70, hero_y - 130, hero_x + 105, hero_y - 95], fill=(210, 180, 90))

        # 6. Banner Tiêu đề phân cảnh phía trên màn hình
        draw.rectangle([60, 40, width - 60, 125], fill=(15, 22, 34))
        draw.rectangle([60, 40, width - 60, 125], outline=(255, 215, 0), width=2)
        draw.text((95, 58), title_text, fill=(255, 215, 0), font=font_title)

        # 7. Khung Phụ đề câu chuyện Thạch Sanh phía dưới màn hình
        draw.rectangle([70, height - 210, width - 70, height - 40], fill=(12, 16, 24))
        draw.rectangle([70, height - 210, width - 70, height - 40], outline=(100, 140, 190), width=2)

        # Tự động ngắt dòng thông minh cho tiếng Việt
        words = dialogue_text.split()
        lines, cur = [], ""
        for w in words:
            if len(cur + " " + w) <= 65:
                cur = (cur + " " + w).strip()
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)

        for l_idx, line in enumerate(lines[:3]):
            draw.text((110, height - 190 + l_idx * 44), line, fill=(255, 255, 255), font=font_sub)

        frame_file = frames_dir / f"frame_{f:04d}.png"
        img.save(frame_file)

    # Đóng gói chuỗi ảnh PNG thành file MP4 hoàn chỉnh
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", str(frames_dir / "frame_%04d.png"),
        "-c:v", "libx264",
        "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-crf", "18",
        str(out_path.as_posix()),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Dọn dẹp frame tạm thời
    try:
        shutil.rmtree(frames_dir, ignore_errors=True)
    except Exception:
        pass

    return out_path


def render_single_shot_headless(storyboard_path: Path, shot_id: str) -> Path:
    """
    Kết xuất cảnh quay chất lượng cao:
    - Nếu có Blender và file .blend thật: gọi Blender EEVEE Headless.
    - Nếu máy chưa cài Blender hoặc file là placeholder: tự động kết xuất bằng Bộ Render 2.5D Điện Ảnh Thạch Sanh,
      đảm bảo 100% video ra đời có hình ảnh sắc nét, tiêu đề và phụ đề tiếng Việt.
    """
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    blend_file = Path(storyboard.get("scene", {}).get("blend_file", "assets/scenes/studio_office.blend"))
    shot = next(s for s in storyboard["shots"] if s["shot_id"] == shot_id)
    out_video = Path(shot["transition"]["raw_render_path"])
    fps = int(storyboard.get("project_meta", {}).get("fps", 24))
    render_script = Path("src/stage3_blender_eevee/render_shot.py")

    blender_bin = shutil.which("blender")
    if blender_bin and is_valid_blend_file(blend_file):
        try:
            cmd = [
                blender_bin, "-b", str(blend_file.as_posix()),
                "-P", str(render_script.as_posix()),
                "--", "--storyboard", str(storyboard_path.as_posix()), "--shot-id", shot_id,
            ]
            subprocess.run(cmd, check=True)
            if out_video.exists() and out_video.stat().st_size > 1000:
                return out_video
        except Exception as exc:
            print(f"[STAGE 3] Blender EEVEE gặp lỗi ({exc}), kích hoạt Bộ Render Điện Ảnh 2.5D...")

    # Bộ render 2.5D chất lượng cao đảm bảo 100% video có hình ảnh
    render_visual_shot_guaranteed(shot, storyboard, out_video, fps=fps)
    return out_video

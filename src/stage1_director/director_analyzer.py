import json
from pathlib import Path
from typing import Dict, Any

def scan_available_3d_assets(assets_root: Path) -> Dict[str, Any]:
    """Quét danh sách tài nguyên 3D thực tế trong thư mục assets/ để cung cấp cho Ông Đạo Diễn."""
    scenes_dir = assets_root / "scenes"
    chars_dir = assets_root / "characters"
    anims_dir = assets_root / "animations"
    luts_dir = assets_root / "luts"

    scenes = [str(p.as_posix()) for p in scenes_dir.glob("*.blend")] if scenes_dir.exists() else []
    chars = [str(p.as_posix()) for p in chars_dir.glob("*.fbx")] if chars_dir.exists() else []
    anims = [str(p.as_posix()) for p in anims_dir.glob("*.fbx")] if anims_dir.exists() else []
    luts = [str(p.as_posix()) for p in luts_dir.glob("*.cube")] if luts_dir.exists() else []

    return {
        "available_scenes": scenes or ["assets/scenes/studio_office.blend"],
        "available_characters": chars or ["assets/characters/char_minh.fbx", "assets/characters/char_lan.fbx"],
        "available_mixamo_animations": anims or [
            "assets/animations/standing_talking_01.fbx",
            "assets/animations/standing_explaining_02.fbx",
            "assets/animations/standing_listening_idle.fbx"
        ],
        "available_luts": luts or ["assets/luts/film_kodak_2383.cube"]
    }

def build_director_prompt_for_antigravity(user_request: str, inventory: Dict[str, Any]) -> str:
    """
    Ông Đạo Diễn phân tích yêu cầu người dùng và lập bản thiết kế kỹ thuật (Prompt)
    để ép `antigravity-cli` xuất ra đúng cấu trúc JSON của bộ phim.
    """
    schema_instruction = """
BẠN LÀ ÔNG ĐẠO DIỄN ĐIỆN ẢNH AI (DIRECTOR CORE) TÍCH HỢP TRONG ANTIGRAVITY-CLI.
Nhiệm vụ: Phân tích yêu cầu tạo video của người dùng và sinh ra DUY NHẤT một chuỗi JSON hợp lệ (không bọc trong ```json)
định nghĩa toàn bộ bộ phim theo đúng định dạng `storyboard.json`.

QUY TẮC ĐẠO DIỄN BẮT BUỘC:
1. Đồng nhất Bối cảnh & Nhân vật: Chọn 1 file `blend_file` từ danh sách `available_scenes` và giữ cố định xuyên suốt mọi cảnh quay.
2. Khóa vị trí đứng: Nhân vật CHAR_MINH đứng tại [-1.1, 0.0, 0.0], nhân vật CHAR_LAN đứng tại [1.1, 0.0, 0.0].
3. Chuyển động Mixamo: Mỗi cảnh phải gán đúng đường dẫn `mixamo_animation` từ `available_mixamo_animations` phù hợp với hành động nói hoặc lắng nghe.
4. Lời thoại & Cảm xúc: Câu thoại tiếng Việt phải tự nhiên, sắc sảo, đúng ngữ cảnh điện ảnh; đi kèm trường `emotion` (calm, urgent, angry, thoughtful), `speaking_rate_multiplier` (0.9 - 1.1) và `pitch_offset_semitones` (-2.0 đến +1.5).
5. Nhịp điệu góc máy: Cảnh 1 dùng `ESTABLISHING_WIDE` hoặc `OTS_CLOSE_UP`, các cảnh đối thoại cao trào dùng `OTS_CLOSE_UP` và `CLOSE_UP` có bật `rack_focus.enabled = true` khi chuyển lượt nói.
"""
    return (
        f"{schema_instruction.strip()}\n\n"
        f"DANH MỤC TÀI NGUYÊN 3D HIỆN CÓ:\n{json.dumps(inventory, ensure_ascii=False, indent=2)}\n\n"
        f"YÊU CẦU TẠO VIDEO TỪ NGƯỜI DÙNG:\n\"{user_request}\"\n\n"
        f"Hãy trả về JSON đầy đủ chứa các khóa: project_meta, scene, characters, shots."
    )

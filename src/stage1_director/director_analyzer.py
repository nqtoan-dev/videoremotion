import json
from pathlib import Path
from typing import Dict, Any

def scan_available_3d_assets(assets_root: Path) -> Dict[str, Any]:
    """Quét danh sách tài nguyên 3D thực tế trong thư mục assets/ để cung cấp cho Ông Đạo Diễn."""
    scenes_dir = assets_root / "scenes"
    chars_dir = assets_root / "characters"
    anims_dir = assets_root / "animations"
    luts_dir = assets_root / "luts"

    def real_files(directory, suffix, headers):
        result = []
        for p in sorted(directory.glob(suffix)):
            with p.open("rb") as f:
                if f.read(32).startswith(headers):
                    result.append(p.as_posix())
        return result

    scenes = real_files(scenes_dir, "*.blend", (b"BLENDER",))
    chars = real_files(chars_dir, "*.fbx", (b"Kaydara FBX Binary", b"; FBX"))
    anims = real_files(anims_dir, "*.fbx", (b"Kaydara FBX Binary", b"; FBX"))
    luts = [str(p.as_posix()) for p in luts_dir.glob("*.cube")] if luts_dir.exists() else []

    return {
        "available_scenes": scenes,
        "available_characters": chars,
        "available_mixamo_animations": anims,
        "available_luts": luts,
    }

def generate_thach_sanh_storyboard(prompt: str = "") -> Dict[str, Any]:
    """Sinh kịch bản chuẩn cho Truyện cổ tích Thạch Sanh với đầy đủ thông số thị giác và lời thoại."""
    return {
        "project_title": "Truyện Cổ Tích: Thạch Sanh",
        "fps": 24,
        "resolution": [1920, 1080],
        "shots": [
            {
                "shot_id": "SHOT_001",
                "scene_title": "Cảnh 1: Gốc Đa & Nghề Đốn Củi",
                "speaker": "Người Kể Chuyện",
                "dialogue": "Ngày xửa ngày xưa, ở quận Cao Bình có chàng Thạch Sanh mồ côi cha mẹ, sống nghèo khổ dưới gốc đa bằng nghề đốn củi nhưng vô cùng thật thà, dũng cảm.",
                "visual_theme": "forest_banyan_tree",
                "sky_color": [0.12, 0.28, 0.18],
                "ground_color": [0.22, 0.15, 0.08],
                "camera_angle": "wide_establishing"
            },
            {
                "shot_id": "SHOT_002",
                "scene_title": "Cảnh 2: Diệt Chằn Tinh",
                "speaker": "Người Kể Chuyện",
                "dialogue": "Bị Lý Thông lừa đi canh miếu thần thế mạng, Thạch Sanh không hề nao núng, vung búa thần đánh tan xác Chằn Tinh hung ác giải cứu dân lành.",
                "visual_theme": "temple_night_battle",
                "sky_color": [0.08, 0.05, 0.18],
                "ground_color": [0.15, 0.12, 0.15],
                "camera_angle": "low_heroic"
            },
            {
                "shot_id": "SHOT_003",
                "scene_title": "Cảnh 3: Bắn Đại Bàng Cứu Công Chúa",
                "speaker": "Người Kể Chuyện",
                "dialogue": "Khi công chúa Quỳnh Nga bị đại bàng khổng lồ bắt cóc, Thạch Sanh dùng cung vàng bắn trúng cánh đại bàng, lần theo vết máu xuống tận hang sâu cứu nàng.",
                "visual_theme": "deep_cave_rescue",
                "sky_color": [0.25, 0.14, 0.06],
                "ground_color": [0.18, 0.10, 0.05],
                "camera_angle": "dynamic_tracking"
            },
            {
                "shot_id": "SHOT_004",
                "scene_title": "Cảnh 4: Tiếng Đàn Thần & Niêu Cơm",
                "speaker": "Người Kể Chuyện",
                "dialogue": "Nhờ tiếng đàn thần giải oan và niêu cơm thần ăn mãi không vơi, Thạch Sanh vạch trần tội ác của mẹ con Lý Thông, kết duyên cùng công chúa và lên ngôi vua.",
                "visual_theme": "royal_palace_victory",
                "sky_color": [0.45, 0.32, 0.08],
                "ground_color": [0.35, 0.12, 0.10],
                "camera_angle": "medium_celebration"
            }
        ]
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
4. Lời thoại, Cảm xúc & Trường thị giác: Câu thoại tiếng Việt phải tự nhiên, sắc sảo, đúng ngữ cảnh điện ảnh; đi kèm trường `scene_title`, `visual_theme`, `sky_color`, `ground_color`, `emotion` (calm, urgent, angry, thoughtful), `speaking_rate_multiplier` (0.9 - 1.1) và `pitch_offset_semitones` (-2.0 đến +1.5).
5. Nhịp điệu góc máy: Cảnh 1 dùng `ESTABLISHING_WIDE` hoặc `OTS_CLOSE_UP`, các cảnh đối thoại cao trào dùng `OTS_CLOSE_UP` và `CLOSE_UP` có bật `rack_focus.enabled = true` khi chuyển lượt nói.
"""
    return (
        f"{schema_instruction.strip()}\n\n"
        f"DANH MỤC TÀI NGUYÊN 3D HIỆN CÓ:\n{json.dumps(inventory, ensure_ascii=False, indent=2)}\n\n"
        f"YÊU CẦU TẠO VIDEO TỪ NGƯỜI DÙNG:\n\"{user_request}\"\n\n"
        "Hãy trả về JSON đầy đủ chứa các khóa: project_meta, scene, characters, shots. "
        "Mỗi shot có shot_id duy nhất, scene_title, speaker, listener (ID trong characters), "
        "actors (mỗi ID chứa position_xyz), dialogue.text tiếng Việt và visual_theme. "
        "Phân cảnh phải đúng nội dung yêu cầu; không dùng 3 cảnh đối thoại kỹ thuật mẫu. "
        "Nếu danh sách tài nguyên rỗng, không được bịa đường dẫn tài nguyên."
    )


def generate_thanh_giong_storyboard() -> Dict[str, Any]:
    """Bản kể ngắn theo truyền thuyết dân gian, dành cho chế độ minh họa 2D.

    References: https://baotanglichsu.vn/vi/Articles/2001/66164/xuat-xu-cua-thanh-giong.html
    https://baotanglichsu.vn/VI/Articles/3096/11520/quan-the-di-tich-phu-djong-va-hoi-giong.html
    """
    beats = [
        ("Làng Phù Đổng", "giong_village", "Ở làng Phù Đổng, có cậu bé Gióng lên ba vẫn chưa biết nói, biết cười."),
        ("Lời gọi của sứ giả", "giong_envoy", "Giặc kéo đến. Nghe sứ giả tìm người cứu nước, Gióng bỗng cất tiếng xin ngựa sắt và giáp sắt."),
        ("Dân làng nuôi Gióng", "giong_growing", "Gióng ăn bao nhiêu cũng không đủ. Dân làng góp gạo nuôi cậu lớn nhanh như thổi."),
        ("Ngựa sắt và áo giáp", "giong_forge", "Thợ rèn ngày đêm đúc ngựa và vũ khí. Gióng vươn vai thành tráng sĩ, khoác giáp lên đường."),
        ("Tráng sĩ ra trận", "giong_battle", "Ngựa sắt phun lửa, đưa Gióng xông thẳng vào quân giặc. Tráng sĩ chiến đấu bảo vệ quê hương."),
        ("Bụi tre bên đường", "giong_bamboo", "Khi vũ khí sắt gãy, Gióng nhổ tre bên đường tiếp tục đánh, khiến quân giặc tháo chạy."),
        ("Bay về trời", "giong_ascension", "Dẹp yên giặc, Gióng đến núi Sóc, cởi áo giáp rồi cùng ngựa sắt bay lên trời."),
        ("Người anh hùng còn mãi", "giong_shrine", "Dân làng lập đền tưởng nhớ. Hình ảnh Thánh Gióng sống mãi cùng lòng yêu nước và sức mạnh đoàn kết."),
    ]
    return {
        "project_title": "Thánh Gióng — Người anh hùng làng Phù Đổng",
        "shots": [
            {"shot_id": f"SHOT_{i:03d}", "scene_title": f"Cảnh {i}: {title}",
             "visual_theme": theme, "dialogue": text,
             "sky_color": [0.24, 0.42, 0.60], "ground_color": [0.30, 0.40, 0.22]}
            for i, (title, theme, text) in enumerate(beats, 1)
        ],
    }


def write_storyboard(path: Path, storyboard: Dict[str, Any]):
    """Readers see a complete snapshot while a render is updating its shots."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(storyboard, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)

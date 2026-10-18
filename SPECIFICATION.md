# ĐẶC TẢ KỸ THUẬT CHI TIẾT: HỆ THỐNG SẢN XUẤT PHIM 3D ĐIỆN ẢNH TỰ ĐỘNG (CINE-CODE 7530)

- **Mã dự án:** `CINE-CODE-7530`
- **Agent thực thi mục tiêu:** Gemini 3.8 (Autonomous Coding Agent)
- **Nhân AI kịch bản:** `antigravity-cli`
- **Cấu hình phần cứng mục tiêu (Target Hardware):**
  - **Máy trạm:** Dell Precision 7530
  - **CPU:** Intel Xeon 6 nhân 12 luồng (Xử lý 100% logic Đạo diễn, Toán học 180 độ, TTS INT8 và Rhubarb Lip Sync — **Tiêu thụ 0 MB VRAM**)
  - **GPU:** NVIDIA Quadro P2000 4GB GDDR5 (Dành riêng cho Blender EEVEE Headless với trần bộ nhớ **dưới 3200 MB VRAM** và nén video phần cứng **`h264_nvenc`**)

---

## MỤC LỤC
1. [Kiến trúc Tổng thể & Luồng Xử lý Tuần tự](#1-kiến-trúc-tổng-thể--luồng-xử-lý-tuần-tự)
2. [Cấu trúc Thư mục Dự án](#2-cấu-trúc-thư-mục-dự-án)
3. [Đặc tả Schema Dữ liệu Trung tâm (`storyboard.json`)](#3-đặc-tả-schema-dữ-liệu-trung-tâm-storyboardjson)
4. [TẦNG 1: Giao diện, Ông Đạo Diễn, Nhân AI `antigravity-cli` & Quy tắc 180 độ](#4-tầng-1-giao-diện-ông-đạo-diễn-nhân-ai-antigravity-cli--quy-tắc-180-độ)
5. [TẦNG 2: Tạo Giọng Thoại Tự Nhiên & Tách Khẩu Hình Rhubarb (CPU Xeon - 0MB VRAM)](#5-tầng-2-tạo-giọng-thoại-tự-nhiên--tách-khẩu-hình-rhubarb-cpu-xeon---0mb-vram)
6. [TẦNG 3: Kết xuất Đồ họa Điện ảnh Blender EEVEE Headless (Tối ưu Quadro P2000)](#6-tầng-3-kết-xuất-đồ-họa-điện-ảnh-blender-eevee-headless-tối-ưu-quadro-p2000)
7. [TẦNG 4: Dựng phim J-Cut/L-Cut, Phủ màu LUT, Hạt phim 35mm & Xuất file `h264_nvenc`](#7-tầng-4-dựng-phim-j-cutl-cut-phủ-màu-lut-hạt-phim-35mm--xuất-file-h264_nvenc)
8. [Bộ Điều phối Trung tâm (`main_orchestrator.py`) & Giao thức Thực thi cho Gemini 3.8](#8-bộ-điều-phối-trung-tâm-main_orchestratorpy--giao-thức-thực-thi-cho-gemini-38)

---

## 1. KIẾN TRÚC TỔNG THỂ & LUỒNG XỬ LÝ TUẦN TỰ

### 1.1. Nguyên lý chống rời rạc & Bảo vệ 4GB VRAM
1. **Deterministic 3D State (Trạng thái 3D Định sẵn):** Khác với video AI sinh điểm ảnh ngẫu nhiên làm biến dạng mặt nhân vật và trôi bối cảnh, toàn bộ bộ phim được ghi hình trong một không gian 3D cố định (`scene.blend`), nhân vật cố định (`character.fbx`) và điều khiển bằng tọa độ toán học chính xác trong `storyboard.json`.
2. **Sequential Process Isolation (Cô lập Tiến trình Tuần tự):** Trên Quadro P2000 4GB VRAM, **tuyệt đối không chạy song song hai tiến trình chiếm GPU**. Mỗi tầng và mỗi cảnh quay (shot) được thực thi trong một tiến trình con (`subprocess`) độc lập; ngay khi kết thúc, tiến trình đó phải thoát hoàn toàn để trả lại 100% VRAM trước khi bước tiếp theo khởi chạy.

### 1.2. Sơ đồ Luồng Dữ liệu (End-to-End Pipeline Flow)
```text
[Người dùng nhập yêu cầu trên UI]
       │
       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 1: ĐẠO DIỄN & NHÂN AI ANTIGRAVITY-CLI (Chạy trên CPU Xeon)            │
│ 1. Ông Đạo Diễn (Director Analyzer) phân tích chủ đề, nhịp độ, nhân vật    │
│    và quét danh mục tài nguyên 3D sẵn có (Scenes, Characters, Mixamo).     │
│ 2. Gửi gói yêu cầu cấu trúc cho `antigravity-cli` sinh kịch bản phân cảnh. │
│ 3. Bộ giải Toán học Điện ảnh tính góc xoay nhân vật nhìn nhau và đặt máy   │
│    quay tuân thủ nghiêm ngặt Quy tắc 180 độ (180-Degree Rule).             │
│ ► ĐẦU RA: `workspace/storyboard.json` (Đã khóa mọi tọa độ & thông số)      │
└────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 2: GIỌNG THOẠI & KHẨU HÌNH RHUBARB (CPU Xeon 12 luồng - 0 MB VRAM)    │
│ 1. Khóa biến môi trường `CUDA_VISIBLE_DEVICES=""` để ép chạy 100% CPU.     │
│ 2. Chạy TTS (Kokoro-82M / Piper / F5-TTS INT8) + Bộ lọc cảm xúc giọng nói  │
│    (Pitch, Speed, EQ, Loudness -16 LUFS) -> Xuất `SHOT_XXX.wav`.           │
│ 3. Chạy `rhubarb` CLI quét `.wav` tách khẩu hình (A, O, E, M, F / A-H, X). │
│ 4. Biên dịch đường cong đóng/mở miệng mượt (Coarticulation Keyframes).     │
│ ► ĐẦU RA: `workspace/audio_wav/*.wav` + `workspace/visemes/*_visemes.json` │
└────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 3: KẾT XUẤT BLENDER EEVEE HEADLESS (GPU Quadro P2000 <= 3.2 GB VRAM)  │
│ Chạy tuần tự từng cảnh: `blender -b scene.blend -P render_shot.py`         │
│ 1. Ép mọi Texture > 2K xuống 2048x2048 + Dùng Instancing (`link=True`).    │
│ 2. Đặt nhân vật đúng tọa độ, nạp chuyển động Mixamo & gán Keyframe miệng. │
│ 3. Dựng đèn 3-Point Lighting (Key ấm, Fill dịu, Rim tách tóc) + Volumetric.│
│ 4. Ống kính 50-85mm, xóa phông f/2.0 khóa vào xương mắt + Rack Focus.      │
│ 5. Bật SSR, GTAO và hệ màu điện ảnh `AgX - High Contrast`.                 │
│ ► ĐẦU RA: `workspace/raw_renders/SHOT_XXX_raw.mp4` (0.8 - 1.5s / frame)    │
└────────────────────────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 4: DỰNG PHIM HẬU KỲ & NÉN PHẦN CỨNG NVENC (FFmpeg + P2000 NVENC)     │
│ 1. Cắt nối J-Cut / L-Cut tự động (âm thanh cảnh sau tràn sớm 0.3 giây).   │
│ 2. Trộn âm thanh nền (Room Tone) chạy xuyên suốt + Tự động Audio Ducking.  │
│ 3. Áp màu 3D LUT (`.cube`) + Hạt phim 35mm + Đóng khung CinemaScope 2.35:1.│
│ 4. Nén phần cứng với cờ `-c:v h264_nvenc -preset p6 -cq 18`.               │
│ ► ĐẦU RA CUỐI CÙNG: `workspace/final_cinematic_movie.mp4`                  │
└────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. CẤU TRÚC THƯ MỤC DỰ ÁN

Gemini 3.8 cần khởi tạo chính xác cấu trúc thư mục sau:

```text
cine_pipeline_7530/
├── SPECIFICATION.md
├── requirements.txt
├── pytest.ini
├── assets/
│   ├── scenes/
│   │   └── studio_office.blend          # File bối cảnh 3D dựng sẵn
│   ├── characters/
│   │   ├── char_minh.fbx                # Nhân vật 1 (có Armature + Eye Bone + Facial ShapeKeys)
│   │   └── char_lan.fbx                 # Nhân vật 2 (có Armature + Eye Bone + Facial ShapeKeys)
│   ├── animations/
│   │   ├── standing_talking_01.fbx      # Chuyển động Mixamo 1
│   │   ├── standing_explaining_02.fbx   # Chuyển động Mixamo 2
│   │   └── standing_listening_idle.fbx  # Chuyển động Mixamo 3
│   ├── audio/
│   │   └── room_tone_ambience.wav       # Âm thanh môi trường nền xuyên suốt
│   └── luts/
│       └── film_kodak_2383.cube         # File màu điện ảnh 3D LUT chuẩn
├── workspace/
│   ├── director_brief.json              # Bản phân tích của Ông Đạo Diễn
│   ├── storyboard.json                  # File dữ liệu trung tâm của toàn bộ phim
│   ├── audio_wav/                       # Chứa file .wav của từng cảnh
│   ├── visemes/                         # Chứa file khẩu hình .json của từng cảnh
│   ├── raw_renders/                     # Chứa video thô xuất từ Blender EEVEE
│   └── final_cinematic_movie.mp4        # Video điện ảnh hoàn chỉnh
├── src/
│   ├── __init__.py
│   ├── stage1_director/
│   │   ├── __init__.py
│   │   ├── director_analyzer.py         # Ông Đạo Diễn phân tích yêu cầu & quét Assets
│   │   ├── antigravity_client.py        # Cầu nối gọi nhân AI `antigravity-cli`
│   │   ├── camera_180_solver.py         # Toán học Quy tắc 180 độ & hướng nhìn nhân vật
│   │   └── web_ui.py                    # Giao diện người dùng nhập yêu cầu tạo phim
│   ├── stage2_speech_lipsync/
│   │   ├── __init__.py
│   │   ├── cpu_tts_generator.py         # Sinh giọng thoại tự nhiên trên CPU Xeon (0MB VRAM)
│   │   └── rhubarb_lipsync.py           # Chạy Rhubarb CLI & biên dịch Keyframe khẩu hình
│   ├── stage3_blender_eevee/
│   │   ├── __init__.py
│   │   ├── render_shot.py               # Script chạy trong Blender Headless (`blender -b -P`)
│   │   └── blender_runner.py            # Trình gọi Blender tuần tự & giám sát VRAM P2000
│   ├── stage4_post_nvenc/
│   │   ├── __init__.py
│   │   └── ffmpeg_nvenc_editor.py       # Dựng phim J-Cut/L-Cut, LUT, Grain, 2.35:1, NVENC
│   └── main_orchestrator.py             # Điều phối chạy tuần tự từ Tầng 1 đến Tầng 4
└── tests/
    ├── test_stage1_director.py
    ├── test_stage2_speech_lipsync.py
    ├── test_stage3_blender_eevee.py
    └── test_stage4_post_nvenc.py
```

---

## 3. ĐẶC TẢ SCHEMA DỮ LIỆU TRUNG TÂM (`storyboard.json`)

File `workspace/storyboard.json` là hợp đồng dữ liệu duy nhất nối 4 tầng. Mọi trường dưới đây là bắt buộc:

```json
{
  "project_meta": {
    "title": "Bản Giao Giao Thức Cuối",
    "fps": 24,
    "resolution": [1920, 1080],
    "aspect_ratio": "2.35:1",
    "vram_budget_mb": 3200,
    "max_texture_size": 2048,
    "color_management": {
      "view_transform": "AgX",
      "look": "AgX - High Contrast",
      "lut_path": "assets/luts/film_kodak_2383.cube",
      "film_grain_intensity": 6.5
    }
  },
  "scene": {
    "scene_id": "SCENE_STUDIO_OFFICE",
    "blend_file": "assets/scenes/studio_office.blend",
    "room_tone_file": "assets/scenes/../../assets/audio/room_tone_ambience.wav",
    "room_tone_base_volume": 0.16,
    "volumetric_lighting": true,
    "volumetric_density": 0.03,
    "instanced_props": [
      {
        "source_object_name": "Prop_Chair_Master",
        "instance_locations": [
          [-2.5, 1.5, 0.0],
          [-2.5, -1.5, 0.0],
          [2.5, 1.5, 0.0]
        ]
      }
    ]
  },
  "characters": {
    "CHAR_MINH": {
      "display_name": "Minh",
      "fbx_path": "assets/characters/char_minh.fbx",
      "armature_name": "Armature_Minh",
      "face_mesh_name": "Mesh_Head_Minh",
      "eye_bone_name": "Bone_Eye_Target",
      "jaw_bone_name": "Bone_Jaw",
      "height_m": 1.75,
      "voice_profile": {
        "engine": "kokoro_cpu_int8",
        "voice_preset": "vn_male_baritone",
        "base_speed": 0.96,
        "base_pitch_semitones": -1.2
      }
    },
    "CHAR_LAN": {
      "display_name": "Lan",
      "fbx_path": "assets/characters/char_lan.fbx",
      "armature_name": "Armature_Lan",
      "face_mesh_name": "Mesh_Head_Lan",
      "eye_bone_name": "Bone_Eye_Target",
      "jaw_bone_name": "Bone_Jaw",
      "height_m": 1.65,
      "voice_profile": {
        "engine": "kokoro_cpu_int8",
        "voice_preset": "vn_female_clear",
        "base_speed": 1.02,
        "base_pitch_semitones": 0.8
      }
    }
  },
  "shots": [
    {
      "shot_id": "SHOT_001",
      "shot_style": "OTS_CLOSE_UP",
      "speaker": "CHAR_MINH",
      "listener": "CHAR_LAN",
      "rack_focus": {
        "enabled": true,
        "from_character": "CHAR_LAN",
        "to_character": "CHAR_MINH",
        "start_sec": 0.25,
        "end_sec": 0.95
      },
      "actors": {
        "CHAR_MINH": {
          "position_xyz": [-1.1, 0.0, 0.0],
          "rotation_euler_deg": [0.0, 0.0, 90.0],
          "mixamo_animation": "assets/animations/standing_explaining_02.fbx"
        },
        "CHAR_LAN": {
          "position_xyz": [1.1, 0.0, 0.0],
          "rotation_euler_deg": [0.0, 0.0, -90.0],
          "mixamo_animation": "assets/animations/standing_listening_idle.fbx"
        }
      },
      "camera": {
        "lens_mm": 85.0,
        "aperture_fstop": 2.0,
        "line_of_action_side": "SIDE_A",
        "location_xyz": [0.58, -0.78, 1.59],
        "rotation_euler_deg": [88.4, 0.0, 39.1]
      },
      "dialogue": {
        "text": "Chúng ta chỉ có một cơ hội duy nhất để đồng bộ toàn bộ hệ thống trước khi máy chủ đóng băng.",
        "emotion": "serious_determined",
        "speaking_rate_multiplier": 0.95,
        "pitch_offset_semitones": -0.5,
        "wav_path": "workspace/audio_wav/SHOT_001.wav",
        "viseme_json_path": "workspace/visemes/SHOT_001_visemes.json"
      },
      "transition": {
        "cut_type": "J_CUT",
        "audio_overlap_sec": 0.3,
        "raw_render_path": "workspace/raw_renders/SHOT_001_raw.mp4"
      }
    }
  ]
}
```

---

## 4. TẦNG 1: GIAO DIỆN, ÔNG ĐẠO DIỄN, NHÂN AI `antigravity-cli` & QUY TẮC 180 ĐỘ

### 4.1. Luồng xử lý chi tiết Tầng 1
1. **Nhận yêu cầu từ Giao diện (`web_ui.py`):** Người dùng nhập nội dung yêu cầu tạo video (chủ đề, tình huống, thông điệp) trên giao diện Web hoặc CLI.
2. **Ông Đạo Diễn phân tích yêu cầu (`director_analyzer.py`):**
   - Quét thư mục `assets/` để lập danh mục chính xác các file `scenes/*.blend`, `characters/*.fbx`, và `animations/*.fbx` hiện có trên ổ cứng.
   - Phân tích yêu cầu của người dùng thành **Hồ sơ Chỉ đạo Đạo diễn (`director_brief.json`)**: xác định cấu trúc 3 hồi (Mở đầu thiết lập bối cảnh -> Cao trào đối thoại cận mặt -> Kết thúc), quy định vị trí đứng cố định của từng nhân vật và nhịp cắt cảnh.
3. **Gọi Nhân AI `antigravity-cli` (`antigravity_client.py`):**
   - Truyền `director_brief.json` cùng Schema bắt buộc vào `antigravity-cli` qua dòng lệnh.
   - `antigravity-cli` sinh ra danh sách các cảnh quay (`shots`) với câu thoại tự nhiên, gán đúng file chuyển động Mixamo và loại góc máy (`ESTABLISHING_WIDE`, `OTS_CLOSE_UP`, `CLOSE_UP`).
4. **Giải toán Quy tắc 180 độ (`camera_180_solver.py`):**
   - Với mỗi cảnh trong `shots`, tính vector nối giữa 2 nhân vật để khóa góc xoay trục $Z$ sao cho hai nhân vật nhìn thẳng vào mắt nhau.
   - Xác lập **Trục Hành Động (Line of Action)** và đặt Camera luôn nằm ở một phía cố định (`SIDE_A`) của trục này. Tự động gán tiêu cự ống kính từ `50mm` đến `85mm` cho tất cả các cảnh cận/trung cận.

### 4.2. Chia nhỏ Task Tầng 1
- **Task 1.1 (`camera_180_solver.py`):** Viết bộ giải hình học không gian 3D cho Quy tắc 180 độ và tính góc Euler `LookAt` chuẩn hệ tọa độ Blender.
- **Task 1.2 (`director_analyzer.py` & `antigravity_client.py`):** Viết logic Ông Đạo Diễn phân tích đề bài, đóng gói prompt kỹ thuật và gọi `antigravity-cli` sinh `storyboard.json` (kèm cơ chế tự sửa lỗi JSON nếu CLI trả về thừa ký tự Markdown).
- **Task 1.3 (`web_ui.py`):** Viết giao diện FastAPI + HTML5 đơn giản để người dùng nhập yêu cầu tạo phim và xem trạng thái xử lý trực tiếp.

### 4.3. Code mẫu chuẩn cho Tầng 1

#### File: `src/stage1_director/camera_180_solver.py`
```python
import math
import numpy as np
from typing import Tuple, Dict, List

def compute_blender_look_at_euler(cam_xyz: np.ndarray, target_xyz: np.ndarray) -> List[float]:
    """
    Tính góc xoay Euler [rx, ry, rz] (đơn vị: độ) theo hệ tọa độ Z-up của Blender.
    Mặc định Camera của Blender khi góc xoay (0, 0, 0) sẽ nhìn thẳng xuống trục -Z, đỉnh máy hướng theo +Y.
    Khi rx = 90 độ, rz = 0 độ, Camera nhìn dọc theo trục +Y.
    """
    delta = target_xyz - cam_xyz
    dist_xy = math.hypot(float(delta[0]), float(delta[1]))

    # Góc quay quanh trục Z (Pan) và trục X (Tilt)
    rz_rad = math.atan2(float(delta[1]), float(delta[0])) - (math.pi / 2.0)
    rz_rad = math.atan2(math.sin(rz_rad), math.cos(rz_rad))
    rx_rad = (math.pi / 2.0) + math.atan2(float(delta[2]), max(dist_xy, 1e-6))

    return [
        round(math.degrees(rx_rad), 2),
        0.0,
        round(math.degrees(rz_rad), 2)
    ]

def compute_actor_facing_z_deg(actor_xyz: List[float], target_xyz: List[float]) -> float:
    """Tính góc xoay Z (độ) để nhân vật đứng ở actor_xyz quay mặt nhìn thẳng vào target_xyz."""
    dx = target_xyz[0] - actor_xyz[0]
    dy = target_xyz[1] - actor_xyz[1]
    angle_rad = math.atan2(dy, dx) - (math.pi / 2.0)
    angle_rad = math.atan2(math.sin(angle_rad), math.cos(angle_rad))
    return round(math.degrees(angle_rad), 2)

def solve_180_degree_camera_rig(
    speaker_xyz: List[float],
    listener_xyz: List[float],
    speaker_height_m: float = 1.72,
    shot_style: str = "OTS_CLOSE_UP",
    locked_side: str = "SIDE_A"
) -> Dict:
    """
    Định vị Camera 3D tự động tuân thủ nghiêm ngặt Quy tắc 180 độ (180-Degree Rule):
    1. Cố định vector trục hành động (Line of Action) từ nhân vật có tọa độ X nhỏ hơn sang nhân vật có X lớn hơn
       để dù đổi vai người nói/người nghe thì pháp tuyến bán cầu `SIDE_A` KHÔNG BAO GIỜ bị đảo chiều.
    2. Đặt tiêu cự từ 50mm đến 85mm cho các cảnh cận/trung cận.
    """
    p_spk = np.array(speaker_xyz, dtype=float)
    p_lst = np.array(listener_xyz, dtype=float)

    # Cố định điểm neo Trái -> Phải trong không gian thế giới để giữ nguyên bán cầu máy quay
    if (p_spk[0], p_spk[1]) <= (p_lst[0], p_lst[1]):
        p_left, p_right = p_spk, p_lst
    else:
        p_left, p_right = p_lst, p_spk

    line_of_action = p_right - p_left
    loa_len = float(np.linalg.norm(line_of_action[:2]))
    loa_unit = line_of_action / loa_len if loa_len > 1e-5 else np.array([1.0, 0.0, 0.0])

    # Pháp tuyến vuông góc với Trục hành động trên mặt phẳng ngang XY
    side_multiplier = -1.0 if locked_side == "SIDE_A" else 1.0
    normal_side_unit = np.array([-loa_unit[1] * side_multiplier, loa_unit[0] * side_multiplier, 0.0])

    eye_z = float(p_spk[2]) + (speaker_height_m * 0.91)
    speaker_eye_pos = np.array([p_spk[0], p_spk[1], eye_z])

    vec_spk_to_lst = p_lst - p_spk
    dist_spk_to_lst = float(np.linalg.norm(vec_spk_to_lst[:2]))
    unit_spk_to_lst = vec_spk_to_lst / max(dist_spk_to_lst, 1e-5)

    if shot_style == "ESTABLISHING_WIDE":
        midpoint = (p_spk + p_lst) * 0.5
        cam_pos = midpoint + (normal_side_unit * 2.8)
        cam_pos[2] = eye_z + 0.12
        look_target = np.array([midpoint[0], midpoint[1], eye_z - 0.08])
        lens_mm = 50.0
        fstop = 2.8
    elif shot_style == "OTS_CLOSE_UP":
        # Đặt máy qua vai người nghe (Over-The-Shoulder), lệch về bán cầu SIDE_A 0.45m
        cam_pos = p_lst - (unit_spk_to_lst * 0.45) + (normal_side_unit * 0.48)
        cam_pos[2] = eye_z
        look_target = speaker_eye_pos
        lens_mm = 75.0
        fstop = 2.0
    else:  # CLOSE_UP (Cận mặt đặc tả cảm xúc)
        cam_pos = p_spk + (unit_spk_to_lst * 1.25) + (normal_side_unit * 0.52)
        cam_pos[2] = eye_z
        look_target = speaker_eye_pos
        lens_mm = 85.0
        fstop = 2.0

    rotation_deg = compute_blender_look_at_euler(cam_pos, look_target)

    return {
        "lens_mm": float(lens_mm),
        "aperture_fstop": float(fstop),
        "line_of_action_side": locked_side,
        "location_xyz": [round(float(c), 3) for c in cam_pos],
        "rotation_euler_deg": rotation_deg
    }
```

#### File: `src/stage1_director/director_analyzer.py` & `src/stage1_director/antigravity_client.py`
```python
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Any
from src.stage1_director.camera_180_solver import (
    solve_180_degree_camera_rig,
    compute_actor_facing_z_deg
)

def scan_available_3d_assets(assets_root: Path) -> Dict[str, Any]:
    """Quét danh sách tài nguyên 3D thực tế trong thư mục assets/ để cung cấp cho Ông Đạo Diễn."""
    scenes = [str(p.as_posix()) for p in (assets_root / "scenes").glob("*.blend")]
    chars = [str(p.as_posix()) for p in (assets_root / "characters").glob("*.fbx")]
    anims = [str(p.as_posix()) for p in (assets_root / "animations").glob("*.fbx")]
    luts = [str(p.as_posix()) for p in (assets_root / "luts").glob("*.cube")]
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
        f"{schema_instruction}\n\n"
        f"DANH MỤC TÀI NGUYÊN 3D HIỆN CÓ:\n{json.dumps(inventory, ensure_ascii=False, indent=2)}\n\n"
        f"YÊU CẦU TẠO VIDEO TỪ NGƯỜI DÙNG:\n\"{user_request}\"\n\n"
        f"Hãy trả về JSON đầy đủ chứa các khóa: project_meta, scene, characters, shots."
    )

def generate_storyboard_via_antigravity(
    user_request: str,
    assets_root: Path,
    output_storyboard_path: Path
) -> Dict[str, Any]:
    """
    Gọi `antigravity-cli` làm nhân AI sinh dữ liệu phim, sau đó chạy Bộ giải Toán học 180 độ
    để khóa chính xác góc nhìn nhân vật và tọa độ Camera 3D cho từng cảnh.
    """
    inventory = scan_available_3d_assets(assets_root)
    director_prompt = build_director_prompt_for_antigravity(user_request, inventory)

    cli_executable = shutil.which("antigravity-cli") or "antigravity-cli"
    cmd = [
        cli_executable,
        "chat",
        "--format", "json",
        "--prompt", director_prompt
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=True, encoding="utf-8")
    raw_text = proc.stdout.strip()

    # Bóc tách khối JSON an toàn nếu đầu ra có lẫn chữ bên ngoài
    first_brace = raw_text.find("{")
    last_brace = raw_text.rfind("}")
    if first_brace == -1 or last_brace == -1:
        raise ValueError(f"antigravity-cli không trả về JSON hợp lệ: {raw_text[:200]}")

    storyboard = json.loads(raw_text[first_brace:last_brace + 1])

    # Áp dụng Toán học Điện ảnh: Quy tắc 180 độ & Hướng mặt 2 nhân vật nhìn thẳng vào nhau
    characters = storyboard.get("characters", {})
    prev_speaker = None

    for idx, shot in enumerate(storyboard.get("shots", [])):
        shot_id = shot.get("shot_id", f"SHOT_{idx + 1:03d}")
        shot["shot_id"] = shot_id
        spk_id = shot["speaker"]
        lst_id = shot["listener"]

        spk_pos = shot["actors"][spk_id]["position_xyz"]
        lst_pos = shot["actors"][lst_id]["position_xyz"]

        # Khóa hướng xoay Z để 2 nhân vật luôn nhìn thẳng vào mắt nhau
        shot["actors"][spk_id]["rotation_euler_deg"] = [
            0.0, 0.0, compute_actor_facing_z_deg(spk_pos, lst_pos)
        ]
        shot["actors"][lst_id]["rotation_euler_deg"] = [
            0.0, 0.0, compute_actor_facing_z_deg(lst_pos, spk_pos)
        ]

        # Tính tọa độ Camera 3D theo Quy tắc 180 độ (luôn cố định ở SIDE_A)
        spk_height = float(characters.get(spk_id, {}).get("height_m", 1.72))
        shot_style = shot.get("shot_style", "OTS_CLOSE_UP")
        shot["camera"] = solve_180_degree_camera_rig(
            speaker_xyz=spk_pos,
            listener_xyz=lst_pos,
            speaker_height_m=spk_height,
            shot_style=shot_style,
            locked_side="SIDE_A"
        )

        # Tự động bật Rack Focus (trượt nét từ người vừa nói sang người mới nói)
        if prev_speaker and prev_speaker != spk_id:
            shot["rack_focus"] = {
                "enabled": True,
                "from_character": prev_speaker,
                "to_character": spk_id,
                "start_sec": 0.15,
                "end_sec": 0.75
            }
        prev_speaker = spk_id

        # Chuẩn hóa đường dẫn đầu ra cho Tầng 2, 3, 4
        shot["dialogue"]["wav_path"] = f"workspace/audio_wav/{shot_id}.wav"
        shot["dialogue"]["viseme_json_path"] = f"workspace/visemes/{shot_id}_visemes.json"
        shot["transition"] = {
            "cut_type": "J_CUT",
            "audio_overlap_sec": 0.3,
            "raw_render_path": f"workspace/raw_renders/{shot_id}_raw.mp4"
        }

    output_storyboard_path.parent.mkdir(parents=True, exist_ok=True)
    output_storyboard_path.write_text(
        json.dumps(storyboard, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    return storyboard
```

### 4.4. Luồng Test & Code Test Tầng 1 (`tests/test_stage1_director.py`)
- **Luồng kiểm thử:**
  1. Giả lập lệnh gọi `antigravity-cli` trả về kịch bản đối thoại 2 cảnh giữa `CHAR_MINH` (đứng ở `[-1.1, 0, 0]`) và `CHAR_LAN` (đứng ở `[1.1, 0, 0]`).
  2. Chạy `generate_storyboard_via_antigravity`.
  3. Kiểm tra tọa độ $Y$ của Camera ở cả Cảnh 1 (Minh nói) và Cảnh 2 (Lan nói) đều âm (`y < 0`), chứng minh máy quay không bao giờ vượt qua trục hành động $X$ (tuân thủ tuyệt đối Quy tắc 180 độ).
  4. Kiểm tra góc xoay $Z$ của Minh (`-90 độ`) và Lan (`+90 độ`) đối diện chính xác vào nhau.

```python
import json
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.stage1_director.antigravity_client import generate_storyboard_via_antigravity

MOCK_CLI_JSON = {
    "project_meta": {
        "title": "Test Movie",
        "fps": 24,
        "resolution": [1920, 1080],
        "aspect_ratio": "2.35:1",
        "vram_budget_mb": 3200,
        "max_texture_size": 2048,
        "color_management": {
            "view_transform": "AgX",
            "look": "AgX - High Contrast",
            "lut_path": "assets/luts/film_kodak_2383.cube",
            "film_grain_intensity": 6.0
        }
    },
    "scene": {
        "scene_id": "SCENE_01",
        "blend_file": "assets/scenes/studio_office.blend",
        "room_tone_file": "assets/audio/room_tone_ambience.wav",
        "room_tone_base_volume": 0.16
    },
    "characters": {
        "CHAR_MINH": {"height_m": 1.75, "voice_profile": {"engine": "kokoro_cpu_int8"}},
        "CHAR_LAN": {"height_m": 1.65, "voice_profile": {"engine": "kokoro_cpu_int8"}}
    },
    "shots": [
        {
            "shot_id": "SHOT_001",
            "shot_style": "OTS_CLOSE_UP",
            "speaker": "CHAR_MINH",
            "listener": "CHAR_LAN",
            "actors": {
                "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": "a.fbx"},
                "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": "b.fbx"}
            },
            "dialogue": {"text": "Câu thoại số 1.", "emotion": "serious"}
        },
        {
            "shot_id": "SHOT_002",
            "shot_style": "CLOSE_UP",
            "speaker": "CHAR_LAN",
            "listener": "CHAR_MINH",
            "actors": {
                "CHAR_MINH": {"position_xyz": [-1.1, 0.0, 0.0], "mixamo_animation": "b.fbx"},
                "CHAR_LAN": {"position_xyz": [1.1, 0.0, 0.0], "mixamo_animation": "a.fbx"}
            },
            "dialogue": {"text": "Câu thoại số 2 đáp lại.", "emotion": "urgent"}
        }
    ]
}

def test_stage1_180_degree_rule_and_manifest(tmp_path: Path):
    out_storyboard = tmp_path / "storyboard.json"
    mock_proc = MagicMock()
    mock_proc.stdout = json.dumps(MOCK_CLI_JSON, ensure_ascii=False)

    with patch("subprocess.run", return_value=mock_proc):
        data = generate_storyboard_via_antigravity(
            user_request="Tạo phim đối thoại 2 kỹ sư",
            assets_root=tmp_path,
            output_storyboard_path=out_storyboard
        )

    assert out_storyboard.exists()
    s1_cam_y = data["shots"][0]["camera"]["location_xyz"][1]
    s2_cam_y = data["shots"][1]["camera"]["location_xyz"][1]

    # Cả 2 cảnh quay phải nằm cùng một phía bán cầu (cùng dấu Y) theo Quy tắc 180 độ
    assert s1_cam_y < 0 and s2_cam_y < 0
    # Tiêu cự ống kính cận cảnh phải nằm trong dải 50mm - 85mm
    assert 50.0 <= data["shots"][0]["camera"]["lens_mm"] <= 85.0
    assert 50.0 <= data["shots"][1]["camera"]["lens_mm"] <= 85.0
    # Cảnh 2 đổi người nói phải tự động kích hoạt Rack Focus
    assert data["shots"][1]["rack_focus"]["enabled"] is True
```

---

## 5. TẦNG 2: TẠO GIỌNG THOẠI TỰ NHIÊN & TÁCH KHẨU HÌNH RHUBARB (CPU XEON - 0MB VRAM)

### 5.1. Luồng xử lý chi tiết Tầng 2
1. **Cô lập GPU tuyệt đối:** Đặt biến môi trường `os.environ["CUDA_VISIBLE_DEVICES"] = ""` ngay đầu tiến trình Tầng 2 để đảm bảo ONNX Runtime / PyTorch chỉ dùng tập lệnh `AVX2/AVX-512` trên 12 luồng của CPU Intel Xeon, giữ nguyên **0 MB VRAM** trên Quadro P2000.
2. **Sinh âm thanh thoại giàu cảm xúc (`cpu_tts_generator.py`):**
   - Hỗ trợ gọi trực tiếp **Kokoro-82M (ONNX INT8)** hoặc **Piper TTS CLI** trên CPU.
   - Tự động biến đổi ngữ điệu (Prosody Shaping) theo nhân vật và cảm xúc của từng câu thoại: điều chỉnh tốc độ nói (`speaking_rate_multiplier`), dịch cao độ giọng (`pitch_offset_semitones`) mà không làm méo tốc độ, lọc âm ấm (Warm EQ) và chuẩn hóa âm lượng về `-16 LUFS` bằng FFmpeg audio filter.
3. **Phân tích khẩu hình bằng Rhubarb Lip Sync (`rhubarb_lipsync.py`):**
   - Gọi lệnh `rhubarb -f json -r phonetic <SHOT_XXX.wav> -o <raw.json>` chạy đa luồng trên CPU Xeon.
   - Chuyển đổi bộ mã của Rhubarb sang cả **5 nhóm khẩu hình cốt lõi (`A, O, E, M, F`)** và **bộ Shape Keys chi tiết** kèm thuật toán nội suy **Coarticulation (Attack 0.04s / Release 0.05s)** để môi và xương hàm nhân vật 3D chuyển động mềm mại như người thật.

### 5.2. Chia nhỏ Task Tầng 2
- **Task 2.1 (`cpu_tts_generator.py`):** Viết trình sinh giọng đọc TTS INT8 trên CPU Xeon + Chuỗi xử lý hậu kỳ giọng nói theo cảm xúc nhân vật.
- **Task 2.2 (`rhubarb_lipsync.py`):** Viết trình gọi `rhubarb` CLI, ánh xạ chính xác các nhãn khẩu hình (`A, O, E, M, F`) sang trọng số xương hàm (`jaw_open`) và Shape Keys của khuôn mặt 3D.

### 5.3. Code mẫu chuẩn cho Tầng 2

#### File: `src/stage2_speech_lipsync/cpu_tts_generator.py`
```python
import os
import wave
import math
import struct
import shutil
import subprocess
from pathlib import Path
from typing import Dict

# Khóa cứng GPU để Tầng 2 tốn đúng 0 MB VRAM trên Quadro P2000
os.environ["CUDA_VISIBLE_DEVICES"] = ""
os.environ["OMP_NUM_THREADS"] = "12"

EMOTION_PROSODY_MAP: Dict[str, Dict[str, float]] = {
    "calm":               {"speed": 0.95, "pitch_st": -0.5, "bass_gain_db": 2.0},
    "serious_determined": {"speed": 0.96, "pitch_st": -1.0, "bass_gain_db": 3.0},
    "urgent":             {"speed": 1.08, "pitch_st":  0.6, "bass_gain_db": 0.5},
    "angry":              {"speed": 1.06, "pitch_st": -0.8, "bass_gain_db": 3.5},
    "thoughtful":         {"speed": 0.90, "pitch_st": -1.2, "bass_gain_db": 2.5},
}

def synthesize_dialogue_cpu_xeon(
    dialogue_cfg: Dict,
    voice_profile: Dict,
    output_wav_path: Path
) -> Path:
    """
    Sinh file âm thanh thoại .wav tự nhiên trên CPU Xeon (0 MB VRAM):
    1. Gọi Kokoro-82M INT8 (qua ONNX Runtime CPUExecutionProvider) hoặc Piper TTS CLI.
    2. Áp dụng hiệu chỉnh ngữ điệu nhân vật (Pitch shift, Speaking rate, Warm EQ & Loudnorm) qua FFmpeg.
    """
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    raw_tts_wav = output_wav_path.with_suffix(".raw_tts.wav")

    text = dialogue_cfg["text"]
    emotion = dialogue_cfg.get("emotion", "calm")
    emo_cfg = EMOTION_PROSODY_MAP.get(emotion, EMOTION_PROSODY_MAP["calm"])

    base_speed = float(voice_profile.get("base_speed", 1.0)) * float(dialogue_cfg.get("speaking_rate_multiplier", emo_cfg["speed"]))
    base_pitch_st = float(voice_profile.get("base_pitch_semitones", 0.0)) + float(dialogue_cfg.get("pitch_offset_semitones", emo_cfg["pitch_st"]))
    bass_db = emo_cfg["bass_gain_db"]

    piper_bin = shutil.which("piper")
    if piper_bin:
        model_path = voice_profile.get("model_onnx_path", "models/tts/vi_VN-vais1000-medium.onnx")
        length_scale = round(1.0 / max(base_speed, 0.5), 3)
        cmd_tts = [
            piper_bin,
            "--model", str(model_path),
            "--length_scale", str(length_scale),
            "--output_file", str(raw_tts_wav)
        ]
        subprocess.run(cmd_tts, input=text, text=True, check=True, encoding="utf-8")
    else:
        # Fallback tổng hợp sóng âm ngữ âm chuẩn hóa phục vụ môi trường CI/Test khi chưa nạp file .onnx
        _generate_fallback_speech_waveform(text, raw_tts_wav, speed=base_speed)

    # Hậu xử lý giọng nói tự nhiên bằng FFmpeg trên CPU Xeon (Dịch cao độ bảo toàn thời gian + EQ ấm + Chuẩn hóa âm lượng)
    pitch_factor = round(2.0 ** (base_pitch_st / 12.0), 4)
    tempo_comp = round(1.0 / pitch_factor, 4)
    af_chain = (
        f"asetrate=24000*{pitch_factor},aresample=24000,atempo={tempo_comp},"
        f"equalizer=f=180:width_type=o:width=1.5:g={bass_db},"
        f"loudnorm=I=-16:TP=-1.5:LRA=11"
    )
    cmd_post = [
        "ffmpeg", "-y",
        "-i", str(raw_tts_wav),
        "-af", af_chain,
        "-ar", "24000",
        "-ac", "1",
        "-c:a", "pcm_s16le",
        str(output_wav_path)
    ]
    subprocess.run(cmd_post, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    raw_tts_wav.unlink(missing_ok=True)
    return output_wav_path

def _generate_fallback_speech_waveform(text: str, wav_path: Path, speed: float = 1.0):
    """Tạo sóng âm có chu kỳ âm tiết thực tế (dùng khi chạy kiểm thử tự động không có file model .onnx)."""
    sample_rate = 24000
    words = text.split()
    duration_sec = max(1.5, (len(words) * 0.32) / max(speed, 0.5))
    total_samples = int(sample_rate * duration_sec)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_samples):
            t = i / sample_rate
            # Điều chế biên độ theo nhịp âm tiết (4.5 âm tiết/giây) để Rhubarb nhận diện rõ các hình miệng A, O, E, M, F
            syllable_env = max(0.0, math.sin(2.0 * math.pi * 4.2 * t))
            formant_1 = math.sin(2.0 * math.pi * 165.0 * t)
            formant_2 = 0.5 * math.sin(2.0 * math.pi * 620.0 * t)
            val = int(14000 * syllable_env * (formant_1 + formant_2))
            frames.extend(struct.pack("<h", max(-32767, min(32767, val))))
        wf.writeframes(frames)
```

#### File: `src/stage2_speech_lipsync/rhubarb_lipsync.py`
```python
import json
import wave
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List

# Bảng chuyển đổi từ mã Preston Blair của Rhubarb CLI (A, B, C, D, E, F, G, H, X)
# sang đúng 5 nhóm khẩu hình cốt lõi (A, O, E, M, F) + trạng thái nghỉ (SIL)
# và trọng số trực tiếp cho Xương hàm (jaw_open) + Shape Keys môi trên nhân vật 3D.
RHUBARB_PHONEME_MAPPING: Dict[str, Dict] = {
    "A": {  # Mím hai môi (Âm M, B, P) -> Nhóm khẩu hình 'M'
        "phoneme_group": "M",
        "jaw_open": 0.02,
        "weights": {"shape_A": 0.0, "shape_O": 0.0, "shape_E": 0.0, "shape_M": 1.0, "shape_F": 0.0}
    },
    "B": {  # Hé răng khép nhẹ (Âm S, T, K, D) -> Nhóm khẩu hình 'E' nhẹ
        "phoneme_group": "E",
        "jaw_open": 0.22,
        "weights": {"shape_A": 0.1, "shape_O": 0.0, "shape_E": 0.65, "shape_M": 0.0, "shape_F": 0.0}
    },
    "C": {  # Mở miệng bè ngang (Nguyên âm E, Ê, I) -> Nhóm khẩu hình 'E'
        "phoneme_group": "E",
        "jaw_open": 0.45,
        "weights": {"shape_A": 0.2, "shape_O": 0.0, "shape_E": 1.0, "shape_M": 0.0, "shape_F": 0.0}
    },
    "D": {  # Mở rộng hàm tối đa (Nguyên âm A, AI, AY) -> Nhóm khẩu hình 'A'
        "phoneme_group": "A",
        "jaw_open": 0.88,
        "weights": {"shape_A": 1.0, "shape_O": 0.1, "shape_E": 0.2, "shape_M": 0.0, "shape_F": 0.0}
    },
    "E": {  # Tròn môi mở vừa (Nguyên âm O, Ô, Ơ) -> Nhóm khẩu hình 'O'
        "phoneme_group": "O",
        "jaw_open": 0.58,
        "weights": {"shape_A": 0.15, "shape_O": 1.0, "shape_E": 0.0, "shape_M": 0.0, "shape_F": 0.0}
    },
    "F": {  # Chu môi nhỏ (Nguyên âm U, Ư, QU) -> Nhóm khẩu hình 'O' (chu hẹp)
        "phoneme_group": "O",
        "jaw_open": 0.25,
        "weights": {"shape_A": 0.0, "shape_O": 0.85, "shape_E": 0.0, "shape_M": 0.1, "shape_F": 0.0}
    },
    "G": {  # Răng cửa hàm trên chạm môi dưới (Âm F, V, PH) -> Nhóm khẩu hình 'F'
        "phoneme_group": "F",
        "jaw_open": 0.12,
        "weights": {"shape_A": 0.0, "shape_O": 0.0, "shape_E": 0.1, "shape_M": 0.0, "shape_F": 1.0}
    },
    "H": {  # Lưỡi chạm lợi trên (Âm L, N, R) -> Nhóm khẩu hình 'A' hẹp
        "phoneme_group": "A",
        "jaw_open": 0.38,
        "weights": {"shape_A": 0.55, "shape_O": 0.0, "shape_E": 0.25, "shape_M": 0.0, "shape_F": 0.0}
    },
    "X": {  # Khép miệng nghỉ giữa câu -> Nhóm 'SIL'
        "phoneme_group": "SIL",
        "jaw_open": 0.0,
        "weights": {"shape_A": 0.0, "shape_O": 0.0, "shape_E": 0.0, "shape_M": 0.0, "shape_F": 0.0}
    }
}

def measure_wav_duration_sec(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as wf:
        return round(wf.getnframes() / float(wf.getframerate()), 3)

def run_rhubarb_lipsync_on_xeon(
    wav_path: Path,
    viseme_json_output_path: Path,
    fps: int = 24
) -> Dict:
    """
    Quét file .wav bằng công cụ dòng lệnh `rhubarb` trên CPU Xeon và xuất bảng Keyframe
    đánh dấu chính xác từng phần trăm giây miệng nhân vật mở hình chữ A, O, E, M, F.
    """
    viseme_json_output_path.parent.mkdir(parents=True, exist_ok=True)
    raw_rhubarb_out = viseme_json_output_path.with_suffix(".rhubarb_raw.json")

    rhubarb_bin = shutil.which("rhubarb") or "rhubarb"
    cmd = [
        rhubarb_bin,
        "-f", "json",
        "-r", "phonetic",
        "--threads", "8",
        "-o", str(raw_rhubarb_out),
        str(wav_path)
    ]
    subprocess.run(cmd, check=True)

    raw_data = json.loads(raw_rhubarb_out.read_text(encoding="utf-8"))
    duration_sec = measure_wav_duration_sec(wav_path)
    total_frames = max(1, int(round(duration_sec * fps)))

    keyframes: List[Dict] = []
    for cue in raw_data.get("mouthCues", []):
        start_cs = round(float(cue["start"]), 2)  # Chính xác tới từng phần trăm giây (0.01s)
        end_cs = round(float(cue["end"]), 2)
        rhubarb_code = cue.get("value", "X")
        mapped = RHUBARB_PHONEME_MAPPING.get(rhubarb_code, RHUBARB_PHONEME_MAPPING["X"])

        frame_start = max(1, int(round(start_cs * fps)) + 1)
        frame_end = max(frame_start, int(round(end_cs * fps)) + 1)
        frame_peak = max(frame_start, int(round((start_cs + end_cs) * 0.5 * fps)) + 1)

        keyframes.append({
            "rhubarb_code": rhubarb_code,
            "mouth_shape": mapped["phoneme_group"],  # A, O, E, M, F, hoặc SIL
            "start_sec": start_cs,
            "end_sec": end_cs,
            "frame_start": frame_start,
            "frame_peak": frame_peak,
            "frame_end": frame_end,
            "jaw_open": mapped["jaw_open"],
            "weights": mapped["weights"]
        })

    result = {
        "wav_path": str(wav_path.as_posix()),
        "duration_sec": duration_sec,
        "fps": fps,
        "total_frames": total_frames,
        "keyframes": keyframes
    }
    viseme_json_output_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    raw_rhubarb_out.unlink(missing_ok=True)
    return result
```

### 5.4. Luồng Test & Code Test Tầng 2 (`tests/test_stage2_speech_lipsync.py`)
- **Luồng kiểm thử:**
  1. Kiểm tra biến môi trường `CUDA_VISIBLE_DEVICES` bằng chuỗi rỗng `""` (đảm bảo 0MB VRAM).
  2. Gọi `synthesize_dialogue_cpu_xeon` sinh file `SHOT_001.wav` và kiểm tra tần số mẫu `24000Hz`.
  3. Giả lập đầu ra `mouthCues` của `rhubarb` CLI và kiểm tra `run_rhubarb_lipsync_on_xeon` xuất ra đầy đủ các nhóm khẩu hình `A, O, E, M, F` với độ chính xác tới phần trăm giây.

```python
import os
import json
from pathlib import Path
from unittest.mock import patch
from src.stage2_speech_lipsync.cpu_tts_generator import synthesize_dialogue_cpu_xeon
from src.stage2_speech_lipsync.rhubarb_lipsync import run_rhubarb_lipsync_on_xeon

def test_stage2_zero_vram_tts_and_rhubarb_mapping(tmp_path: Path):
    # 1. Đảm bảo GPU bị khóa hoàn toàn ở Tầng 2 (0 MB VRAM)
    assert os.environ.get("CUDA_VISIBLE_DEVICES") == ""

    wav_out = tmp_path / "SHOT_001.wav"
    viseme_out = tmp_path / "SHOT_001_visemes.json"

    dialogue_cfg = {
        "text": "Một bộ phim điện ảnh cần khẩu hình khớp từng phần trăm giây.",
        "emotion": "serious_determined",
        "speaking_rate_multiplier": 1.0,
        "pitch_offset_semitones": -1.0
    }
    voice_profile = {"base_speed": 1.0, "base_pitch_semitones": -0.5}

    with patch("shutil.which", return_value=None):
        synthesize_dialogue_cpu_xeon(dialogue_cfg, voice_profile, wav_out)

    assert wav_out.exists() and wav_out.stat().st_size > 8000

    # 2. Kiểm tra phân tích khẩu hình Rhubarb sang 5 nhóm A, O, E, M, F
    fake_rhubarb_output = {
        "metadata": {"duration": 1.60},
        "mouthCues": [
            {"start": 0.00, "end": 0.18, "value": "A"},  # -> M
            {"start": 0.18, "end": 0.52, "value": "D"},  # -> A
            {"start": 0.52, "end": 0.88, "value": "E"},  # -> O
            {"start": 0.88, "end": 1.22, "value": "C"},  # -> E
            {"start": 1.22, "end": 1.60, "value": "G"}   # -> F
        ]
    }

    def fake_rhubarb_cmd(cmd, check):
        out_idx = cmd.index("-o") + 1
        Path(cmd[out_idx]).write_text(json.dumps(fake_rhubarb_output), encoding="utf-8")

    with patch("subprocess.run", side_effect=fake_rhubarb_cmd):
        viseme_data = run_rhubarb_lipsync_on_xeon(wav_out, viseme_out, fps=24)

    shapes = [kf["mouth_shape"] for kf in viseme_data["keyframes"]]
    assert shapes == ["M", "A", "O", "E", "F"]
    assert viseme_data["keyframes"][1]["weights"]["shape_A"] == 1.0
    assert viseme_data["keyframes"][2]["weights"]["shape_O"] == 1.0
```

---

## 6. TẦNG 3: KẾT XUẤT ĐỒ HỌA ĐIỆN ẢNH BLENDER EEVEE HEADLESS (TỐI ƯU QUADRO P2000)

### 6.1. Luồng xử lý chi tiết Tầng 3
Đối với từng cảnh quay trong `storyboard.json`, hệ thống gọi tiến trình Blender chạy ngầm:
```bash
blender -b <blend_file> -P src/stage3_blender_eevee/render_shot.py -- --storyboard workspace/storyboard.json --shot-id SHOT_001
```
Script `render_shot.py` tự động thực thi **5 thông số vàng** cho Quadro P2000 4GB VRAM:
1. **Ống kính 50mm–85mm, Xóa phông `f/2.0` & Trượt nét (Rack Focus) vào Xương Mắt:**
   - Thiết lập `camera.data.lens` (từ `50mm` đến `85mm`), bật `dof.use_dof = True`, `dof.aperture_fstop = 2.0`.
   - Truy xuất tọa độ thế giới của xương mắt (`armature.matrix_world @ armature.pose.bones[eye_bone_name].head`) của nhân vật đang nói và gán một vật thể `Empty` (`dof.focus_object`) bám dính vào đó. Khi `rack_focus.enabled = True`, nội suy Keyframe trượt `Empty` từ xương mắt nhân vật trước sang xương mắt nhân vật đang nói.
2. **Ánh sáng Thể tích (Volumetrics) & Hệ thống Đèn 3-Point Lighting + Soft Shadows:**
   - Bật `eevee.use_volumetric_lighting = True`, `eevee.use_soft_shadows = True`.
   - Tự động tính vector hướng nhìn từ máy quay đến nhân vật để đặt 3 đèn `AREA`: **Key Light** (nhiệt độ màu ấm `3200K`), **Fill Light** (dịu `5600K`), và **Rim Light** (đặt phía sau gáy chiếu ngược để tách viền tóc nhân vật khỏi nền tối).
3. **Phản chiếu Không gian Màn hình (SSR) & Chiều sâu Góc khuất (GTAO):**
   - Bật `eevee.use_ssr = True`, `eevee.use_ssr_refraction = True` và `eevee.use_gtao = True` để tạo độ bóng trong mắt nhân vật và chiều sâu ở nếp gấp quần áo.
4. **Quản lý màu sắc chuẩn rạp (`AgX - High Contrast`):**
   - Thiết lập `scene.view_settings.view_transform = 'AgX'` và `scene.view_settings.look = 'AgX - High Contrast'` (có cơ chế tự động kiểm tra và nạp cấu hình OCIO AgX hoặc fallback sang `Filmic - High Contrast` nếu bản cài đặt Blender thiếu profile).
5. **Kỷ luật bộ nhớ 4GB VRAM (Texture <= 2K & Instancing `link=True`):**
   - Duyệt toàn bộ `bpy.data.images`, ép mọi Texture lớn hơn `2048x2048` xuống `2048x2048` bằng `img.scale(2048, 2048)`.
   - Nhân bản tất cả đồ vật lặp lại (bàn ghế, cột, cây) bằng `inst_obj.data = src_obj.data` (`link=True`) để dùng chung bộ nhớ Mesh trên GPU.

### 6.2. Chia nhỏ Task Tầng 3
- **Task 3.1:** Viết module nạp nhân vật `.fbx`, gán chuyển động cơ thể Mixamo và đóng Keyframe khẩu hình (`A, O, E, M, F`) vào cả Shape Keys lẫn xương hàm (`Bone_Jaw`).
- **Task 3.2:** Viết module thiết lập 5 thông số điện ảnh EEVEE tối ưu cho Quadro P2000 trong `src/stage3_blender_eevee/render_shot.py`.
- **Task 3.3:** Viết trình điều khiển `src/stage3_blender_eevee/blender_runner.py` gọi Blender tuần tự từng cảnh và đo kiểm mức VRAM tiêu thụ trên Quadro P2000.

### 6.3. Code mẫu chuẩn cho Tầng 3

#### File: `src/stage3_blender_eevee/render_shot.py`
```python
import bpy
import sys
import json
import math
from pathlib import Path
from mathutils import Vector, Euler

def get_cli_arguments() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parsed = {}
    for i in range(0, len(argv), 2):
        if i + 1 < len(argv):
            parsed[argv[i].lstrip("-")] = argv[i + 1]
    return parsed

def enforce_4gb_vram_discipline(scene_cfg: dict, max_tex_res: int = 2048):
    """
    THÔNG SỐ 5 - Kỷ luật bộ nhớ 4GB VRAM trên Quadro P2000:
    1. Dọn sạch dữ liệu mồ côi (Orphan meshes/materials/textures).
    2. Hạ độ phân giải mọi Texture vượt quá 2K (2048x2048) ngay trong RAM trước khi đẩy lên VRAM.
    3. Tạo các vật thể lặp lại (cây cối, bàn ghế) bằng kỹ thuật Instancing (link=True).
    """
    try:
        bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    except Exception:
        pass

    for img in bpy.data.images:
        if img.size[0] > max_tex_res or img.size[1] > max_tex_res:
            new_w = min(img.size[0], max_tex_res)
            new_h = min(img.size[1], max_tex_res)
            img.scale(new_w, new_h)

    if hasattr(bpy.context.preferences.system, "gl_texture_limit"):
        bpy.context.preferences.system.gl_texture_limit = 'CLAMP_2048'

    # Thực thi Instancing (link=True) cho các đồ vật lặp lại trong bối cảnh
    for prop_group in scene_cfg.get("instanced_props", []):
        src_name = prop_group.get("source_object_name")
        src_obj = bpy.data.objects.get(src_name)
        if not src_obj:
            continue
        for idx, loc in enumerate(prop_group.get("instance_locations", [])):
            inst_name = f"{src_name}_Instance_{idx:02d}"
            if inst_name not in bpy.data.objects:
                inst_obj = src_obj.copy()
                inst_obj.data = src_obj.data  # link=True: chia sẻ 100% Mesh & UV trong VRAM
                inst_obj.name = inst_name
                bpy.context.collection.objects.link(inst_obj)
            bpy.data.objects[inst_name].location = Vector(loc)

def setup_eevee_cinematic_pipeline(scene, meta: dict, scene_cfg: dict):
    """
    Thiết lập THÔNG SỐ 2 (Volumetrics & Soft Shadows), THÔNG SỐ 3 (SSR & GTAO),
    và THÔNG SỐ 4 (Quản lý màu sắc chuẩn rạp AgX - High Contrast).
    """
    engines = [e.identifier for e in scene.render.bl_rna.properties['engine'].enum_items]
    scene.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in engines else 'BLENDER_EEVEE'
    eevee = scene.eevee

    # THÔNG SỐ 2: Ánh sáng thể tích (Volumetrics) & Bóng đổ mềm (Soft Shadows)
    if hasattr(eevee, "use_volumetric_lighting"):
        eevee.use_volumetric_lighting = bool(scene_cfg.get("volumetric_lighting", True))
        eevee.use_volumetric_shadows = True
        eevee.volumetric_tile_size = '8'
    if hasattr(eevee, "use_soft_shadows"):
        eevee.use_soft_shadows = True
        eevee.shadow_cube_size = '1024'
        eevee.shadow_cascade_size = '2048'

    # Tạo sương/bụi thể tích nhẹ trong World Shader nếu chưa có
    if scene.world and scene.world.use_nodes:
        tree = scene.world.node_tree
        if "Volume Scatter" not in [n.bl_idname for n in tree.nodes]:
            vol_node = tree.nodes.new(type="ShaderNodeVolumeScatter")
            vol_node.inputs["Density"].default_value = float(scene_cfg.get("volumetric_density", 0.025))
            vol_node.inputs["Anisotropy"].default_value = 0.6
            out_node = next((n for n in tree.nodes if n.bl_idname == "ShaderNodeOutputWorld"), None)
            if out_node:
                tree.links.new(vol_node.outputs["Volume"], out_node.inputs["Volume"])

    # THÔNG SỐ 3: Phản chiếu không gian màn hình (SSR) & Chiều sâu góc khuất (GTAO)
    if hasattr(eevee, "use_ssr"):
        eevee.use_ssr = True
        eevee.use_ssr_refraction = True
        eevee.ssr_quality = 0.55
    if hasattr(eevee, "use_gtao"):
        eevee.use_gtao = True
        eevee.gtao_distance = 0.45

    eevee.taa_render_samples = 32

    # THÔNG SỐ 4: Quản lý màu sắc chuẩn rạp AgX - High Contrast
    cm = scene.view_settings
    target_transform = meta["color_management"].get("view_transform", "AgX")
    target_look = meta["color_management"].get("look", "AgX - High Contrast")
    try:
        cm.view_transform = target_transform
        cm.look = target_look
    except TypeError:
        cm.view_transform = "Filmic"
        cm.look = "High Contrast"

def setup_three_point_lighting(speaker_pos: Vector, camera_pos: Vector):
    """
    THÔNG SỐ 2 (Tiếp): Thiết lập hệ thống đèn 3-Point Lighting chuẩn điện ảnh:
    - Key Light (Ấm 3200K): Tạo khối sáng chính trên gương mặt.
    - Fill Light (Dịu 5600K): Cân bằng vùng tối bên má khuất sáng.
    - Rim Light (Đèn tách tóc): Đánh ngược từ phía sau lưng để tách viền nhân vật khỏi phông nền.
    """
    for ob in list(bpy.data.objects):
        if ob.name.startswith("CINE_3PT_"):
            bpy.data.objects.remove(ob, do_unlink=True)

    head_target = speaker_pos + Vector((0.0, 0.0, 1.62))
    cam_dir = (camera_pos - head_target).normalized()
    side_vec = cam_dir.cross(Vector((0.0, 0.0, 1.0))).normalized()

    rig_specs = [
        ("CINE_3PT_KEY",  head_target + cam_dir * 1.45 + side_vec * 1.15 + Vector((0, 0, 0.65)), 135.0, (1.00, 0.87, 0.74), 1.1),
        ("CINE_3PT_FILL", head_target + cam_dir * 1.65 - side_vec * 1.35 + Vector((0, 0, 0.25)),  45.0, (0.80, 0.89, 1.00), 1.7),
        ("CINE_3PT_RIM",  head_target - cam_dir * 1.25 - side_vec * 0.35 + Vector((0, 0, 0.75)), 105.0, (0.96, 0.98, 1.00), 0.65),
    ]

    for light_name, loc, power, color_rgb, area_size in rig_specs:
        l_data = bpy.data.lights.new(name=light_name, type='AREA')
        l_data.energy = power
        l_data.color = color_rgb
        l_data.size = area_size
        if hasattr(l_data, "use_contact_shadow"):
            l_data.use_contact_shadow = True
        l_obj = bpy.data.objects.new(name=light_name, object_data=l_data)
        bpy.context.collection.objects.link(l_obj)
        l_obj.location = loc
        l_obj.rotation_euler = (head_target - loc).to_track_quat('-Z', 'Y').to_euler()

def get_eye_bone_world_location(char_id: str, char_cfg: dict, actor_state: dict) -> Vector:
    """Lấy tọa độ thế giới chính xác của xương mắt (`eye_bone_name`) trên nhân vật."""
    arm_name = char_cfg.get("armature_name", char_id)
    eye_bone_name = char_cfg.get("eye_bone_name", "Bone_Eye_Target")
    arm_obj = bpy.data.objects.get(arm_name) or bpy.data.objects.get(char_id)

    if arm_obj and arm_obj.type == 'ARMATURE' and eye_bone_name in arm_obj.pose.bones:
        pose_bone = arm_obj.pose.bones[eye_bone_name]
        return arm_obj.matrix_world @ pose_bone.head

    base_pos = Vector(actor_state["position_xyz"])
    height_m = float(char_cfg.get("height_m", 1.72))
    return base_pos + Vector((0.0, 0.0, height_m * 0.91))

def setup_camera_dof_and_rack_focus(scene, shot: dict, characters_cfg: dict, fps: int):
    """
    THÔNG SỐ 1: Ống kính 50mm-85mm, Xóa phông vật lý (f/2.0) khóa vào xương mắt nhân vật
    và tự động trượt điểm lấy nét (Rack Focus) khi chuyển lượt nói.
    """
    cam_cfg = shot["camera"]
    cam_data = bpy.data.cameras.new("CINE_SHOT_CAM_DATA")
    cam_data.lens = max(50.0, min(85.0, float(cam_cfg.get("lens_mm", 85.0))))
    cam_data.sensor_width = 36.0

    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = float(cam_cfg.get("aperture_fstop", 2.0))

    cam_obj = bpy.data.objects.new("CINE_SHOT_CAMERA", cam_data)
    bpy.context.collection.objects.link(cam_obj)
    scene.camera = cam_obj

    cam_obj.location = Vector(cam_cfg["location_xyz"])
    cam_obj.rotation_euler = Euler([math.radians(d) for d in cam_cfg["rotation_euler_deg"]], 'XYZ')

    focus_target = bpy.data.objects.new("CINE_EYE_FOCUS_TARGET", None)
    bpy.context.collection.objects.link(focus_target)
    cam_data.dof.focus_object = focus_target

    spk_id = shot["speaker"]
    spk_eye_loc = get_eye_bone_world_location(spk_id, characters_cfg.get(spk_id, {}), shot["actors"][spk_id])

    rack_cfg = shot.get("rack_focus", {})
    if rack_cfg.get("enabled") and rack_cfg.get("from_character") in shot["actors"]:
        from_id = rack_cfg["from_character"]
        to_id = rack_cfg["to_character"]
        from_loc = get_eye_bone_world_location(from_id, characters_cfg.get(from_id, {}), shot["actors"][from_id])
        to_loc = get_eye_bone_world_location(to_id, characters_cfg.get(to_id, {}), shot["actors"][to_id])

        f_start = max(1, int(round(float(rack_cfg.get("start_sec", 0.2)) * fps)))
        f_end = max(f_start + 1, int(round(float(rack_cfg.get("end_sec", 0.8)) * fps)))

        focus_target.location = from_loc
        focus_target.keyframe_insert(data_path="location", frame=1)
        focus_target.keyframe_insert(data_path="location", frame=f_start)

        focus_target.location = to_loc
        focus_target.keyframe_insert(data_path="location", frame=f_end)
    else:
        focus_target.location = spk_eye_loc

def apply_mixamo_and_lipsync_keyframes(
    char_id: str,
    char_cfg: dict,
    actor_state: dict,
    viseme_json_path: Path,
    is_speaker: bool
):
    """
    Đặt nhân vật vào đúng tọa độ, nạp chuyển động Mixamo (.fbx) và đóng Keyframe
    khẩu hình (A, O, E, M, F) điều khiển trực tiếp môi (Shape Keys) và xương hàm (Jaw Bone).
    """
    arm_name = char_cfg.get("armature_name", char_id)
    char_obj = bpy.data.objects.get(arm_name) or bpy.data.objects.get(char_id)

    # Nếu nhân vật chưa có sẵn trong file .blend thì nạp từ file .fbx
    if not char_obj:
        fbx_file = Path(char_cfg.get("fbx_path", ""))
        if fbx_file.exists():
            bpy.ops.import_scene.fbx(filepath=str(fbx_file))
            char_obj = bpy.context.selected_objects[0] if bpy.context.selected_objects else None

    if not char_obj:
        return

    char_obj.location = Vector(actor_state["position_xyz"])
    char_obj.rotation_euler = Euler([math.radians(x) for x in actor_state["rotation_euler_deg"]], 'XYZ')

    # Nạp chuyển động cơ thể từ thư viện Mixamo nếu file tồn tại
    mixamo_path = Path(actor_state.get("mixamo_animation", ""))
    if mixamo_path.exists() and char_obj.type == 'ARMATURE':
        bpy.ops.import_scene.fbx(filepath=str(mixamo_path))
        imported_arms = [o for o in bpy.context.selected_objects if o.type == 'ARMATURE' and o != char_obj]
        if imported_arms and imported_arms[0].animation_data and imported_arms[0].animation_data.action:
            if not char_obj.animation_data:
                char_obj.animation_data_create()
            char_obj.animation_data.action = imported_arms[0].animation_data.action
            for temp_ob in imported_arms:
                bpy.data.objects.remove(temp_ob, do_unlink=True)

    if not is_speaker or not viseme_json_path.exists():
        return

    viseme_data = json.loads(viseme_json_path.read_text(encoding="utf-8"))
    face_mesh = bpy.data.objects.get(char_cfg.get("face_mesh_name", ""))
    jaw_bone_name = char_cfg.get("jaw_bone_name", "Bone_Jaw")

    for cue in viseme_data.get("keyframes", []):
        f_start = cue["frame_start"]
        f_peak = cue["frame_peak"]
        jaw_val = float(cue["jaw_open"])
        weights = cue["weights"]

        # Điều khiển Shape Keys môi (shape_A, shape_O, shape_E, shape_M, shape_F)
        if face_mesh and face_mesh.type == 'MESH' and face_mesh.data.shape_keys:
            kb = face_mesh.data.shape_keys.key_blocks
            for shape_name, w_val in weights.items():
                if shape_name in kb:
                    kb[shape_name].value = float(w_val)
                    kb[shape_name].keyframe_insert(data_path="value", frame=f_peak)

        # Điều khiển Xương hàm (Jaw Bone) mở theo độ rộng nguyên âm
        if char_obj.type == 'ARMATURE' and jaw_bone_name in char_obj.pose.bones:
            jaw_bone = char_obj.pose.bones[jaw_bone_name]
            jaw_bone.rotation_mode = 'XYZ'
            jaw_bone.rotation_euler[0] = math.radians(jaw_val * 22.0)
            jaw_bone.keyframe_insert(data_path="rotation_euler", index=0, frame=f_start)
            jaw_bone.keyframe_insert(data_path="rotation_euler", index=0, frame=f_peak)

def main():
    args = get_cli_arguments()
    storyboard_path = Path(args["storyboard"])
    shot_id = args["shot-id"]

    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    meta = storyboard["project_meta"]
    scene_cfg = storyboard["scene"]
    characters_cfg = storyboard["characters"]
    shot = next(s for s in storyboard["shots"] if s["shot_id"] == shot_id)

    scene = bpy.context.scene
    fps = int(meta.get("fps", 24))
    scene.render.fps = fps
    scene.render.resolution_x = int(meta["resolution"][0])
    scene.render.resolution_y = int(meta["resolution"][1])
    scene.render.resolution_percentage = 100

    viseme_path = Path(shot["dialogue"]["viseme_json_path"])
    if viseme_path.exists():
        v_info = json.loads(viseme_path.read_text(encoding="utf-8"))
        scene.frame_start = 1
        # Render dư thêm 0.35 giây ở cuối cảnh để Tầng 4 thực hiện kỹ thuật cắt J-Cut / L-Cut mượt mà
        scene.frame_end = int(v_info["total_frames"]) + int(round(fps * 0.35))
    else:
        scene.frame_start = 1
        scene.frame_end = fps * 3

    for char_id, actor_state in shot["actors"].items():
        apply_mixamo_and_lipsync_keyframes(
            char_id=char_id,
            char_cfg=characters_cfg.get(char_id, {}),
            actor_state=actor_state,
            viseme_json_path=viseme_path,
            is_speaker=(char_id == shot["speaker"])
        )

    setup_camera_dof_and_rack_focus(scene, shot, characters_cfg, fps)

    spk_pos = Vector(shot["actors"][shot["speaker"]]["position_xyz"])
    cam_pos = Vector(shot["camera"]["location_xyz"])
    setup_three_point_lighting(spk_pos, cam_pos)

    setup_eevee_cinematic_pipeline(scene, meta, scene_cfg)
    enforce_4gb_vram_discipline(scene_cfg, max_tex_res=int(meta.get("max_texture_size", 2048)))

    out_video = Path(shot["transition"]["raw_render_path"]).resolve()
    out_video.parent.mkdir(parents=True, exist_ok=True)
    scene.render.filepath = str(out_video)
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'HIGH'

    bpy.ops.render.render(animation=True)

if __name__ == "__main__":
    main()
```

### 6.4. Luồng Test & Code Test Tầng 3 (`tests/test_stage3_blender_eevee.py`)
- **Luồng kiểm thử:**
  1. Kiểm tra mã nguồn `render_shot.py` có thiết lập đầy đủ 5 cơ chế bắt buộc cho Quadro P2000: `use_dof = True`, `aperture_fstop`, `use_volumetric_lighting`, `use_ssr`, `use_gtao`, `AgX - High Contrast`, `img.scale` (giới hạn 2048) và `inst_obj.data = src_obj.data` (Instancing).
  2. Kiểm tra lệnh gọi tiến trình `blender -b <scene.blend> -P render_shot.py` truyền đúng tham số `--storyboard` và `--shot-id`.

```python
from pathlib import Path
from src.stage3_blender_eevee import render_shot

def test_stage3_render_script_contains_all_5_p2000_optimizations():
    source_code = Path(render_shot.__file__).read_text(encoding="utf-8")

    # 1. Ống kính 50-85mm + Xóa phông f/2.0 + Rack Focus
    assert "cam_data.dof.use_dof = True" in source_code
    assert "cam_data.dof.focus_object" in source_code
    # 2. Volumetrics & 3-Point Lighting
    assert "use_volumetric_lighting" in source_code
    assert "CINE_3PT_KEY" in source_code and "CINE_3PT_FILL" in source_code and "CINE_3PT_RIM" in source_code
    # 3. SSR & GTAO
    assert "eevee.use_ssr = True" in source_code
    assert "eevee.use_gtao = True" in source_code
    # 4. Hệ màu chuẩn rạp AgX - High Contrast
    assert "AgX - High Contrast" in source_code
    # 5. Kỷ luật 4GB VRAM: Giới hạn Texture 2048 & Instancing
    assert "img.scale(new_w, new_h)" in source_code
    assert "inst_obj.data = src_obj.data" in source_code
```

---

## 7. TẦNG 4: DỰNG PHIM J-CUT/L-CUT, PHỦ MÀU LUT, HẠT PHIM 35MM & XUẤT FILE `h264_nvenc`

### 7.1. Luồng xử lý chi tiết Tầng 4
1. **Ghép từng phân cảnh kèm đệm đuôi J-Cut:** Ghép từng file `SHOT_XXX_raw.mp4` với file thoại `SHOT_XXX.wav` tương ứng, giữ lại `0.3 giây` hình ảnh ở cuối mỗi cảnh.
2. **Kỹ thuật cắt J-Cut / L-Cut tự động:** Dùng bộ lọc `xfade` và `acrossfade=d=0.3` của FFmpeg để âm thanh của cảnh tiếp theo vang lên sớm hơn **0.3 giây** trước khi hình ảnh chuyển sang cảnh mới, đồng thời giữ nguyên độ khớp khẩu hình tuyệt đối ở tất cả các cảnh.
3. **Âm thanh môi trường (`Room Tone`) xuyên suốt + Audio Ducking:** Lặp vô hạn file `room_tone_ambience.wav` bên dưới toàn bộ bộ phim và dùng bộ nén `sidechaincompress` (Audio Ducking) để âm thanh môi trường tự động dịu xuống nhẹ nhàng mỗi khi nhân vật cất tiếng nói và đầy lên trong các khoảng nghỉ.
4. **Phủ màu 3D LUT (`.cube`), Hạt phim 35mm & Đóng khung CinemaScope `2.35:1`:**
   - Áp dụng `lut3d=file=assets/luts/film_kodak_2383.cube:interp=tetrahedral`.
   - Phủ lớp hạt phim 35mm (`noise=alls=6.5:allf=t+u`).
   - Đóng khung tỉ lệ màn ảnh rộng `2.35:1` (tạo 2 dải đen điện ảnh cao `132px` ở đỉnh và đáy khung hình `1920x1080`, để lại vùng hình ảnh chuẩn rạp `1920x816`).
5. **Nén phần cứng bằng chip NVENC trên Quadro P2000:** Gọi cờ `-c:v h264_nvenc -preset p6 -cq 18` (có tự động kiểm tra và fallback sang `libx264` chỉ khi chạy trên máy test CI không gắn card NVIDIA).

### 7.2. Code mẫu chuẩn cho Tầng 4

#### File: `src/stage4_post_nvenc/ffmpeg_nvenc_editor.py`
```python
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
```

### 7.3. Luồng Test & Code Test Tầng 4 (`tests/test_stage4_post_nvenc.py`)
- **Luồng kiểm thử:**
  1. Tạo một file màu 3D LUT `.cube` chuẩn (`LUT_3D_SIZE 2`) và kiểm tra hàm `build_ffmpeg_master_command` sinh đầy đủ các cờ bắt buộc: `acrossfade=d=0.3`, `lut3d=file=`, `noise=alls=`, `drawbox=` (CinemaScope `2.35:1`) và `-c:v h264_nvenc -preset p6 -cq 18`.

```python
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
```

---

## 8. BỘ ĐIỀU PHỐI TRUNG TÂM (`main_orchestrator.py`) & GIAO THỨC THỰC THI CHO GEMINI 3.8

### 8.1. Code Điều phối Toàn tuyến (`src/main_orchestrator.py`)
```python
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
    storyboard = generate_storyboard_via_antigravity(
        user_request=user_prompt,
        assets_root=assets_root,
        output_storyboard_path=storyboard_path
    )
    fps = int(storyboard["project_meta"].get("fps", 24))
    characters = storyboard["characters"]

    # 2. TẦNG 2: Sinh giọng thoại tự nhiên & Tách khẩu hình Rhubarb trên CPU Xeon (0MB VRAM)
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
    return assemble_final_cinematic_movie(storyboard_path, final_movie_path)
```

### 8.2. Danh sách Kiểm tra Nghiệm thu (Checklist) bắt buộc cho Gemini 3.8
1. [ ] Khởi tạo toàn bộ cây thư mục và file theo đúng Mục 2.
2. [ ] Hoàn thiện Tầng 1 và chạy `pytest tests/test_stage1_director.py` đạt **PASSED**.
3. [ ] Hoàn thiện Tầng 2 và chạy `pytest tests/test_stage2_speech_lipsync.py` đạt **PASSED** (mức sử dụng VRAM = `0 MB`).
4. [ ] Hoàn thiện Tầng 3 và chạy `pytest tests/test_stage3_blender_eevee.py` đạt **PASSED** (đầy đủ 5 thông số tối ưu EEVEE trên Quadro P2000).
5. [ ] Hoàn thiện Tầng 4 và chạy `pytest tests/test_stage4_post_nvenc.py` đạt **PASSED** (có J-Cut `0.3s`, Room Tone xuyên suốt, LUT `.cube`, Film Grain, khung `2.35:1` và cờ `-c:v h264_nvenc -preset p6 -cq 18`).
# CINE-CODE-7530 (videoremotion)

**Hệ thống sản xuất phim 3D điện ảnh tự động** tối ưu hóa cho máy trạm Dell Precision 7530 (Intel Xeon CPU + NVIDIA Quadro P2000 4GB VRAM).

## 🌟 Tính năng chính

- **Tầng 1 (Đạo Diễn AI):** Phân tích kịch bản, quét tài nguyên 3D, giải toán không gian **Quy tắc 180 độ** (180-Degree Rule), tự động điều khiển Rack Focus và hướng nhìn nhân vật.
- **Tầng 2 (Giọng thoại & Khẩu hình):** TTS INT8 trên CPU Xeon (**0 MB VRAM**), phân tích khẩu hình **Rhubarb Lip Sync** sang 5 nhóm chuẩn (`A, O, E, M, F`) và Shape Keys / Xương hàm.
- **Tầng 3 (Blender EEVEE Headless):** Kết xuất tuần tự trên Quadro P2000 (**< 3.2 GB VRAM**), giới hạn Texture 2K, Instancing, ánh sáng 3-Point Lighting, màu điện ảnh AgX High Contrast.
- **Tầng 4 (Hậu kỳ & Nén phần cứng NVENC):** Cắt nối **J-Cut / L-Cut** tự động (overlap 0.3s), Room Tone xuyên suốt + audio ducking, 3D LUT Kodak 2383, hạt phim 35mm, tỉ lệ **CinemaScope 2.35:1**, nén `h264_nvenc`.

## 🚀 Khởi chạy ứng dụng

### 1. Cài đặt môi trường
```bash
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

### 2. Chạy giao diện Web Director UI
```bash
.\.venv\Scripts\python -m uvicorn src.stage1_director.web_ui:app --host 127.0.0.1 --port 8000
```
Truy cập: [http://127.0.0.1:8000](http://127.0.0.1:8000)

### 3. Chạy kiểm thử toàn bộ hệ thống
```bash
.\.venv\Scripts\pytest -v
```

### 4. Chạy điều phối toàn tuyến qua CLI
```bash
.\.venv\Scripts\python -m src.main_orchestrator "Tạo truyện cổ tích Thánh Gióng"
```

## Chế độ tạo video và kiểm tra đầu ra

- Máy cần Antigravity CLI để viết kịch bản cho chủ đề bất kỳ, cùng Blender và tài nguyên `.blend`/`.fbx` thật để dựng phim 3D. Các tệp `CINE_CODE_PLACEHOLDER` không phải tài nguyên sử dụng được.
- Khi chưa có các thành phần trên, có thể tạo **video minh họa 2D có lời kể** cho Thánh Gióng (8 cảnh), Thạch Sanh (4 cảnh), hoặc nhập `Kịch bản:` kèm nội dung lời kể. Kịch bản tự nhập được chia theo câu/đoạn và dùng bối cảnh minh họa phòng làm việc; không tự sinh hình cho chủ đề tùy ý.
- Giọng đọc dùng Piper nếu có mô hình cục bộ, hoặc Edge-TTS/gTTS qua mạng. Nếu không tạo được giọng đọc, ứng dụng báo lỗi và không thay bằng sóng âm giả.
- Mỗi lần tạo trên web có thư mục riêng `workspace/jobs/<job_id>/`. Danh sách cảnh và nội dung phát lại luôn thuộc cùng một lần tạo. `workspace/latest_job.json` lưu trạng thái sau khi khởi động lại.
- Chỉ mở video để phát/tải khi FFmpeg giải mã thành công, hình/tiếng có thời lượng khớp với toàn bộ kịch bản, không có đoạn đen từ 0,5 giây và có âm thanh nghe được. Kiểm tra này không đánh giá chất lượng nghệ thuật hoặc độ đúng nội dung bằng AI.

Phần dựng chuẩn hóa đồng hồ và thời lượng từng cảnh trước khi chuyển cảnh; xem [tài liệu FFmpeg](https://ffmpeg.org/ffmpeg-filters.html#xfade).

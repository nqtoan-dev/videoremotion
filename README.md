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
.\.venv\Scripts\python -m src.main_orchestrator "Hai kỹ sư tranh luận về bảo mật máy chủ"
```

import json
import time
import threading
from pathlib import Path
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from pydantic import BaseModel

from src.main_orchestrator import execute_cinematic_pipeline

app = FastAPI(
    title="CINE-CODE 7530 Director Studio",
    description="Hệ thống Sản xuất Phim 3D Điện ảnh Tự động tối ưu cho Dell Precision 7530 (Xeon + Quadro P2000)",
)

WORKSPACE_DIR = Path("workspace")
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

# Trạng thái tiến trình toàn cục phục vụ giao diện theo dõi thời gian thực
PIPELINE_STATE: Dict[str, Any] = {
    "status": "idle",  # idle | running | completed | error
    "current_stage": 0,
    "percent": 0,
    "message": "Sẵn sàng nhận yêu cầu từ Đạo diễn.",
    "logs": [],
    "video_ready": (WORKSPACE_DIR / "final_cinematic_movie.mp4").exists(),
    "video_timestamp": int(time.time()),
    "error_detail": None,
}
STATE_LOCK = threading.Lock()


class RenderJobRequest(BaseModel):
    prompt: str


def _update_progress(stage: int, message: str, percent: int):
    with STATE_LOCK:
        PIPELINE_STATE["current_stage"] = stage
        PIPELINE_STATE["percent"] = percent
        PIPELINE_STATE["message"] = message
        timestamp = time.strftime("%H:%M:%S")
        PIPELINE_STATE["logs"].append(f"[{timestamp}] [TẦNG {stage}] {message}")


def _background_pipeline_worker(prompt: str):
    with STATE_LOCK:
        PIPELINE_STATE["status"] = "running"
        PIPELINE_STATE["current_stage"] = 1
        PIPELINE_STATE["percent"] = 5
        PIPELINE_STATE["message"] = "Khởi động dây chuyền sản xuất 4 tầng..."
        PIPELINE_STATE["logs"] = [f"[{time.strftime('%H:%M:%S')}] Nhận đề bài: {prompt}"]
        PIPELINE_STATE["error_detail"] = None

    try:
        out_video = execute_cinematic_pipeline(prompt, progress_callback=_update_progress)
        with STATE_LOCK:
            PIPELINE_STATE["status"] = "completed"
            PIPELINE_STATE["current_stage"] = 4
            PIPELINE_STATE["percent"] = 100
            PIPELINE_STATE["video_ready"] = out_video.exists()
            PIPELINE_STATE["video_timestamp"] = int(time.time())
            PIPELINE_STATE["message"] = "Đã xuất bản bộ phim điện ảnh thành công!"
    except Exception as exc:
        with STATE_LOCK:
            PIPELINE_STATE["status"] = "error"
            PIPELINE_STATE["error_detail"] = str(exc)
            PIPELINE_STATE["message"] = f"Lỗi thực thi: {exc}"
            PIPELINE_STATE["logs"].append(f"[ERROR] {exc}")


@app.post("/api/render")
def start_render_job(req: RenderJobRequest):
    if not req.prompt or not req.prompt.strip():
        raise HTTPException(status_code=400, detail="Vui lòng nhập nội dung yêu cầu tạo video.")

    with STATE_LOCK:
        if PIPELINE_STATE["status"] == "running":
            raise HTTPException(status_code=409, detail="Hệ thống đang kết xuất một bộ phim khác, vui lòng đợi.")

    worker = threading.Thread(target=_background_pipeline_worker, args=(req.prompt.strip(),), daemon=True)
    worker.start()
    return {"status": "started", "prompt": req.prompt.strip()}


@app.get("/api/status")
def get_pipeline_status():
    storyboard_data = None
    sb_path = WORKSPACE_DIR / "storyboard.json"
    if sb_path.exists():
        try:
            storyboard_data = json.loads(sb_path.read_text(encoding="utf-8"))
            # Đính kèm tóm tắt khẩu hình từ Tầng 2 cho từng cảnh để hiển thị trên UI
            for shot in storyboard_data.get("shots", []):
                v_path = Path(shot.get("dialogue", {}).get("viseme_json_path", ""))
                if v_path.exists():
                    v_json = json.loads(v_path.read_text(encoding="utf-8"))
                    shot["viseme_summary"] = {
                        "duration_sec": v_json.get("duration_sec", 0.0),
                        "total_frames": v_json.get("total_frames", 0),
                        "mouth_sequence": [k["mouth_shape"] for k in v_json.get("keyframes", [])[:18]],
                    }
        except Exception:
            storyboard_data = None

    with STATE_LOCK:
        video_file = WORKSPACE_DIR / "final_cinematic_movie.mp4"
        return {
            **PIPELINE_STATE,
            "video_ready": video_file.exists() and video_file.stat().st_size > 1000,
            "storyboard": storyboard_data,
        }


@app.get("/api/video")
def stream_final_video():
    video_file = WORKSPACE_DIR / "final_cinematic_movie.mp4"
    if not video_file.exists():
        raise HTTPException(status_code=404, detail="Chưa có file video đầu ra.")
    return FileResponse(
        path=str(video_file),
        media_type="video/mp4",
        filename="final_cinematic_movie.mp4",
    )


@app.get("/api/audio/{shot_id}")
def stream_shot_audio(shot_id: str):
    wav_file = WORKSPACE_DIR / "audio_wav" / f"{shot_id}.wav"
    if not wav_file.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file âm thanh của cảnh này.")
    return FileResponse(path=str(wav_file), media_type="audio/wav")


STUDIO_HTML = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>CINE-CODE 7530 — Bàn Dựng Đạo Diễn Điện Ảnh 3D</title>
  <style>
    :root {
      --bg-dark: #090d16;
      --bg-panel: #111827;
      --bg-card: #1e293b;
      --border: #334155;
      --accent: #38bdf8;
      --accent-gold: #f59e0b;
      --success: #10b981;
      --danger: #ef4444;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
      background-color: var(--bg-dark);
      color: var(--text-main);
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    header {
      background: linear-gradient(90deg, #0f172a 0%, #1e293b 100%);
      border-bottom: 1px solid var(--border);
      padding: 14px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .brand-badge {
      background: var(--accent-gold);
      color: #000;
      font-weight: 800;
      font-size: 12px;
      padding: 4px 8px;
      border-radius: 4px;
      letter-spacing: 0.5px;
    }
    .brand h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0.3px;
    }
    .hw-pills {
      display: flex;
      gap: 10px;
      font-size: 12px;
    }
    .hw-pill {
      background: rgba(56, 189, 248, 0.12);
      border: 1px solid rgba(56, 189, 248, 0.35);
      color: var(--accent);
      padding: 5px 10px;
      border-radius: 6px;
      font-weight: 600;
    }
    .studio-grid {
      display: grid;
      grid-template-columns: 340px 1fr 390px;
      gap: 16px;
      padding: 16px;
      flex: 1;
    }
    @media (max-width: 1280px) {
      .studio-grid { grid-template-columns: 1fr; }
    }
    .panel {
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: 10px;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }
    .panel-header {
      padding: 12px 16px;
      background: rgba(255, 255, 255, 0.03);
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.6px;
      color: var(--accent);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    .panel-body {
      padding: 16px;
      display: flex;
      flex-direction: column;
      gap: 14px;
      flex: 1;
      overflow-y: auto;
    }
    label {
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      display: block;
      margin-bottom: 6px;
    }
    textarea {
      width: 100%;
      min-height: 125px;
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-main);
      padding: 12px;
      font-size: 14px;
      line-height: 1.5;
      resize: vertical;
    }
    textarea:focus {
      outline: none;
      border-color: var(--accent);
    }
    .preset-chips {
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .chip {
      background: var(--bg-card);
      border: 1px solid var(--border);
      color: var(--text-muted);
      padding: 8px 10px;
      border-radius: 6px;
      font-size: 12px;
      cursor: pointer;
      text-align: left;
      transition: all 0.15s;
    }
    .chip:hover {
      border-color: var(--accent);
      color: var(--text-main);
    }
    .btn-primary {
      background: linear-gradient(135deg, #0284c7 0%, #2563eb 100%);
      color: #fff;
      border: none;
      padding: 13px 16px;
      border-radius: 8px;
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      transition: opacity 0.2s;
    }
    .btn-primary:disabled {
      opacity: 0.5;
      cursor: not-allowed;
    }
    .spec-box {
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      font-size: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .spec-row {
      display: flex;
      justify-content: space-between;
      border-bottom: 1px dashed rgba(255,255,255,0.07);
      padding-bottom: 5px;
    }
    /* Cột giữa: Pipeline 4 tầng & Màn chiếu 2.35:1 */
    .stages-bar {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
    }
    .stage-card {
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 12px;
      transition: all 0.25s;
    }
    .stage-card.active {
      border-color: var(--accent);
      box-shadow: 0 0 12px rgba(56, 189, 248, 0.25);
    }
    .stage-card.done {
      border-color: var(--success);
      background: rgba(16, 185, 129, 0.08);
    }
    .stage-num {
      font-size: 11px;
      font-weight: 800;
      color: var(--accent-gold);
    }
    .stage-name {
      font-size: 12px;
      font-weight: 700;
      margin-top: 3px;
    }
    .stage-hw {
      font-size: 11px;
      color: var(--text-muted);
      margin-top: 2px;
    }
    .progress-wrap {
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 14px;
    }
    .progress-top {
      display: flex;
      justify-content: space-between;
      font-size: 12px;
      margin-bottom: 6px;
    }
    .progress-track {
      width: 100%;
      height: 8px;
      background: #1e293b;
      border-radius: 99px;
      overflow: hidden;
    }
    .progress-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--accent), var(--success));
      width: 0%;
      transition: width 0.3s ease;
    }
    .viewport-box {
      background: #000;
      border: 1px solid var(--border);
      border-radius: 10px;
      overflow: hidden;
      position: relative;
      aspect-ratio: 16 / 9;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    video {
      width: 100%;
      height: 100%;
      object-fit: contain;
      background: #000;
    }
    .viewport-placeholder {
      text-align: center;
      color: var(--text-muted);
      padding: 24px;
      font-size: 13px;
    }
    .action-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
    }
    .btn-download {
      background: var(--success);
      color: #000;
      font-weight: 700;
      font-size: 13px;
      padding: 9px 16px;
      border-radius: 6px;
      text-decoration: none;
      display: inline-block;
    }
    .console-box {
      background: #05080f;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px;
      font-family: monospace;
      font-size: 12px;
      color: #cbd5e1;
      height: 135px;
      overflow-y: auto;
      line-height: 1.45;
    }
    /* Cột phải: Storyboard & Shot Inspector */
    .shot-card {
      background: #0b1120;
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .shot-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 12px;
      font-weight: 700;
    }
    .badge-shot {
      background: rgba(245, 158, 11, 0.15);
      color: var(--accent-gold);
      border: 1px solid rgba(245, 158, 11, 0.4);
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 11px;
    }
    .shot-dialogue {
      font-size: 13px;
      color: #e2e8f0;
      font-style: italic;
      background: rgba(255,255,255,0.03);
      padding: 8px;
      border-left: 3px solid var(--accent);
      border-radius: 4px;
    }
    .shot-meta {
      font-size: 11px;
      color: var(--text-muted);
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 4px;
    }
    .viseme-strip {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 2px;
    }
    .v-pill {
      font-size: 10px;
      font-weight: 700;
      padding: 2px 5px;
      border-radius: 3px;
      background: #1e293b;
      color: var(--accent);
      border: 1px solid #334155;
    }
    audio {
      width: 100%;
      height: 30px;
      margin-top: 4px;
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <span class="brand-badge">CINE-CODE 7530</span>
      <h1>STUDIO ĐẠO DIỄN ĐIỆN ẢNH 3D TỰ ĐỘNG</h1>
    </div>
    <div class="hw-pills">
      <span class="hw-pill">CPU: Intel Xeon 6C/12T (TTS + Rhubarb: 0MB VRAM)</span>
      <span class="hw-pill">GPU: Quadro P2000 4GB (EEVEE &lt; 3.2GB VRAM + h264_nvenc)</span>
    </div>
  </header>

  <div class="studio-grid">
    <!-- CỘT 1: CHỈ ĐẠO ĐẠO DIỄN & KỶ LUẬT PHẦN CỨNG -->
    <section class="panel">
      <div class="panel-header">
        <span>1. Bàn Chỉ Đạo Đạo Diễn (Tầng 1)</span>
        <span>antigravity-cli</span>
      </div>
      <div class="panel-body">
        <div>
          <label for="promptInput">NHẬP YÊU CẦU TẠO PHIM CHO ÔNG ĐẠO DIỄN:</label>
          <textarea id="promptInput" placeholder="Nhập chủ đề, tình huống hoặc lời thoại bạn muốn tạo phim...">Cuộc tranh luận lúc nửa đêm giữa hai kỹ sư Minh và Lan về việc kích hoạt hệ thống bảo mật AI trước khi máy chủ trung tâm bị quá tải.</textarea>
        </div>

        <div>
          <label>KỊCH BẢN MẪU NHANH:</label>
          <div class="preset-chips">
            <button class="chip" onclick="setPreset('Cuộc đối thoại căng thẳng giữa Minh và Lan về lỗ hổng bảo mật cấp độ cao trong phòng máy chủ lúc nửa đêm. Cảnh 1 thiết lập không gian. Cảnh 2 cận mặt qua vai tranh luận. Cảnh 3 chốt phương án xử lý.')">
              🎬 Mẫu 1: Đối thoại Bảo mật Phòng Server (3 cảnh)
            </button>
            <button class="chip" onclick="setPreset('Minh thuyết trình kế hoạch kiến trúc đồ họa 3D chuẩn điện ảnh trên máy trạm Dell Precision 7530. Lan kiểm tra thông số ống kính 85mm f/2.0 và xác nhận đồng bộ khẩu hình một trăm phần trăm.')">
              🎥 Mẫu 2: Kiến trúc Phim 3D Chuẩn Rạp (3 cảnh)
            </button>
          </div>
        </div>

        <button id="renderBtn" class="btn-primary" onclick="triggerPipeline()">
          🚀 PHÂN TÍCH KỊCH BẢN &amp; XUẤT PHIM ĐIỆN ẢNH
        </button>

        <div class="spec-box">
          <div style="font-weight:700; color:var(--accent-gold); margin-bottom:2px;">THÔNG SỐ KỸ THUẬT ĐÃ KHÓA:</div>
          <div class="spec-row"><span>Quy tắc Góc máy:</span><strong>180-Degree Rule (SIDE_A)</strong></div>
          <div class="spec-row"><span>Ống kính &amp; Xóa phông:</span><strong>50mm–85mm | DoF f/2.0</strong></div>
          <div class="spec-row"><span>Ánh sáng &amp; Hệ màu:</span><strong>3-Point Light + AgX + LUT</strong></div>
          <div class="spec-row"><span>Khẩu hình (Tầng 2):</span><strong>Rhubarb (A, O, E, M, F)</strong></div>
          <div class="spec-row"><span>Kỹ thuật Dựng (Tầng 4):</span><strong>J-Cut / L-Cut (0.3s) + 2.35:1</strong></div>
          <div class="spec-row"><span>Giới hạn Texture VRAM:</span><strong>Tối đa 2048px + Instancing</strong></div>
        </div>
      </div>
    </section>

    <!-- CỘT 2: MÀN CHIẾU CINEMASCOPE 2.35:1 & TIẾN TRÌNH 4 TẦNG -->
    <section class="panel">
      <div class="panel-header">
        <span>2. Tiến Trình 4 Tầng &amp; Màn Chiếu CinemaScope (2.35:1)</span>
        <span id="statusBadge">SẴN SÀNG</span>
      </div>
      <div class="panel-body">
        <div class="stages-bar">
          <div id="stageCard1" class="stage-card">
            <div class="stage-num">TẦNG 1</div>
            <div class="stage-name">Đạo Diễn &amp; Góc 180°</div>
            <div class="stage-hw">CPU Xeon + Antigravity</div>
          </div>
          <div id="stageCard2" class="stage-card">
            <div class="stage-num">TẦNG 2</div>
            <div class="stage-name">Thoại &amp; Rhubarb Lip</div>
            <div class="stage-hw">CPU Xeon (0MB VRAM)</div>
          </div>
          <div id="stageCard3" class="stage-card">
            <div class="stage-num">TẦNG 3</div>
            <div class="stage-name">Blender EEVEE 3D</div>
            <div class="stage-hw">Quadro P2000 (&lt;3.2GB)</div>
          </div>
          <div id="stageCard4" class="stage-card">
            <div class="stage-num">TẦNG 4</div>
            <div class="stage-name">J-Cut, LUT &amp; NVENC</div>
            <div class="stage-hw">FFmpeg + h264_nvenc</div>
          </div>
        </div>

        <div class="progress-wrap">
          <div class="progress-top">
            <span id="progressMsg">Chờ lệnh từ Đạo diễn...</span>
            <strong id="progressPct">0%</strong>
          </div>
          <div class="progress-track">
            <div id="progressFill" class="progress-fill"></div>
          </div>
        </div>

        <div class="viewport-box">
          <video id="moviePlayer" controls preload="metadata" style="display:none;"></video>
          <div id="videoPlaceholder" class="viewport-placeholder">
            <p style="font-size:15px; font-weight:700; color:#e2e8f0; margin-bottom:6px;">
              MÀN CHIẾU MASTER CINEMASCOPE 2.35:1 (1920x1080 @ 24fps)
            </p>
            <p>Nhấn nút <strong>"Phân tích Kịch bản &amp; Xuất Phim Điện Ảnh"</strong> ở cột trái để chạy tuần tự 4 tầng và phát video trực tiếp tại đây.</p>
          </div>
        </div>

        <div class="action-bar">
          <span style="font-size:12px; color:var(--text-muted);">
            Đầu ra chuẩn: <code>workspace/final_cinematic_movie.mp4</code>
          </span>
          <a id="downloadBtn" href="/api/video" download="final_cinematic_movie.mp4" class="btn-download" style="display:none;">
            ⬇ TẢI VIDEO MP4 VỀ MÁY
          </a>
        </div>

        <div>
          <label>NHẬT KÝ ĐIỀU PHỐI HỆ THỐNG (LIVE PIPELINE LOGS):</label>
          <div id="consoleBox" class="console-box"></div>
        </div>
      </div>
    </section>

    <!-- CỘT 3: BẢNG PHÂN CẢNH STORYBOARD.JSON & KIỂM TRA KHẨU HÌNH -->
    <section class="panel">
      <div class="panel-header">
        <span>3. Hồ Sơ Phân Cảnh (storyboard.json)</span>
        <span id="shotCountBadge">0 Cảnh</span>
      </div>
      <div class="panel-body" id="storyboardContainer">
        <div style="color:var(--text-muted); font-size:13px; text-align:center; padding-top:30px;">
          Dữ liệu phân cảnh, tọa độ Camera 3D, file âm thanh <code>.wav</code> và chuỗi khẩu hình <code>A, O, E, M, F</code> sẽ hiển thị chi tiết tại đây ngay khi Tầng 1 &amp; Tầng 2 hoàn tất.
        </div>
      </div>
    </section>
  </div>

  <script>
    let lastVideoTimestamp = 0;
    let pollTimer = null;

    function setPreset(text) {
      document.getElementById('promptInput').value = text;
    }

    async function triggerPipeline() {
      const prompt = document.getElementById('promptInput').value.trim();
      if (!prompt) {
        alert('Vui lòng nhập yêu cầu tạo phim!');
        return;
      }
      const btn = document.getElementById('renderBtn');
      btn.disabled = true;

      try {
        const res = await fetch('/api/render', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt })
        });
        if (!res.ok) {
          const err = await res.json();
          alert(err.detail || 'Không thể khởi chạy pipeline.');
          btn.disabled = false;
          return;
        }
        pollStatus();
      } catch (e) {
        alert('Lỗi kết nối tới server: ' + e);
        btn.disabled = false;
      }
    }

    function updateStageCards(currentStage, status) {
      for (let i = 1; i <= 4; i++) {
        const card = document.getElementById('stageCard' + i);
        card.className = 'stage-card';
        if (status === 'completed' || i < currentStage) {
          card.classList.add('done');
        } else if (i === currentStage && status === 'running') {
          card.classList.add('active');
        }
      }
    }

    function renderStoryboardInspector(storyboard, videoTimestamp) {
      if (!storyboard || !storyboard.shots) return;
      const container = document.getElementById('storyboardContainer');
      const shots = storyboard.shots;
      document.getElementById('shotCountBadge').textContent = shots.length + ' Cảnh';

      container.innerHTML = shots.map(shot => {
        const cam = shot.camera || {};
        const loc = (cam.location_xyz || [0,0,0]).join(', ');
        const rack = (shot.rack_focus && shot.rack_focus.enabled) ? 'Bật (Trượt nét mắt)' : 'Khóa nét tĩnh';
        const vSum = shot.viseme_summary || {};
        const mouths = (vSum.mouth_sequence || []).map(m => `<span class="v-pill">${m}</span>`).join('');

        return `
          <div class="shot-card">
            <div class="shot-head">
              <span>${shot.shot_id} — ${shot.speaker}</span>
              <span class="badge-shot">${shot.shot_style} | ${cam.lens_mm || 85}mm f/${cam.aperture_fstop || 2.0}</span>
            </div>
            <div class="shot-dialogue">"${shot.dialogue.text}"</div>
            <div class="shot-meta">
              <span><strong>Tọa độ Cam:</strong> [${loc}]</span>
              <span><strong>Bán cầu 180°:</strong> ${cam.line_of_action_side || 'SIDE_A'}</span>
              <span><strong>Rack Focus:</strong> ${rack}</span>
              <span><strong>Dựng cảnh:</strong> ${shot.transition ? shot.transition.cut_type : 'J_CUT'} (0.3s)</span>
            </div>
            ${mouths ? `<div><label style="margin-bottom:3px;">Chuỗi Khẩu hình Rhubarb (A,O,E,M,F):</label><div class="viseme-strip">${mouths}</div></div>` : ''}
            <audio controls preload="none" src="/api/audio/${shot.shot_id}?t=${videoTimestamp}"></audio>
          </div>
        `;
      }).join('');
    }

    async function pollStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();

        document.getElementById('progressMsg').textContent = data.message || '';
        document.getElementById('progressPct').textContent = (data.percent || 0) + '%';
        document.getElementById('progressFill').style.width = (data.percent || 0) + '%';
        document.getElementById('statusBadge').textContent = (data.status || 'idle').toUpperCase();

        updateStageCards(data.current_stage || 0, data.status);

        const consoleBox = document.getElementById('consoleBox');
        if (data.logs && data.logs.length) {
          consoleBox.innerHTML = data.logs.map(l => `<div>${l}</div>`).join('');
          consoleBox.scrollTop = consoleBox.scrollHeight;
        }

        if (data.storyboard) {
          renderStoryboardInspector(data.storyboard, data.video_timestamp || 1);
        }

        const btn = document.getElementById('renderBtn');
        btn.disabled = (data.status === 'running');

        if (data.video_ready && data.video_timestamp !== lastVideoTimestamp) {
          lastVideoTimestamp = data.video_timestamp;
          const player = document.getElementById('moviePlayer');
          const placeholder = document.getElementById('videoPlaceholder');
          const dlBtn = document.getElementById('downloadBtn');

          player.src = '/api/video?t=' + lastVideoTimestamp;
          player.style.display = 'block';
          placeholder.style.display = 'none';
          dlBtn.href = '/api/video?t=' + lastVideoTimestamp;
          dlBtn.style.display = 'inline-block';
          player.load();
        }
      } catch (err) {
        console.error('Lỗi lấy trạng thái:', err);
      }
    }

    window.addEventListener('DOMContentLoaded', () => {
      pollStatus();
      pollTimer = setInterval(pollStatus, 1500);
    });
  </script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def render_studio_dashboard():
    return HTMLResponse(content=STUDIO_HTML)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.stage1_director.web_ui:app", host="0.0.0.0", port=8000, reload=False)

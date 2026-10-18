import os
import json
from pathlib import Path
from fastapi import FastAPI, BackgroundTasks, Form
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

app = FastAPI(title="CINE-CODE-7530 Web Director UI", version="1.0.0")

class MovieRequest(BaseModel):
    user_prompt: str
    auto_render: bool = False

CURRENT_STATUS = {
    "status": "idle",
    "stage": 0,
    "message": "Ready to receive instructions",
    "storyboard": None
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CINE-CODE 7530 - Đạo Diễn AI</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            background-color: #0f1117;
            color: #e2e8f0;
            margin: 0;
            padding: 24px;
        }
        .container {
            max-width: 900px;
            margin: 0 auto;
            background: #1a202c;
            border-radius: 12px;
            padding: 32px;
            box-shadow: 0 10px 25px rgba(0,0,0,0.5);
            border: 1px solid #2d3748;
        }
        h1 { color: #f6ad55; margin-top: 0; }
        .badge {
            background: #2b6cb0;
            color: white;
            padding: 4px 10px;
            border-radius: 6px;
            font-size: 13px;
        }
        textarea {
            width: 100%;
            height: 120px;
            background: #2d3748;
            color: #fff;
            border: 1px solid #4a5568;
            border-radius: 8px;
            padding: 12px;
            box-sizing: border-box;
            font-size: 15px;
            margin-top: 8px;
            resize: vertical;
        }
        button {
            background: #dd6b20;
            color: white;
            border: none;
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            margin-top: 12px;
            transition: background 0.2s;
        }
        button:hover { background: #c05621; }
        .status-box {
            margin-top: 24px;
            padding: 16px;
            border-radius: 8px;
            background: #232d3f;
            border: 1px solid #3182ce;
        }
        pre {
            background: #11141c;
            padding: 16px;
            border-radius: 8px;
            overflow-x: auto;
            color: #68d391;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>🎬 CINE-CODE 7530: HỆ THỐNG ĐẠO DIỄN 3D</h1>
        <p><span class="badge">Dell Precision 7530</span> | Intel Xeon 12 Threads (0MB VRAM) + Quadro P2000 4GB</p>
        
        <form id="directorForm">
            <label for="prompt"><strong>Nhập kịch bản hoặc yêu cầu cảnh quay:</strong></label>
            <textarea id="prompt" name="prompt" placeholder="Ví dụ: Hai kỹ sư Minh và Lan tranh luận khẩn cấp về việc ngắt kết nối máy chủ trước khi bị tấn công..."></textarea>
            <button type="submit">Khởi tạo Kịch bản Điện ảnh (Stage 1)</button>
        </form>

        <div class="status-box" id="statusBox">
            <h3>Trạng thái hệ thống: <span id="statusText">Sẵn sàng</span></h3>
            <p id="statusMsg">Chưa có tác vụ nào đang chạy.</p>
        </div>

        <h3>Storyboard JSON (Hợp đồng dữ liệu 4 tầng)</h3>
        <pre id="storyboardOutput">// Dữ liệu phân cảnh sẽ xuất hiện tại đây...</pre>
    </div>

    <script>
        const form = document.getElementById('directorForm');
        form.onsubmit = async (e) => {
            e.preventDefault();
            const prompt = document.getElementById('prompt').value;
            if (!prompt) return alert('Vui lòng nhập yêu cầu kịch bản!');
            
            document.getElementById('statusText').innerText = 'Đang xử lý Tầng 1...';
            document.getElementById('statusMsg').innerText = 'Ông Đạo Diễn đang quét tài nguyên 3D & tính toán góc quay 180 độ...';
            
            try {
                const res = await fetch('/api/director/create_storyboard', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({user_prompt: prompt, auto_render: false})
                });
                const data = await res.json();
                document.getElementById('statusText').innerText = 'Hoàn thành Tầng 1!';
                document.getElementById('statusMsg').innerText = 'Đã khóa toàn bộ tọa độ máy quay và nhân vật.';
                document.getElementById('storyboardOutput').innerText = JSON.stringify(data, null, 2);
            } catch (err) {
                document.getElementById('statusText').innerText = 'Lỗi!';
                document.getElementById('statusMsg').innerText = err.message;
            }
        };
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=HTML_TEMPLATE)

@app.get("/api/status")
def get_status():
    return JSONResponse(content=CURRENT_STATUS)

@app.post("/api/director/create_storyboard")
def create_storyboard(req: MovieRequest):
    from src.stage1_director.antigravity_client import generate_storyboard_via_antigravity
    assets_root = Path("assets")
    output_path = Path("workspace/storyboard.json")

    CURRENT_STATUS["status"] = "processing"
    CURRENT_STATUS["stage"] = 1
    CURRENT_STATUS["message"] = "Generating storyboard via AI and 180-degree solver"

    try:
        storyboard = generate_storyboard_via_antigravity(
            user_request=req.user_prompt,
            assets_root=assets_root,
            output_storyboard_path=output_path
        )
        CURRENT_STATUS["status"] = "completed"
        CURRENT_STATUS["storyboard"] = storyboard
        CURRENT_STATUS["message"] = "Stage 1 finished successfully"
        return JSONResponse(content=storyboard)
    except Exception as e:
        CURRENT_STATUS["status"] = "error"
        CURRENT_STATUS["message"] = str(e)
        return JSONResponse(content={"error": str(e)}, status_code=500)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.stage1_director.web_ui:app", host="0.0.0.0", port=8000, reload=False)

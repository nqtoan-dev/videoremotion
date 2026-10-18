import os
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Optional

def query_gpu_vram_mb() -> Optional[int]:
    """Truy vấn mức VRAM đang sử dụng trên Quadro P2000 bằng nvidia-smi."""
    try:
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,nounits,noheader"],
            capture_output=True, text=True, check=True
        )
        first_line = res.stdout.strip().split("\n")[0]
        return int(first_line.strip())
    except Exception:
        return None

def run_blender_shot_sequential(
    blend_file: Path,
    render_script: Path,
    storyboard_path: Path,
    shot_id: str,
    blender_bin: Optional[str] = None
) -> subprocess.CompletedProcess:
    """
    Gọi Blender chạy ngầm kết xuất tuần tự từng cảnh (Sequential Process Isolation).
    Sau khi tiến trình con kết thúc, hệ điều hành tự động thu hồi 100% VRAM của Quadro P2000.
    """
    executable = blender_bin or shutil.which("blender") or "blender"
    cmd = [
        executable,
        "-b", str(blend_file.as_posix()),
        "-P", str(render_script.as_posix()),
        "--",
        "--storyboard", str(storyboard_path.as_posix()),
        "--shot-id", shot_id
    ]

    vram_before = query_gpu_vram_mb()
    if vram_before is not None:
        print(f"[{shot_id}] VRAM trước khi render: {vram_before} MB")

    proc = subprocess.run(cmd, check=True)

    vram_after = query_gpu_vram_mb()
    if vram_after is not None:
        print(f"[{shot_id}] VRAM sau khi render: {vram_after} MB")

    return proc

def render_all_shots_sequential(storyboard_path: Path) -> None:
    """Duyệt toàn bộ shots trong storyboard.json và thực thi render lần lượt từng cảnh."""
    storyboard = json.loads(storyboard_path.read_text(encoding="utf-8"))
    blend_file = Path(storyboard["scene"]["blend_file"])
    render_script = Path("src/stage3_blender_eevee/render_shot.py")

    for shot in storyboard.get("shots", []):
        shot_id = shot["shot_id"]
        print(f"==> Bắt đầu kết xuất cảnh: {shot_id}")
        run_blender_shot_sequential(
            blend_file=blend_file,
            render_script=render_script,
            storyboard_path=storyboard_path,
            shot_id=shot_id
        )
        print(f"<== Hoàn thành cảnh: {shot_id}")

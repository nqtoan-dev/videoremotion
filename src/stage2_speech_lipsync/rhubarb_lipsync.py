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

import os
import wave
import math
import struct
import shutil
import asyncio
import subprocess
from array import array
from pathlib import Path
from typing import Dict, Optional

# Restrict only the TTS child process. The renderer and NVENC still need the GPU.
def _tts_cpu_env():
    return {**os.environ, "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "12"}

EMOTION_PROSODY_MAP: Dict[str, Dict[str, float]] = {
    "calm":               {"speed": 0.95, "pitch_st": -0.5, "bass_gain_db": 2.0},
    "serious_determined": {"speed": 0.96, "pitch_st": -1.0, "bass_gain_db": 3.0},
    "urgent":             {"speed": 1.08, "pitch_st":  0.6, "bass_gain_db": 0.5},
    "angry":              {"speed": 1.06, "pitch_st": -0.8, "bass_gain_db": 3.5},
    "thoughtful":         {"speed": 0.90, "pitch_st": -1.2, "bass_gain_db": 2.5},
}


async def _edge_tts_save(text: str, mp3_path: str, voice: str = "vi-VN-NamMinhNeural"):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await asyncio.wait_for(communicate.save(mp3_path), timeout=30)


def validate_speech_wav(wav_path: Path) -> float:
    with wave.open(str(wav_path), "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getnframes() == 0:
            raise RuntimeError("Giọng đọc phải là WAV PCM 16-bit và có dữ liệu.")
        duration = wf.getnframes() / float(wf.getframerate())
        samples = array("h", wf.readframes(wf.getnframes()))
    if duration < 0.2 or max((abs(s) for s in samples), default=0) < 32:
        raise RuntimeError("Giọng đọc bị rỗng hoặc im lặng; hãy thử tạo lại.")
    return duration


def generate_vietnamese_tts(
    text: str,
    output_wav: Path,
    voice: str = "vi-VN-NamMinhNeural"
) -> float:
    """
    Tạo giọng đọc thật bằng Edge-TTS hoặc gTTS; báo lỗi nếu cả hai không hoạt động.
    Trả về thời lượng thực tế của file âm thanh (giây).
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    if not text.strip():
        raise ValueError("Cảnh quay chưa có lời thoại để tạo giọng đọc.")
    output_wav.unlink(missing_ok=True)
    temp_mp3 = output_wav.with_suffix(".temp_tts.mp3")
    temp_mp3.unlink(missing_ok=True)

    tts_generated = False

    # Ưu tiên 1: Edge-TTS (Giọng đọc AI tự nhiên Nam Minh / Hoài My)
    try:
        asyncio.run(_edge_tts_save(text, str(temp_mp3), voice))
        if temp_mp3.exists() and temp_mp3.stat().st_size > 1000:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(temp_mp3),
                "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", str(output_wav)
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            tts_generated = True
    except Exception as exc:
        print(f"[STAGE 2] Edge-TTS gặp lỗi ({exc}), chuyển sang gTTS...")

    # Ưu tiên 2: gTTS (Google Translate TTS tiếng Việt)
    if not tts_generated:
        temp_mp3.unlink(missing_ok=True)
        try:
            from gtts import gTTS
            gTTS(text=text, lang="vi", timeout=(5, 20)).save(str(temp_mp3))
            if temp_mp3.exists() and temp_mp3.stat().st_size > 1000:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(temp_mp3),
                    "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", str(output_wav)
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                tts_generated = True
        except Exception as exc:
            print(f"[STAGE 2] gTTS gặp lỗi ({exc}).")

    if temp_mp3.exists():
        temp_mp3.unlink(missing_ok=True)

    if not tts_generated:
        output_wav.unlink(missing_ok=True)
        raise RuntimeError("Không tạo được giọng đọc tiếng Việt. Kiểm tra kết nối Edge-TTS/gTTS hoặc cài mô hình Piper.")
    try:
        return validate_speech_wav(output_wav)
    except Exception:
        output_wav.unlink(missing_ok=True)
        raise


def synthesize_dialogue_cpu_xeon(
    dialogue_cfg: Dict,
    voice_profile: Dict,
    output_wav_path: Path
) -> Path:
    """
    Sinh file âm thanh thoại .wav tự nhiên trên CPU Xeon (0 MB VRAM):
    1. Ưu tiên gọi edge-tts (hoặc piper nếu có onnx).
    2. Xuất chuẩn WAV PCM 16-bit 44.1kHz Stereo.
    3. Cập nhật thời lượng 'duration_sec' chính xác vào dialogue_cfg.
    """
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)
    text = dialogue_cfg.get("text", "")
    if not text.strip():
        raise ValueError("Cảnh quay chưa có lời thoại để tạo giọng đọc.")

    # Chọn giọng đọc phù hợp
    preset = voice_profile.get("voice_preset", "").lower()
    if "female" in preset or "lan" in preset or "hoaimy" in preset:
        voice = "vi-VN-HoaiMyNeural"
    else:
        voice = "vi-VN-NamMinhNeural"

    # Kiểm tra piper trước nếu có binary và file model thực tế
    piper_bin = shutil.which("piper")
    model_path = Path(voice_profile.get("model_onnx_path", "models/tts/vi_VN-vais1000-medium.onnx"))
    if piper_bin and model_path.exists():
        raw_tts_wav = output_wav_path.with_suffix(".raw_tts.wav")
        base_speed = float(voice_profile.get("base_speed", 1.0)) * float(dialogue_cfg.get("speaking_rate_multiplier", 1.0))
        length_scale = round(1.0 / max(base_speed, 0.5), 3)
        cmd_tts = [
            piper_bin,
            "--model", str(model_path),
            "--length_scale", str(length_scale),
            "--output_file", str(raw_tts_wav)
        ]
        subprocess.run(cmd_tts, input=text, text=True, check=True, encoding="utf-8", env=_tts_cpu_env())
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw_tts_wav),
            "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            str(output_wav_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw_tts_wav.unlink(missing_ok=True)
        dur = validate_speech_wav(output_wav_path)
        dialogue_cfg["duration_sec"] = dur
    else:
        dur = generate_vietnamese_tts(text=text, output_wav=output_wav_path, voice=voice)
        dialogue_cfg["duration_sec"] = dur

    return output_wav_path


def _generate_fallback_speech_waveform(text: str, wav_path: Path, speed: float = 1.0):
    """Test fixture only. Never use generated tones as a production voice."""
    sample_rate = 24000
    words = text.split()
    duration_sec = max(1.8, (len(words) * 0.35) / max(speed, 0.5))
    total_samples = int(sample_rate * duration_sec)

    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        frames = bytearray()
        for i in range(total_samples):
            t = i / sample_rate
            # Điều chế biên độ theo nhịp âm tiết để Rhubarb nhận diện rõ các hình miệng A, O, E, M, F
            syllable_env = max(0.0, math.sin(2.0 * math.pi * 4.2 * t))
            formant_1 = math.sin(2.0 * math.pi * 165.0 * t)
            formant_2 = 0.5 * math.sin(2.0 * math.pi * 620.0 * t)
            val = int(14000 * syllable_env * (formant_1 + formant_2))
            frames.extend(struct.pack("<h", max(-32767, min(32767, val))))
        wf.writeframes(frames)

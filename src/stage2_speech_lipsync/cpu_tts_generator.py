import os
import wave
import math
import struct
import shutil
import asyncio
import subprocess
from pathlib import Path
from typing import Dict, Optional

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


async def _edge_tts_save(text: str, mp3_path: str, voice: str = "vi-VN-NamMinhNeural"):
    import edge_tts
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(mp3_path)


def generate_vietnamese_tts(
    text: str,
    output_wav: Path,
    voice: str = "vi-VN-NamMinhNeural"
) -> float:
    """
    Tạo file âm thanh .wav tiếng Việt chất lượng cao bằng Edge-TTS (AI Neural),
    với gTTS và Bộ tạo sóng âm chuẩn hóa làm fallback để đảm bảo 100% không bao giờ sinh file rỗng.
    Trả về thời lượng thực tế của file âm thanh (giây).
    """
    output_wav.parent.mkdir(parents=True, exist_ok=True)
    temp_mp3 = output_wav.with_suffix(".temp_tts.mp3")

    tts_generated = False

    # Ưu tiên 1: Edge-TTS (Giọng đọc AI tự nhiên Nam Minh / Hoài My)
    try:
        asyncio.run(_edge_tts_save(text, str(temp_mp3), voice))
        if temp_mp3.exists() and temp_mp3.stat().st_size > 1000:
            subprocess.run([
                "ffmpeg", "-y", "-i", str(temp_mp3),
                "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                str(output_wav)
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            tts_generated = True
    except Exception as exc:
        print(f"[STAGE 2] Edge-TTS gặp lỗi ({exc}), chuyển sang gTTS...")

    # Ưu tiên 2: gTTS (Google Translate TTS tiếng Việt)
    if not tts_generated:
        try:
            from gtts import gTTS
            gTTS(text=text, lang="vi").save(str(temp_mp3))
            if temp_mp3.exists() and temp_mp3.stat().st_size > 1000:
                subprocess.run([
                    "ffmpeg", "-y", "-i", str(temp_mp3),
                    "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
                    str(output_wav)
                ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                tts_generated = True
        except Exception as exc:
            print(f"[STAGE 2] gTTS gặp lỗi ({exc}), chuyển sang sóng âm giả lập...")

    if temp_mp3.exists():
        temp_mp3.unlink(missing_ok=True)

    # Ưu tiên 3: Fallback tạo sóng âm ngữ âm chuẩn hóa (phục vụ test/CI hoặc khi mất mạng hoàn toàn)
    if not tts_generated or not output_wav.exists() or output_wav.stat().st_size < 1000:
        _generate_fallback_speech_waveform(text, output_wav, speed=1.0)

    # Đo thời lượng thực tế của giọng đọc từ file WAV
    with wave.open(str(output_wav), "rb") as wf:
        frames = wf.getnframes()
        rate = wf.getframerate()
        duration = frames / float(rate)

    if duration < 0.5:
        duration = 1.0

    return round(duration, 2)


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
        subprocess.run(cmd_tts, input=text, text=True, check=True, encoding="utf-8")
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw_tts_wav),
            "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            str(output_wav_path)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw_tts_wav.unlink(missing_ok=True)
        with wave.open(str(output_wav_path), "rb") as wf:
            dur = round(wf.getnframes() / float(wf.getframerate()), 2)
        dialogue_cfg["duration_sec"] = dur
    else:
        dur = generate_vietnamese_tts(text=text, output_wav=output_wav_path, voice=voice)
        dialogue_cfg["duration_sec"] = dur

    return output_wav_path


def _generate_fallback_speech_waveform(text: str, wav_path: Path, speed: float = 1.0):
    """Tạo sóng âm có chu kỳ âm tiết thực tế (dùng khi chạy kiểm thử tự động offline)."""
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

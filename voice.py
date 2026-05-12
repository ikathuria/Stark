"""TTS layer: ElevenLabs (primary) → Kokoro (neural local) → pyttsx3 (system fallback)."""
import io
import logging
import os
import tempfile

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_ELEVENLABS_KEY = os.getenv("ELEVENLABS_API_KEY")
_ELEVENLABS_VOICE = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam

# Cache Kokoro pipeline across calls — it's expensive to initialise
_kokoro_pipeline = None


def speak(text: str) -> tuple[bytes, str]:
    """Return (audio_bytes, mime_type). Tries ElevenLabs, then Kokoro, then pyttsx3."""
    if _ELEVENLABS_KEY:
        try:
            return _speak_elevenlabs(text)
        except Exception as e:
            logger.warning("ElevenLabs failed (%s) — using local fallback", e)
    return _speak_fallback(text)


def _speak_elevenlabs(text: str) -> tuple[bytes, str]:
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=_ELEVENLABS_KEY)
    audio_iter = client.text_to_speech.convert(
        text=text,
        voice_id=_ELEVENLABS_VOICE,
        model_id="eleven_flash_v2_5",
        output_format="mp3_44100_128",
    )
    audio_bytes = b"".join(audio_iter)
    return audio_bytes, "audio/mpeg"


def _speak_fallback(text: str) -> tuple[bytes, str]:
    """Try Kokoro neural TTS; fall back to pyttsx3 system TTS if unavailable."""
    try:
        return _speak_kokoro(text)
    except Exception as e:
        logger.warning("Kokoro unavailable (%s) — using pyttsx3", e)
        return _speak_pyttsx3(text)


def _speak_kokoro(text: str) -> tuple[bytes, str]:
    global _kokoro_pipeline
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline  # type: ignore[import]

    if _kokoro_pipeline is None:
        _kokoro_pipeline = KPipeline(lang_code="a")

    chunks = []
    for _, _, audio in _kokoro_pipeline(text, voice="af_heart"):
        if audio is not None:
            chunks.append(audio)

    if not chunks:
        raise RuntimeError("Kokoro returned no audio")

    combined = np.concatenate(chunks)
    buf = io.BytesIO()
    sf.write(buf, combined, 24000, format="WAV")
    buf.seek(0)
    return buf.read(), "audio/wav"


def _speak_pyttsx3(text: str) -> tuple[bytes, str]:
    import pyttsx3

    engine = pyttsx3.init()
    tmp = tempfile.mktemp(suffix=".wav")
    try:
        engine.save_to_file(text, tmp)
        engine.runAndWait()
        with open(tmp, "rb") as f:
            return f.read(), "audio/wav"
    finally:
        try:
            os.unlink(tmp)
        except Exception:
            pass

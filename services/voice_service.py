import logging
import os
import tempfile
from typing import Optional

from openai import AsyncOpenAI

from config.settings import settings

logger = logging.getLogger(__name__)


class VoiceService:
    @staticmethod
    def is_configured() -> bool:
        return bool(settings.OPENAI_API_KEY)

    @staticmethod
    async def transcribe(audio_data: bytes, filename: str = "voice.ogg") -> Optional[str]:
        if not VoiceService.is_configured():
            logger.warning("Voice transcription not configured")
            return None

        try:
            tmp = None
            try:
                tmp = tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False)
                tmp.write(audio_data)
                tmp.flush()
                tmp.close()

                kwargs = {"api_key": settings.OPENAI_API_KEY}
                if settings.ai_base_url:
                    kwargs["base_url"] = settings.ai_base_url
                client = AsyncOpenAI(**kwargs)
                with open(tmp.name, "rb") as audio_file:
                    transcript = await client.audio.transcriptions.create(
                        model="whisper-1",
                        file=audio_file,
                        language="ru",
                        response_format="text",
                    )
                text = transcript.strip() if isinstance(transcript, str) else getattr(transcript, 'text', '')
                if text:
                    text = text.strip()
                    logger.info("Voice transcribed: %s", text[:50])
                return text
            finally:
                if tmp and os.path.exists(tmp.name):
                    os.unlink(tmp.name)
        except Exception as e:
            logger.error("Voice transcription error: %s", e)
            return None

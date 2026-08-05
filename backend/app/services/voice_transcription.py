from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.speech import SpeechLanguage, SpeechTranscript
from app.services.audio_upload_security import AudioUpload, validate_audio_upload
from app.services.speech_provider import (
    SpeechProvider,
    SpeechProviderError,
    SpeechProviderResponseError,
    SpeechProviderUnavailableError,
)


class VoiceTranscriptionService:
    __slots__ = ("_config", "_provider")

    def __init__(self, *, config: Settings, provider: SpeechProvider) -> None:
        self._config = config
        self._provider = provider

    async def transcribe(
        self,
        upload: AudioUpload,
        *,
        language_hint: SpeechLanguage,
    ) -> SpeechTranscript:
        audio = await validate_audio_upload(
            upload,
            language_hint=language_hint,
            config=self._config,
        )

        try:
            provider_result = await self._provider.transcribe(audio)
        except SpeechProviderError:
            raise
        except Exception:
            raise SpeechProviderUnavailableError from None

        try:
            return SpeechTranscript.model_validate(provider_result)
        except ValidationError:
            raise SpeechProviderResponseError from None

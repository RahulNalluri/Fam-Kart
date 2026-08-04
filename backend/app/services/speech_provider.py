from dataclasses import dataclass
from typing import Protocol

from app.schemas.speech import SpeechLanguage, SpeechTranscript


class SpeechProviderError(RuntimeError):
    pass


class SpeechProviderUnavailableError(SpeechProviderError):
    def __init__(self) -> None:
        super().__init__("The speech transcription service is unavailable.")


class SpeechProviderResponseError(SpeechProviderError):
    def __init__(self) -> None:
        super().__init__(
            "The speech transcription service returned an invalid response."
        )


@dataclass(frozen=True, slots=True)
class SpeechAudioInput:
    content: bytes
    media_type: str
    file_name: str
    language_hint: SpeechLanguage


class SpeechProvider(Protocol):
    async def transcribe(self, audio: SpeechAudioInput) -> SpeechTranscript: ...

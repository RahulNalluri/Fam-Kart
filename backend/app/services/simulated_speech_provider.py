from app.core.config import Settings
from app.schemas.speech import SpeechTranscript
from app.services.speech_provider import (
    SpeechAudioInput,
    SpeechProviderError,
)


class TranscriptSimulationDisabledError(SpeechProviderError):
    def __init__(self) -> None:
        super().__init__("Transcript simulation is disabled for this environment.")


class SimulatedSpeechProvider:
    __slots__ = ("_transcript",)

    def __init__(self, *, config: Settings, transcript: SpeechTranscript) -> None:
        if not config.transcript_simulation_enabled:
            raise TranscriptSimulationDisabledError
        self._transcript = transcript

    async def transcribe(self, audio: SpeechAudioInput) -> SpeechTranscript:
        del audio
        return self._transcript

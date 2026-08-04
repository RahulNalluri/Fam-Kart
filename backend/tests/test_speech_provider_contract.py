import asyncio
from dataclasses import FrozenInstanceError

import pytest

from app.schemas.speech import SpeechLanguage, SpeechTranscript
from app.services.speech_provider import (
    SpeechAudioInput,
    SpeechProvider,
    SpeechProviderResponseError,
    SpeechProviderUnavailableError,
)


class StubSpeechProvider:
    def __init__(self) -> None:
        self.received_audio: SpeechAudioInput | None = None

    async def transcribe(self, audio: SpeechAudioInput) -> SpeechTranscript:
        self.received_audio = audio
        return SpeechTranscript(
            text="Palu rendu packets teesukura",
            language=audio.language_hint,
        )


def test_async_provider_contract_returns_validated_transcript() -> None:
    audio = SpeechAudioInput(
        content=b"test-audio",
        media_type="audio/mp4",
        file_name="voice-command.m4a",
        language_hint=SpeechLanguage.TELUGU,
    )
    provider: SpeechProvider = StubSpeechProvider()

    transcript = asyncio.run(provider.transcribe(audio))

    assert transcript == SpeechTranscript(
        text="Palu rendu packets teesukura",
        language=SpeechLanguage.TELUGU,
    )
    assert isinstance(provider, StubSpeechProvider)
    assert provider.received_audio is audio


def test_speech_audio_input_is_immutable() -> None:
    audio = SpeechAudioInput(
        content=b"test-audio",
        media_type="audio/mp4",
        file_name="voice-command.m4a",
        language_hint=SpeechLanguage.ENGLISH,
    )

    with pytest.raises(FrozenInstanceError):
        audio.file_name = "changed.m4a"


@pytest.mark.parametrize(
    "error",
    [SpeechProviderUnavailableError(), SpeechProviderResponseError()],
)
def test_controlled_provider_errors_do_not_expose_audio(error: Exception) -> None:
    private_audio = b"private-family-voice-command"

    assert private_audio.decode() not in str(error)
    assert private_audio.decode() not in repr(error)

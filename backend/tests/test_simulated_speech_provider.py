import asyncio

import pytest

from app.core.config import Settings
from app.schemas.speech import SpeechLanguage, SpeechTranscript
from app.services.simulated_speech_provider import (
    SimulatedSpeechProvider,
    TranscriptSimulationDisabledError,
)
from app.services.speech_provider import SpeechAudioInput, SpeechProvider

JWT_SECRET = "test-only-jwt-secret-key-at-least-32-characters"


def _settings(*, enabled: bool) -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key=JWT_SECRET,
        environment="testing",
        transcript_simulation_enabled=enabled,
    )


def _audio(content: bytes = b"private-family-audio") -> SpeechAudioInput:
    return SpeechAudioInput(
        content=content,
        media_type="audio/mp4",
        file_name="voice-command.m4a",
        language_hint=SpeechLanguage.TELUGU,
    )


def test_simulated_provider_requires_explicit_opt_in() -> None:
    transcript = SpeechTranscript(text="Rice", language="en")

    with pytest.raises(TranscriptSimulationDisabledError):
        SimulatedSpeechProvider(config=_settings(enabled=False), transcript=transcript)


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Rice 5 kg kavali", SpeechLanguage.ENGLISH),
        ("పాలు రెండు ప్యాకెట్లు తీసుకురా", SpeechLanguage.TELUGU),
        ("Onions and potatoes add cheyyi", SpeechLanguage.TELUGU),
    ],
)
def test_simulated_provider_returns_prevalidated_transcript(
    text: str,
    language: SpeechLanguage,
) -> None:
    expected = SpeechTranscript(text=text, language=language)
    provider: SpeechProvider = SimulatedSpeechProvider(
        config=_settings(enabled=True),
        transcript=expected,
    )

    result = asyncio.run(provider.transcribe(_audio()))

    assert result is expected


def test_simulated_provider_does_not_retain_audio() -> None:
    private_audio = b"private-family-audio-that-must-not-be-retained"
    provider = SimulatedSpeechProvider(
        config=_settings(enabled=True),
        transcript=SpeechTranscript(text="Palu", language="te"),
    )

    asyncio.run(provider.transcribe(_audio(private_audio)))

    assert not hasattr(provider, "__dict__")
    assert provider.__slots__ == ("_transcript",)
    assert private_audio.decode() not in repr(provider)

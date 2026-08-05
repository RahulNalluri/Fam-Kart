import asyncio
from typing import cast

import pytest

from app.core.config import Settings
from app.schemas.speech import SpeechLanguage, SpeechTranscript
from app.services.audio_upload_security import InvalidAudioContentError
from app.services.speech_provider import (
    SpeechAudioInput,
    SpeechProvider,
    SpeechProviderResponseError,
    SpeechProviderUnavailableError,
)
from app.services.voice_transcription import VoiceTranscriptionService

JWT_SECRET = "test-only-jwt-secret-key-at-least-32-characters"
VALID_M4A = b"\x00\x00\x00\x18ftypM4A private-audio"


class FakeUpload:
    def __init__(self, content: bytes, *, content_type: str = "audio/mp4") -> None:
        self.content_type = content_type
        self._content = content
        self._position = 0
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        if size < 0:
            size = len(self._content)
        start = self._position
        self._position += size
        return self._content[start : self._position]

    async def close(self) -> None:
        self.closed = True


class RecordingSpeechProvider:
    def __init__(
        self,
        *,
        transcript: SpeechTranscript | None = None,
        error: Exception | None = None,
    ) -> None:
        self.transcript = transcript or SpeechTranscript(
            text="Palu rendu packets teesukura",
            language=SpeechLanguage.TELUGU,
        )
        self.error = error
        self.calls: list[SpeechAudioInput] = []

    async def transcribe(self, audio: SpeechAudioInput) -> SpeechTranscript:
        self.calls.append(audio)
        if self.error is not None:
            raise self.error
        return self.transcript


class InvalidResponseProvider:
    async def transcribe(self, audio: SpeechAudioInput) -> SpeechTranscript:
        del audio
        return cast(
            SpeechTranscript,
            {"text": "", "language": "unsupported", "unexpected": True},
        )


def _config() -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key=JWT_SECRET,
        environment="testing",
    )


def _transcribe(
    provider: SpeechProvider,
    upload: FakeUpload,
    *,
    language_hint: SpeechLanguage = SpeechLanguage.TELUGU,
) -> SpeechTranscript:
    service = VoiceTranscriptionService(config=_config(), provider=provider)
    return asyncio.run(
        service.transcribe(upload, language_hint=language_hint),
    )


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Rice five kg kavali", SpeechLanguage.ENGLISH),
        ("పాలు రెండు ప్యాకెట్లు తీసుకురా", SpeechLanguage.TELUGU),
    ],
)
def test_validated_audio_is_transcribed_into_a_validated_transcript(
    text: str,
    language: SpeechLanguage,
) -> None:
    expected = SpeechTranscript(text=text, language=language)
    provider = RecordingSpeechProvider(transcript=expected)
    upload = FakeUpload(VALID_M4A, content_type="audio/x-m4a")

    result = _transcribe(provider, upload, language_hint=language)

    assert result == expected
    assert upload.closed is True
    assert len(provider.calls) == 1
    assert provider.calls[0] == SpeechAudioInput(
        content=VALID_M4A,
        media_type="audio/mp4",
        file_name="voice-command.m4a",
        language_hint=language,
    )


def test_rejected_audio_never_reaches_the_speech_provider() -> None:
    provider = RecordingSpeechProvider()
    upload = FakeUpload(b"private-content-that-is-not-audio")

    with pytest.raises(InvalidAudioContentError):
        _transcribe(provider, upload)

    assert provider.calls == []
    assert upload.closed is True


@pytest.mark.parametrize(
    "provider_error",
    [SpeechProviderUnavailableError(), SpeechProviderResponseError()],
)
def test_controlled_provider_errors_are_preserved(
    provider_error: Exception,
) -> None:
    provider = RecordingSpeechProvider(error=provider_error)

    with pytest.raises(type(provider_error)) as captured:
        _transcribe(provider, FakeUpload(VALID_M4A))

    assert captured.value is provider_error


def test_invalid_provider_output_becomes_a_controlled_response_error() -> None:
    provider: SpeechProvider = InvalidResponseProvider()

    with pytest.raises(SpeechProviderResponseError) as captured:
        _transcribe(provider, FakeUpload(VALID_M4A))

    assert "unsupported" not in str(captured.value)
    assert captured.value.__cause__ is None


def test_unexpected_provider_failure_is_sanitized() -> None:
    private_detail = VALID_M4A.decode(errors="ignore")
    provider = RecordingSpeechProvider(error=RuntimeError(private_detail))

    with pytest.raises(SpeechProviderUnavailableError) as captured:
        _transcribe(provider, FakeUpload(VALID_M4A))

    assert private_detail not in str(captured.value)
    assert private_detail not in repr(captured.value)
    assert captured.value.__cause__ is None


def test_integration_service_does_not_store_audio_or_transcripts() -> None:
    provider = RecordingSpeechProvider()
    service = VoiceTranscriptionService(config=_config(), provider=provider)

    asyncio.run(
        service.transcribe(
            FakeUpload(VALID_M4A),
            language_hint=SpeechLanguage.TELUGU,
        ),
    )

    assert not hasattr(service, "__dict__")
    assert service.__slots__ == ("_config", "_provider")
    assert VALID_M4A.decode(errors="ignore") not in repr(service)

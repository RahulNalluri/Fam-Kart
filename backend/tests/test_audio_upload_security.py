import asyncio

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.speech import SpeechLanguage
from app.services.audio_upload_security import (
    AUDIO_UPLOAD_CHUNK_BYTES,
    AudioUploadSecurityError,
    AudioUploadTooLargeError,
    EmptyAudioUploadError,
    InvalidAudioContentError,
    UnsupportedAudioTypeError,
    validate_audio_upload,
)

JWT_SECRET = "test-only-jwt-secret-key-at-least-32-characters"


class FakeUpload:
    def __init__(
        self,
        content: bytes,
        *,
        content_type: str | None,
    ) -> None:
        self.content_type = content_type
        self._content = content
        self._position = 0
        self.read_sizes: list[int] = []
        self.closed = False

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            size = len(self._content)
        start = self._position
        self._position += size
        return self._content[start : self._position]

    async def close(self) -> None:
        self.closed = True


def _config(*, maximum_bytes: int = 5 * 1024 * 1024) -> Settings:
    return Settings(
        _env_file=None,
        jwt_secret_key=JWT_SECRET,
        audio_upload_max_bytes=maximum_bytes,
    )


def _validate(
    upload: FakeUpload,
    *,
    maximum_bytes: int = 5 * 1024 * 1024,
):
    return asyncio.run(
        validate_audio_upload(
            upload,
            language_hint=SpeechLanguage.TELUGU,
            config=_config(maximum_bytes=maximum_bytes),
        )
    )


@pytest.mark.parametrize(
    ("content_type", "content", "expected_type", "expected_name"),
    [
        (
            "audio/mp4",
            b"\x00\x00\x00\x18ftypM4A test",
            "audio/mp4",
            "voice-command.m4a",
        ),
        ("audio/webm", b"\x1a\x45\xdf\xa3webm", "audio/webm", "voice-command.webm"),
        (
            "audio/wav",
            b"RIFF\x04\x00\x00\x00WAVEdata",
            "audio/wav",
            "voice-command.wav",
        ),
    ],
)
def test_supported_audio_is_normalized_for_the_speech_provider(
    content_type: str,
    content: bytes,
    expected_type: str,
    expected_name: str,
) -> None:
    upload = FakeUpload(content, content_type=content_type)

    result = _validate(upload)

    assert result.content == content
    assert result.media_type == expected_type
    assert result.file_name == expected_name
    assert result.language_hint is SpeechLanguage.TELUGU
    assert upload.closed is True


def test_media_type_alias_is_normalized_and_parameters_are_ignored() -> None:
    upload = FakeUpload(
        b"\x00\x00\x00\x18ftypM4A test",
        content_type="Audio/X-M4A; charset=binary",
    )

    result = _validate(upload)

    assert result.media_type == "audio/mp4"
    assert result.file_name == "voice-command.m4a"


def test_audio_is_read_in_bounded_chunks() -> None:
    upload = FakeUpload(
        b"\x00\x00\x00\x18ftypM4A " + b"a" * AUDIO_UPLOAD_CHUNK_BYTES,
        content_type="audio/mp4",
    )

    _validate(upload)

    assert len(upload.read_sizes) > 2
    assert set(upload.read_sizes) == {AUDIO_UPLOAD_CHUNK_BYTES}


def test_audio_at_the_configured_size_limit_is_accepted() -> None:
    header = b"\x00\x00\x00\x18ftypM4A test"
    content = header + b"a" * (1024 - len(header))
    upload = FakeUpload(content, content_type="audio/mp4")

    result = _validate(upload, maximum_bytes=1024)

    assert result.content == content


def test_oversized_audio_is_rejected_and_closed() -> None:
    header = b"\x00\x00\x00\x18ftypM4A test"
    content = header + b"a" * (1025 - len(header))
    upload = FakeUpload(content, content_type="audio/mp4")

    with pytest.raises(AudioUploadTooLargeError):
        _validate(upload, maximum_bytes=1024)

    assert upload.closed is True


@pytest.mark.parametrize(
    "content_type",
    [None, "", "application/octet-stream", "video/mp4"],
)
def test_missing_or_unsupported_media_type_is_rejected(
    content_type: str | None,
) -> None:
    upload = FakeUpload(b"private-audio", content_type=content_type)

    with pytest.raises(UnsupportedAudioTypeError):
        _validate(upload)

    assert upload.read_sizes == []
    assert upload.closed is True


def test_empty_audio_is_rejected_and_closed() -> None:
    upload = FakeUpload(b"", content_type="audio/mp4")

    with pytest.raises(EmptyAudioUploadError):
        _validate(upload)

    assert upload.closed is True


@pytest.mark.parametrize(
    ("content_type", "content"),
    [
        ("audio/mp4", b"not-an-m4a-file"),
        ("audio/mp4", b"\x1a\x45\xdf\xa3webm"),
        ("audio/webm", b"\x00\x00\x00\x18ftypM4A test"),
    ],
)
def test_spoofed_or_mismatched_audio_content_is_rejected(
    content_type: str,
    content: bytes,
) -> None:
    upload = FakeUpload(content, content_type=content_type)

    with pytest.raises(InvalidAudioContentError):
        _validate(upload)

    assert upload.closed is True


def test_security_errors_do_not_expose_private_audio() -> None:
    private_audio = b"private-family-voice-command"
    upload = FakeUpload(private_audio, content_type="audio/mp4")

    with pytest.raises(AudioUploadSecurityError) as captured:
        _validate(upload)

    assert private_audio.decode() not in str(captured.value)
    assert private_audio.decode() not in repr(captured.value)


def test_audio_upload_limit_has_a_safe_default() -> None:
    config = _config()

    assert config.audio_upload_max_bytes == 5 * 1024 * 1024


@pytest.mark.parametrize("maximum_bytes", [1023, 10 * 1024 * 1024 + 1])
def test_audio_upload_limit_rejects_unsafe_configuration(
    maximum_bytes: int,
) -> None:
    with pytest.raises(ValidationError):
        _config(maximum_bytes=maximum_bytes)

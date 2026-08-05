from dataclasses import dataclass
from typing import Protocol

from app.core.config import Settings
from app.schemas.speech import SpeechLanguage
from app.services.speech_provider import SpeechAudioInput

AUDIO_UPLOAD_CHUNK_BYTES = 64 * 1024


class AudioUploadSecurityError(ValueError):
    pass


class EmptyAudioUploadError(AudioUploadSecurityError):
    def __init__(self) -> None:
        super().__init__("The audio recording is empty.")


class AudioUploadTooLargeError(AudioUploadSecurityError):
    def __init__(self) -> None:
        super().__init__("The audio recording is larger than the allowed limit.")


class UnsupportedAudioTypeError(AudioUploadSecurityError):
    def __init__(self) -> None:
        super().__init__("The audio recording format is not supported.")


class InvalidAudioContentError(AudioUploadSecurityError):
    def __init__(self) -> None:
        super().__init__("The uploaded file does not contain supported audio.")


class AudioUpload(Protocol):
    content_type: str | None

    async def read(self, size: int = -1) -> bytes: ...

    async def close(self) -> None: ...


@dataclass(frozen=True, slots=True)
class AudioFormat:
    media_type: str
    safe_extension: str


M4A_FORMAT = AudioFormat(media_type="audio/mp4", safe_extension="m4a")
WEBM_FORMAT = AudioFormat(media_type="audio/webm", safe_extension="webm")
WAV_FORMAT = AudioFormat(media_type="audio/wav", safe_extension="wav")

_FORMATS_BY_MEDIA_TYPE = {
    "audio/m4a": M4A_FORMAT,
    "audio/mp4": M4A_FORMAT,
    "audio/x-m4a": M4A_FORMAT,
    "audio/webm": WEBM_FORMAT,
    "audio/wav": WAV_FORMAT,
    "audio/x-wav": WAV_FORMAT,
}


def _declared_audio_format(content_type: str | None) -> AudioFormat:
    if content_type is None:
        raise UnsupportedAudioTypeError

    normalized_type = content_type.partition(";")[0].strip().casefold()
    try:
        return _FORMATS_BY_MEDIA_TYPE[normalized_type]
    except KeyError as error:
        raise UnsupportedAudioTypeError from error


def _detected_audio_format(content: bytes) -> AudioFormat | None:
    if len(content) >= 12 and content[4:8] == b"ftyp":
        return M4A_FORMAT
    if content.startswith(b"\x1a\x45\xdf\xa3"):
        return WEBM_FORMAT
    if len(content) >= 12 and content.startswith(b"RIFF") and content[8:12] == b"WAVE":
        return WAV_FORMAT
    return None


async def _read_bounded_audio(upload: AudioUpload, maximum_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total_bytes = 0

    while True:
        chunk = await upload.read(AUDIO_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        total_bytes += len(chunk)
        if total_bytes > maximum_bytes:
            raise AudioUploadTooLargeError
        chunks.append(chunk)

    if total_bytes == 0:
        raise EmptyAudioUploadError
    return b"".join(chunks)


async def validate_audio_upload(
    upload: AudioUpload,
    *,
    language_hint: SpeechLanguage,
    config: Settings,
) -> SpeechAudioInput:
    try:
        declared_format = _declared_audio_format(upload.content_type)
        content = await _read_bounded_audio(upload, config.audio_upload_max_bytes)
        detected_format = _detected_audio_format(content)
        if detected_format != declared_format:
            raise InvalidAudioContentError

        return SpeechAudioInput(
            content=content,
            media_type=detected_format.media_type,
            file_name=f"voice-command.{detected_format.safe_extension}",
            language_hint=language_hint,
        )
    finally:
        await upload.close()

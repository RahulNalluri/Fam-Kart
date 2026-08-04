import pytest
from pydantic import ValidationError

from app.schemas.speech import SpeechLanguage, SpeechTranscript


@pytest.mark.parametrize(
    ("text", "language"),
    [
        ("Rice 5 kg kavali", "en"),
        ("పాలు రెండు ప్యాకెట్లు తీసుకురా", "te"),
        ("Onions and potatoes add cheyyi", "te"),
    ],
)
def test_speech_transcript_supports_familykart_languages(
    text: str,
    language: str,
) -> None:
    transcript = SpeechTranscript(text=text, language=language)

    assert transcript.text == text
    assert transcript.language is SpeechLanguage(language)


def test_speech_transcript_normalizes_spacing_without_losing_telugu() -> None:
    transcript = SpeechTranscript(
        text="  పాలు   రెండు   packets  తీసుకురా  ",
        language="te",
    )

    assert transcript.text == "పాలు రెండు packets తీసుకురా"


@pytest.mark.parametrize(
    "payload",
    [
        {"text": "", "language": "en"},
        {"text": "   ", "language": "en"},
        {"text": "Rice", "language": "hi"},
        {"text": "x" * 10_001, "language": "en"},
        {"text": "Rice", "language": "en", "confidence": 0.9},
    ],
)
def test_speech_transcript_rejects_invalid_provider_output(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        SpeechTranscript.model_validate(payload)


def test_speech_transcript_is_immutable() -> None:
    transcript = SpeechTranscript(text="Rice", language="en")

    with pytest.raises(ValidationError):
        transcript.text = "Milk"

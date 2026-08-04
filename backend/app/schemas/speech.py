from enum import StrEnum
from unicodedata import normalize as unicode_normalize

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SpeechLanguage(StrEnum):
    ENGLISH = "en"
    TELUGU = "te"


class SpeechTranscript(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=10_000)
    language: SpeechLanguage

    @field_validator("text", mode="before")
    @classmethod
    def normalize_transcript(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = " ".join(unicode_normalize("NFKC", value).split())
        if not normalized:
            raise ValueError("Speech transcript cannot be blank.")
        return normalized

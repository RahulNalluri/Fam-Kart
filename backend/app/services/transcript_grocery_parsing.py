from collections.abc import Mapping
from typing import Protocol

from app.schemas.grocery_extraction import GroceryExtractionRequest
from app.schemas.speech import SpeechLanguage, SpeechTranscript
from app.services.ai_parsing import AIParsingOutcome


class TranscriptParser(Protocol):
    async def parse(
        self,
        request: GroceryExtractionRequest,
        *,
        household_aliases: Mapping[str, str] | None = None,
    ) -> AIParsingOutcome: ...


class TranscriptGroceryParsingService:
    __slots__ = ("_parser",)

    def __init__(self, *, parser: TranscriptParser) -> None:
        self._parser = parser

    async def parse(
        self,
        transcript: SpeechTranscript,
        *,
        household_aliases: Mapping[str, str] | None = None,
    ) -> AIParsingOutcome:
        preferred_language = (
            "te" if transcript.language is SpeechLanguage.TELUGU else "en"
        )
        request = GroceryExtractionRequest(
            text=transcript.text,
            preferred_language=preferred_language,
        )
        return await self._parser.parse(
            request,
            household_aliases=household_aliases,
        )

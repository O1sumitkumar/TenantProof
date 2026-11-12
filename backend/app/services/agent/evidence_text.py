"""Where the agent's tools get evidence text and extracted facts.

Nothing in the database stores them yet (WS1 ingest writes the text, the extract step writes the
facts), so the tools read through this protocol. Only stripped content is ever served: no EXIF,
no GPS, never the original file. The real store comes with WS1 or a later `schema:` PR;
`InMemoryTextStore` is for tests and for building the loop before then."""

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class Page:
    locator: str  # "page 1", "message 3": what a SourceRef.locator must match
    text: str


@dataclass(frozen=True)
class Fact:
    evidence_id: str
    locator: str
    text: str  # the extracted fact, copied from the evidence


class EvidenceTextStore(Protocol):
    def pages(self, case_id: str, evidence_id: str) -> list[Page]:
        """The pages of one evidence item of this case, in order. Empty when no text exists."""
        ...

    def facts(self, case_id: str) -> list[Fact]:
        """Every extracted fact of this case."""
        ...


@dataclass
class InMemoryTextStore:
    """Keyed by case, so a lookup for another case's evidence id finds nothing."""

    _pages: dict[tuple[str, str], list[Page]] = field(default_factory=dict)
    _facts: dict[str, list[Fact]] = field(default_factory=dict)

    def add_pages(self, case_id: str, evidence_id: str, pages: list[Page]) -> None:
        self._pages[(case_id, evidence_id)] = pages

    def add_facts(self, case_id: str, facts: list[Fact]) -> None:
        self._facts.setdefault(case_id, []).extend(facts)

    def pages(self, case_id: str, evidence_id: str) -> list[Page]:
        return list(self._pages.get((case_id, evidence_id), []))

    def facts(self, case_id: str) -> list[Fact]:
        return list(self._facts.get(case_id, []))

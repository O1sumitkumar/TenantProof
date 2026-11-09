"""LLM provider protocol, the Anthropic provider and the fixture provider.

Tests and CI use `FixtureProvider` only and never reach the network. The API key is read from
the environment in one place (`_live_api_key`), and only in live mode. TODO (schema: PR):
`anthropic_api_key`, `llm_model` and `record_fixtures` move into `config.py`.
"""

import hashlib
import json
import os
import re
import warnings
from pathlib import Path
from typing import Any, Literal, Protocol

import anthropic
from pydantic import BaseModel, Field

from app.config import Settings

MODEL = "claude-sonnet-5-5"
CALL_TIMEOUT_S = 45.0  # one hung call must not eat the 60 s run target
MAX_RETRIES = 1
FIXTURES_DIR = Path(__file__).parent / "fixtures"
_FIXTURE_KEY = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,150}$")


class LLMError(Exception):
    pass


class LLMConfigError(LLMError):
    """Live mode without a usable setup (for example no API key)."""


class LLMCallError(LLMError):
    """The provider call failed. Carries the error type and HTTP status only."""


class FixtureMissing(LLMError):
    pass


class FixtureMismatch(LLMError):
    """The recorded request_hash differs from the request (strict mode)."""


class FixtureHashWarning(UserWarning):
    """Same, outside strict mode."""


# --------------------------------------------------------------------------- data types


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str | list[dict[str, Any]]


class ToolUse(BaseModel):
    id: str
    name: str
    input: dict[str, Any]


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0

    def __add__(self, other: "Usage") -> "Usage":
        return Usage(
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
        )


class LLMRequest(BaseModel):
    system: str
    messages: list[Message]
    tools: list[dict[str, Any]] = Field(default_factory=list)  # tools.tool_specs() output
    max_tokens: int = Field(default=4096, ge=1)
    # Names the recorded response. Chosen by the caller, for example
    # "extract-<sha256>-<prompt_version>" or "timeline-turn3". Letters, digits, `_`, `.`, `-`.
    fixture_key: str


class LLMResponse(BaseModel):
    text: str = ""
    tool_uses: list[ToolUse] = Field(default_factory=list)
    stop_reason: Literal["end_turn", "tool_use", "max_tokens", "other"] = "end_turn"
    usage: Usage = Field(default_factory=Usage)


class LLMProvider(Protocol):
    async def complete(self, request: LLMRequest) -> LLMResponse: ...


# --------------------------------------------------------------------------- fixture hashing


def request_hash(request: LLMRequest) -> str:
    """12 hex chars over the system prompt and each tool's name, description and schema. It
    changes when a prompt or a tool definition changes, so stale fixtures are noticed."""
    tools = sorted(
        (
            {
                "name": t.get("name"),
                "description": t.get("description"),
                "input_schema": t.get("input_schema"),
            }
            for t in request.tools
        ),
        key=lambda t: str(t["name"]),
    )
    blob = json.dumps({"system": request.system, "tools": tools}, sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]


def fixture_document(request: LLMRequest, response: LLMResponse) -> dict[str, Any]:
    """The JSON stored in a fixture file."""
    return {"request_hash": request_hash(request), "response": response.model_dump(mode="json")}


def _fixture_path(directory: Path, key: str) -> Path:
    if not _FIXTURE_KEY.fullmatch(key) or ".." in key:
        raise LLMError(f"invalid fixture_key {key!r}")
    return directory / f"{key}.json"


# --------------------------------------------------------------------------- providers


class FixtureProvider:
    """Replays recorded responses. Never touches the network.

    `strict` (default: env FIXTURE_STRICT=1, which tests set) turns a request_hash mismatch
    into an error. Otherwise it warns (FixtureHashWarning) and replays anyway. `scripted`
    entries are in-memory responses for unit tests and skip the hash check.
    """

    def __init__(
        self,
        directory: Path | None = None,
        *,
        strict: bool | None = None,
        scripted: dict[str, LLMResponse] | None = None,
    ) -> None:
        self.directory = directory or FIXTURES_DIR
        self.strict = os.environ.get("FIXTURE_STRICT") == "1" if strict is None else strict
        self.scripted = scripted or {}

    async def complete(self, request: LLMRequest) -> LLMResponse:
        if request.fixture_key in self.scripted:
            return self.scripted[request.fixture_key]
        path = _fixture_path(self.directory, request.fixture_key)
        if not path.is_file():
            raise FixtureMissing(f"no fixture for key {request.fixture_key!r} ({path.name})")
        doc = json.loads(path.read_text(encoding="utf-8"))
        self._check_hash(request, doc.get("request_hash"))
        return LLMResponse.model_validate(doc["response"])

    def _check_hash(self, request: LLMRequest, recorded: str | None) -> None:
        current = request_hash(request)
        if recorded == current:
            return
        msg = (
            f"fixture {request.fixture_key!r} was recorded for request_hash {recorded}, "
            f"this request is {current}: the prompt or tool schemas changed, re-record it"
        )
        if self.strict:
            raise FixtureMismatch(msg)
        warnings.warn(msg, FixtureHashWarning, stacklevel=3)


_STOP_REASONS: dict[str, Literal["end_turn", "tool_use", "max_tokens"]] = {
    "end_turn": "end_turn",
    "tool_use": "tool_use",
    "max_tokens": "max_tokens",
}


class AnthropicProvider:
    """Live provider. `client` is injectable so tests use a fake and never reach the network."""

    def __init__(
        self,
        api_key: str,
        model: str = MODEL,
        client: Any | None = None,
    ) -> None:
        self.model = model
        self.client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=CALL_TIMEOUT_S, max_retries=MAX_RETRIES
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "system": request.system,
            "messages": [m.model_dump(mode="json") for m in request.messages],
        }
        if request.tools:
            kwargs["tools"] = request.tools
        try:
            raw = await self.client.messages.create(**kwargs)
        except anthropic.APIError as exc:
            status = getattr(exc, "status_code", None)
            raise LLMCallError(f"{type(exc).__name__} (status {status})") from None
        return _to_response(raw)


def _to_response(raw: Any) -> LLMResponse:
    text_parts: list[str] = []
    tool_uses: list[ToolUse] = []
    for block in raw.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_uses.append(ToolUse(id=block.id, name=block.name, input=dict(block.input)))
    return LLMResponse(
        text="".join(text_parts),
        tool_uses=tool_uses,
        stop_reason=_STOP_REASONS.get(raw.stop_reason, "other"),
        usage=Usage(
            input_tokens=raw.usage.input_tokens,
            output_tokens=raw.usage.output_tokens,
        ),
    )


def _live_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise LLMConfigError(
            "LLM_MODE=live needs ANTHROPIC_API_KEY: export it in the process environment "
            "(backend/.env is not read for it yet)"
        )
    return key


def get_provider(settings: Settings) -> LLMProvider:
    """Fixture mode never reads the key. Live mode fails early if it is missing."""
    if settings.llm_mode == "fixture":
        return FixtureProvider()
    return AnthropicProvider(api_key=_live_api_key())

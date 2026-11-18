"""The package page's version line ends its sentence after the build time. An en-CA time
already ends in "a.m." or "p.m.", so the sentence must not add a second full stop
("11:37 p.m.." on issue #92). `fmtTime` and `endSentence` in web/index.html run under node."""

import json
import re
import shutil
from pathlib import Path

import pytest

from tests.node_support import node_json

INDEX = Path(__file__).resolve().parents[2] / "web" / "index.html"
BLOCK = re.compile(r"/\* fmtTime:start \*/(.*?)/\* fmtTime:end \*/", re.S)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


def ended(values: list[str | None]) -> list[str]:
    match = BLOCK.search(INDEX.read_text(encoding="utf-8"))
    assert match, "fmtTime block not found in web/index.html"
    script = (
        match.group(1)
        + f"\nconsole.log(JSON.stringify({json.dumps(values)}.map(v => endSentence(fmtTime(v)))));"
    )
    return node_json(script)


@pytest.mark.parametrize("built_at", ["2026-11-17T23:37:00", "2026-11-17T09:05:00"])
def test_an_am_or_pm_time_gets_one_full_stop(built_at: str) -> None:
    [text] = ended([built_at])
    assert re.search(r"[ap]\.m\.$", text), text
    assert not text.endswith(".."), text


def test_a_time_without_a_full_stop_still_ends_the_sentence() -> None:
    assert ended([None, "not a date"]) == ["—.", "not a date."]


def test_the_version_line_ends_the_build_time_with_end_sentence() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert "${endSentence(fmtTime(S.pkg.built_at))} " in html
    assert "${fmtTime(S.pkg.built_at)}." not in html

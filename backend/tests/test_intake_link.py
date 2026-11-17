"""Which intake link the caseworker pages show (`sessionLink` in web/index.html, a pure function
run under node). The raw link is returned only once, by `POST /cases/{id}/intake-link`, so the page
keeps it in memory with the case it was made for. Issue #38: the Tenant view shows it right after
"Send intake link", for that case only; another case, or a page with no link sent, shows none."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

INDEX = Path(__file__).resolve().parents[2] / "web" / "index.html"
BLOCK = re.compile(r"/\* Fix #38: intakeLink:start.*?\*/(.*?)/\* intakeLink:end \*/", re.S)

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")

# Placeholder, not a real token: tests never hold a real intake link.
LINK = "https://tenantproof.example/i/not-a-real-token"


def shown(*calls: tuple[object, object]) -> list[object]:
    match = BLOCK.search(INDEX.read_text(encoding="utf-8"))
    assert match, "intakeLink block not found in web/index.html"
    args = ", ".join(f"[{json.dumps(last)}, {json.dumps(case_id)}]" for last, case_id in calls)
    call = f"[{args}].map(a => sessionLink(...a))"
    script = match.group(1) + f"\nconsole.log(JSON.stringify({call}));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_the_link_just_sent_is_shown_for_its_case() -> None:
    assert shown(({"caseId": "case_demo_001", "url": LINK}, "case_demo_001")) == [LINK]


def test_no_link_sent_in_this_page_shows_none() -> None:
    """After a reload the page has no link (it is shown only once), so the view offers Send."""
    assert shown((None, "case_demo_001")) == [None]


def test_another_case_never_shows_the_link() -> None:
    assert shown(({"caseId": "case_demo_001", "url": LINK}, "case_002")) == [None]


def test_no_case_selected_shows_none() -> None:
    assert shown(({"caseId": "case_demo_001", "url": LINK}, None)) == [None]


def test_the_link_box_markup_is_shared_by_the_evidence_page_and_the_tenant_view() -> None:
    html = INDEX.read_text(encoding="utf-8")
    assert html.count('<span class="linkbox">') == 1, "one link box template, used by both views"
    assert html.count("linkBox(link)") == 2

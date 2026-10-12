"""Vercel 배포 설정 — 진입점이 서버 앱 정본을 쓰는지, CLI 배포가 비밀값·원본 데이터를 올리지 않는지."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_entry_is_the_server_app():
    import app
    import server.api

    assert app.app is server.api.app


def test_vercelignore_allows_only_what_the_server_needs():
    lines = [
        ln.strip()
        for ln in (ROOT / ".vercelignore").read_text().splitlines()
        if ln.strip() and not ln.startswith("#")
    ]
    assert lines[0] == "/*"  # 먼저 전부 막고 허용 목록만 연다
    allowed = {ln[1:] for ln in lines if ln.startswith("!")}
    assert allowed == {
        "app.py",
        "vercel.json",
        "pyproject.toml",
        "uv.lock",
        ".python-version",
        "server",
        "scripts",
        "scripts/defect_precedent",
    }
    # 뒤 줄이 앞 줄을 덮는다 — scripts를 열고, 그 아래를 다시 닫고, 서버가 import하는 defect_precedent만 연다
    assert (
        lines.index("!scripts")
        < lines.index("scripts/*")
        < lines.index("!scripts/defect_precedent")
    )
    assert not any(a.startswith((".env", "data", ".agent", "tests", "docs")) for a in allowed)


def test_function_settings():
    conf = json.loads((ROOT / "vercel.json").read_text())
    assert (
        conf["framework"] == "fastapi"
    )  # CLI로 만든 프로젝트는 프리셋이 비어 app.py를 함수로 못 찾는다
    assert conf["functions"] == {"app.py": {"maxDuration": 60}}
    assert conf["regions"] == ["syd1"]  # 운영 Supabase(ap-southeast-2)와 같은 지역

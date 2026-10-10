"""로컬 build 파일을 읽어 검증한다 (DEC-039 — 검색은 API 서버 메모리에서, 데이터는 `nhtsa build`가 만든 로컬 파일).

검증은 Supabase 적재(`load_db.load_files`, `--causes full`)와 같은 검사를 그대로 쓴다 — 카드·시험지는 `build.json`, 원인 파일은
`causes.manifest.json`(줄 수·캠페인 목록·실패 캠페인 목록)과 대조한다. 하나라도 다르면 섞인 판본이라 서버를 띄우지 않는다.
`build_id`는 입력 파일 해시라 명세의 실패 사유(`failed_kinds`)는 들어가지 않는다 — 그래서 서버는 시작할 때 명세 전체를
DB에 적재된 `data_builds.causes_spec`과도 대조한다(`check_against_db`). 같은 `build_id`가 늘 같은 응답 상태를 내게 하기 위해서다(AGENTS.md 2-4).
"""

import json
from dataclasses import dataclass
from pathlib import Path

from scripts.defect_precedent.load_db import PROCESSED, load_files, read_jsonl


class BuildMismatch(RuntimeError):
    """build 파일이 기록·명세·DB와 다르다."""


@dataclass(frozen=True)
class Build:
    build_id: str
    snapshot_date: str
    cards: list[dict]
    causes: dict[str, dict]  # 캠페인 6자리(`campno[:6]`) → Part 573 원인 행
    unreadable: dict[str, str]  # 보고서는 있는데 읽지 못한 캠페인 → 사유 (명세의 `failed_kinds`)
    causes_spec: dict  # 적재 때 data_builds.causes_spec에 들어간 것과 같은 명세


def _canon(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def load_build(data_dir: Path = PROCESSED) -> Build:
    try:
        meta = load_files(data_dir, "full")["build"]
    except SystemExit as e:  # load_db는 명령줄 도구라 sys.exit로 멈춘다
        raise BuildMismatch(f"{e} — 섞인 판본으로 서버를 띄우지 않는다") from e
    spec = meta["causes_spec"]
    unreadable = dict(spec.get("failed_kinds") or {})
    if set(unreadable) != set(spec["failed_campaigns"]):
        raise BuildMismatch(
            "causes.manifest.json의 실패 사유(failed_kinds)와 실패 캠페인 목록(failed_campaigns)이 다르다"
        )
    causes = {r["campaign"]: r for r in read_jsonl(data_dir / "causes.jsonl")}
    return Build(
        meta["build_id"],
        meta["snapshot_date"].isoformat(),
        read_jsonl(data_dir / "recalls.jsonl"),
        causes,
        unreadable,
        spec,
    )


def check_against_db(conn, build: Build) -> None:
    """로컬 명세가 DB에 적재된 같은 build의 명세와 같아야 한다 (실패 사유까지)."""
    row = conn.execute(
        "select causes_spec from data_builds where build_id = %s", (build.build_id,)
    ).fetchone()
    if row is None:
        raise BuildMismatch(
            f"build {build.build_id}가 DB에 없다 — load_db load --causes full로 먼저 올린다"
        )
    if _canon(row[0]) != _canon(build.causes_spec):
        raise BuildMismatch(
            f"build {build.build_id}의 원인 명세가 DB에 적재된 것과 다르다 — 같은 build_id로 다른 상태를 내지 않는다"
        )

"""로컬 build 파일을 읽어 검증한다 (DEC-039 — 검색은 API 서버 메모리에서, 데이터는 `nhtsa build`가 만든 로컬 파일).

카드(`recalls.jsonl`)·시험지(`eval.jsonl`)는 `build.json`의 sha256과, 원인 파일(`causes.jsonl`)은 `causes.manifest.json`과
대조한다. 하나라도 다르면 섞인 판본이라 서버를 띄우지 않는다. `build_id`는 Supabase 적재(`load_db`)와 같은 규칙으로 계산해
모든 응답에 싣는다 — 답변에서 데이터 판본까지 되짚기 위해서다(AGENTS.md 2-4).
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from scripts.defect_precedent.load_db import MANIFEST_NAME, PROCESSED, build_id_of, read_jsonl


class BuildMismatch(RuntimeError):
    """build 파일의 해시가 기록과 다르다."""


@dataclass(frozen=True)
class Build:
    build_id: str
    snapshot_date: str
    cards: list[dict]
    causes: dict[str, dict]  # 캠페인 6자리(`campno[:6]`) → Part 573 원인 행


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_build(data_dir: Path = PROCESSED) -> Build:
    meta = json.loads((data_dir / "build.json").read_text(encoding="utf-8"))
    manifest = json.loads((data_dir / MANIFEST_NAME).read_text(encoding="utf-8"))
    expected = {
        "recalls.jsonl": meta["recalls_sha256"],
        "eval.jsonl": meta["eval_sha256"],
        "causes.jsonl": manifest["file_sha256"],
    }
    actual = {name: _sha256(data_dir / name) for name in expected}
    for name, want in expected.items():
        if actual[name] != want:
            raise BuildMismatch(
                f"{name}의 sha256이 기록과 다르다 (파일 {actual[name][:12]}…, 기록 {want[:12]}…) — 섞인 판본으로 서버를 띄우지 않는다"
            )
    build_id = build_id_of(
        meta["raw_manifest_sha256"],
        actual["recalls.jsonl"],
        actual["eval.jsonl"],
        actual["causes.jsonl"],
    )
    causes = {r["campaign"]: r for r in read_jsonl(data_dir / "causes.jsonl")}
    return Build(build_id, meta["snapshot_date"], read_jsonl(data_dir / "recalls.jsonl"), causes)

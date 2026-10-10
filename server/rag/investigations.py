"""리콜 카드에 NHTSA 결함 조사 요약을 원문 그대로 붙인다 (docs/계획_P2_API서버.md 1절).

- 말한 주체는 NHTSA 결함 조사(조사관이 쓴 요약)다 — 573 원인 칸(리콜 제조사)과 따로 싣는다.
- 원본은 `data/raw/nhtsa/FLAT_INV.zip`. 서버는 시작할 때 `manifest.json`의 sha256이 build의 `raw_manifest_sha256`과 같고
  `FLAT_INV.zip`의 sha256이 manifest 기록과 같은지 확인한다 — build_id에서 조사 원본까지 되짚기 위해서다(AGENTS.md 2-4).
- **색인에는 넣지 않는다.** 조사 요약은 대리 평가 시험 질문의 출처라 넣으면 누수다(AGENTS.md 5-2). 검색이 고른 카드에 표시만 한다.
- 요약 칸이 비었거나 자리표시 문구("There is no summary currently available")면 싣지 않는다(`why_stats.linked_campnos`와 같은 규칙).
- 같은 조사 번호에 요약 판본이 여러 개면 어느 것이 맞는지 짐작하지 않고 서버를 띄우지 않는다(AGENTS.md 2-3, 현재 원본 0건).
"""

import hashlib
import json
from pathlib import Path

from scripts.defect_precedent.nhtsa import INV_COLS, PLACEHOLDER, RAW_DIR, read_flat
from server.rag.build import BuildMismatch

SPEAKER_INV = "NHTSA 결함 조사 (조사관 요약)"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_investigations(
    raw_manifest_sha256: str, campnos: set[str], raw_dir: Path = RAW_DIR
) -> dict[str, list[dict]]:
    """리콜 번호 → 그 리콜에 연결된 조사 요약 목록(조사 번호 순). 요약 글은 원본 칸 그대로다."""
    manifest_path = raw_dir / "manifest.json"
    if _sha256(manifest_path) != raw_manifest_sha256:
        raise BuildMismatch(
            "data/raw/nhtsa/manifest.json이 build의 raw_manifest_sha256과 다르다 — 다른 날 받은 원본이다"
        )
    expected = json.loads(manifest_path.read_text(encoding="utf-8"))["files"]["FLAT_INV.zip"][
        "sha256"
    ]
    if _sha256(raw_dir / "FLAT_INV.zip") != expected:
        raise BuildMismatch("FLAT_INV.zip의 sha256이 manifest.json 기록과 다르다")
    try:
        rows = read_flat(raw_dir / "FLAT_INV.zip", INV_COLS)
    except SystemExit as e:  # read_flat은 명령줄 도구라 칸이 밀리면 sys.exit로 멈춘다
        raise BuildMismatch(str(e)) from e

    by_action: dict[str, dict] = {}
    links: dict[str, set[str]] = {}
    for r in rows:
        campno, summary = r["CAMPNO"].strip(), r["SUMMARY"]
        if campno not in campnos or not summary.strip() or PLACEHOLDER.search(summary.strip()):
            continue
        action = r["ACTION"].strip()
        inv = {
            "action": action,
            "subject": r["SUBJECT"],
            "summary": summary,
            "open_date": r["ODATE"].strip(),
            "close_date": r["CDATE"].strip(),
        }
        if action in by_action and by_action[action]["summary"] != summary:
            raise BuildMismatch(
                f"조사 {action}의 요약 판본이 여러 개다 — 어느 것인지 짐작하지 않는다"
            )
        by_action.setdefault(action, inv)
        links.setdefault(campno, set()).add(action)
    return {c: [by_action[a] for a in sorted(acts)] for c, acts in links.items()}

"""리콜 카드에 NHTSA 결함 조사 요약을 원문 그대로 붙인다 (docs/product/계획_P2_API서버.md 1절).

- 말한 주체는 NHTSA 결함 조사(조사관이 쓴 요약)다 — 573 원인 칸(리콜 제조사)과 따로 싣는다.
- 원본은 `data/raw/nhtsa/FLAT_INV.zip`. 서버는 시작할 때 `manifest.json`의 sha256이 build의 `raw_manifest_sha256`과 같고
  `FLAT_INV.zip`의 sha256이 manifest 기록과 같은지 확인한다 — build_id에서 조사 원본까지 되짚기 위해서다(AGENTS.md 2-4).
- **색인에는 넣지 않는다.** 조사 요약은 대리 평가 시험 질문의 출처라 넣으면 누수다(AGENTS.md 5-2). 검색이 고른 카드에 표시만 한다.
- 요약 칸이 비었거나 자리표시 문구("There is no summary currently available")면 싣지 않는다(`why_stats.linked_campnos`와 같은 규칙).
- 조사 기록의 리콜 번호가 9자리로 카드와 정확히 같을 때만 잇는다. 6자리(캠페인 번호)로 적힌 기록은 어느 카드인지 짐작해야
  하므로 잇지 않는다(현재 원본 72,977줄, 앞 6자리로는 284장에 걸림 — 응답에서는 "조사 요약 없음"과 구별되지 않는다).
- 같은 조사 번호의 줄(차종별로 여러 줄, 다른 리콜 번호 줄 포함)마다 요약·제목·개시일·종료일이 하나라도 다르면 어느 것이 맞는지
  짐작하지 않고 서버를 띄우지 않는다(AGENTS.md 2-3, 현재 원본: 연결된 917개 조사 모두 일관).
"""

import hashlib
import json
from pathlib import Path

from scripts.defect_precedent.nhtsa import INV_COLS, RAW_DIR, read_flat
from scripts.defect_precedent.rules import (  # 연결 수(1,870)를 낸 규칙과 같은 정규식 — nhtsa 쪽은 더 좁다
    INV_SUMMARY_PLACEHOLDER,
)
from server.rag.build import BuildMismatch

SPEAKER_INV = "NHTSA 결함 조사 (조사관 요약)"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_investigations(
    raw_manifest_sha256: str, campnos: set[str], raw_dir: Path = RAW_DIR
) -> dict[str, list[dict]]:
    """리콜 번호 → 그 리콜에 연결된 조사 요약 목록(조사 번호 순). 요약 글은 원본 칸 그대로다."""
    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.exists() or not (raw_dir / "FLAT_INV.zip").exists():
        raise BuildMismatch(
            f"{raw_dir}에 manifest.json·FLAT_INV.zip이 없다 — build와 같은 날 받은 원본을 둔다(팀 드라이브 사본)"
        )
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

    def usable(r: dict) -> bool:
        summary = r["SUMMARY"].strip()
        return bool(summary) and not INV_SUMMARY_PLACEHOLDER.search(summary)

    # 1) 카드에 이어지는 조사 번호
    linked = {r["ACTION"].strip() for r in rows if r["CAMPNO"].strip() in campnos and usable(r)}
    # 2) 그 조사 번호의 **모든 줄**(다른 리콜 번호 줄 포함)이 요약·제목·날짜가 같아야 한다 — 다르면 짐작하지 않는다
    by_action: dict[str, dict] = {}
    for r in rows:
        action = r["ACTION"].strip()
        if action not in linked:
            continue
        inv = {
            "action": action,
            "subject": r["SUBJECT"],
            "summary": r["SUMMARY"],
            "open_date": r["ODATE"].strip(),
            "close_date": r["CDATE"].strip(),
        }
        if by_action.setdefault(action, inv) != inv:
            raise BuildMismatch(
                f"조사 {action}의 줄마다 요약·제목·날짜가 다르다 — 어느 것인지 짐작하지 않는다"
            )
    links: dict[str, set[str]] = {}
    for r in rows:
        campno = r["CAMPNO"].strip()
        if campno in campnos and usable(r):
            links.setdefault(campno, set()).add(r["ACTION"].strip())
    return {c: [by_action[a] for a in sorted(acts)] for c, acts in links.items()}

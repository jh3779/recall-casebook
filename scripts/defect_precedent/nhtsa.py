"""NHTSA 공개 리콜·결함 조사 파일을 받아 리콜 카드와 시험지(eval)를 만든다.

사용법:
    uv run python -m scripts.defect_precedent.nhtsa fetch   # 원본 zip 받기 (data/raw/nhtsa/)
    uv run python -m scripts.defect_precedent.nhtsa build   # recalls.jsonl·eval.jsonl 만들기 (data/processed/defect/)

결함 선례 기획(docs/기획_결함선례.md, DEC-030)의 수치를 저장소에서 재현하기 위한 스크립트다.
AGENTS.md 7절: 원본 데이터는 커밋하지 않고(data/raw·data/processed는 .gitignore), 다시 만드는 스크립트를 커밋한다.
NHTSA 파일은 매일 갱신되므로 fetch가 남기는 manifest.json(받은 시각·크기·sha256)으로 스냅샷을 구분한다.
"""

import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw" / "nhtsa"
OUT_DIR = REPO_ROOT / "data" / "processed" / "defect"

BASE = "https://static.nhtsa.gov/odi/ffdd"
# rcl/FLAT_RCL.zip은 404 — 2010년 전/후 두 파일로 나뉘어 있다 (명세: rcl/RCL.txt)
FILES = {
    "FLAT_RCL_PRE_2010.zip": f"{BASE}/rcl/FLAT_RCL_PRE_2010.zip",
    "FLAT_RCL_POST_2010.zip": f"{BASE}/rcl/FLAT_RCL_POST_2010.zip",
    "FLAT_INV.zip": f"{BASE}/inv/FLAT_INV.zip",
    "RCL.txt": f"{BASE}/rcl/RCL.txt",
    "INV.txt": f"{BASE}/inv/INV.txt",
}

# 필드 순서는 RCL.txt·INV.txt 명세 그대로 (CONEQUENCE_DEFECT 철자도 원문)
RCL_COLS = (
    "RECORD_ID CAMPNO MAKETXT MODELTXT YEARTXT MFGCAMPNO COMPNAME MFGNAME BGMAN ENDMAN RCLTYPECD "
    "POTAFF ODATE INFLUENCED_BY MFGTXT RCDATE DATEA RPNO FMVSS DESC_DEFECT CONEQUENCE_DEFECT "
    "CORRECTIVE_ACTION NOTES RCL_CMPT_ID MFR_COMP_NAME MFR_COMP_DESC MFR_COMP_PTNO DO_NOT_DRIVE "
    "PARK_OUTSIDE"
).split()
INV_COLS = "ACTION MAKE MODEL YEAR COMPNAME MFR_NAME ODATE CDATE CAMPNO SUBJECT SUMMARY".split()

# 요약 칸에 실제 요약 대신 들어 있는 자리표시 문구
PLACEHOLDER = re.compile(r"^(There is no summary currently available|=+)$")
# 원본 보고서(Part 573) 정형 양식이 시작된 날 — 이 이후 접수 리콜만 573 원인 칸을 기대할 수 있다
RCLRPT_FROM = "20140820"

# 문장 끝처럼 보이지만 끝이 아닌 약어
_ABBR = re.compile(
    r"(\bU\.S\.|\bU\.S\.A\.|\b[A-Z]\.|\bNo\.|\bInc\.|\bCo\.|\bCorp\.|\bLtd\.|\bMr\.|\bMs\.|\bDr\."
    r"|\bapprox\.|\bvs\.|\be\.g\.|\bi\.e\.|\bSt\.|\bMfg\.|\bJan\.|\bFeb\.|\bAug\.|\bSept?\."
    r"|\bOct\.|\bNov\.|\bDec\.)$",
    re.I,
)


def first_sentence(text: str) -> str:
    """조사 요약의 첫 문장. 시험 질문으로 쓴다.

    마침표마다 자르면 "approximately 2.5 million"이 "approximately 2."에서 잘리고(EA12006),
    마침표 뒤 공백만 보면 "fourteen.During"처럼 공백이 빠진 경계를 놓친다 — 둘 다 처리한다.
    """
    text = text.strip()
    joined = re.sub(r"(?<=[a-z0-9\)])\.(?=[A-Z][a-z])", ". ", text)
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z\"(])", joined):
        candidate = joined[: m.start()].rstrip()
        if _ABBR.search(candidate):
            continue
        return candidate
    return joined


def read_flat(zip_path: Path, cols: list[str]) -> list[dict]:
    """탭 구분·cp1252 flat 파일을 압축을 풀지 않고 읽는다. 빈 줄은 건너뛴다."""
    rows = []
    with zipfile.ZipFile(zip_path) as zf, zf.open(zf.namelist()[0]) as raw:
        for line in io.TextIOWrapper(raw, encoding="cp1252", errors="replace", newline=""):
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            parts = (line.split("\t") + [""] * len(cols))[: len(cols)]
            rows.append(dict(zip(cols, parts, strict=True)))
    return rows


def _defect_body(defect: str) -> str:
    """결함 설명에서 첫 문장(회사·차종 나열)을 뗀 본문. 같은 본문이면 복사된 리콜로 본다."""
    text = re.sub(r"\s+", " ", defect.strip())
    parts = re.split(r"(?<=\.)\s", text, maxsplit=1)
    return parts[1] if len(parts) > 1 else text


def build_cards(rcl_rows: list[dict], snapshot_date: str) -> dict[str, dict]:
    """리콜 × 차종 × 연식 × 부품 줄을 리콜(CAMPNO) 1건 = 카드 1장으로 합친다. 대표 값은 파일상 첫 줄."""
    cards: dict[str, dict] = {}
    for r in rcl_rows:
        campno = r["CAMPNO"].strip()
        if not campno:
            continue
        card = cards.get(campno)
        if card is None:
            body = _defect_body(r["DESC_DEFECT"])
            card = cards[campno] = {
                "campno": campno,
                # 회사명 대응표가 생기기 전에는 원문과 같다 (예: "FORD MOTOR COMPANY"와 "Ford Motor Company"가 따로 셈)
                "maker": r["MFGNAME"].strip(),
                "raw_maker": r["MFGNAME"].strip(),
                "components": [],
                "defect": r["DESC_DEFECT"].strip(),
                "consequence": r["CONEQUENCE_DEFECT"].strip(),
                "remedy": r["CORRECTIVE_ACTION"].strip(),
                "received_date": r["RCDATE"].strip(),
                "recall_type": r["RCLTYPECD"].strip(),
                "influenced_by": r["INFLUENCED_BY"].strip(),
                "dup_group": (
                    hashlib.sha1(body.encode()).hexdigest()[:12] if len(body) > 60 else campno
                ),
                "snapshot_date": snapshot_date,
            }
        comp = r["COMPNAME"].strip()
        if comp and comp not in card["components"]:
            card["components"].append(comp)
    return cards


def build_eval(inv_rows: list[dict], cards: dict[str, dict]) -> list[dict]:
    """결함 조사 → 리콜 연결로 시험지를 만든다. 조사 1건 = 질문 1개, 정답 = 연결 리콜 ID 집합.

    걸러지는 순서 (docs/기획_결함선례.md 6절): PE·EA 조사만 → 리콜 파일에 있는 리콜만 →
    고유 조사로 묶음 → 빈 요약(자리표시 문구) 제외.
    이 시험은 대리 평가다 — 정답 리콜 대부분이 조사 시작 뒤에 접수돼 "과거 선례 찾기"는 재지 못한다.
    """
    by_action: dict[str, dict] = {}
    for r in inv_rows:
        action = r["ACTION"].strip()
        prefix = re.match(r"[A-Z]+", action)
        if not prefix or prefix.group() not in ("PE", "EA"):
            continue
        item = by_action.setdefault(
            action, {"open_date": r["ODATE"].strip(), "summary": r["SUMMARY"].strip(), "gold": []}
        )
        campno = r["CAMPNO"].strip()
        if campno and campno in cards and campno not in item["gold"]:
            item["gold"].append(campno)

    questions = []
    for action, item in by_action.items():
        if not item["gold"] or not item["summary"] or PLACEHOLDER.match(item["summary"]):
            continue
        tags = ["all"]
        if item["open_date"] >= "20100101":
            tags.append("since2010")
        if cards[item["gold"][0]]["received_date"] >= RCLRPT_FROM:
            tags.append("rclrpt_range")
        questions.append(
            {
                "action_no": action,
                "question": first_sentence(item["summary"]),
                "open_date": item["open_date"],
                "gold_campnos": item["gold"],
                "set": tags,
            }
        )
    return questions


def fetch() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"), "files": {}}
    for name, url in FILES.items():
        print(f"다운로드: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310 — 고정된 정부 공개 URL
            data = resp.read()
            last_modified = resp.headers.get("Last-Modified")
        (RAW_DIR / name).write_bytes(data)
        manifest["files"][name] = {
            "url": url,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "last_modified": last_modified,
        }
    (RAW_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"완료: {RAW_DIR}/manifest.json")


def _write_jsonl(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build() -> None:
    manifest_path = RAW_DIR / "manifest.json"
    if not manifest_path.exists():
        sys.exit("원본이 없다 — 먼저 `... nhtsa fetch`를 실행한다")
    snapshot_date = json.loads(manifest_path.read_text(encoding="utf-8"))["downloaded_at"][:10]

    rcl_rows = read_flat(RAW_DIR / "FLAT_RCL_PRE_2010.zip", RCL_COLS) + read_flat(
        RAW_DIR / "FLAT_RCL_POST_2010.zip", RCL_COLS
    )
    inv_rows = read_flat(RAW_DIR / "FLAT_INV.zip", INV_COLS)
    cards = build_cards(rcl_rows, snapshot_date)
    questions = build_eval(inv_rows, cards)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    _write_jsonl(OUT_DIR / "recalls.jsonl", cards.values())
    _write_jsonl(OUT_DIR / "eval.jsonl", questions)

    groups: dict[str, int] = {}
    for c in cards.values():
        groups[c["dup_group"]] = groups.get(c["dup_group"], 0) + 1
    shared = sum(n for n in groups.values() if n > 1)
    # 기준값: 2026-10-06 스냅샷 (docs/기획_결함선례.md) — 매일 갱신되므로 조금씩 달라질 수 있다
    print(f"스냅샷 {snapshot_date}")
    print(f"리콜 줄 {len(rcl_rows):,} → 리콜 카드 {len(cards):,} (2026-10-06: 327,429 → 30,347)")
    print(f"결함 조사 {len({r['ACTION'] for r in inv_rows}):,} (2026-10-06: 5,349)")
    print(f"본문이 다른 리콜과 같은 리콜 {shared:,} (2026-10-06: 4,761)")
    print(f"시험 질문 {len(questions):,} (2026-10-06: 749)")
    for tag in ("since2010", "rclrpt_range"):
        print(f"  {tag}: {sum(tag in q['set'] for q in questions):,}")
    print(f"출력: {OUT_DIR}")


if __name__ == "__main__":
    commands = {"fetch": fetch, "build": build}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit("사용법: uv run python -m scripts.defect_precedent.nhtsa {fetch|build}")
    commands[sys.argv[1]]()

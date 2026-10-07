"""NHTSA 공개 리콜·결함 조사 파일을 받아 리콜 카드와 시험지(eval)를 만든다.

사용법:
    uv run python -m scripts.defect_precedent.nhtsa fetch   # 원본 zip 받기 (data/raw/nhtsa/)
    uv run python -m scripts.defect_precedent.nhtsa build   # recalls.jsonl·eval.jsonl 만들기 (data/processed/defect/)
    uv run python -m scripts.defect_precedent.nhtsa freeze scripts/defect_precedent/baseline_<날짜>.json  # 기준 고정

결함 선례 기획(docs/기획_결함선례.md, DEC-030)의 수치를 다시 계산하는 스크립트다.
같은 값의 재현은 기준일 원본 사본이 있을 때만 가능하다 (README "재현 범위").
AGENTS.md 7절: 원본 데이터는 커밋하지 않고(data/raw·data/processed는 .gitignore), 다시 만드는 스크립트를 커밋한다.
NHTSA 파일은 매일 갱신되므로 fetch가 남기는 manifest.json(받은 시각·크기·sha256)으로 스냅샷을 구분한다.
"""

import hashlib
import json
import re
import shutil
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

# 문장 끝처럼 보이지만 끝이 아닌 약어. 한 글자 이니셜("J.")은 대문자일 때만 본다 (re.I로 "a."까지 잡지 않게).
_ABBR = re.compile(
    r"(\bU\.S\.|\bU\.S\.A\.|\bNo\.|\bInc\.|\bCo\.|\bCorp\.|\bLtd\.|\bMr\.|\bMs\.|\bDr\."
    r"|\bapprox\.|\bvs\.|\be\.g\.|\bi\.e\.|\bSt\.|\bMfg\.|\bJan\.|\bFeb\.|\bAug\.|\bSept?\."
    r"|\bOct\.|\bNov\.|\bDec\.)$",
    re.I,
)
_INITIAL = re.compile(r"(?<![A-Za-z0-9])[A-Z]\.$")  # "V70S."는 이니셜이 아니다


def split_first_sentence(text: str) -> tuple[str, str]:
    """(첫 문장, 나머지). 조사 요약의 첫 문장은 시험 질문, 리콜 결함 설명의 나머지는 복사본 판단에 쓴다.

    마침표마다 자르면 "approximately 2.5 million"이 "approximately 2."에서 잘리고(EA12006),
    마침표 뒤 공백만 보면 "fourteen.During"처럼 공백이 빠진 경계를 놓친다 — 둘 다 처리한다.
    "Inc.", "U.S." 같은 약어 뒤에서는 자르지 않는다. 옛 요약은 전부 대문자라 대문자 경계도 본다.
    """
    # 공백이 빠진 경계: "fourteen.During", 옛 대문자 요약의 "PE99-076.THE"
    joined = re.sub(r"(?<=[a-z0-9\)])\.(?=[A-Z][a-z])", ". ", text.strip())
    joined = re.sub(r"(?<=[A-Z0-9\)])\.(?=[A-Z]{2,})", ". ", joined)
    for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z\"(])", joined):
        candidate = joined[: m.start()].rstrip()
        if _ABBR.search(candidate) or _INITIAL.search(candidate):
            continue
        return candidate, joined[m.end() :]
    return joined, ""


def first_sentence(text: str) -> str:
    return split_first_sentence(text)[0]


def _decode(raw: bytes) -> tuple[str, bool]:
    """원본은 UTF-8이다. UTF-8로 읽지 못하는 줄만 cp1252로 읽고 그 사실을 알린다 (조용히 글자를 깨지 않게)."""
    try:
        return raw.decode("utf-8"), False
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace"), True


def read_flat(zip_path: Path, cols: list[str]) -> list[dict]:
    """탭 구분 flat 파일을 압축을 풀지 않고 읽는다. 빈 줄은 건너뛴다.

    칸 수가 명세와 다른 줄이 있으면 값이 옆 칸으로 밀렸을 수 있으므로 그 자리에서 중단한다 (추측해 맞추지 않는다).
    """
    rows, fallback = [], 0
    with zipfile.ZipFile(zip_path) as zf, zf.open(zf.namelist()[0]) as raw:
        for lineno, raw_line in enumerate(raw, 1):
            line, used_fallback = _decode(raw_line)
            fallback += used_fallback
            line = line.rstrip("\r\n")
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) != len(cols):
                sys.exit(
                    f"{zip_path.name} {lineno}번째 줄: 칸 {len(parts)}개 (명세 {len(cols)}개) — 원본을 확인한다"
                )
            rows.append(dict(zip(cols, parts, strict=True)))
    if fallback:
        print(f"주의: {zip_path.name} — UTF-8로 읽지 못해 cp1252로 읽은 줄 {fallback}")
    return rows


def _defect_body(defect: str) -> str:
    """결함 설명에서 첫 문장(회사·차종 나열)을 뗀 본문. 같은 본문이면 복사된 리콜로 본다."""
    first, rest = split_first_sentence(re.sub(r"\s+", " ", defect))
    return rest or first


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


def install_dir(new: Path, target: Path, keep_old_as: Path | None = None) -> None:
    """new 폴더를 target으로 통째로 바꾼다.

    - 교체 도중 실패하면 옛 target을 되돌린다.
    - 지난번 교체가 중간에 멈춰 `.old`만 남아 있으면 지우지 않고 중단한다 (그것이 마지막 사본일 수 있다).
    - keep_old_as를 주면 옛 target을 지우지 않고 그 이름으로 보관한다 (NHTSA 옛 스냅샷은 다시 받을 수 없다).
    """
    old = target.with_name(target.name + ".old")
    if old.exists():
        if not target.exists():
            sys.exit(f"지난 교체가 중간에 멈췄다 — {old}를 {target}으로 되돌린 뒤 다시 실행한다")
        shutil.rmtree(old)
    if target.exists():
        target.rename(old)
    try:
        new.rename(target)
    except OSError:
        if old.exists():
            old.rename(target)
        raise
    if old.exists():
        if keep_old_as is not None:
            old.rename(keep_old_as)
        else:
            shutil.rmtree(old)


def fetch() -> None:
    """모든 파일을 임시 폴더에 받고 전부 성공했을 때만 data/raw/nhtsa를 교체한다 (서로 다른 시점의 파일이 섞이지 않게)."""
    tmp = RAW_DIR.with_name(RAW_DIR.name + ".partial")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    manifest = {"downloaded_at": datetime.now(UTC).isoformat(timespec="seconds"), "files": {}}
    for name, url in FILES.items():
        print(f"다운로드: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=300) as resp:  # 고정된 정부 공개 URL
            data = resp.read()
            last_modified = resp.headers.get("Last-Modified")
        (tmp / name).write_bytes(data)
        manifest["files"][name] = {
            "url": url,
            "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
            "last_modified": last_modified,
        }
    (tmp / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    keep = None
    if (RAW_DIR / "manifest.json").exists():
        # 옛 스냅샷은 받은 시각 이름으로 보관한다 (예: data/raw/nhtsa.2026-10-06T08-10-00+00-00)
        prev = json.loads((RAW_DIR / "manifest.json").read_text(encoding="utf-8"))["downloaded_at"]
        keep = RAW_DIR.with_name(f"{RAW_DIR.name}.{prev.replace(':', '-')}")
        if keep.exists():
            keep = None  # 같은 스냅샷이 이미 보관돼 있으면 옛 폴더는 지운다
    install_dir(tmp, RAW_DIR, keep_old_as=keep)
    if keep is not None:
        print(f"이전 스냅샷 보관: {keep}")
    print(f"완료: {RAW_DIR}/manifest.json")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_raw(raw_dir: Path) -> dict:
    """manifest의 sha256과 실제 파일을 비교한다. 하나라도 다르면 중단한다."""
    manifest_path = raw_dir / "manifest.json"
    if not manifest_path.exists():
        sys.exit("원본이 없다 — 먼저 `... nhtsa fetch`를 실행한다")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for name, info in manifest["files"].items():
        path = raw_dir / name
        if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != info["sha256"]:
            sys.exit(f"{name}이 manifest와 다르다 — 다시 fetch한다")
    return manifest


def write_jsonl(path: Path, rows) -> None:
    """임시 파일에 다 쓴 뒤 교체한다 — 중간에 멈추면 기존 파일이 남고 잘린 파일은 .partial로 남는다."""
    tmp = path.with_name(path.name + ".partial")
    with tmp.open(
        "w", encoding="utf-8", newline="\n"
    ) as f:  # Windows에서도 LF — 줄바꿈이 다르면 파일 sha256이 달라진다
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)


def build() -> None:
    snapshot_date = verify_raw(RAW_DIR)["downloaded_at"][:10]

    rcl_rows = read_flat(RAW_DIR / "FLAT_RCL_PRE_2010.zip", RCL_COLS) + read_flat(
        RAW_DIR / "FLAT_RCL_POST_2010.zip", RCL_COLS
    )
    inv_rows = read_flat(RAW_DIR / "FLAT_INV.zip", INV_COLS)
    cards = build_cards(rcl_rows, snapshot_date)
    questions = build_eval(inv_rows, cards)

    # 카드·시험지·build.json을 한 폴더에 다 만든 뒤 폴더째 교체한다 — 서로 다른 실행 결과가 섞이지 않게.
    # 573 판독 결과 등 이 단계가 만들지 않는 파일은 새 폴더로 옮겨 둔다.
    tmp = OUT_DIR.with_name(OUT_DIR.name + ".partial")
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    write_jsonl(tmp / "recalls.jsonl", cards.values())
    write_jsonl(tmp / "eval.jsonl", questions)
    build_info = {
        "raw_manifest_sha256": sha256_file(RAW_DIR / "manifest.json"),
        "recalls_sha256": sha256_file(tmp / "recalls.jsonl"),
        "eval_sha256": sha256_file(tmp / "eval.jsonl"),
        "snapshot_date": snapshot_date,
    }
    (tmp / "build.json").write_text(json.dumps(build_info, indent=1) + "\n", encoding="utf-8")
    if OUT_DIR.exists():
        for old in OUT_DIR.iterdir():
            if old.name not in ("recalls.jsonl", "eval.jsonl", "build.json"):
                shutil.copy2(old, tmp / old.name)
    install_dir(tmp, OUT_DIR)

    groups: dict[str, int] = {}
    for c in cards.values():
        groups[c["dup_group"]] = groups.get(c["dup_group"], 0) + 1
    shared = sum(n for n in groups.values() if n > 1)
    # 기준값: 2026-10-06 스냅샷 (docs/기획_결함선례.md) — 매일 갱신되므로 조금씩 달라질 수 있다
    print(f"스냅샷 {snapshot_date}")
    print(f"리콜 줄 {len(rcl_rows):,} → 리콜 카드 {len(cards):,} (2026-10-06: 327,429 → 30,350)")
    print(f"결함 조사 {len({r['ACTION'] for r in inv_rows}):,} (2026-10-06: 5,349)")
    print(f"본문이 다른 리콜과 같은 리콜 {shared:,} (2026-10-06: 6,404)")
    print(f"시험 질문 {len(questions):,} (2026-10-06: 749)")
    for tag in ("since2010", "rclrpt_range"):
        print(f"  {tag}: {sum(tag in q['set'] for q in questions):,}")
    print(f"출력: {OUT_DIR}")


def verify_build(raw_dir: Path = RAW_DIR, out_dir: Path = OUT_DIR) -> dict:
    """build.json이 지금 원본 manifest와 지금 카드·시험지 파일을 가리키는지 확인한다. 다르면 중단한다."""
    verify_raw(raw_dir)
    info_path = out_dir / "build.json"
    if not info_path.exists():
        sys.exit("build.json이 없다 — 먼저 `... nhtsa build`를 실행한다")
    info = json.loads(info_path.read_text(encoding="utf-8"))
    checks = {
        "원본 manifest": (raw_dir / "manifest.json", info["raw_manifest_sha256"]),
        "recalls.jsonl": (out_dir / "recalls.jsonl", info["recalls_sha256"]),
        "eval.jsonl": (out_dir / "eval.jsonl", info["eval_sha256"]),
    }
    for label, (path, expected) in checks.items():
        if sha256_file(path) != expected:
            sys.exit(f"{label}이 build.json과 다르다 — `... nhtsa build`를 다시 실행한다")
    return info


def freeze(out_path: Path) -> None:
    """기준 실행을 고정하는 작은 파일을 만든다 (저장소에 커밋).

    원본은 커밋하지 않고 해시만 남긴다. NHTSA 원본 URL은 매일 덮어써지므로, 같은 원본 사본
    (data/raw/nhtsa 또는 보관된 nhtsa.<받은 시각>)이 있어야 같은 점수를 "재현"할 수 있다.
    사본이 없으면 같은 질문 번호로 "재평가"만 할 수 있다 (bm25_baseline --allow-drift).
    """
    info = verify_build()
    manifest = json.loads((RAW_DIR / "manifest.json").read_text(encoding="utf-8"))
    questions = [json.loads(line) for line in (OUT_DIR / "eval.jsonl").open(encoding="utf-8")]
    sample = []
    # 573 표본: 리콜마다 당시 판본 목록과 각 PDF의 sha256, 고른 판본을 남긴다
    for name in ("causes_sample.jsonl", "causes_sample_failures.jsonl"):
        path = OUT_DIR / name
        if path.exists():
            for line in path.open(encoding="utf-8"):
                row = json.loads(line)
                sample.append(
                    {
                        "campaign": row["campaign"],
                        "pdfs": row.get("pdfs", {}),
                        "selected": row.get("source_file"),
                    }
                )
    baseline = {
        "raw": manifest,
        "build": info,
        "eval_action_nos": [q["action_no"] for q in questions],
        "rclrpt_sample": sample,
    }
    out_path.write_text(json.dumps(baseline, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"기준 파일: {out_path} (질문 {len(questions)}, 표본 {len(sample)})")


if __name__ == "__main__":
    if sys.argv[1:2] == ["freeze"] and len(sys.argv) == 3:
        freeze(Path(sys.argv[2]))
    elif len(sys.argv) == 2 and sys.argv[1] in ("fetch", "build"):
        {"fetch": fetch, "build": build}[sys.argv[1]]()
    else:
        sys.exit(
            "사용법: uv run python -m scripts.defect_precedent.nhtsa {fetch|build|freeze 파일}"
        )

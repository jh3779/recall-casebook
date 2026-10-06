"""리콜 원본 보고서(Part 573 Safety Recall Report, RCLRPT PDF)에서 원인·공급사 칸을 뽑는다.

사용법:
    uv run python -m scripts.defect_precedent.rclrpt sample 300   # 무작위 표본 N건 (기본 시드 20261006)
    uv run python -m scripts.defect_precedent.rclrpt all          # 전체 (약 1.2만 건, 수 시간 — 팀 확인 후)

먼저 `scripts.defect_precedent.nhtsa build`로 recalls.jsonl을 만들어 둔다.
PDF 텍스트 추출에 poppler의 `pdftotext`가 필요하다 (macOS: `brew install poppler`).

- 파일 목록: static.nhtsa.gov는 S3 목록 조회(`?list-type=2&prefix=`)를 허용한다 — 연도별 몇 번의 요청으로 전체 주소를 얻는다.
- 한 리콜에 수정본이 여러 개일 수 있다. 파일명 끝 번호는 순서가 아니므로 본문의 `Submission Date`가 가장 늦은 판본을 쓴다.
- 2025년 하반기부터 양식이 바뀌었다 (`Description of the cause:` 소문자, `Tier of Supplier` 칸) — 두 양식을 모두 읽는다.
- 시점 평가에서는 질문 기준일 이전 판본만 써야 한다 (docs/기획_결함선례.md 6절) — 여기서는 최신 판본만 만든다.
"""

import json
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from scripts.defect_precedent.nhtsa import OUT_DIR, RCLRPT_FROM, REPO_ROOT

PDF_DIR = REPO_ROOT / "data" / "raw" / "rclrpt"
LIST_URL = "https://static.nhtsa.gov/"
UA = {"User-Agent": "Mozilla/5.0"}
DEFAULT_SEED = 20261006
REQUEST_GAP_SEC = 0.25  # 공개 서버 부담을 줄이려는 요청 간격

_CAUSE = re.compile(
    r"Description of the cause\s*:[ \t]*(.*?)(?=\n\s*(?:Identification of any warning|Involved Components"
    r"|Supplier Identification|Component Manufacturer|Description of the Safety|Chronology|Population)|\Z)",
    re.S | re.I,
)
# 원인 칸이 있어도 실제로는 비어 있는 값
_EMPTY_CAUSE = re.compile(
    r"^(NR|.*NR - Not Reported|.*has not reported the cause|still being investigated|N/?A|none"
    r"|unknown|tbd|to be determined|under investigation|investigation (is )?ongoing|not known|unclear)\b",
    re.I,
)
_SUPPLIER_BLOCK = re.compile(
    r"(?:Supplier Identification\s*:|Component Manufacturer\s*\n\s*Tier of Supplier)(.*?)"
    r"(?:Involved Components|Chronology|Description of Remedy|\Z)",
    re.S,
)
_SUBMISSION = re.compile(r"Submission Date\s*:\s*([A-Z]{3} \d{2}, \d{4})")


def parse_report(text: str) -> dict:
    """pdftotext -layout 결과에서 제출일·원인·공급사를 뽑는다."""
    flat = re.sub(r"[ \t]+", " ", text)
    m = _SUBMISSION.search(flat)
    submission = datetime.strptime(m.group(1), "%b %d, %Y").strftime("%Y%m%d") if m else ""

    m = _CAUSE.search(flat)
    cause = re.sub(r"\s+", " ", m.group(1)).strip() if m else None
    if m is None:
        cause_status = "no_field"
    elif not cause or _EMPTY_CAUSE.match(cause):
        cause_status = "empty"
    else:
        cause_status = "filled"

    block = _SUPPLIER_BLOCK.search(flat)
    names, countries = [], []
    if block:
        names = [
            n.strip() for n in re.findall(r"(?<!Component )Name\s*:[ \t]*([^\n]*)", block.group(1))
        ]
        names = [n for n in names if n and not re.match(r"^(NR|N/A)\b", n, re.I)]
        countries = [c.strip() for c in re.findall(r"Country\s*:[ \t]*([^\n]*)", block.group(1))]
        countries = [c for c in countries if c]
    return {
        "submission_date": submission,
        "cause_text": cause if cause_status == "filled" else "",
        "cause_status": cause_status,
        "supplier_names": names,
        "supplier_countries": countries,
        "new_form": "Tier of Supplier" in flat,
    }


def list_reports(years: range) -> dict[str, list[str]]:
    """연도별 S3 목록 조회로 RCLRPT 파일 주소를 모은다. 키는 리콜 번호 앞 6자리 (예: 24V412)."""
    by_campaign: dict[str, list[str]] = {}
    for year in years:
        token = None
        while True:
            query = {"list-type": "2", "prefix": f"odi/rcl/{year}/RCLRPT-"}
            if token:
                query["continuation-token"] = token
            req = urllib.request.Request(LIST_URL + "?" + urllib.parse.urlencode(query), headers=UA)
            body = urllib.request.urlopen(req, timeout=60).read().decode()  # noqa: S310 — 고정된 정부 공개 URL
            for key in re.findall(r"<Key>([^<]*)</Key>", body):
                m = re.search(r"RCLRPT-(\d\d[A-Z]\d{3})", key)
                if m:
                    by_campaign.setdefault(m.group(1), []).append(key)
            m = re.search(r"<NextContinuationToken>([^<]*)<", body)
            if not m:
                break
            token = m.group(1)
    return by_campaign


def _pdf_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=False
    ).stdout


def latest_parsed(keys: list[str]) -> tuple[str, dict]:
    """한 리콜의 모든 판본을 받아 Submission Date가 가장 늦은 판본(같으면 더 긴 것)을 고른다."""
    best = None
    for key in keys:
        path = PDF_DIR / key.split("/")[-1]
        if not path.exists():
            req = urllib.request.Request(LIST_URL + key, headers=UA)
            path.write_bytes(urllib.request.urlopen(req, timeout=60).read())  # noqa: S310
            time.sleep(REQUEST_GAP_SEC)
        text = _pdf_text(path)
        parsed = parse_report(text)
        rank = (parsed["submission_date"], len(text))
        if best is None or rank > best[0]:
            best = (rank, key, parsed)
    return best[1], best[2]


def run(mode: str, n: int = 300, seed: int = DEFAULT_SEED) -> None:
    if shutil.which("pdftotext") is None:
        sys.exit("pdftotext가 없다 — poppler를 설치한다 (macOS: brew install poppler)")
    recalls_path = OUT_DIR / "recalls.jsonl"
    if not recalls_path.exists():
        sys.exit("recalls.jsonl이 없다 — 먼저 `... nhtsa build`를 실행한다")
    received = {}
    for line in recalls_path.open(encoding="utf-8"):
        card = json.loads(line)
        received[card["campno"][:6]] = card["received_date"]

    reports = list_reports(range(2014, datetime.now().year + 1))
    eligible = sorted(c for c in reports if received.get(c, "") >= RCLRPT_FROM)
    missing = sum(1 for c in reports if c not in received)
    print(
        f"보고서가 있는 리콜 {len(reports):,}, 그중 {RCLRPT_FROM} 이후 접수·리콜 파일에 있음 {len(eligible):,}"
    )
    print(f"(리콜 파일에 없는 보고서 {missing:,} — 2026-10-06: 11,856 / 11,734 / 66)")

    picked = random.Random(seed).sample(eligible, n) if mode == "sample" else eligible
    PDF_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / ("causes_sample.jsonl" if mode == "sample" else "causes.jsonl")
    counts = {"filled": 0, "empty": 0, "no_field": 0}
    with out_path.open("w", encoding="utf-8") as f:
        for campaign in picked:
            key, parsed = latest_parsed(reports[campaign])
            counts[parsed["cause_status"]] += 1
            row = {
                "campaign": campaign,
                "versions": len(reports[campaign]),
                "source_file": key,
                **parsed,
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    total = len(picked)
    print(
        f"원인 칸: 채워짐 {counts['filled']} / 비어 있음 {counts['empty']} / 칸 없음 {counts['no_field']} (총 {total})"
    )
    if mode == "sample":
        print("  2026-10-06 표본 300건: 채워짐 205 (68.3%, 시드 20261006)")
    print(f"출력: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "sample":
        run("sample", n=int(sys.argv[2]) if len(sys.argv) > 2 else 300)
    elif len(sys.argv) == 2 and sys.argv[1] == "all":
        run("all")
    else:
        sys.exit("사용법: uv run python -m scripts.defect_precedent.rclrpt {sample [N]|all}")

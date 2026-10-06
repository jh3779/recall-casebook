"""리콜 원본 보고서(Part 573 Safety Recall Report, RCLRPT PDF)에서 원인·공급사 칸을 뽑는다.

사용법:
    uv run python -m scripts.defect_precedent.rclrpt sample 300   # 무작위 표본 N건 (기본 시드 20261006)
    uv run python -m scripts.defect_precedent.rclrpt sample --baseline scripts/defect_precedent/baseline_2026-10-06.json  # 기준 표본 그대로
    uv run python -m scripts.defect_precedent.rclrpt all          # 전체 (약 1.2만 건, 수 시간 — 팀 확인 후)

먼저 `scripts.defect_precedent.nhtsa build`로 recalls.jsonl을 만들어 둔다.
PDF 텍스트 추출에 poppler의 `pdftotext`가 필요하다 (macOS: `brew install poppler`).

- 파일 목록: static.nhtsa.gov는 S3 목록 조회(`?list-type=2&prefix=`)를 허용한다 — 연도별 몇 번의 요청으로 전체 주소를 얻는다.
- 한 리콜에 수정본이 여러 개일 수 있다. 파일명 끝 번호는 순서가 아니므로 본문의 `Submission Date`가 가장 늦은 판본을 쓴다.
- 2025년 하반기부터 양식이 바뀌었다 (`Description of the cause:` 소문자, `Tier of Supplier` 칸) — 두 양식을 모두 읽는다.
- 시점 평가에서는 질문 기준일 이전 판본만 써야 한다 (docs/기획_결함선례.md 6절) — 여기서는 최신 판본만 만든다.
"""

import argparse
import http.client
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

from scripts.defect_precedent.nhtsa import OUT_DIR, RCLRPT_FROM, REPO_ROOT, write_jsonl

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
# "JUN 05, 2024", "NOV 18,2014", "Sep 14, 2015" 모두 있다
_SUBMISSION = re.compile(r"Submission Date\s*:\s*([A-Za-z]{3})\s+(\d{1,2})\s*,\s*(\d{4})")
# 원인 칸이 쪽을 넘으면 pdftotext가 쪽 꼬리말·머리말을 본문 사이에 끼운다
_PAGE_NOISE = re.compile(
    r"The information contained in this report was submitted pursuant to 49 CFR\s*§\s*573"
    r"|Part 573 Safety Recall Report\s+\d\d[A-Z]-?\d{3}"
    r"|\bPage \d+(?: of \d+)?\b"
)


def parse_report(text: str) -> dict:
    """pdftotext -layout 결과에서 제출일·원인·공급사를 뽑는다."""
    flat = re.sub(r"[ \t]+", " ", text)
    m = _SUBMISSION.search(flat)
    submission = (
        datetime.strptime(f"{m.group(1).title()} {m.group(2)} {m.group(3)}", "%b %d %Y").strftime(
            "%Y%m%d"
        )
        if m
        else ""
    )

    m = _CAUSE.search(flat)
    cause = re.sub(r"\s+", " ", _PAGE_NOISE.sub(" ", m.group(1))).strip() if m else None
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
        countries = [c for c in countries if c and not re.match(r"^(NR|N/A)\b", c, re.I)]
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
            body = urllib.request.urlopen(req, timeout=60).read().decode()  # 고정된 정부 공개 URL
            for key in re.findall(r"<Key>([^<]*)</Key>", body):
                m = re.search(r"RCLRPT-(\d\d[A-Z]\d{3})", key)
                if m:
                    by_campaign.setdefault(m.group(1), []).append(key)
            m = re.search(r"<NextContinuationToken>([^<]*)<", body)
            if not m:
                break
            token = m.group(1)
    return by_campaign


class ReportError(Exception):
    """PDF를 받거나 읽지 못한 경우 — "원인 칸 없음"과 구분해 실패 목록에 남긴다."""


def _pdf_text(path: Path) -> str:
    result = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise ReportError(f"pdftotext 실패({result.returncode}): {path.name}")
    return result.stdout  # 글자 없는 이미지 PDF면 빈 문자열


def _download(key: str) -> Path:
    """받은 PDF는 .part로 쓴 뒤 이름을 바꾼다 — 중간에 끊긴 파일이 완성본 이름으로 남지 않게."""
    path = PDF_DIR / key.split("/")[-1]
    if not path.exists():
        req = urllib.request.Request(LIST_URL + key, headers=UA)
        part = path.with_name(path.name + ".part")
        try:
            part.write_bytes(urllib.request.urlopen(req, timeout=60).read())
        except (OSError, http.client.HTTPException) as e:  # 응답이 중간에 끊기면 IncompleteRead
            raise ReportError(f"다운로드 실패: {key} ({e})") from e
        part.replace(path)
        time.sleep(REQUEST_GAP_SEC)
    return path


def latest_parsed(keys: list[str]) -> tuple[str, dict]:
    """한 리콜의 모든 판본을 읽어 Submission Date가 가장 늦은 판본(같으면 더 긴 것)을 고른다.

    - 받기·변환이 실패한 판본이 있으면 최신판을 확정할 수 없으므로 ReportError를 낸다.
    - 글자가 없는 이미지 판본(첨부 스캔 등)은 건너뛰고 그 수를 `image_only_versions`에 남긴다.
      읽을 판본이 하나도 없으면 ReportError.
    """
    best, image_only = None, 0
    for key in keys:
        text = _pdf_text(_download(key))
        if not text.strip():
            image_only += 1
            continue
        parsed = parse_report(text)
        rank = (parsed["submission_date"], len(text))
        if best is None or rank > best[0]:
            best = (rank, key, parsed)
    if best is None:
        raise ReportError(f"글자를 읽을 수 있는 판본 없음: {keys}")
    # 이미지 판본의 제출일은 알 수 없다 — 그것이 실제 최신 수정본이면 고른 판본이 최신이 아닐 수 있다
    return best[1], {
        **best[2],
        "image_only_versions": image_only,
        "latest_uncertain": image_only > 0,
    }


def run(mode: str, n: int = 300, seed: int = DEFAULT_SEED, baseline: Path | None = None) -> None:
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

    if baseline is not None:
        # 기준 실행과 같은 표본 — 목록이 매일 바뀌어도 같은 리콜을 다시 읽는다
        picked = json.loads(baseline.read_text(encoding="utf-8"))["rclrpt_sample_campaigns"]
        gone = [c for c in picked if c not in reports]
        if gone:
            sys.exit(f"기준 표본 중 보고서 목록에서 사라진 리콜: {gone}")
    elif mode == "sample":
        picked = random.Random(seed).sample(eligible, n)
    else:
        picked = eligible

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / ("causes.jsonl" if mode == "all" else "causes_sample.jsonl")
    counts = {"filled": 0, "empty": 0, "no_field": 0}
    rows, failures = [], []
    for campaign in picked:
        try:
            key, parsed = latest_parsed(reports[campaign])
        except ReportError as e:
            failures.append({"campaign": campaign, "error": str(e)})
            continue
        counts[parsed["cause_status"]] += 1
        rows.append(
            {"campaign": campaign, "versions": len(reports[campaign]), "source_file": key, **parsed}
        )
    write_jsonl(out_path, rows)
    write_jsonl(out_path.with_name(out_path.stem + "_failures.jsonl"), failures)
    uncertain = sum(1 for r in rows if r["latest_uncertain"])
    if uncertain:
        print(
            f"주의: 글자 없는 이미지 판본이 있어 최신 판본이 불확실한 리콜 {uncertain}건 (latest_uncertain)"
        )
    no_date = sum(1 for r in rows if not r["submission_date"])
    if no_date:
        print(f"주의: 제출일을 읽지 못한 최신 판본 {no_date}건 — 판본 선택·시점 평가에 쓸 수 없음")
    print(
        f"원인 칸: 채워짐 {counts['filled']} / 비어 있음 {counts['empty']} / 칸 없음 {counts['no_field']}"
        f" / 읽지 못함 {len(failures)} (총 {len(picked)})"
    )
    if mode == "sample":
        print("  2026-10-06 표본 300건 (--baseline): 채워짐 205 (68.3%)")
    print(f"출력: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Part 573 원본 보고서 판독")
    parser.add_argument("mode", choices=["sample", "all"])
    parser.add_argument("n", nargs="?", type=int, default=300, help="sample 모드의 표본 수")
    parser.add_argument(
        "--baseline", type=Path, help="기준 파일의 표본 목록을 그대로 쓴다 (sample 전용)"
    )
    args = parser.parse_args()
    if args.mode == "all" and args.baseline is not None:
        parser.error("--baseline은 sample 모드에서만 쓴다")
    if args.baseline is not None and not args.baseline.exists():
        parser.error(f"기준 파일이 없다: {args.baseline}")
    run(args.mode, n=args.n, baseline=args.baseline)

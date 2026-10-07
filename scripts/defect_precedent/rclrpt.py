"""리콜 원본 보고서(Part 573 Safety Recall Report, RCLRPT PDF)에서 원인·공급사 칸을 뽑는다.

사용법:
    uv run python -m scripts.defect_precedent.rclrpt sample 300   # 무작위 표본 N건 (기본 시드 20261006)
    uv run python -m scripts.defect_precedent.rclrpt sample --baseline scripts/defect_precedent/baseline_2026-10-06.json  # 기준 표본 그대로
    uv run python -m scripts.defect_precedent.rclrpt sample 1000 --out data/processed/defect/causes_pilot_1000.jsonl  # 파일럿 (표본 파일을 덮어쓰지 않는다)
    uv run python -m scripts.defect_precedent.rclrpt all --expect-campaigns 11737   # 전체 (수 시간) — 기대 캠페인 수는 필수

먼저 `scripts.defect_precedent.nhtsa build`로 recalls.jsonl을 만들어 둔다.
PDF 텍스트 추출에 poppler의 `pdftotext`가 필요하다 (macOS: `brew install poppler`).

- 파일 목록: static.nhtsa.gov는 S3 목록 조회(`?list-type=2&prefix=`)를 허용한다 — 연도별 몇 번의 요청으로 전체 주소를 얻는다.
- 한 리콜에 수정본이 여러 개일 수 있다. 파일명 끝 번호는 순서가 아니므로 본문의 `Submission Date`가 가장 늦은 판본을 쓴다.
- 2025년 하반기부터 양식이 바뀌었다 (`Description of the cause:` 소문자, `Tier of Supplier` 칸) — 두 양식을 모두 읽는다.
- 긴 실행에 대비한다: 일시적인 오류(연결 끊김·타임아웃·5xx·429)는 간격을 늘려 다시 시도하고, 이미 받은 PDF는 건너뛰므로
  중간에 끊겨도 다시 실행하면 이어서 한다. 100건마다 진행률을, 200건마다 `*.partial.jsonl`에 중간 결과를 쓴다.
  Ctrl+C로 멈춰도 `*.partial.jsonl`만 남긴다.
- `all` 모드는 시작할 때 목록에서 얻은 수집 대상 수가 `--expect-campaigns N`과 같은지 먼저 확인한다 (서버가 빈 목록이나
  일부 연도만 돌려줘도 완성본처럼 보이는 것을 막는다). N은 같은 실행 앞부분이 출력하는 "그중 … 접수·리콜 파일에 있음" 값이다.
- `all` 모드는 **실패가 하나도 없을 때만** `causes.jsonl`을 만든다 (일부만 담긴 파일이 완성본으로 올라가는 것을 막는다).
  실패가 있으면 `causes.partial.jsonl`과 `causes_failures.jsonl`만 남기니, 원인을 보고 다시 실행한다 (실패한 건만 다시 받는다).
- 시점 평가에서는 질문 기준일 이전 판본만 써야 한다 (docs/기획_결함선례.md 6절) — 여기서는 최신 판본만 만든다.
"""

import argparse
import hashlib
import http.client
import json
import random
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from scripts.defect_precedent.nhtsa import OUT_DIR, RCLRPT_FROM, REPO_ROOT, write_jsonl

PDF_DIR = REPO_ROOT / "data" / "raw" / "rclrpt"
# 사람이 이미지 판본을 열어 확인한 제출일 (저장소에 커밋)
MANUAL_DATES = Path(__file__).with_name("manual_submission_dates.json")
LIST_URL = "https://static.nhtsa.gov/"
UA = {"User-Agent": "Mozilla/5.0"}
DEFAULT_SEED = 20261006
REQUEST_GAP_SEC = 0.25  # 공개 서버 부담을 줄이려는 요청 간격
RETRIES = 3  # 일시적인 오류일 때 다시 시도하는 횟수 (2·4·8초 간격)
RETRY_BACKOFF_SEC = 2.0
PROGRESS_EVERY = 100
CHECKPOINT_EVERY = 200

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


def _get(req: urllib.request.Request) -> bytes:
    """일시적인 오류(연결 끊김·타임아웃·IncompleteRead·429·5xx)는 간격을 늘려 다시 시도한다.
    404 같은 나머지 4xx는 다시 해도 같으므로 바로 실패시킨다."""
    for attempt in range(RETRIES + 1):
        try:
            return urllib.request.urlopen(req, timeout=60).read()  # 고정된 정부 공개 URL
        except urllib.error.HTTPError as e:
            if (e.code < 500 and e.code != 429) or attempt == RETRIES:
                raise
        except (OSError, http.client.HTTPException):
            if attempt == RETRIES:
                raise
        time.sleep(RETRY_BACKOFF_SEC * 2**attempt)
    raise AssertionError("unreachable")


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
            body = _get(req).decode()
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


def require_poppler() -> str:
    """`pdftotext`가 poppler인지 확인하고 버전 줄을 돌려준다.

    xpdf 같은 다른 pdftotext는 출력 인코딩(UTF-8이 아님)과 줄 배치가 달라 기준 데이터와 다른 값을 만든다.
    그런 도구로는 시작하지 않는다 (기준 표본 205/95를 재현하지 못한다).
    """
    result = subprocess.run(["pdftotext", "-v"], capture_output=True, check=False)
    banner = (result.stdout + result.stderr).decode("utf-8", errors="replace")
    if "poppler" not in banner.lower():
        first = banner.strip().splitlines()[0] if banner.strip() else "(버전을 읽지 못함)"
        sys.exit(
            f"이 pdftotext는 poppler가 아니다 ({first}) — poppler를 설치하고 PATH 맨 앞에 둔다 "
            "(macOS: brew install poppler, Windows: winget install oschwartz10612.Poppler). "
            "기준 데이터가 poppler로 만들어져 다른 도구는 같은 값을 만들지 못한다."
        )
    return banner.strip().splitlines()[0]


def _quarantine(path: Path) -> None:
    """읽지 못한 PDF를 `.bad`로 옮긴다 — 같은 이름으로 남으면 다음 실행이 "이미 받음"으로 건너뛰어 계속 실패한다."""
    if path.exists():
        path.replace(path.with_name(path.name + ".bad"))


def _pdf_text(path: Path) -> str:
    # 출력을 UTF-8로 고정하고 바이트로 받아 직접 해독한다 — 컴퓨터의 기본 문자 인코딩(Windows는 cp949 등)에 기대면
    # 같은 PDF가 환경마다 다른 글자(또는 조용히 깨진 글자)가 된다
    result = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", "-layout", str(path), "-"], capture_output=True, check=False
    )
    if result.returncode != 0:
        _quarantine(path)
        raise ReportError(
            f"pdftotext 실패({result.returncode}): {path.name} — 파일을 .bad로 옮겼다 (다시 실행하면 다시 받는다)"
        )
    try:
        return result.stdout.decode("utf-8")  # 글자 없는 이미지 PDF면 빈 문자열
    except UnicodeDecodeError as e:
        raise ReportError(f"pdftotext 출력을 UTF-8로 읽지 못함: {path.name} ({e.reason})") from e


def _download(key: str) -> Path:
    """받은 PDF는 .part로 쓴 뒤 이름을 바꾼다 — 중간에 끊긴 파일이 완성본 이름으로 남지 않게."""
    path = PDF_DIR / key.split("/")[-1]
    if not path.exists():
        req = urllib.request.Request(LIST_URL + key, headers=UA)
        part = path.with_name(path.name + ".part")
        try:
            data = _get(req)
        except (
            OSError,
            http.client.HTTPException,
        ) as e:  # 다시 시도해도 안 되면 (IncompleteRead 포함)
            raise ReportError(f"다운로드 실패: {key} ({e})") from e
        if not data.startswith(
            b"%PDF"
        ):  # 서버가 오류 문서(HTML 등)를 200으로 돌려주면 PDF 이름으로 저장하지 않는다
            raise ReportError(f"PDF가 아닌 응답: {key} ({len(data):,}바이트)")
        part.write_bytes(data)
        part.replace(path)
        time.sleep(REQUEST_GAP_SEC)
    return path


def load_manual_dates(path: Path | None = None) -> dict:
    """사람이 이미지 판본을 직접 열어 확인한 제출일. 키 = PDF 주소, sha256이 같을 때만 쓴다."""
    path = path or MANUAL_DATES
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def latest_parsed(keys: list[str], manual: dict | None = None) -> tuple[str, dict]:
    """한 리콜의 모든 판본 중 Submission Date가 가장 늦은 판본(같으면 더 긴 것)을 고른다.

    - 받기·변환이 실패한 판본이 있으면 ReportError (최신판을 확정할 수 없음).
    - 글자가 없는 이미지 판본은 사람이 확인한 제출일(manual, sha256 일치)이 있을 때만 순서 비교에 넣는다.
    - 날짜를 모르는 판본이 하나라도 있거나 가장 늦은 판본이 글자를 읽을 수 없는 이미지면
      `resolution = "unresolved"` — 원인 칸 통계에서 뺀다 (짐작으로 최신판을 정하지 않는다).
    """
    manual = manual or {}
    pdfs, dated, reasons, used_manual = {}, [], [], False
    for key in keys:
        path = _download(key)
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        pdfs[key] = sha
        text = _pdf_text(path)
        if not text.strip():
            note = manual.get(key)
            if note and note["sha256"] == sha:
                dated.append(((note["submission_date"], 0), key, None))
                used_manual = True
            else:
                reasons.append(f"이미지 판본 제출일 미확인: {key}")
            continue
        parsed = parse_report(text)
        if not parsed["submission_date"]:
            reasons.append(f"제출일 미판독: {key}")
            continue
        dated.append(((parsed["submission_date"], len(text)), key, parsed))
    if not dated:
        raise ReportError(f"날짜를 확인할 수 있는 판본 없음: {keys}")
    _, key, parsed = max(dated, key=lambda d: d[0])
    if parsed is None:
        reasons.append(f"가장 늦은 판본이 글자 없는 이미지: {key}")
        parsed = parse_report("")
    resolution = "unresolved" if reasons else ("manual" if used_manual else "auto")
    return key, {**parsed, "pdfs": pdfs, "resolution": resolution, "unresolved_reasons": reasons}


def run(
    mode: str,
    n: int = 300,
    seed: int = DEFAULT_SEED,
    baseline: Path | None = None,
    out: Path | None = None,
    expect_campaigns: int | None = None,
) -> None:
    if mode == "all" and expect_campaigns is None:
        sys.exit(
            "all은 --expect-campaigns N(기대 캠페인 수)이 필요하다 — 목록이 불완전해도 완성본처럼 보이는 것을 막기 위해서다"
        )
    if shutil.which("pdftotext") is None:
        sys.exit(
            "pdftotext가 없다 — poppler를 설치한다 (macOS: brew install poppler, Windows: winget install oschwartz10612.Poppler)"
        )
    print(f"pdftotext: {require_poppler()}")
    manual = load_manual_dates()
    if baseline is not None:
        # 기준 실행과 같은 입력: 당시 판본 목록만 쓰고, 각 PDF가 당시 sha256과 같은지 확인한다
        base = json.loads(baseline.read_text(encoding="utf-8"))
        sample = base["rclrpt_sample"]
        reports = {s["campaign"]: list(s["pdfs"]) for s in sample}
        expected_sha = {k: v for s in sample for k, v in s["pdfs"].items()}
        picked = [s["campaign"] for s in sample]
        print(
            f"기준 파일 {baseline.name}: 표본 {len(picked)}건, 당시 판본 {len(expected_sha)}개만 사용"
        )
    else:
        recalls_path = OUT_DIR / "recalls.jsonl"
        if not recalls_path.exists():
            sys.exit("recalls.jsonl이 없다 — 먼저 `... nhtsa build`를 실행한다")
        received = {}
        for line in recalls_path.open(encoding="utf-8"):
            card = json.loads(line)
            received[card["campno"][:6]] = card["received_date"]
        try:
            reports = list_reports(range(2014, datetime.now().year + 1))
        except (OSError, http.client.HTTPException) as e:
            sys.exit(f"파일 목록 조회에 실패했다 — 네트워크를 확인하고 다시 실행한다 ({e})")
        if not reports:
            sys.exit("파일 목록이 비어 있다 — 서버 응답을 확인하고 다시 실행한다")
        eligible = sorted(c for c in reports if received.get(c, "") >= RCLRPT_FROM)
        missing = sum(1 for c in reports if c not in received)
        print(
            f"보고서가 있는 리콜 {len(reports):,}, 그중 {RCLRPT_FROM} 이후 접수·리콜 파일에 있음 {len(eligible):,}"
        )
        print(f"(리콜 파일에 없는 보고서 {missing:,} — 2026-10-06: 11,856 / 11,734 / 66)")
        if mode == "all" and len(eligible) != expect_campaigns:
            sys.exit(
                f"수집 대상이 {len(eligible):,}개 캠페인이다 — 기대 {expect_campaigns:,}개와 다르다 "
                "(목록이 불완전하거나 NHTSA 데이터가 바뀐 것일 수 있다. 확인한 뒤 기대 값을 고쳐 다시 실행한다)"
            )
        picked = random.Random(seed).sample(eligible, n) if mode == "sample" else eligible
        expected_sha = {}

    PDF_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = out or OUT_DIR / ("causes.jsonl" if mode == "all" else "causes_sample.jsonl")
    partial_path = out_path.with_name(out_path.stem + ".partial.jsonl")
    failures_path = out_path.with_name(out_path.stem + "_failures.jsonl")
    counts = {"filled": 0, "empty": 0, "no_field": 0}
    rows, failures, unresolved = [], [], 0
    started = time.monotonic()
    interrupted = False

    def checkpoint() -> None:
        write_jsonl(partial_path, rows)
        write_jsonl(failures_path, failures)

    try:
        for i, campaign in enumerate(picked, 1):
            try:
                key, parsed = latest_parsed(reports[campaign], manual)
            except ReportError as e:
                failures.append({"campaign": campaign, "keys": reports[campaign], "error": str(e)})
                key = None
            except Exception as e:  # 몇 시간짜리 실행이 한 건 때문에 멈추지 않게 기록하고 계속한다
                failures.append(
                    {
                        "campaign": campaign,
                        "keys": reports[campaign],
                        "error": f"예상 못 한 오류 {type(e).__name__}: {e}",
                    }
                )
                key = None
            if key is not None:
                changed = [
                    k
                    for k, v in parsed["pdfs"].items()
                    if k in expected_sha and expected_sha[k] != v
                ]
                if changed:
                    failures.append(
                        {
                            "campaign": campaign,
                            "keys": reports[campaign],
                            "error": f"기준과 sha256 다름: {changed}",
                        }
                    )
                else:
                    if parsed["resolution"] == "unresolved":
                        unresolved += 1
                    else:
                        counts[parsed["cause_status"]] += 1
                    rows.append(
                        {
                            "campaign": campaign,
                            "versions": len(reports[campaign]),
                            "source_file": key,
                            **parsed,
                        }
                    )
            if i % PROGRESS_EVERY == 0 or i == len(picked):
                minutes = (time.monotonic() - started) / 60
                print(
                    f"  {i:,}/{len(picked):,} ({i / len(picked):.0%}) 경과 {minutes:.1f}분 · 실패 {len(failures)}"
                )
            if i % CHECKPOINT_EVERY == 0:
                checkpoint()
    except KeyboardInterrupt:
        interrupted = True

    if interrupted or (mode == "all" and failures):
        # 일부만 담긴 파일이 완성본 이름으로 남지 않게 한다 — 이어서 하려면 같은 명령을 다시 실행한다
        checkpoint()
        why = "중단됨" if interrupted else f"실패 {len(failures)}건"
        print(
            f"{why}: {len(rows):,}/{len(picked):,}건만 읽었다 → {partial_path.name} (완성본 {out_path.name}은 만들지 않았다)"
        )
        print(
            f"  실패 목록: {failures_path.name} — 원인을 보고 같은 명령을 다시 실행한다 (받은 PDF는 건너뛴다)"
        )
        if out_path.exists():
            print(
                f"  주의: 이전 실행의 {out_path.name}이 그대로 남아 있다 — 이번 실행 결과가 아니다"
            )
        sys.exit(130 if interrupted else 1)
    write_jsonl(out_path, rows)
    write_jsonl(failures_path, failures)
    partial_path.unlink(missing_ok=True)
    if mode == "all":
        print(
            f"  완성본 {len(rows):,}줄 — 올릴 때: load_db load --causes full --expect-rows {len(rows)}"
        )
    manual_used = sum(1 for r in rows if r["resolution"] == "manual")
    print(
        f"원인 칸: 채워짐 {counts['filled']} / 비어 있음 {counts['empty']} / 칸 없음 {counts['no_field']}"
        f" / 최신판 미확정 {unresolved} / 읽지 못함 {len(failures)} (총 {len(picked)},"
        f" 그중 사람 확인 제출일 사용 {manual_used})"
    )
    if mode == "sample":
        print("  2026-10-06 표본 300건 (--baseline): 채워짐 205 (68.3%) · 비어 있음 95 · 미확정 0")
    print(f"출력: {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Part 573 원본 보고서 판독")
    parser.add_argument("mode", choices=["sample", "all"])
    parser.add_argument("n", nargs="?", type=int, default=300, help="sample 모드의 표본 수")
    parser.add_argument(
        "--baseline", type=Path, help="기준 파일의 표본·판본 목록을 그대로 쓴다 (sample 전용)"
    )
    parser.add_argument(
        "--out", type=Path, help="결과 파일 (기본: causes_sample.jsonl / causes.jsonl)"
    )
    parser.add_argument(
        "--expect-campaigns",
        type=int,
        help="all 모드의 기대 캠페인 수 (목록과 다르면 시작 전에 중단)",
    )
    args = parser.parse_args()
    if args.mode == "all" and args.baseline is not None:
        parser.error("--baseline은 sample 모드에서만 쓴다")
    if args.mode == "all" and args.expect_campaigns is None:
        parser.error("all은 --expect-campaigns N(기대 캠페인 수)이 필요하다")
    if args.mode != "all" and args.expect_campaigns is not None:
        parser.error("--expect-campaigns는 all 모드에서만 쓴다")
    if args.baseline is not None and not args.baseline.exists():
        parser.error(f"기준 파일이 없다: {args.baseline}")
    run(
        args.mode,
        n=args.n,
        baseline=args.baseline,
        out=args.out,
        expect_campaigns=args.expect_campaigns,
    )

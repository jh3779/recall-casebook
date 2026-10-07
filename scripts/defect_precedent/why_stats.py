"""기획 5절 "왜"(원인 근거) 집계 — 이미 받은 파일만으로 계산한다 (추가 수집 없음).

세는 것 (정의는 이슈 #24, 패턴이 넓어서 "원인처럼 보이는 표현이 있는 비율"의 상한에 가까운 대략치다):
- 결함문 원인 표현: 카드 `defect`가 PATTERN과 맞는 리콜 (제조사가 한 말)
- 조사 요약 연결: 결함 조사 파일의 `CAMPNO`가 카드에 있고 요약이 비어 있지 않은 리콜 (정부 조사관이 한 말).
  자리표시 요약(PLACEHOLDER)은 제외한다
- 둘 중 하나 = 합집합
- 추정: 2014-08-20 이후 리콜은 573 표본(`causes_sample.jsonl`)에서 잰 "둘 중 하나" 비율로 바꿔 전체에 적용한다.
  573 원인 칸이 채워진 것도 근거로 센다. 표본은 573이 있는 캠페인에서 뽑았으므로 573이 없는 리콜에는 약간 과대다.
  정확한 값은 573 전체 수집(`rclrpt all`) 뒤에 낼 수 있다.

- 회사 이름 겹침 (이슈 #24 B 파트): 시험 질문 중 **정답 리콜의 회사 이름이 질문에 들어 있는 문항**. 정답 리콜이 여러 개면 하나라도
  들어 있으면 센다. 회사 이름(`maker`)을 단어(영문·숫자)로 나눠 길이 3 이상이고 일반어(COMPANY·MOTORS·AMERICA 등)가 아닌
  단어가 질문 단어와 하나라도 겹치면 "겹침"이다. 회사 이름 전체 문자열이 질문에 그대로 들어 있는 문항은 따로 센다.
  질문에서 회사 이름을 떼지 않으면 같은 회사 리콜만 나오기 쉬워서, 떼어야 하는 문항의 비율을 본다.

- 집계 단위: 573 표본은 **캠페인**(리콜 번호 앞 6자리) 단위라서 표본 비율은 캠페인 비율이다. 2014-08-20 이후 리콜은 리콜 번호와
  캠페인이 1:1이라(앞 6자리가 겹치는 리콜이 없다) 캠페인 수와 리콜 수가 같다 — 이 전제를 `post_one_to_one`으로 확인해 출력하고,
  1:1이 아니면 단위가 섞이므로 전체 추정을 내지 않고 멈춘다.

재현할 때는 기준 파일을 넘긴다. 입력(원본·카드·시험지 sha256, 573 표본의 캠페인·원인 칸 내용)이 기준과 같을 때만 "재현"이고, 다르면
멈춘다(`--allow-drift`를 주면 현재 데이터로 "재계산"한다). 입력 사본은 `docs/환경셋팅.md` 4절(2026-10-06 원본 사본)을 따른다.

    uv run python -m scripts.defect_precedent.why_stats --baseline scripts/defect_precedent/baseline_2026-10-06.json
    uv run python -m scripts.defect_precedent.why_stats    # 기준 파일 없이 현재 데이터로 계산 (재현이 아니다)
"""

import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

from scripts.defect_precedent import nhtsa

PATTERN = re.compile(
    r"due to|caused by|because|result(?:s|ed)? (?:of|from)|attributed to|insufficient|improper(?:ly)?"
    r"|inadequate|incorrect(?:ly)?|out of specification|manufacturing (?:error|defect|variation|process)"
    r"|supplier",
    re.I,
)
PLACEHOLDER = re.compile(r"no summary currently available|^=+$", re.I)
# 회사 이름에서 흔해서 겹쳐도 같은 회사라고 보기 어려운 단어 (이슈 #24 정의)
GENERIC_WORDS = {
    "INC", "CORP", "CO", "LLC", "LTD", "THE", "OF", "AND", "COMPANY", "CORPORATION", "MOTOR", "MOTORS",
    "NORTH", "AMERICA", "USA", "US", "VEHICLE", "VEHICLES", "AUTOMOTIVE",
}  # fmt: skip


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def linked_campnos(inv_rows: list[dict], campnos: set[str]) -> set[str]:
    """조사 요약이 실제로 있는 조사에 연결된 카드의 리콜 번호 (PE·EA 외 조사 종류도 포함)."""
    out = set()
    for r in inv_rows:
        campno, summary = r["CAMPNO"].strip(), r["SUMMARY"].strip()
        if campno in campnos and summary and not PLACEHOLDER.search(summary):
            out.add(campno)
    return out


def _words(text: str) -> list[str]:
    return re.findall(r"[A-Z0-9]+", text.upper())


def maker_overlap(questions: list[dict], recalls: list[dict]) -> dict:
    """시험 질문 중 정답 리콜의 회사 이름이 질문에 들어 있는 문항 수.

    - overlap: 회사 이름의 핵심 단어(길이 3 이상, 일반어 제외)가 질문 단어와 하나라도 겹치는 문항
    - full_name: 회사 이름 전체 문자열(대문자, 끝의 `.` 제거)이 질문에 그대로 들어 있는 문항
    정답 리콜이 여러 개면 하나라도 맞으면 센다.
    """
    maker_of = {r["campno"]: r["maker"] for r in recalls}
    overlap = full_name = 0
    for q in questions:
        makers = [maker_of[c] for c in q["gold_campnos"] if c in maker_of]
        q_words = set(_words(q["question"]))
        key_words = [
            {w for w in _words(m) if len(w) >= 3 and w not in GENERIC_WORDS} for m in makers
        ]
        overlap += any(words & q_words for words in key_words)
        upper = q["question"].upper()
        full_name += any(m.upper().rstrip(".") in upper for m in makers)
    return {"questions": len(questions), "overlap": overlap, "full_name": full_name}


def compute(recalls: list[dict], inv_rows: list[dict], causes_sample: list[dict]) -> dict:
    campnos = {r["campno"] for r in recalls}
    expressed = {r["campno"] for r in recalls if PATTERN.search(r["defect"])}
    linked = linked_campnos(inv_rows, campnos)
    either = expressed | linked

    post = {r["campno"] for r in recalls if r["received_date"] >= nhtsa.RCLRPT_FROM}
    pre = campnos - post
    # 표본 비율은 캠페인 단위이므로 환산도 캠페인 수에 곱한다. 이후 리콜은 캠페인과 1:1이어야 리콜 수와 같다
    post_campaigns = {c[:6] for c in post}

    # 표본: 캠페인(앞 6자리) 하나가 여러 리콜에 붙을 수 있다 — 그중 하나라도 기존 방식 근거가 있으면 있는 것으로 센다
    by_campaign = defaultdict(list)
    for c in campnos:
        by_campaign[c[:6]].append(c)
    old_in_sample = union_in_sample = 0
    for row in causes_sample:
        has_old = any(c in either for c in by_campaign[row["campaign"]])
        old_in_sample += has_old
        union_in_sample += has_old or row["cause_status"] == "filled"
    n = len(causes_sample)
    p = union_in_sample / n if n else 0.0
    half_width = 1.96 * math.sqrt(p * (1 - p) / n) if n else 0.0  # 정규 근사 95%
    estimate = len(either & pre) + len(post_campaigns) * p
    return {
        "recalls": len(campnos),
        "expressed": len(expressed),
        "linked": len(linked),
        "either": len(either),
        "post_recalls": len(post),
        "post_campaigns": len(post_campaigns),
        "post_one_to_one": len(post) == len(post_campaigns),
        "post_either": len(either & post),
        "pre_recalls": len(pre),
        "pre_either": len(either & pre),
        "sample": n,
        "sample_old": old_in_sample,
        "sample_filled": sum(r["cause_status"] == "filled" for r in causes_sample),
        "sample_union": union_in_sample,
        "sample_union_rate": p,
        "sample_half_width": half_width,
        "estimate": estimate,
        "estimate_half_width": len(post_campaigns) * half_width,
    }


def sample_digest(rows: list[dict]) -> str:
    """573 표본의 내용 지문 — 줄마다 [캠페인, cause_status, resolution, submission_date, 정렬한 (판본, sha256)]을 정렬해 해시한다.

    줄바꿈 방식·칸 순서와 무관하고, 원인 칸 판독 결과(205/95)를 정하는 값이 바뀌면 달라진다.
    """
    items = [
        [
            r["campaign"],
            r["cause_status"],
            r["resolution"],
            r["submission_date"],
            sorted(r["pdfs"].items()),
        ]
        for r in rows
    ]
    return hashlib.sha256(
        json.dumps(sorted(items), ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def sample_matches(base: dict, causes_sample: list[dict]) -> bool:
    """573 표본이 기준과 같은가: 중복 없이 같은 캠페인 300개이고, 기준 파일에 내용 지문이 있으면 그것과도 같아야 한다.

    지문이 없는 기준 파일(옛 형식)이면 원인 칸 건수(채워짐·비어 있음·미확정)와 판본 sha256만 대조한다.
    """
    campaigns = [r["campaign"] for r in causes_sample]
    if len(set(campaigns)) != len(campaigns) or set(campaigns) != {
        s["campaign"] for s in base["rclrpt_sample"]
    }:
        return False
    spec = base.get("causes_sample")
    if spec:
        return (
            len(causes_sample) == spec["rows"]
            and sample_digest(causes_sample) == spec["content_sha256"]
        )
    expected = base["expected"]
    got = {
        "rclrpt_sample_filled": sum(r["cause_status"] == "filled" for r in causes_sample),
        "rclrpt_sample_empty": sum(r["cause_status"] == "empty" for r in causes_sample),
        "rclrpt_sample_unresolved": sum(r["resolution"] == "unresolved" for r in causes_sample),
    }
    same_pdfs = {r["campaign"]: r["pdfs"] for r in causes_sample} == {
        s["campaign"]: s["pdfs"] for s in base["rclrpt_sample"]
    }
    return same_pdfs and all(got[k] == expected[k] for k in got)


def input_label(
    baseline_name: str, base: dict, info: dict, causes_sample: list[dict], allow_drift: bool
) -> str:
    """기준 파일과 같은 입력인지 확인해 출력용 문구를 만든다. 다르면 멈춘다 (--allow-drift면 재계산으로 표시)."""
    same_files = all(
        info[k] == base["build"][k]
        for k in ("raw_manifest_sha256", "recalls_sha256", "eval_sha256")
    )
    same_sample = sample_matches(base, causes_sample)
    if same_files and same_sample:
        return f"{baseline_name} 재현 (원본·카드·시험지 sha256 일치, 573 표본 캠페인·원인 칸 내용 일치)"
    if allow_drift:
        return f"{baseline_name}와 다른 입력으로 재계산 (재현 아님)"
    what = []
    if not same_files:
        what.append("원본·카드·시험지 sha256")
    if not same_sample:
        what.append("573 표본 캠페인·원인 칸 내용")
    sys.exit(
        f"{', '.join(what)}이 기준 파일과 다르다 — 같은 원본 사본(data/raw/nhtsa.<받은 시각>)과 표본으로 다시 만들거나, "
        "현재 데이터로 재계산만 하려면 --allow-drift를 붙인다"
    )


def main(baseline: Path | None = None, allow_drift: bool = False) -> None:
    recalls = read_jsonl(nhtsa.OUT_DIR / "recalls.jsonl")
    causes_sample = read_jsonl(nhtsa.OUT_DIR / "causes_sample.jsonl")
    label = "현재 데이터로 계산 (기준 파일과 같은 입력인지 확인하지 않음 — 재현이 아니다)"
    if baseline is not None:
        base = json.loads(baseline.read_text(encoding="utf-8"))
        label = input_label(baseline.name, base, nhtsa.verify_build(), causes_sample, allow_drift)
    s = compute(
        recalls, nhtsa.read_flat(nhtsa.RAW_DIR / "FLAT_INV.zip", nhtsa.INV_COLS), causes_sample
    )
    if not s["post_one_to_one"]:
        sys.exit(
            f"2014-08-20 이후 리콜 {s['post_recalls']:,}건이 캠페인 {s['post_campaigns']:,}개에 걸려 있다 — 표본 비율(캠페인 단위)을 "
            "리콜 건수에 곱하는 전체 추정은 단위가 섞여서 내지 않는다. 캠페인 단위로 다시 정의한 뒤에 계산한다"
        )
    total = s["recalls"]
    overlap = maker_overlap(read_jsonl(nhtsa.OUT_DIR / "eval.jsonl"), recalls)

    def pct(x: float, whole: float) -> str:
        return f"{x:,.0f}건 ({x / whole:.1%})"

    print(f"입력: {label}")
    print(f"전체 리콜 {total:,}건")
    print(f"  결함문 원인 표현   {pct(s['expressed'], total)}")
    print(f"  조사 요약 연결     {pct(s['linked'], total)}")
    print(f"  둘 중 하나         {pct(s['either'], total)}")
    print(
        f"2014-08-20 이후 {s['post_recalls']:,}건 중 기존 방식 {pct(s['post_either'], s['post_recalls'])}"
    )
    print(
        f"  (이 리콜 {s['post_recalls']:,}건은 캠페인 {s['post_campaigns']:,}개와 1:1 — 표본 비율을 그대로 곱해도 단위가 같다)"
    )
    print(
        f"2014-08-20 이전 {s['pre_recalls']:,}건 중 기존 방식 {pct(s['pre_either'], s['pre_recalls'])}"
    )
    n = s["sample"]
    print(
        f"573 표본 {n}개 캠페인: 기존 방식 {pct(s['sample_old'], n)} · 573 원인 칸 {pct(s['sample_filled'], n)}"
    )
    print(f"  둘 중 하나 {pct(s['sample_union'], n)} ±{s['sample_half_width']:.1%}p")
    q = overlap["questions"]
    print(
        f"시험 질문 {q}개 중 정답 리콜의 회사 이름이 질문에 들어 있는 문항 {pct(overlap['overlap'], q)}"
    )
    print(f"  그중 회사 이름 전체가 그대로 들어 있는 문항 {pct(overlap['full_name'], q)}")
    print(
        f"전체 추정 약 {s['estimate']:,.0f}건 ({s['estimate'] / total:.1%}, ±약 {s['estimate_half_width'] / total:.1%}p)"
        " — 573 전체 수집 전의 추정"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="기획 5절 '왜' 집계")
    parser.add_argument(
        "--baseline",
        type=Path,
        help="기준 파일 — 입력 sha256·573 표본 캠페인을 대조해 재현인지 확인한다",
    )
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help="입력이 기준과 달라도 현재 데이터로 재계산한다 (--baseline과 함께)",
    )
    args = parser.parse_args()
    if args.baseline is not None and not args.baseline.exists():
        parser.error(f"기준 파일이 없다: {args.baseline}")
    if args.allow_drift and args.baseline is None:
        parser.error("--allow-drift는 --baseline과 함께 쓴다")
    main(args.baseline, args.allow_drift)

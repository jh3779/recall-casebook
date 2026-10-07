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

    uv run python -m scripts.defect_precedent.why_stats
"""

import json
import math
import re
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
    estimate = len(either & pre) + len(post) * p
    return {
        "recalls": len(campnos),
        "expressed": len(expressed),
        "linked": len(linked),
        "either": len(either),
        "post_recalls": len(post),
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
        "estimate_half_width": len(post) * half_width,
    }


def main() -> None:
    s = compute(
        read_jsonl(nhtsa.OUT_DIR / "recalls.jsonl"),
        nhtsa.read_flat(nhtsa.RAW_DIR / "FLAT_INV.zip", nhtsa.INV_COLS),
        read_jsonl(nhtsa.OUT_DIR / "causes_sample.jsonl"),
    )
    total = s["recalls"]
    overlap = maker_overlap(
        read_jsonl(nhtsa.OUT_DIR / "eval.jsonl"), read_jsonl(nhtsa.OUT_DIR / "recalls.jsonl")
    )

    def pct(x: float, whole: float) -> str:
        return f"{x:,.0f}건 ({x / whole:.1%})"

    print(f"전체 리콜 {total:,}건")
    print(f"  결함문 원인 표현   {pct(s['expressed'], total)}")
    print(f"  조사 요약 연결     {pct(s['linked'], total)}")
    print(f"  둘 중 하나         {pct(s['either'], total)}")
    print(
        f"2014-08-20 이후 {s['post_recalls']:,}건 중 기존 방식 {pct(s['post_either'], s['post_recalls'])}"
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
    main()

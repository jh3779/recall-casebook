"""리콜 카드의 회사명(raw_maker)을 같은 회사끼리 묶는 대응표 초안을 만든다.

사용법:
    uv run python -m scripts.defect_precedent.maker_aliases   # maker_aliases.csv 만들기

- 자동으로 묶는 것은 대소문자·문장부호·공백·Inc/Incorporated·Corp/Corporation·Co/Company 차이뿐이다.
- 법인 형태(LLC·Corp 등)나 지역 이름(North America·USA)만 다른 이름은 같은 회사인지 짐작하지 않는다.
  묶지 않고 `status = 확인 필요`로 표시한다 — 사람(D 파트)이 보고 `maker`를 직접 고친다.
- 이 표는 아직 recalls.jsonl의 maker에 적용하지 않는다. 적용하면 카드 sha256이 바뀌어 기준 파일 재현이 깨지므로
  사람 확인 뒤 새 기준(freeze)과 함께 적용한다.
"""

import csv
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RECALLS = REPO_ROOT / "data" / "processed" / "defect" / "recalls.jsonl"
OUT = Path(__file__).resolve().parent / "maker_aliases.csv"

_SAME_WORD = {"INCORPORATED": "INC", "CORPORATION": "CORP", "COMPANY": "CO", "L L C": "LLC"}
_LOOSE_DROP = {
    "INC",
    "LLC",
    "CORP",
    "CO",
    "LTD",
    "LIMITED",
    "LP",
    "NA",
    "USA",
    "NORTH",
    "AMERICA",
    "THE",
}


def _tokens(name: str) -> str:
    s = name.upper().replace("&", " AND ")
    s = re.sub(r"[^A-Z0-9]+", " ", s).strip()
    s = re.sub(r"\bL L C\b", "LLC", s)
    return " ".join(_SAME_WORD.get(t, t) for t in s.split())


def strict_key(name: str) -> str:
    """대소문자·문장부호·Inc/Incorporated류 표기 차이만 지운 키. 같으면 같은 이름으로 본다."""
    return _tokens(name)


def loose_key(name: str) -> str:
    """법인 형태·지역 이름까지 지운 키. 같은데 strict_key가 다르면 사람이 확인한다."""
    return " ".join(t for t in _tokens(name).split() if t not in _LOOSE_DROP)


def build_table(counts: Counter) -> list[dict]:
    strict: dict[str, list[str]] = defaultdict(list)
    for raw in counts:
        strict[strict_key(raw)].append(raw)
    loose: dict[str, set[str]] = defaultdict(set)
    for key in strict:
        loose[loose_key(next(iter(strict[key])))].add(key)

    rows = []
    for raws in strict.values():
        # 대표 이름: 소문자가 섞인 표기 중 가장 많은 것, 없으면 가장 많은 것
        mixed = [r for r in raws if r != r.upper()]
        canon = max(mixed or raws, key=lambda r: (counts[r], r))
        group = loose[loose_key(raws[0])]
        for raw in raws:
            rows.append(
                {
                    "raw_maker": raw,
                    "maker": canon,
                    "count": counts[raw],
                    "status": "확인 필요" if len(group) > 1 else "자동",
                    "group": loose_key(raws[0]) if len(group) > 1 else "",
                }
            )
    rows.sort(key=lambda r: (-r["count"], r["raw_maker"]))
    return rows


def main() -> None:
    with RECALLS.open(encoding="utf-8") as f:
        counts = Counter(json.loads(line)["raw_maker"] for line in f if line.strip())
    rows = build_table(counts)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["raw_maker", "maker", "count", "status", "group"])
        w.writeheader()
        w.writerows(rows)
    merged = len({r["maker"] for r in rows})
    review = sum(r["status"] == "확인 필요" for r in rows)
    print(
        f"원문 이름 {len(rows):,}개 → 자동으로 묶은 뒤 {merged:,}개 / 확인 필요 {review:,}줄 → {OUT.name}"
    )


if __name__ == "__main__":
    main()

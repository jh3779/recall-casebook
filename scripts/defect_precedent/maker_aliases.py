"""리콜 카드의 회사명(raw_maker)을 같은 회사끼리 묶는 대응표 초안을 만든다.

사용법:
    uv run python -m scripts.defect_precedent.maker_aliases   # maker_aliases.csv 만들기

칸 두 개를 따로 채운다 (DEC-033).
- `maker`: 신고서 이름을 정리한 이름. 대소문자·문장부호·Inc/Incorporated류 표기 차이와 법인 형태 차이
  (Corp ↔ LLC, 법인 표기 유무)는 한 이름으로 통일한다. 지역(America·North America·USA)이 다르면 따로 둔다.
- `maker_group`: 사용자가 "같은 회사의 선례"로 묶어 보고 싶은 단위. 미국 법인과 본사(Hyundai Motor America ↔
  Hyundai Motor Company), 이름이 바뀐 회사(Chrysler → FCA → Stellantis)를 한 묶음으로 본다. 모든 줄이 값을 가진다.
  묶을 이름이 없으면 `maker`와 같다.

`maker_group`의 근거는 `group_basis`에 적는다: 없음(묶을 이름 없음) · 자동(이름의 핵심 단어가 같음) ·
초안(이름 목록으로 직접 지정 — 사람이 확인하기 전 값). `review = 확인 필요`인 줄만 사람이 보면 된다.

이 표는 아직 recalls.jsonl의 maker에 적용하지 않는다. 적용하면 카드 sha256이 바뀌어 기준 파일 재현이 깨지므로
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
_LEGAL = {"INC", "LLC", "CORP", "CO", "LTD", "LIMITED", "LP"}
_REGION = {"NA", "USA", "NORTH", "AMERICA", "THE"}

# 이름이 달라서 규칙으로는 못 잇는 묶음. 신고서 이름을 하나씩 적었다 (키워드로 찾으면
# "Hyundai Translead"(트레일러 회사)처럼 다른 회사가 섞인다). 지식 기반 초안이므로 사람이 확인한다.
CURATED_GROUPS = {
    "Chrysler (DaimlerChrysler·FCA·Stellantis 이어짐)": [
        "CHRYSLER CORPORATION",
        "CHRYSLER LLC",
        "CHRYSLER GROUP LLC",
        "Chrysler (FCA US, LLC)",
        "Chrysler (FCA US, LLC) (Stellantis)",
        "DAIMLERCHRYSLER CORPORATION",
        "CHRYSLER CORP-OVERSEAS",
    ],
    "Kia": [
        "Kia Motors America",
        "Kia America, Inc.",
        "KIA MOTORS CORPORATION",
    ],
    "Toyota": [
        "TOYOTA MOTOR NORTH AMERICA, INC.",
        "TOYOTA MOTOR CO., LTD.",
        "Toyota Motor Engineering & Manufacturing",
    ],
    "Volkswagen": [
        "Volkswagen Group of America, Inc.",
        "VOLKSWAGEN OF AMERICA, INC",
    ],
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
    """법인 형태·지역 이름까지 지운 키. 같으면 같은 회사의 변형으로 본다."""
    return " ".join(t for t in _tokens(name).split() if t not in _LEGAL | _REGION)


def _region(name: str) -> frozenset[str]:
    return frozenset(t for t in _tokens(name).split() if t in _REGION - {"THE"})


def _pick(names: list[str], counts: Counter) -> str:
    """대표 이름: 소문자가 섞인 표기 중 가장 많은 것, 없으면 가장 많은 것."""
    mixed = [n for n in names if n != n.upper()]
    return max(mixed or names, key=lambda n: (counts[n], n))


def build_table(counts: Counter) -> list[dict]:
    # maker: 같은 핵심 이름 + 같은 지역 표기끼리 한 이름 (표기·법인 형태 차이를 통일)
    by_maker: dict[tuple[str, frozenset], list[str]] = defaultdict(list)
    for raw in counts:
        by_maker[(loose_key(raw), _region(raw))].append(raw)
    maker_of: dict[str, str] = {}
    basis_of: dict[str, str] = {}
    for raws in by_maker.values():
        name = _pick(raws, counts)
        for raw in raws:
            maker_of[raw] = name
            if len(raws) == 1:
                basis_of[raw] = "원문"
            elif len({strict_key(r) for r in raws}) == 1:
                basis_of[raw] = "표기 통일"
            else:
                basis_of[raw] = "법인 형태 통일"

    # maker_group: 이름 목록으로 지정한 것 먼저, 아니면 핵심 이름이 같은 maker끼리
    # 목록에 없는 표기라도 같은 maker로 합쳐졌으면 그 maker의 묶음을 따른다 (예: KIA MOTORS AMERICA, INC.)
    listed = {strict_key(raw): label for label, raws in CURATED_GROUPS.items() for raw in raws}
    curated = {
        maker_of[raw]: listed[strict_key(raw)] for raw in counts if strict_key(raw) in listed
    }
    by_core: dict[str, set[str]] = defaultdict(set)
    for raw in counts:
        by_core[loose_key(raw)].add(maker_of[raw])
    core_label = {
        core: max(makers, key=lambda m: (counts[m], m)) for core, makers in by_core.items()
    }

    rows = []
    for raw, n in counts.items():
        core = loose_key(raw)
        if maker_of[raw] in curated:
            group, basis, review = curated[maker_of[raw]], "초안", "확인 필요"
        elif len(by_core[core]) > 1:
            group, basis = core_label[core], "자동"
            review = "확인 필요" if len(core.split()) == 1 else ""
        else:
            group, basis, review = maker_of[raw], "없음", ""
        rows.append(
            {
                "raw_maker": raw,
                "maker": maker_of[raw],
                "maker_group": group,
                "count": n,
                "maker_basis": basis_of[raw],
                "group_basis": basis,
                "review": review,
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["raw_maker"]))
    return rows


def main() -> None:
    with RECALLS.open(encoding="utf-8") as f:
        counts = Counter(json.loads(line)["raw_maker"] for line in f if line.strip())
    present = {strict_key(c) for c in counts}
    missing = [r for raws in CURATED_GROUPS.values() for r in raws if strict_key(r) not in present]
    if missing:
        print(f"주의: 이름 목록에 있지만 데이터에 없는 이름 {missing}")
    rows = build_table(counts)
    fields = ["raw_maker", "maker", "maker_group", "count", "maker_basis", "group_basis", "review"]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    makers = len({r["maker"] for r in rows})
    groups = len({r["maker_group"] for r in rows})
    review = sum(r["review"] == "확인 필요" for r in rows)
    print(
        f"원문 이름 {len(rows):,}개 → maker {makers:,}개 → maker_group {groups:,}개 / 확인 필요 {review}줄 → {OUT.name}"
    )


if __name__ == "__main__":
    main()

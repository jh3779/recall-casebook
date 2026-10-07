"""리콜 카드의 회사명(raw_maker)을 같은 회사끼리 묶는 대응표 초안을 만든다.

사용법:
    uv run python -m scripts.defect_precedent.maker_aliases   # maker_aliases_draft.csv 만들기

파일은 둘로 나눈다. 이 스크립트는 **초안**(`maker_aliases_draft.csv`)만 만들고 언제든 다시 만들 수 있다.
사람이 확인한 결과는 초안을 복사해 `maker_aliases.csv`로 저장해서 고친다 — 스크립트가 이 파일은 건드리지 않으므로
확인 결과가 덮어써지지 않는다. CSV는 엑셀용 UTF-8 BOM으로 쓰므로 읽을 때 `encoding="utf-8-sig"`를 쓴다.

칸 두 개를 따로 채운다 (DEC-033).
- `maker`: 신고서 이름을 정리한 이름. 대소문자·문장부호·Inc/Incorporated류 표기 차이와 법인 형태 차이
  (Corp ↔ LLC, 법인 표기 유무)는 한 이름으로 통일한다. 지역(America·North America·USA)이 다르면 따로 둔다.
- `maker_group`: 사용자가 "같은 회사의 선례"로 묶어 보고 싶은 단위. 미국 법인과 본사(Hyundai Motor America ↔
  Hyundai Motor Company), 이름이 바뀐 회사(Chrysler → FCA → Stellantis)를 한 묶음으로 본다. 모든 줄이 값을 가진다.
  묶을 이름이 없으면 `maker`와 같다.

`maker_group`의 근거는 `group_basis`에 적는다: 없음(묶을 이름 없음) · 자동(이름의 핵심 단어가 같음) ·
초안(이름 목록으로 직접 지정 — 사람이 확인하기 전 값).

`review`는 확인 상태다: `확인 필요`(검토 전) · `확인 완료` · `보류`(판단 못 함) · 빈칸(사람이 볼 필요 없음).
`review_note`에 이유(무엇을 확인할지)와 사람의 메모를 적는다. `review_required`는 스크립트가 쓰는 고정 칸이다:
검토가 필요했던 줄은 `필요`라고 적혀 있어서 사람이 `review`를 지우거나 오타를 내도 "확인했다"로 통과하지 못한다.
카드에 적용하는 코드는 `unreviewed(확인본, 초안)`이 비어 있을 때만 진행한다 — 초안과 대조해서 줄이 사라지거나 늘거나
`review_required`가 바뀌면 중단하고, 검토가 필요했던 줄은 `review`가 정확히 `확인 완료`일 때만 통과하며,
`확인 필요`·`보류`가 남거나 알 수 없는 값(오타)이 있으면 중단한다.

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
OUT = Path(__file__).resolve().parent / "maker_aliases_draft.csv"
REVIEW_PENDING = ("확인 필요", "보류")
REVIEW_STATES = ("", "확인 필요", "확인 완료", "보류")
REVIEW_REQUIRED = "필요"  # review_required 칸 — 스크립트가 쓰고 사람이 고치지 않는다. 지워도 검토가 필요했다는 기록이 남는다

_SAME_WORD = {"INCORPORATED": "INC", "CORPORATION": "CORP", "COMPANY": "CO", "L L C": "LLC"}
_LEGAL = {"INC", "LLC", "CORP", "CO", "LTD", "LIMITED", "LP"}
_REGION = {"NA", "USA", "NORTH", "AMERICA", "THE"}
# 이 서비스의 사용자가 납품하는 완성차 회사. 자동으로 묶은 이름도 미국 법인·본사 연결이 맞는지 사람이 본다
CUSTOMER_CORES = {"HYUNDAI", "KIA", "GENESIS"}

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
    # 점이 찍힌 약어(N.A.·U.S.A.·L.L.C.)는 점을 지워 한 단어로 본다 — 점에서 자르면 N·A로 갈라져 NA·USA와 달라진다
    s = re.sub(r"\b[A-Z](?:\.[A-Z])+\b", lambda m: m.group().replace(".", ""), s)
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


# 법인 표기 앞에 쉼표 대신 마침표가 찍힌 오타 ("Americas. Inc."). MFG.·BLDR. 같은 약어(3글자 이하)는 해당하지 않는다.
_TYPO = re.compile(r"[A-Za-z]{4,}\.\s+(?:Inc|LLC|Corp|Co|Ltd)\b", re.IGNORECASE)


def _pick(names: list[str], counts: Counter) -> str:
    """대표 이름: 마침표 오타가 없는 표기 → 소문자가 섞인 표기 → 가장 많은 표기 순으로 고른다."""
    return max(names, key=lambda n: (not _TYPO.search(n), n != n.upper(), counts[n], n))


def build_table(counts: Counter) -> list[dict]:
    # maker: 같은 핵심 이름 + 같은 지역 표기끼리 한 이름 (표기·법인 형태 차이를 통일)
    by_maker: dict[tuple[str, frozenset], list[str]] = defaultdict(list)
    for raw in counts:
        by_maker[(loose_key(raw), _region(raw))].append(raw)
    maker_of: dict[str, str] = {}
    basis_of: dict[str, str] = {}
    typo_makers: set[str] = (
        set()
    )  # 합쳐진 원문 중 마침표 오타가 있는 maker — 대표 이름을 사람이 본다
    for raws in by_maker.values():
        name = _pick(raws, counts)
        if len(raws) > 1 and any(_TYPO.search(r) for r in raws):
            typo_makers.add(name)
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
        notes = []
        if maker_of[raw] in curated:
            group, basis, review = curated[maker_of[raw]], "초안", "확인 필요"
            notes.append("maker_group: 이름 목록으로 지정한 초안")
        elif len(by_core[core]) > 1:
            group, basis = core_label[core], "자동"
            review = "확인 필요" if len(core.split()) == 1 else ""
            if len(core.split()) == 1:
                notes.append("maker_group: 핵심 단어가 하나뿐이라 우연히 같은 이름일 수 있음")
            if core.split()[0] in CUSTOMER_CORES:
                review = "확인 필요"
                notes.append(
                    "maker_group: 고객사(현대·기아·제네시스) 묶음 — 미국 법인과 본사 연결이 맞는지 확인"
                )
        else:
            group, basis, review = maker_of[raw], "없음", ""
        if maker_of[raw] in typo_makers:
            review = "확인 필요"
            notes.append("maker: 합쳐진 원문에 마침표 오타('. Inc.')가 있어 대표 이름(철자) 확인")
        rows.append(
            {
                "raw_maker": raw,
                "maker": maker_of[raw],
                "maker_group": group,
                "count": n,
                "maker_basis": basis_of[raw],
                "group_basis": basis,
                "review": review,
                "review_required": REVIEW_REQUIRED if review else "",
                "review_note": "; ".join(notes),
            }
        )
    rows.sort(key=lambda r: (-r["count"], r["raw_maker"]))
    return rows


FIXED_COLUMNS = ("count", "maker_basis", "group_basis")  # 사람이 고치지 않는 칸


def read_table(path: Path) -> list[dict]:
    """대응표 CSV를 읽는다 (엑셀용 UTF-8 BOM)."""
    with path.open(encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def reason_added(note: str | None, draft_note: str | None) -> bool:
    """초안 메모는 그대로 두고 그 뒤에 실제 설명이 덧붙었는가 (빈칸·공백·`;`만 덧붙인 것, 초안 메모 삭제, 빈 칸(None)은 아니다)."""
    note, draft_note = note or "", draft_note or ""
    return note.startswith(draft_note) and bool(note[len(draft_note) :].strip(" ;\t\r\n"))


def unreviewed(rows: list[dict], draft: list[dict]) -> list[dict]:
    """확인이 끝나지 않은 줄. 카드에 적용하기 전에 비어 있어야 한다.

    사람이 고친 확인본(rows)만 믿지 않고 스크립트가 만든 초안(draft)과 대조한다:
    - 줄이 사라졌거나 늘었거나 같은 `raw_maker`가 겹치면 오류로 멈춘다 (검토 대상 줄을 통째로 지운 경우를 잡는다).
    - `review_required`가 초안과 다르면 오류로 멈춘다 (`review`와 `review_required`를 함께 지운 경우를 잡는다).
    - 알 수 없는 상태값(오타 `확인완료` 등)은 짐작하지 않고 오류로 멈춘다.
    - `maker`·`maker_group`이 비어 있으면 오류로 멈춘다. 초안과 값이 다른 줄은 `review`가 `확인 완료`이고 `review_note`가
      초안 메모를 그대로 둔 채 그 뒤에 실제 설명이 덧붙어 있어야 한다 (이유 없이 고치거나 메모를 지운 줄을 잡는다). `count`·`maker_basis`·`group_basis`는 사람이 고치지 않는 칸이라
      초안과 같아야 한다 (열 하나만 정렬이 어긋난 경우를 잡는다).
    - `확인 필요`·`보류`는 끝나지 않은 줄이고, 검토가 필요했던 줄(`review_required = 필요`)은 `review`가 정확히
      `확인 완료`일 때만 끝난 것이다.
    """
    names = Counter(r["raw_maker"] for r in rows)
    duplicated = sorted(n for n, c in names.items() if c > 1)
    if duplicated:
        raise ValueError(f"raw_maker가 겹치는 줄이 있다 {duplicated[:5]} (총 {len(duplicated)}개)")
    original = {r["raw_maker"]: r for r in draft}
    missing, extra = sorted(set(original) - set(names)), sorted(set(names) - set(original))
    if missing or extra:
        raise ValueError(
            f"확인본의 줄이 초안과 다르다 — 사라진 줄 {len(missing)}개 {missing[:5]}, 늘어난 줄 {len(extra)}개 {extra[:5]}"
        )
    changed = sorted(
        r["raw_maker"]
        for r in rows
        if r["review_required"] != original[r["raw_maker"]]["review_required"]
    )
    if changed:
        raise ValueError(
            f"review_required가 초안과 다르다 {changed[:5]} (총 {len(changed)}줄) — 이 칸은 스크립트가 쓰는 고정 칸이다"
        )
    empty = sorted(
        r["raw_maker"]
        for r in rows
        if not (r["maker"] or "").strip() or not (r["maker_group"] or "").strip()
    )
    if empty:
        raise ValueError(f"maker·maker_group이 빈 줄이 있다 {empty[:5]} (총 {len(empty)}줄)")
    moved = sorted(
        r["raw_maker"]
        for r in rows
        if any(str(r[c]) != str(original[r["raw_maker"]][c]) for c in FIXED_COLUMNS)
    )
    if moved:
        raise ValueError(
            f"count·maker_basis·group_basis가 초안과 다르다 {moved[:5]} (총 {len(moved)}줄) — 고치지 않는 칸이다"
        )
    unexplained = sorted(
        r["raw_maker"]
        for r in rows
        if (
            r["maker"] != original[r["raw_maker"]]["maker"]
            or r["maker_group"] != original[r["raw_maker"]]["maker_group"]
        )
        and (
            r["review"] != "확인 완료"
            or not reason_added(r["review_note"], original[r["raw_maker"]]["review_note"])
        )
    )
    if unexplained:
        raise ValueError(
            f"maker·maker_group을 고친 줄은 review를 `확인 완료`로 하고 review_note에 이유를 적어야 한다 "
            f"{unexplained[:5]} (총 {len(unexplained)}줄)"
        )
    unknown = sorted({r["review"] for r in rows if r["review"] not in REVIEW_STATES})
    if unknown:
        raise ValueError(
            f"알 수 없는 검토 상태 {unknown} — {', '.join(repr(s) for s in REVIEW_STATES)}만 쓴다"
        )
    return [
        r
        for r in rows
        if r["review"] in REVIEW_PENDING
        or (r["review_required"] == REVIEW_REQUIRED and r["review"] != "확인 완료")
    ]


def main() -> None:
    with RECALLS.open(encoding="utf-8") as f:
        counts = Counter(json.loads(line)["raw_maker"] for line in f if line.strip())
    present = {strict_key(c) for c in counts}
    missing = [r for raws in CURATED_GROUPS.values() for r in raws if strict_key(r) not in present]
    if missing:
        print(f"주의: 이름 목록에 있지만 데이터에 없는 이름 {missing}")
    rows = build_table(counts)
    fields = [
        "raw_maker",
        "maker",
        "maker_group",
        "count",
        "maker_basis",
        "group_basis",
        "review",
        "review_required",
        "review_note",
    ]
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator="\n")
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

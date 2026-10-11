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

- 전수 확인(`--full`): 573 전체 수집이 끝난 완성본(`causes.jsonl`)과 명세(`causes.manifest.json`)로 "추정"이 아니라 확인한 만큼을 센다.
  명세의 파일 sha256·줄 수, 성공+수용한 실패=기대 수, 성공∪실패=기대 목록 지문이 모두 맞아야 하고, **`--baseline`이 필수**다 — 기준 파일에
  고정한 전수 결과의 값(대상 목록·실패 목록·원인 파일·명세 파일 지문)과도 같아야 한다(일부 캠페인만 모은 파일과 그에 맞춘 명세는
  여기서 걸린다. 고정값이 없는 기준 파일이면 멈추고, 대조 없이 재계산만 하려면 `--allow-drift`). 값은 **하한~상한**이다:
  원인 칸이 확인된 채움(최신판 확정)과 기존 방식의 합집합이 하한이고, 확인 불가(읽지 못해 수용한 실패·최신판 미확정)의 리콜을
  모두 "있음"으로 더한 값이 상한이다. 573 보고서가 목록에 없는 리콜은 목록에 없는 이유를 확인하지 못했고(`report_status_unknown`) 두 값 모두 0으로 센다.

    uv run python -m scripts.defect_precedent.why_stats --baseline scripts/defect_precedent/baseline_2026-10-06_maker-aliases.json
    uv run python -m scripts.defect_precedent.why_stats --baseline scripts/defect_precedent/baseline_2026-10-06_maker-aliases.json --full
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
        "rclrpt_sample_stated_unknown": sum(
            r["cause_status"] == "stated_unknown" for r in causes_sample
        ),
        "rclrpt_sample_unresolved": sum(r["resolution"] == "unresolved" for r in causes_sample),
    }
    same_pdfs = {r["campaign"]: r["pdfs"] for r in causes_sample} == {
        s["campaign"]: s["pdfs"] for s in base["rclrpt_sample"]
    }
    # stated_unknown이 없던 옛 기준 파일은 그 상태가 없던 규칙이라 0이다(DEC-047)
    return same_pdfs and all(got[k] == expected.get(k, 0) for k in got)


def full_coverage(
    recalls: list[dict], inv_rows: list[dict], causes: list[dict], failed_campaigns: list[str]
) -> dict:
    """573 완성본으로 센 값 — 확인된 만큼의 **하한**과, 확인 불가를 모두 "있음"으로 쳤을 때의 **상한**.

    확인 상태를 나눈다:
    - 확인된 채움: `cause_status == "filled"`이고 최신판이 확정된(`resolution != "unresolved"`) 캠페인
    - 확인된 비어 있음: 최신판이 확정된 `empty`
    - 573 목록에서 찾지 못함: 원문 목록에도 실패 목록에도 없는 리콜 (보고서가 없다는 뜻이 아니다 — 이유 미확인, `report_status_unknown`)
    - 확인 불가: 읽지 못해 수용한 실패(`failed_campaigns`)와 최신판 미확정(`unresolved`) 캠페인
    하한은 확인 불가를 "없음"으로 센 값이고(= 확인된 근거의 최소), 상한은 확인 불가의 리콜 중 기존 방식 근거가 없는 것을 모두 "있음"으로 더한 값이다.
    """
    campnos = {r["campno"] for r in recalls}
    expressed = {r["campno"] for r in recalls if PATTERN.search(r["defect"])}
    linked = linked_campnos(inv_rows, campnos)
    either = expressed | linked
    post = {r["campno"] for r in recalls if r["received_date"] >= nhtsa.RCLRPT_FROM}
    pre = campnos - post
    by_campaign = defaultdict(list)
    for c in campnos:
        by_campaign[c[:6]].append(c)

    def expand(campaigns) -> set[str]:
        return {c for camp in campaigns for c in by_campaign.get(camp, [])}

    filled = {
        r["campaign"]
        for r in causes
        if r["cause_status"] == "filled" and r["resolution"] != "unresolved"
    }
    unresolved = {r["campaign"] for r in causes if r["resolution"] == "unresolved"}
    post_filled = expand(filled) & post
    post_union = (either & post) | post_filled
    unknown = expand(unresolved | set(failed_campaigns)) & post
    can_add = unknown - post_union
    pre_either = len(either & pre)
    return {
        "recalls": len(campnos),
        "expressed": len(expressed),
        "linked": len(linked),
        "either": len(either),
        "post_recalls": len(post),
        "post_campaigns": len({c[:6] for c in post}),
        "post_either": len(either & post),
        "pre_recalls": len(pre),
        "pre_either": pre_either,
        "causes_rows": len(causes),
        "post_with_report": len(expand({r["campaign"] for r in causes}) & post),
        "unresolved_campaigns": len(unresolved),
        "failed_campaigns": len(set(failed_campaigns)),
        "unknown_recalls": len(unknown),
        "post_filled": len(post_filled),
        "post_union": len(post_union),
        "post_union_upper": len(post_union) + len(can_add),
        "total_union": pre_either + len(post_union),
        "total_union_upper": pre_either + len(post_union) + len(can_add),
    }


def _digest(campaigns) -> str:
    """캠페인 번호 목록의 지문 — `rclrpt.campaigns_digest`·`load_db.campaigns_digest`와 같은 규칙."""
    return hashlib.sha256("\n".join(sorted(campaigns)).encode()).hexdigest()


def verify_causes(causes_path: Path, manifest_path: Path, causes: list[dict]) -> dict:
    """완성본이 수집이 남긴 명세와 같고 대상이 빠짐없이 모였는지 확인한다. 다르면 멈춘다.

    파일 sha256·줄 수·캠페인 중복뿐 아니라, 성공 캠페인과 수용한 실패 캠페인이 겹치지 않고
    둘을 합친 목록이 수집을 시작할 때 기록한 기대 목록(`expected_campaigns_sha256`)·기대 수와 같은지 본다.
    (일부 대상만 모은 파일이 그 파일에 맞는 명세와 함께 와도 통과하지 못한다.)
    """
    if not manifest_path.exists():
        sys.exit(f"{manifest_path.name}이 없다 — 수집(`rclrpt all`)이 끝나야 만들어진다")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("kind") != "full":
        sys.exit(f"{manifest_path.name}의 종류가 full이 아니다")
    if hashlib.sha256(causes_path.read_bytes()).hexdigest() != manifest["file_sha256"]:
        sys.exit(
            f"{causes_path.name}이 {manifest_path.name}의 파일 sha256과 다르다 — 수집 뒤 파일이 바뀌었다"
        )
    campaigns = [r["campaign"] for r in causes]
    if len(causes) != manifest["rows"] or len(set(campaigns)) != len(campaigns):
        sys.exit(f"{causes_path.name}의 줄 수가 명세와 다르거나 캠페인이 겹친다")
    failed = manifest["failed_campaigns"]
    if len(set(failed)) != len(failed) or set(failed) & set(campaigns):
        sys.exit(f"{manifest_path.name}의 실패 캠페인이 겹치거나 완성본에도 들어 있다")
    if len(campaigns) + len(failed) != manifest["expect_campaigns"]:
        sys.exit(
            f"성공 {len(campaigns):,} + 실패 {len(failed):,}이 기대 캠페인 수 {manifest['expect_campaigns']:,}와 다르다 — 전체 수집이 아니다"
        )
    if _digest([*campaigns, *failed]) != manifest["expected_campaigns_sha256"]:
        sys.exit(
            "성공·실패 캠페인을 합친 목록이 수집을 시작할 때의 기대 목록과 다르다 — 빠졌거나 대상이 아닌 캠페인이 있다"
        )
    return manifest


def input_label(
    baseline_name: str,
    base: dict,
    info: dict,
    causes_sample: list[dict] | None,
    allow_drift: bool,
) -> str:
    """기준 파일과 같은 입력인지 확인해 출력용 문구를 만든다. 다르면 멈춘다 (--allow-drift면 재계산으로 표시)."""
    same_files = all(
        info[k] == base["build"][k]
        for k in ("raw_manifest_sha256", "recalls_sha256", "eval_sha256")
    )
    same_sample = causes_sample is None or sample_matches(base, causes_sample)
    if same_files and same_sample:
        if causes_sample is None:
            return f"{baseline_name}와 같은 원본·카드·시험지(sha256 일치)"
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


def full_baseline_check(base: dict, manifest: dict, manifest_sha256: str, allow_drift: bool) -> str:
    """전수 결과가 기준 파일에 고정해 둔 값과 같은지 본다 (대상 목록·실패 목록·원인 파일·명세 파일 지문, 줄 수).

    명세는 수집 프로그램이 스스로 기록한 값이라 명세 안의 숫자끼리 맞는 것만으로는 일부 캠페인만 모은 파일을 걸러내지 못한다.
    기준 파일에 따로 고정한 값과 비교해야 그런 파일이 통과하지 못한다. 다르면 멈춘다(--allow-drift면 재계산으로 표시).
    """
    spec = base.get("causes_full")
    if not spec:
        if allow_drift:
            return "기준 파일에 전수 결과의 고정값이 없어 대조하지 않고 재계산 (재현 아님)"
        sys.exit(
            "기준 파일에 전수 결과의 고정값(causes_full)이 없다 — 전체 수집이 맞는지 독립적으로 대조할 수 없다. "
            "고정값이 있는 기준 파일을 쓰거나, 대조 없이 재계산만 하려면 --allow-drift를 붙인다"
        )
    got = {
        "rows": manifest["rows"],
        "failures": manifest["failures"],
        "expect_campaigns": manifest["expect_campaigns"],
        "causes_sha256": manifest["file_sha256"],
        "expected_campaigns_sha256": manifest["expected_campaigns_sha256"],
        "failed_campaigns_sha256": _digest(manifest["failed_campaigns"]),
        "manifest_sha256": manifest_sha256,
    }
    different = [k for k, v in got.items() if v != spec.get(k)]
    if not different:
        return "기준 파일의 고정값과 일치 (대상 목록·실패 목록·원인 파일·명세 파일)"
    if allow_drift:
        return f"기준과 다른 전수 결과로 재계산 (다른 항목: {', '.join(different)})"
    sys.exit(
        f"전수 결과가 기준 파일의 고정값과 다르다 ({', '.join(different)}) — 같은 완성본·명세로 다시 만들거나, "
        "현재 결과로 재계산만 하려면 --allow-drift를 붙인다"
    )


def main_full(baseline: Path | None = None, allow_drift: bool = False) -> None:
    """573 완성본 기준의 확인된 값(하한)과 상한. 추정이 아니라 확인한 만큼만 센다."""
    if baseline is None:  # 어떤 파일을 읽기 전에 먼저 막는다
        sys.exit(
            "--full은 --baseline이 필요하다 — 기준 파일에 고정한 전수 결과의 값과 대조하지 않으면 "
            "일부만 수집한 자료도 전수 집계로 계산된다"
        )
    recalls = read_jsonl(nhtsa.OUT_DIR / "recalls.jsonl")
    causes_path = nhtsa.OUT_DIR / "causes.jsonl"
    if not causes_path.exists():
        sys.exit("causes.jsonl이 없다 — 573 전체 수집(`rclrpt all`)을 끝낸 뒤에 쓴다")
    causes = read_jsonl(causes_path)
    manifest_path = nhtsa.OUT_DIR / "causes.manifest.json"
    manifest = verify_causes(causes_path, manifest_path, causes)
    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    base = json.loads(baseline.read_text(encoding="utf-8"))
    label = input_label(baseline.name, base, nhtsa.verify_build(), None, allow_drift)
    full_check = full_baseline_check(base, manifest, manifest_sha256, allow_drift)
    s = full_coverage(
        recalls,
        nhtsa.read_flat(nhtsa.RAW_DIR / "FLAT_INV.zip", nhtsa.INV_COLS),
        causes,
        manifest["failed_campaigns"],
    )
    if s["post_recalls"] != s["post_campaigns"]:
        sys.exit(
            f"2014-08-20 이후 리콜 {s['post_recalls']:,}건이 캠페인 {s['post_campaigns']:,}개에 걸려 있다 — 573은 캠페인 단위라 "
            "리콜 건수와 단위가 섞인다. 캠페인 단위로 다시 정의한 뒤에 계산한다"
        )
    total = s["recalls"]

    def pct(x: float, whole: float) -> str:
        return f"{x:,.0f}건 ({x / whole:.1%})"

    post = s["post_recalls"]
    no_report = post - s["post_with_report"] - s["failed_campaigns"]
    unknown = s["unresolved_campaigns"] + s["failed_campaigns"]
    print(f"입력: {label}")
    print(f"573 전수 결과: {full_check}")
    print(
        f"573 완성본: {s['causes_rows']:,}줄 (원인 파일 sha256 {manifest['file_sha256'][:12]}…이 명세 기록과 일치, "
        f"명세 파일 sha256 {manifest_sha256[:12]}…, "
        f"성공 {s['causes_rows']:,} + 수용한 실패 {manifest['failures']} = 기대 {manifest['expect_campaigns']:,})"
    )
    print(f"전체 리콜 {total:,}건")
    print(f"  결함문 원인 표현   {pct(s['expressed'], total)}")
    print(f"  조사 요약 연결     {pct(s['linked'], total)}")
    print(f"  둘 중 하나         {pct(s['either'], total)}")
    print(f"2014-08-20 이후 {post:,}건 (캠페인 {s['post_campaigns']:,}개와 1:1)")
    print(f"  기존 방식              {pct(s['post_either'], post)}")
    print(f"  573 원인 칸 채워짐     {pct(s['post_filled'], post)}  (확인된 것만)")
    print(
        f"  확인 불가              {s['unknown_recalls']}건 = 읽지 못해 수용한 실패 {s['failed_campaigns']} + 최신판 미확정 "
        f"{s['unresolved_campaigns']} (합 {unknown}캠페인)"
    )
    print(f"  573 목록·실패 목록에서 찾지 못함 {no_report}건 (이유 미확인)")
    print(
        f"  둘 중 하나             하한 {pct(s['post_union'], post)} ~ 상한 {pct(s['post_union_upper'], post)}"
    )
    print(
        f"2014-08-20 이전 {s['pre_recalls']:,}건 중 기존 방식 {pct(s['pre_either'], s['pre_recalls'])}"
    )
    print(
        f"전체 {total:,}건 중 원인 근거 있음 하한 {pct(s['total_union'], total)} ~ 상한 {pct(s['total_union_upper'], total)}"
        ' — 확인 불가를 모두 "없음"으로 센 값이 하한, 모두 "있음"으로 센 값이 상한'
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
        "--full",
        action="store_true",
        help="573 완성본(causes.jsonl)과 명세로 추정이 아닌 확인값(하한~상한)을 낸다",
    )
    parser.add_argument(
        "--allow-drift",
        action="store_true",
        help="입력이 기준과 달라도 현재 데이터로 재계산한다 (--baseline과 함께)",
    )
    args = parser.parse_args()
    if args.baseline is not None and not args.baseline.exists():
        parser.error(f"기준 파일이 없다: {args.baseline}")
    if args.full and args.baseline is None:
        parser.error(
            "--full은 --baseline과 함께 쓴다 (기준 파일에 고정한 전수 결과의 값과 대조한다)"
        )
    if args.allow_drift and args.baseline is None:
        parser.error("--allow-drift는 --baseline과 함께 쓴다")
    (main_full if args.full else main)(args.baseline, args.allow_drift)

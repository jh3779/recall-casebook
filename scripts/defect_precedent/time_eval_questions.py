"""시점 평가 질문을 조사 개시 당시 문서(ODI Resume, 파일명 `INOA-…`)에서 옮긴다 (이슈 #38, 기획 6절 시점 평가).

사용법:
    uv run python -m scripts.defect_precedent.time_eval_questions --write   # 문서를 받아 질문을 뽑고 파일로 쓴다
    uv run python -m scripts.defect_precedent.time_eval_questions --check   # 파일의 해시·질문이 지금 PDF와 같은지 다시 확인한다

흐름 (추첨 목록 `time_eval_draw.json`을 입력으로 쓴다):
1. 조사마다 static.nhtsa.gov의 목록 조회(`?list-type=2&prefix=odi/inv/<연도>/INOA-<조사번호>-`)로 개시 문서 주소를 찾는다.
   문서가 없으면 건너뛰고 대체 목록(`reserve`)의 앞에서부터 차례로 채운다. 문서는 한 개여야 한다.
   글자를 뽑을 수 없는 문서(2010년 이전 개시 문서는 대부분 스캔한 이미지라 글자 정보가 없다, 개시 문서가 아닌 편지 등)도
   같은 이유로 건너뛴다 — OCR은 원문 그대로라고 보장할 수 없어 쓰지 않는다. 대체 목록을 다 쓰면 같은 해시 순위로 이어서 채운다.
2. PDF를 받아 sha256을 잰다 (원본은 커밋하지 않는다: data/raw/time_eval_docs/).
   기준일 당시 판본이라는 근거로 PDF 안에 적힌 수정일(ModDate)을 기록하고, 개시일보다 3일 넘게 늦거나 없으면 쓰지 않는다.
   질문 본문에 개시일보다 늦은 날짜가 나와도 쓰지 않는다 ("판본 근거 부족", 다른 건너뜀과 같이 대체 목록으로 채움).
   이 기준은 DEC-037 ⑥에서 팀이 정했다. 파일 서버의 수정 시각은 2022-02-28 일괄 이전 날짜라 근거가 못 된다.
   한계: ModDate는 파일 안의 기록이라 공개 시점을 증명하지는 못한다 - 그래서 결과는 "개시 문서 기준 근사 시점 평가"로만 보고한다.
3. `pdftotext -raw`로 텍스트를 뽑아 `Summary:` 뒤의 요약을 질문으로 옮긴다. AI가 요약하거나 고치지 않는다.
   쪽을 넘는 문서에는 쪽 머리글(`Resume Page 2 of 2` 등)이 요약 사이에 끼므로 그 줄만 뺀다. 단어는 바꾸지 않는다.
4. 줄바꿈·여러 칸 공백을 한 칸으로 바꾼 상태로, 옮긴 질문이 문서 텍스트 안에 그대로 들어 있는지 대조한다
   (`Date Opened`가 시험지의 개시일과 같은지도 본다). 실패하면 고치지 않고 실패로 표시한다.

평가표에는 조사마다 action_no, open_date, query_source(= ODI Resume), 파일 주소, PDF sha256, 대조 결과를 남긴다.
"""

import hashlib
import json
import re
import subprocess
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

from scripts.defect_precedent.time_eval_draw import rank

REPO_ROOT = Path(__file__).resolve().parents[2]
DRAW = Path(__file__).resolve().parent / "time_eval_draw.json"
OUT = Path(__file__).resolve().parent / "time_eval_questions.json"
DOC_DIR = REPO_ROOT / "data" / "raw" / "time_eval_docs"
HOST = "https://static.nhtsa.gov"
MAX_BYTES = 20_000_000
QUERY_SOURCE = "ODI Resume"
# 질문은 정부 공개 문서 원문이라 서비스 원칙 검사가 찾는 판정 낱말과 철자가 같은 일반 영어 낱말이 들어 있을 수 있다 — 질문 줄마다 정당한 사용 표시를 단다
QUESTION_NOTE = "principle-ok: 정부 공개 문서(ODI Resume) 원문 그대로 인용한 영어 문장"

# 요약 사이에 끼는 쪽 머리글 줄 (줄 전체가 이 모양일 때만 뺀다)
SKIP = ("문서 없음", "추출 불가", "판본 근거 부족")  # 이 상태면 건너뛰고 대체 목록으로 채운다
# 파일 서버의 수정 시각은 2022-02-28 일괄 이전 날짜라 공개 시점의 증거가 못 된다. 대신 PDF 안에 적힌 수정일(ModDate)이 개시일에서
# 이 일수 안이면 "개시 직후 만든 판본에서 나중에 고치지 않았다"는 근거로 본다. 수정일이 없거나 이보다 늦으면 쓰지 않는다 (DEC-037 ⑥)
MOD_GAP_MAX_DAYS = 3
BASIS = "개시 문서 기준 근사 시점 평가 - PDF 수정일이 개시일 + 3일 이내, 질문 본문에 개시일보다 늦은 날짜 없음 (DEC-037 ⑥). 공개 시점의 증명은 아니다"
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
MONTH_NO = {m: i for i, m in enumerate(MONTHS.split("|"), 1)}
HEADER_LINES = [
    re.compile(r"ODI RESUME"),
    re.compile(r"Resume Page \d+ of \d+"),
    re.compile(r"Investigation: [A-Z]{2} ?\d{2}-?\d{3}( Open)?( Resume Page \d+ of \d+)?"),
    re.compile(r"Investigation: [A-Z]{2}\d{5} (Open|Close) Resume Page \d+ of \d+"),
    # 첨부 쪽 머리글: `EA18-004 opening resume Page 2`, `NHTSA Office of Defects Investigation, Opening Resume Attachment`,
    # `Engineering Analysis Open Resume Attachment Page 1 of 2`
    re.compile(
        r"(?:[A-Z]{2} ?\d{2}-?\d{3} )?(?:NHTSA Office of Defects Investigation, )?"
        r"(?:(?:Engineering Analysis|Preliminary Evaluation|Defect Petition|Recall Query|Audit Query) )?"
        r"(?:Opening|Open) Resume(?: Attachment)?(?: Page \d+(?: of \d+)?)?",
        re.IGNORECASE,
    ),
    re.compile(r"Page \d+ of \d+"),
]
# 머리글을 뺀 뒤에도 이런 흔적이 질문에 남으면 고치지 않고 실패로 표시한다 (판별 규칙이 모르는 꼴이 있다는 신호)
LEFTOVER_HEADER = re.compile(
    r"Resume Page|Resume Attachment|[A-Z]{2} ?\d{2}-?\d{3} (?:Open|Opening) Resume|\bPage \d+ of \d+\b",
    re.IGNORECASE,
)


def draw_digest() -> str:
    """추첨 파일의 해시. 저장소는 LF, Windows 체크아웃은 CRLF라서 줄바꿈을 LF로 맞춘 뒤 잰다."""
    return hashlib.sha256(DRAW.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def dumps(result: dict) -> str:
    """결과를 JSON 글로 만든다. 질문 줄마다 같은 줄에 `principle-ok:` 표시를 단다 (질문 글자는 바꾸지 않는다)."""
    text = json.dumps(result, ensure_ascii=False, indent=1)
    marked = re.sub(
        r'^(\s*"question": .*),$',
        lambda m: f'{m.group(1)}, "question_note": "{QUESTION_NOTE}",',
        text,
        flags=re.M,
    )
    return marked + "\n"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def is_header(line: str) -> bool:
    return any(p.fullmatch(line.strip()) for p in HEADER_LINES)


def extract(text: str, open_date: str) -> dict:
    """문서 텍스트에서 개시일·질문을 뽑고 원문 대조 결과를 돌려준다. 질문을 고치거나 요약하지 않는다."""
    m = re.search(r"Date Opened:\s*(\d{2})/(\d{2})/(\d{4})", text)
    doc_date = f"{m.group(3)}{m.group(1)}{m.group(2)}" if m else None
    lines = text.splitlines()
    start = next((i for i, ln in enumerate(lines) if ln.strip().startswith("Summary:")), None)
    result = {
        "doc_date_opened": doc_date,
        "question": None,
        "removed_header_lines": 0,
        "hyphen_line_breaks": 0,
    }
    problems = []
    if doc_date is None:
        problems.append("문서에서 Date Opened를 찾지 못함")
    elif doc_date != open_date:
        problems.append(f"개시일 불일치(문서 {doc_date} ≠ 시험지 {open_date})")
    if start is None:
        problems.append("Summary: 를 찾지 못함")
    else:
        first = lines[start].strip()[len("Summary:") :].strip()
        body = ([first] if first else []) + [ln.strip() for ln in lines[start + 1 :]]
        kept, removed = [], 0
        for ln in body:
            if not ln:
                continue
            if is_header(ln):
                removed += 1
            else:
                kept.append(ln)
        question = norm(" ".join(kept))
        reference = norm(" ".join(ln.strip() for ln in lines if ln.strip() and not is_header(ln)))
        result.update(
            question=question,
            removed_header_lines=removed,
            hyphen_line_breaks=sum(1 for ln in kept if ln.endswith("-") and not ln.endswith("--")),
        )
        if not question:
            problems.append("요약이 비어 있음")
        elif question not in reference:
            problems.append("옮긴 질문이 문서 텍스트에 그대로 들어 있지 않음")
        elif LEFTOVER_HEADER.search(question):
            problems.append("쪽 머리글로 보이는 문구가 질문에 남음 — 머리글 판별 규칙 확인 필요")
    result["extractable"] = (
        doc_date is not None
    )  # 개시 문서에는 Date Opened가 있다 — 없으면 글자가 없거나 개시 문서 양식이 아니다(편지 등)
    result["check"] = "통과" if not problems else "실패: " + "; ".join(problems)
    return result


def find_opening_resume(action_no: str) -> list[str]:
    """목록 조회로 개시 문서(INOA) 파일 키를 찾는다. 0개면 문서 없음, 2개 이상이면 사람이 확인해야 한다."""
    year = 2000 + int(action_no[2:4])
    prefix = f"odi/inv/{year}/INOA-{action_no}-"
    with urllib.request.urlopen(f"{HOST}/?list-type=2&prefix={prefix}", timeout=30) as r:
        body = r.read().decode("utf-8")
    keys = re.findall(r"<Key>([^<]+)</Key>", body)
    return [
        k
        for k in keys
        if re.fullmatch(rf"odi/inv/{year}/INOA-{action_no}-\d+\.pdf", k, re.IGNORECASE)
    ]


def download(key: str) -> bytes:
    with urllib.request.urlopen(f"{HOST}/{key}", timeout=60) as r:
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"{key}: 파일이 {MAX_BYTES:,}바이트보다 크다")
    if not data.startswith(b"%PDF"):
        raise ValueError(f"{key}: PDF가 아니다")
    return data


def pdf_text(path: Path) -> str:
    out = subprocess.run(
        ["pdftotext", "-raw", str(path), "-"], capture_output=True, check=True, timeout=120
    )
    return out.stdout.decode("utf-8", errors="replace")


def later_dates(question: str, open_date: str) -> list[str]:
    """질문 본문에 나오는 날짜 중 개시일보다 늦은 것 (YYYYMMDD 또는 월만 아는 날짜는 YYYYMM). 모르는 꼴의 날짜는 잡지 못한다."""
    found = []
    # 완전한 날짜를 먼저 찾고 그 글자를 지운 뒤에 월만 아는 날짜를 찾는다 (같은 날짜가 두 번 잡히지 않게)
    for mo, d, y in re.findall(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", question):
        found.append(f"{int(y):04d}{int(mo):02d}{int(d):02d}")
    question = re.sub(r"\b\d{1,2}/\d{1,2}/\d{4}\b", " ", question)
    for mo, d, y in re.findall(rf"\b({MONTHS})\.? (\d{{1,2}}),? (\d{{4}})\b", question):
        found.append(f"{int(y):04d}{MONTH_NO[mo]:02d}{int(d):02d}")
    for d, mo, y in re.findall(rf"\b(\d{{1,2}}) ({MONTHS}),? (\d{{4}})\b", question):
        found.append(f"{int(y):04d}{MONTH_NO[mo]:02d}{int(d):02d}")
    question = re.sub(
        rf"\b({MONTHS})\.? \d{{1,2}},? \d{{4}}\b|\b\d{{1,2}} ({MONTHS}),? \d{{4}}\b", " ", question
    )
    for mo, y in re.findall(rf"\b({MONTHS}),? (\d{{4}})\b", question):
        found.append(f"{int(y):04d}{MONTH_NO[mo]:02d}")
    return sorted({d for d in found if d > open_date[: len(d)]})


def pdf_mod_date(path: Path) -> str | None:
    """PDF 안에 적힌 수정일(`pdfinfo`의 ModDate)을 YYYYMMDD로. 없거나 읽을 수 없으면 None."""
    out = subprocess.run(["pdfinfo", str(path)], capture_output=True, timeout=60).stdout
    m = re.search(
        r"ModDate:\s*\w{3} (\w{3})\s+(\d+) \d\d:\d\d:\d\d (\d{4})", out.decode("latin-1", "replace")
    )
    if not m:
        return None
    try:
        return datetime.strptime(f"{m.group(1)} {m.group(2)} {m.group(3)}", "%b %d %Y").strftime(
            "%Y%m%d"
        )
    except ValueError:
        return None


def mod_gap_days(mod_date: str | None, open_date: str) -> int | None:
    if mod_date is None:
        return None
    return (datetime.strptime(mod_date, "%Y%m%d") - datetime.strptime(open_date, "%Y%m%d")).days


def build_record(
    action_no: str,
    open_date: str,
    finder=find_opening_resume,
    fetch=download,
    text_of=pdf_text,
    mod_of=pdf_mod_date,
) -> dict:
    """조사 1건의 문서를 받아 질문과 대조 결과를 만든다. 문서가 없으면 status만 `문서 없음`으로 돌려준다."""
    keys = finder(action_no)
    if not keys:
        return {"action_no": action_no, "open_date": open_date, "status": "문서 없음"}
    if len(keys) > 1:
        return {
            "action_no": action_no,
            "open_date": open_date,
            "status": "문서 여러 개",
            "keys": keys,
        }
    key = keys[0]
    data = fetch(key)
    path = DOC_DIR / action_no / Path(key).name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    got = extract(text_of(path), open_date)
    if not got.pop("extractable"):
        return {
            "action_no": action_no,
            "open_date": open_date,
            "status": "추출 불가",
            "source_url": f"{HOST}/{key}",
            "pdf_sha256": hashlib.sha256(data).hexdigest(),
        }
    mod = mod_of(path)
    gap = mod_gap_days(mod, open_date)
    evidence = {"pdf_mod_date": mod, "pdf_mod_gap_days": gap}
    base = {
        "action_no": action_no,
        "open_date": open_date,
        "source_url": f"{HOST}/{key}",
        "pdf_sha256": hashlib.sha256(data).hexdigest(),
        **evidence,
    }
    if gap is None or gap > MOD_GAP_MAX_DAYS:
        return {
            **base,
            "status": "판본 근거 부족",
        }  # 개시 이후에 고쳐졌을 수 있어 기준일 당시 판본이라고 말할 수 없다
    later = later_dates(got["question"] or "", open_date)
    if later:
        return {
            **base,
            "status": "판본 근거 부족",
            "later_dates_in_text": later,
        }  # 개시일 뒤의 일이 본문에 나온다
    return {**base, "query_source": QUERY_SOURCE, "status": "확보", **got}


def fill(draw: dict, make=build_record) -> dict:
    """예비·본 평가 자리를 채운다. 문서가 없거나 글자를 뽑을 수 없는 조사는 건너뛰고 대체 목록의 앞에서부터 차례로 채운다 (예비 먼저).

    대체 목록은 `reserve` 30개 뒤에 같은 해시 순위로 남은 후보를 이어 붙인 것이다 (내용을 보고 고르지 않는다).
    """
    drawn = {r["action_no"] for r in draw["pilot"] + draw["main"] + draw["reserve"]}
    rest = sorted(
        (a for a, _ in draw["pool"] if a not in drawn), key=lambda a: rank(a, draw["seed"])
    )
    dates = dict(draw["pool"])
    reserve = [dict(r) for r in draw["reserve"]] + [
        {"action_no": a, "open_date": dates[a]} for a in rest
    ]
    out, replaced = {"pilot": [], "main": []}, []
    for name, size in (("pilot", draw["pilot"]), ("main", draw["main"])):
        for row in size:
            rec = make(row["action_no"], row["open_date"])
            skipped = row["action_no"]
            while rec["status"] in SKIP:
                if not reserve:
                    raise ValueError("대체 목록을 다 썼다")
                nxt = reserve.pop(0)
                replaced.append(
                    {
                        "skipped": skipped,
                        "reason": rec["status"],
                        "replaced_by": nxt["action_no"],
                        "slot": name,
                    }
                )
                skipped = nxt["action_no"]
                rec = make(nxt["action_no"], nxt["open_date"])
            out[name].append(rec)
    return {"pilot": out["pilot"], "main": out["main"], "replacements": replaced}


def build() -> dict:
    draw = json.loads(DRAW.read_text(encoding="utf-8"))
    filled = fill(draw)
    records = filled["pilot"] + filled["main"]
    return {
        "draw_sha256": draw_digest(),
        "draw_seed": draw["seed"],
        "query_source": QUERY_SOURCE,
        "basis": BASIS,
        "counts": {
            "pilot": len(filled["pilot"]),
            "main": len(filled["main"]),
            "check_passed": sum(1 for r in records if r["check"] == "통과"),
            "check_failed": sum(1 for r in records if r["check"] != "통과"),
            "replacements": len(filled["replacements"]),
        },
        **filled,
    }


def main() -> None:
    if sys.argv[1:] not in (["--write"], ["--check"]):
        sys.exit(
            "사용법: uv run python -m scripts.defect_precedent.time_eval_questions {--write|--check}"
        )
    result = build()
    text = dumps(result)
    if sys.argv[1:] == ["--check"]:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != text:
            sys.exit(f"{OUT.name}이 지금 받은 문서·규칙으로 만든 결과와 다르다")
        print(f"일치: {OUT.name} {result['counts']}")
        return
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"{OUT.name}에 썼다 {result['counts']}")


if __name__ == "__main__":
    main()

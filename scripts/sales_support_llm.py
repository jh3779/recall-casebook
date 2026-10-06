"""영업·지원 도메인 생성 단계 테스트 — 검색 상위 청크 → gpt-4o-mini 체크리스트 → 코드 검증.

기획v1 5절 ⑤⑥⑦을 FAQ 질문으로 돌려 **구조 준수·근거 검증·판정 표현** 같은 자동 지표만 잰다.
FAQ 질문은 "새 업무를 맡은 사람"의 상황이 아니므로 체크리스트 품질은 판단하지 않는다(합성 질문 세트 뒤에 평가).

유료 API(OpenAI)를 부른다 — 호출 수·비용은 실행 전에 출력하고, 예산($)을 넘으면 중단한다(AGENTS.md 7절).
키는 환경변수 `OPENAI_API_KEY`로만 읽는다(`.env`를 읽지 않는다).

사용법 (색인은 sales_support_poc.py의 `index`로 먼저 만든다):
    uv run python -m scripts.sales_support_llm --limit 30                # 계획만 출력 (호출 없음)
    uv run python -m scripts.sales_support_llm --limit 30 --run          # 표본 30개로 실제 호출
    uv run python -m scripts.sales_support_llm --limit 0 --run --retrieval hybrid  # 전체
"""

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from scripts import sales_support_poc as poc

MODEL = "gpt-4o-mini"
# OpenAI 공식 모델 페이지(gpt-4o-mini) 기준 100만 토큰당 가격($). 실제 청구액은 대시보드로 확인한다.
PRICE_INPUT_PER_M = 0.15
PRICE_OUTPUT_PER_M = 0.60
PRICE_CHECKED_ON = "2026-10-05 (OpenAI 모델 페이지 gpt-4o-mini)"
# 요약에 항상 붙이는 해석 주의 — 이 값은 "근거 품질"이 아니다
QUOTE_FOUND_NOTE = (
    "items_quote_found*는 evidence_quote가 해당 청크 안에 실제로 있는지만 확인한 값이다. "
    "item·reason이 인용문의 주장을 뒷받침하는지는 확인하지 않으므로 사람 표본 평가로 따로 측정해야 한다."
)
TOP_K_CHUNKS = 5
MAX_CHUNK_CHARS_IN_PROMPT = 2000
MAX_OUTPUT_TOKENS = 1200
MAX_QUESTION_CHARS = 1000  # 외부 질문 파일의 비정상적으로 긴 질문이 비용을 키우지 못하게 막는다
DEFAULT_BUDGET_USD = 1.0
# 호출 전 추정(여유 포함): 입력 2,500토큰·출력 600토큰 (청크 평균 731자 × 5 + 지시문)
EST_INPUT_TOKENS = 2500
EST_OUTPUT_TOKENS = 600

PROMPT_VERSION = "v2"  # v1(지시문 해시 PROMPT_V1_SHA)은 인용문 제거 34건 중 88%가 대소문자·구두점·마크다운 차이였다
PROMPT_V1_SHA = "d178413ddcdb3fb3"

# 서비스 원칙 — 판정하지 않는다(AGENTS.md 2절 1항). 후보 항목과 근거만 낸다.
INSTRUCTIONS = (
    "You prepare onboarding checklist candidates for a new employee from numbered excerpts of the "
    "GitLab handbook. Use ONLY the excerpts. "
    "For each candidate give: item (what to do), reason (why, based on the excerpt), "
    "criteria (the condition stated in the excerpt that separates when it matters, or null if the "
    "excerpt states none), check_method (how to confirm it is done, as stated in the excerpt, or null), "
    "chunk_no (the excerpt number), evidence_quote (an exact contiguous quote copied "
    "character-for-character from that excerpt that supports the item; keep the original capitalization, "
    "punctuation, spacing and any markdown such as link syntax or bold markers, and do not paraphrase). "
    "criteria and check_method must each be copied verbatim from your evidence_quote (a contiguous part of "
    "it) or be null; never rewrite them in your own words. "
    "Do not decide whether anything applies to the user. Do not invent conditions, deadlines, tools or "  # principle-ok: 판정을 하지 말라는 지시문(출력 문구가 아님)
    "names that are not in the excerpt. If the excerpts contain nothing relevant, return an empty list. "
    "Write in English."
)

_ITEM_PROPS = {
    "item": {"type": "string"},
    "reason": {"type": "string"},
    "criteria": {"type": ["string", "null"]},
    "check_method": {"type": ["string", "null"]},
    "chunk_no": {"type": "integer"},
    "evidence_quote": {"type": "string"},
}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": _ITEM_PROPS,
                "required": list(_ITEM_PROPS),
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}

# 판정으로 읽히는 영어 표현 — 출력에 나오는 횟수만 센다(제거하지 않는다)
JUDGMENT_PHRASES = (
    "applies to you",  # principle-ok: 출력에서 판정 표현을 검출하기 위한 금지어 목록
    "does not apply",
    "do not apply",
    "not applicable",
    "is applicable",
    "you are eligible",
    "you are not eligible",
)


def require_pinned_data(index_meta: dict) -> None:
    """수정된 핸드북(고정 스냅샷과 지문이 다른 데이터)으로는 생성 실행을 하지 않는다.

    수정된 데이터는 공식 커밋으로 복원할 수 없어, 실행 기록에 해시만 남으면 나중에 모델이 본 원문을 확인할 수 없다.
    """
    if index_meta.get("data_status") != "matches_pinned_snapshot":
        sys.exit(
            "색인이 고정 스냅샷과 같은 데이터가 아닙니다(data_status="
            f"{index_meta.get('data_status')!r}). 수정된 원문으로 만든 생성 실행은 나중에 모델이 본 원문을 "
            "복원할 수 없어 거부합니다. 공식 스냅샷 데이터로 `index`를 다시 만든 뒤 실행하세요."
        )


def positive_budget(text: str) -> float:
    """비용 상한 인자 — 0 이하·NaN·무한대는 거부한다."""
    import argparse
    import math

    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"숫자가 아닙니다: {text}") from None
    if not math.isfinite(value) or value <= 0:
        raise argparse.ArgumentTypeError(f"비용 상한은 0보다 큰 유한한 숫자여야 합니다: {text}")
    return value


def cost_usd(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * PRICE_INPUT_PER_M / 1e6 + output_tokens * PRICE_OUTPUT_PER_M / 1e6


def build_prompt(question: str, chunks: list[poc.Chunk]) -> str:
    parts = [f"Question: {question}", "", "Excerpts:"]
    for n, c in enumerate(chunks, start=1):
        heading = c.heading_path.replace(">", " > ") or "(intro)"
        parts.append(f"[{n}] {heading}\n{c.chunk_text[:MAX_CHUNK_CHARS_IN_PROMPT]}")
    return "\n\n".join(parts)


def strip_markdown(text: str) -> str:
    """인용 불일치 원인 분류용 — 링크·강조·코드·표 기호를 걷어 낸다."""
    import re

    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"[*`]", "", text)  # 강조·코드 기호는 글자에 붙어 있으므로 공백 없이 지운다
    text = re.sub(r"[|>]", " ", text)
    return re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)


def diagnose_quote(quote: str, chunk_text: str) -> str:
    """청크에 그대로 없던 인용문이 왜 안 맞는지 분류한다 (측정용, 판정에는 쓰지 않는다).

    found / markdown_stripped(마크다운을 걷어 내면 일치) / case_or_punctuation(대소문자·구두점만 다름) /
    mostly_overlapping_reworded(단어 80% 이상이 겹치는데 말이 바뀜) / not_in_text(청크에 없는 내용).
    """
    import re

    q, c = poc.collapse_whitespace(quote), poc.collapse_whitespace(chunk_text)
    if q in c:
        return "found"
    if q in poc.collapse_whitespace(strip_markdown(chunk_text)):
        return "markdown_stripped"

    def norm(t: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()

    if norm(q) in norm(chunk_text) or norm(q) in norm(strip_markdown(chunk_text)):
        return "case_or_punctuation"
    q_tokens, c_tokens = set(norm(q).split()), set(norm(chunk_text).split())
    if q_tokens and len(q_tokens & c_tokens) / len(q_tokens) >= 0.8:
        return "mostly_overlapping_reworded"
    return "not_in_text"


MIN_TRIMMED_QUOTE_CHARS = 12  # 경계 정리 뒤 이보다 짧으면 아무 데나 맞을 수 있어 인정하지 않는다
FLAG_KEYS = (
    "criteria_outside_quote",
    "check_method_outside_quote",
    "judgment_wording",
    "quote_boundary_adjusted",
)
_QUOTE_CHARS = "\"'\u201c\u201d\u2018\u2019"


def trim_quote_boundaries(quote: str) -> str:
    """인용문 **양 끝**의 경계 문자만 정리한다 — 목록 기호(`- `·`* `·`1. `), 감싼 따옴표, 줄임표, 끝 구두점.

    가운데의 글자·대소문자·구두점은 건드리지 않는다 (DEC-028).
    """
    import re

    q = poc.collapse_whitespace(quote)
    for _ in range(3):  # 겹겹이 감싼 경우(예: `- "..."`)를 위해 몇 번 반복
        before = q
        q = re.sub(r"^(?:[-*\u2022]\s+|\d+[.)]\s+)", "", q)
        q = q.lstrip(_QUOTE_CHARS + "\u2026 ")
        q = re.sub(r"^\.{3,}\s*", "", q)
        q = re.sub(r"\s*\.{3,}$", "", q)
        q = q.rstrip(_QUOTE_CHARS + "\u2026 ")
        q = re.sub(r"[\s.,;:!?\u2014\u2013-]+$", "", q)
        if q == before:
            break
    return q.strip()


def locate_quote(quote: str, visible_collapsed: str) -> str | None:
    """모델이 낸 인용문을 원문(공백 정리한 보낸 구간)에서 찾아 **원문의 정확한 구간**을 돌려준다. 없으면 None.

    1) 그대로(공백 정리만) 있으면 그 구간, 2) 아니면 양 끝 경계 문자만 정리해 다시 찾는다(가운데는 정확히 같아야 하고,
    정리 뒤 MIN_TRIMMED_QUOTE_CHARS자 미만이면 거부). 대소문자는 구분한다.
    """
    exact = poc.collapse_whitespace(quote)
    if exact and exact in visible_collapsed:
        return exact
    trimmed = trim_quote_boundaries(quote)
    if len(trimmed) >= MIN_TRIMMED_QUOTE_CHARS and trimmed in visible_collapsed:
        return trimmed
    return None


def validate_items(
    items: list[dict], shown: list[poc.Chunk], removed_log: list[dict] | None = None
) -> tuple[list[dict], dict[str, int], dict[str, int]]:
    """모델 항목을 코드로 검증한다 (기획v1 5절 ⑦). 통과 항목, 제거 사유별 개수, 경고 개수를 돌려준다.

    제거: 필수 문자열 비어 있음 / 청크 번호가 범위 밖 / evidence_quote가 모델에게 보낸 청크 범위(앞 MAX_CHUNK_CHARS_IN_PROMPT자) 안에 없음(공백 정리 기준).
    `source`·`domains`·`commit_sha`는 모델이 아니라 검증된 청크에서 코드가 채운다.
    경고(제거하지 않고 센다): criteria·check_method가 evidence_quote 밖 글을 쓴 경우, 판정으로 읽히는 표현.
    """
    valid: list[dict] = []
    removed: dict[str, int] = {}
    flags = dict.fromkeys(FLAG_KEYS, 0)

    def drop(reason: str, it: dict | None = None, chunk: poc.Chunk | None = None) -> None:
        removed[reason] = removed.get(reason, 0) + 1
        if removed_log is not None and it is not None:
            removed_log.append(
                {
                    "reason": reason,
                    "chunk_no": it.get("chunk_no"),
                    "chunk_key": chunk.chunk_key if chunk else None,
                    "item": str(it.get("item"))[:200],
                    "evidence_quote": str(it.get("evidence_quote"))[:500],
                    "diagnosis": diagnose_quote(
                        str(it.get("evidence_quote") or ""), chunk.chunk_text
                    )
                    if chunk and reason in ("quote_not_in_chunk", "quote_outside_shown_text")
                    else None,
                }
            )

    for it in items:
        if not all(
            isinstance(it.get(k), str) and it[k].strip()
            for k in ("item", "reason", "evidence_quote")
        ):
            drop("empty_field")
            continue
        n = it.get("chunk_no")
        if not isinstance(n, int) or not 1 <= n <= len(shown):
            drop("bad_chunk_no")
            continue
        chunk = shown[n - 1]
        visible = poc.collapse_whitespace(chunk.chunk_text[:MAX_CHUNK_CHARS_IN_PROMPT])
        quote = locate_quote(it["evidence_quote"], visible)
        if quote is None:
            # 모델에게 보내지 않은 뒷부분에만 있으면 인용 확인으로 세지 않는다
            beyond = locate_quote(it["evidence_quote"], poc.collapse_whitespace(chunk.chunk_text))
            drop("quote_outside_shown_text" if beyond else "quote_not_in_chunk", it, chunk)
            continue
        adjusted = quote != poc.collapse_whitespace(it["evidence_quote"])
        if adjusted:
            flags["quote_boundary_adjusted"] += 1
        for key, flag in (
            ("criteria", "criteria_outside_quote"),
            ("check_method", "check_method_outside_quote"),
        ):
            value = it.get(key)
            if value and poc.collapse_whitespace(value) not in quote:
                flags[flag] += 1
        text = " ".join(
            str(it.get(k) or "") for k in ("item", "reason", "criteria", "check_method")
        ).lower()
        if any(w in text for w in JUDGMENT_PHRASES):
            flags["judgment_wording"] += 1
        valid.append(
            {
                **it,
                # 경계 문자를 정리해 통과했으면 사용자에게 보이는 인용문은 코드가 찾은 원문 구간으로 바꾼다
                "evidence_quote": quote,
                **({"model_quote": it["evidence_quote"]} if adjusted else {}),
                "source": chunk.section_key,
                "chunk_key": chunk.chunk_key,
                "doc_id": chunk.doc_id,
                "domains": chunk.domains,
                "commit_sha": chunk.commit_sha,
            }
        )
    return valid, removed, flags


def item_matches_schema(it: object) -> bool:
    """모델 항목이 고정 스키마(필수 키 전부, 허용하지 않은 키 없음, 타입 일치)를 지키는지 로컬에서 검사한다."""
    if not isinstance(it, dict) or set(it) != set(_ITEM_PROPS):
        return False
    return (
        all(isinstance(it[k], str) for k in ("item", "reason", "evidence_quote"))
        and all(it[k] is None or isinstance(it[k], str) for k in ("criteria", "check_method"))
        and isinstance(it["chunk_no"], int)
        and not isinstance(it["chunk_no"], bool)
    )


def max_call_cost(q: poc.EvalQuestion, shown: list[poc.Chunk]) -> float:
    """다음 호출이 청구할 수 있는 최대 비용 — 입력은 UTF-8 바이트 수(토큰 수의 상한), 출력은 최대 출력 토큰."""
    sent = INSTRUCTIONS + build_prompt(q.question, shown) + json.dumps(OUTPUT_SCHEMA)
    return cost_usd(len(sent.encode("utf-8")), MAX_OUTPUT_TOKENS)


def _classify_api_error(e: Exception) -> tuple[bool, bool]:
    """(요청이 처리되기 전에 거부돼 요금이 없는 오류인가, 더 시도해도 소용없어 배치를 멈춰야 하는가)."""
    import openai

    fatal = isinstance(e, (openai.AuthenticationError, openai.PermissionDeniedError))
    no_charge = fatal or isinstance(
        e, (openai.BadRequestError, openai.NotFoundError, openai.UnprocessableEntityError)
    )
    return no_charge, fatal


def run_question(client, q: poc.EvalQuestion, shown: list[poc.Chunk]) -> dict:
    """질문 하나를 모델에 보내고 검증 결과·토큰·지연을 한 줄 기록으로 돌려준다. 오류가 나도 중단하지 않는다."""
    rec: dict = {
        "question_id": q.question_id,
        "question": q.question,
        "shown_chunks": shown_chunks(shown),
        "schema_ok": False,
        "n_raw": 0,
        "n_quote_found": 0,
        "removed": {},
        "flags": {},
        "gold_cited": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_s": 0.0,
        "error": None,
        "rejected_before_processing": False,
        "fatal": False,
        "response_model": None,
        "removed_items": [],
        "quote_found_items": [],
    }
    start = time.time()
    try:
        response = client.responses.create(
            model=MODEL,
            instructions=INSTRUCTIONS,
            input=build_prompt(q.question, shown),
            text={
                "format": {
                    "type": "json_schema",
                    "name": "checklist_candidates",
                    "strict": True,
                    "schema": OUTPUT_SCHEMA,
                }
            },
            temperature=0,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            store=False,
        )
    except Exception as e:  # noqa: BLE001 — 한 질문의 실패가 전체 실행을 멈추지 않게 기록만 한다
        rec["error"] = f"{type(e).__name__}: {e}"
        rec["rejected_before_processing"], rec["fatal"] = _classify_api_error(e)
        rec["latency_s"] = time.time() - start
        return rec
    rec["latency_s"] = time.time() - start
    rec["response_model"] = getattr(response, "model", None)
    usage = getattr(response, "usage", None)
    rec["input_tokens"] = getattr(usage, "input_tokens", 0) or 0
    rec["output_tokens"] = getattr(usage, "output_tokens", 0) or 0
    try:
        parsed = json.loads(response.output_text)
        if not isinstance(parsed, dict) or set(parsed) != {"items"}:
            raise ValueError("최상위 객체가 {items}만 가진 형태가 아님")
        items = parsed["items"]
        if not isinstance(items, list) or not all(item_matches_schema(i) for i in items):
            raise ValueError("items가 고정 스키마를 지키지 않음")
    except (ValueError, KeyError, TypeError):
        return rec
    rec["schema_ok"] = True
    removed_log: list[dict] = []
    valid, removed, flags = validate_items(items, shown, removed_log)
    rec["removed_items"] = removed_log
    rec.update(
        n_raw=len(items),
        n_quote_found=len(valid),
        removed=removed,
        flags=flags,
        quote_found_items=valid,
        gold_cited=any(v["source"] in q.gold_section_keys for v in valid),
    )
    return rec


def shown_chunks(shown: list[poc.Chunk]) -> list[dict]:
    """모델에게 보여 준 청크를 순위와 함께 기록한다 — 같은 섹션이 여러 청크로 나뉘어도 정확한 조각을 되짚을 수 있다."""
    return [
        {
            "rank": n,
            "chunk_key": c.chunk_key,
            "chunk_hash": c.chunk_hash,
            "doc_id": c.doc_id,
            "section_key": c.section_key,
            "shown_chars": len(c.chunk_text[:MAX_CHUNK_CHARS_IN_PROMPT]),
            "shown_text_sha256": hashlib.sha256(
                c.chunk_text[:MAX_CHUNK_CHARS_IN_PROMPT].encode("utf-8")
            ).hexdigest(),
        }
        for n, c in enumerate(shown, start=1)
    ]


def _rejected(q: poc.EvalQuestion, shown: list[poc.Chunk], reason: str) -> dict:
    return {
        "question_id": q.question_id,
        "question": q.question[:80],
        "shown_chunks": shown_chunks(shown),
        "schema_ok": False,
        "n_raw": 0,
        "n_quote_found": 0,
        "removed": {},
        "flags": {},
        "gold_cited": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_s": 0.0,
        "error": reason,
        "quote_found_items": [],
    }


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code_hashes() -> dict[str, str]:
    """이 실행에 쓴 스크립트의 내용 해시 — 커밋하지 않은 수정도 구분한다."""
    here = Path(__file__).resolve().parent
    return {
        name: file_sha256(here / name) for name in ("sales_support_llm.py", "sales_support_poc.py")
    }


def make_client():
    """자동 재시도를 끈 OpenAI 클라이언트 — 재시도가 비용 상한 계산 밖에서 호출을 늘리지 못하게 한다."""
    from openai import OpenAI

    return OpenAI(max_retries=0)


def git_commit() -> str | None:
    """이 코드를 실행한 저장소 커밋 SHA (변경이 커밋되지 않았으면 `-dirty`를 붙인다). git이 없으면 None."""
    import subprocess

    try:
        root = Path(__file__).resolve().parent.parent
        sha = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--", "scripts"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        return sha + ("-dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return None


def build_run_config(
    index_meta: dict,
    retrieval: str,
    embeddings_path: Path | None = None,
    index_meta_path: Path | None = None,
) -> dict:
    """실행 요약에 남기는 재현 정보 — 모델·프롬프트·스키마·검색·데이터·색인·라이브러리·코드가 무엇이었는지 파일만 보고 알 수 있게 한다."""
    from importlib.metadata import version

    def sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    return {
        "model": MODEL,
        "openai_version": version("openai"),
        "temperature": 0,
        "prompt_version": PROMPT_VERSION,
        "instructions_sha": sha(INSTRUCTIONS),
        "schema_sha": sha(json.dumps(OUTPUT_SCHEMA, sort_keys=True)),
        "top_k_chunks": TOP_K_CHUNKS,
        "max_chunk_chars_in_prompt": MAX_CHUNK_CHARS_IN_PROMPT,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "max_question_chars": MAX_QUESTION_CHARS,
        "price_per_m_tokens": {"input": PRICE_INPUT_PER_M, "output": PRICE_OUTPUT_PER_M},
        "price_checked_on": PRICE_CHECKED_ON,
        "retrieval": retrieval,
        "retrieval_settings": {
            "candidates": poc.CANDIDATES,
            "rrf_k": poc.RRF_K,
            "top_k_eval": list(poc.TOP_K),
            "tokenizer": "lowercase [a-z0-9]+",
        },
        "libraries": {
            lib: version(lib.replace("_", "-"))
            for lib in ("fastembed", "rank_bm25", "numpy", "openai")
        },
        "data_commit_sha": index_meta.get("data_commit_sha"),
        "pinned_snapshot_commit_sha": index_meta.get("pinned_snapshot_commit_sha"),
        "data_fingerprint": index_meta.get("data_fingerprint"),
        "data_status": index_meta.get("data_status"),
        "index_chunks_digest": index_meta.get("chunks_digest"),
        "index_embedding_model": index_meta.get("embedding_model"),
        "chunk_key_recipe": index_meta.get("chunk_key_recipe"),
        "embeddings_sha256": file_sha256(embeddings_path) if embeddings_path else None,
        "index_meta_sha256": file_sha256(index_meta_path) if index_meta_path else None,
        "repo_commit": git_commit(),
        "code_sha256": code_hashes(),
        "client_max_retries": 0,
    }


def question_sets_summary(planned: list[poc.EvalQuestion], records: list[dict]) -> dict:
    """계획한 질문과 실제 시도한 질문을 따로 기록하고 결과를 유형별로 센다.

    all_attempted: 계획한 질문을 모두 시도했는가(예산 중단이면 False — 완주 실행과 직접 비교하지 않는다).
    all_succeeded: 모두 시도했고 전부 성공(API 오류·구조 오류·로컬 거부가 0)인가.
    실패한 호출의 실제 청구액은 응답을 못 받으면 코드가 알 수 없으므로 OpenAI 대시보드로 확인한다.
    """
    done_ids = {r["question_id"] for r in records}
    processed = [q for q in planned if q.question_id in done_ids]
    outcomes = {"success": 0, "schema_error": 0, "api_error": 0, "local_rejected": 0}
    for r in records:
        err = r.get("error")
        if err == "question_too_long":
            outcomes["local_rejected"] += 1
        elif err:
            outcomes["api_error"] += 1
        elif r.get("schema_ok"):
            outcomes["success"] += 1
        else:
            outcomes["schema_error"] += 1
    all_attempted = len(processed) == len(planned)
    return {
        "planned": {"n": len(planned), "digest": poc.question_set_digest(planned)},
        "processed": {"n": len(processed), "digest": poc.question_set_digest(processed)},
        "outcomes": outcomes,
        "all_attempted": all_attempted,
        "all_succeeded": all_attempted and outcomes["success"] == len(planned),
    }


def run_batch(client, jobs: list[tuple[poc.EvalQuestion, list[poc.Chunk]]], budget_usd: float):
    """질문을 차례로 보낸다. 누적 비용이 예산 이상이 되면 거기서 멈추고 (기록, 중단 여부)를 돌려준다."""
    records: list[dict] = []
    spent = 0.0
    for q, shown in jobs:
        if len(q.question) > MAX_QUESTION_CHARS:
            records.append(_rejected(q, shown, "question_too_long"))
            continue
        if spent + max_call_cost(q, shown) > budget_usd:  # 호출하기 전에 최대 비용으로 확인한다
            return records, True
        rec = run_question(client, q, shown)
        # 응답을 못 받아 사용량을 모르는 실패는 요금이 났을 수 있으므로 최악 비용을 누적한다
        rec["cost_unknown"] = (
            rec["error"] is not None
            and not rec["rejected_before_processing"]
            and not (rec["input_tokens"] or rec["output_tokens"])
        )
        spent += (
            max_call_cost(q, shown)
            if rec["cost_unknown"]
            else cost_usd(rec["input_tokens"], rec["output_tokens"])
        )
        records.append(rec)
        if rec["fatal"]:  # 인증·권한 오류는 다음 질문도 똑같이 실패하므로 바로 멈춘다
            break
    return records, False


def quote_diagnosis_counts(records: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for r in records:
        for x in r.get("removed_items", []):
            if x.get("diagnosis"):
                counts[x["diagnosis"]] = counts.get(x["diagnosis"], 0) + 1
    return counts


def summarize(records: list[dict]) -> dict:
    n = len(records)
    ok = [r for r in records if r["schema_ok"]]
    raw = sum(r["n_raw"] for r in ok)
    removed: dict[str, int] = {}
    flags = dict.fromkeys(FLAG_KEYS, 0)
    for r in ok:
        for k, v in r["removed"].items():
            removed[k] = removed.get(k, 0) + v
        for k, v in r["flags"].items():
            flags[k] += v
    valid = sum(r["n_quote_found"] for r in ok)
    in_tok = sum(r["input_tokens"] for r in records)
    out_tok = sum(r["output_tokens"] for r in records)
    lat = sorted(r["latency_s"] for r in records)
    return {
        "n_questions": n,
        "n_api_errors": sum(r["error"] not in (None, "question_too_long") for r in records),
        "n_local_rejected": sum(r["error"] == "question_too_long" for r in records),
        "n_cost_unknown": sum(bool(r.get("cost_unknown")) for r in records),
        "aborted_on_fatal_error": any(r.get("fatal") for r in records),
        "removed_quote_diagnosis": quote_diagnosis_counts(records),
        "response_models": sorted(
            {r["response_model"] for r in records if r.get("response_model")}
        ),
        "notes": [QUOTE_FOUND_NOTE],
        "schema_ok_rate": len(ok) / n if n else 0.0,
        "items_raw": raw,
        "items_quote_found": valid,
        "items_quote_found_rate": valid / raw if raw else 0.0,
        "removed_by_reason": removed,
        "warnings": flags,
        "questions_with_quote_found_item_rate": sum(r["n_quote_found"] > 0 for r in ok) / n
        if n
        else 0.0,
        "gold_cited_rate": sum(r["gold_cited"] for r in records) / n if n else 0.0,
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": cost_usd(in_tok, out_tok),
        "latency_median_s": lat[len(lat) // 2] if lat else 0.0,
    }


def pick_sample(questions: list[poc.EvalQuestion], limit: int) -> list[poc.EvalQuestion]:
    """처음부터 같은 간격으로 뽑아 실행마다 같은 표본이 되게 한다 (limit 0이면 전체)."""
    if not limit or limit >= len(questions):
        return questions
    step = len(questions) / limit
    return [questions[int(i * step)] for i in range(limit)]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--handbook-dir", type=Path, default=poc.HANDBOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=poc.OUT_DIR)
    parser.add_argument("--limit", type=int, default=30, help="표본 질문 수 (0이면 전체)")
    parser.add_argument(
        "--questions",
        type=Path,
        help="질문 JSONL (없으면 FAQ에서 뽑는다, 형식은 sales_support_poc.py 참고)",
    )
    parser.add_argument("--retrieval", choices=["bm25", "vector", "hybrid"], default="hybrid")
    parser.add_argument(
        "--budget", type=positive_budget, default=DEFAULT_BUDGET_USD, help="비용 상한($)"
    )
    parser.add_argument(
        "--run", action="store_true", help="실제로 API를 호출한다 (없으면 계획만 출력)"
    )
    args = parser.parse_args()
    if not args.handbook_dir.is_dir():
        sys.exit(f"핸드북 데이터가 없습니다: {args.handbook_dir}")

    chunks, vectors = poc.load_checked_index(args.handbook_dir, args.out_dir)
    require_pinned_data(json.loads((args.out_dir / poc.INDEX_META).read_text(encoding="utf-8")))
    keys = {c.section_key for c in chunks}
    if args.questions:
        loaded = poc.load_questions(args.questions)
        missing = [q.question_id for q in loaded if not set(q.gold_section_keys) <= keys]
        if missing:
            sys.exit(
                f"정답 섹션이 색인에 없는 질문이 있습니다 ({len(missing)}개, 예: {missing[:3]})"
            )
    else:
        loaded = [q for q in poc.build_faq(args.handbook_dir) if set(q.gold_section_keys) <= keys]
    questions = pick_sample(loaded, args.limit)
    est = len(questions) * cost_usd(EST_INPUT_TOKENS, EST_OUTPUT_TOKENS)
    print(
        f"계획: 질문 {len(questions)}개 × 검색 {args.retrieval} = 호출 {len(questions)}회, 모델 {MODEL}, "
        f"예상 비용 약 ${est:.3f} (상한 ${args.budget:.2f})"
    )
    if not args.run:
        print("호출하지 않았습니다. 실제로 돌리려면 --run을 붙이세요.")
        return

    import os

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("환경변수 OPENAI_API_KEY가 없습니다. 터미널에서 설정한 뒤 다시 실행하세요.")
    ranks = poc.Retriever(chunks, vectors).rank([q.question for q in questions])[args.retrieval]
    jobs = [
        (q, [chunks[i] for i in order[:TOP_K_CHUNKS]])
        for q, order in zip(questions, ranks, strict=True)
    ]
    records, stopped = run_batch(make_client(), jobs, args.budget)
    summary = summarize(records)
    summary["stopped_by_budget"] = stopped
    summary["retrieval"] = args.retrieval
    summary["question_sets"] = question_sets_summary(questions, records)
    meta_path = args.out_dir / poc.INDEX_META
    summary["run_config"] = build_run_config(
        json.loads(meta_path.read_text(encoding="utf-8")),
        args.retrieval,
        embeddings_path=args.out_dir / "embeddings.npz",
        index_meta_path=meta_path,
    )

    run_dir = args.out_dir / "llm_runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = run_dir / f"{stamp}_{args.retrieval}_{len(records)}"
    with base.with_suffix(".jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    base.with_suffix(".summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"저장: {base}.jsonl / .summary.json (gitignore 대상)")


if __name__ == "__main__":
    main()

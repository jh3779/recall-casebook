"""근거 연결형 초안 (DEC-065) — 8D D2·D4에 선례 원문을 묶어 보여 준다. LLM은 묶고 제목을 붙일 뿐 문장을 쓰지 않는다.

- 입력은 검색이 넘긴 선례의 **원문 문장**뿐이다(D2 = 결함·결과, D4 = 573 원인 칸). 판정·원인 추정·조치 권고를 시키지 않는다.
- LLM이 돌려준 인용 문자열은 그대로 쓰지 않는다 — 서버가 원문에서 그 구간을 **찾아** 원문 글자를 잘라 싣는다(`locate`).
  원문과 다른 문자열(글자를 바꿨거나 지어낸 것)은 버리고 센다. NHTSA 글에는 마침표 뒤 이중 공백이 많아, 공백만 다르면
  원문 구간으로 되짚되 싣는 글자는 언제나 원문 것이다(AGENTS.md 2-2).
- 묶음 제목은 도구가 만든 문장이다 — 화면은 "도구가 붙인 제목"으로 표시해야 한다. 판정 표현이 들어 있으면 제목을 버린다.
- 꺼져 있거나(`DRAFT_ENABLED` 아님) LLM이 실패하면 묶음 없이 원문 목록만 돌려준다(`degraded`).
- 호출은 표준 라이브러리만 쓴다(런타임 의존성을 늘리지 않는다). 키는 서버 환경변수 `OPENAI_API_KEY`뿐이고 응답·오류에 싣지 않는다.
"""

import json
import os
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial

STEPS = ("d2", "d4")
MAX_CARDS = 6  # 한 번에 보내는 선례 수 상한 — 입력 크기와 비용을 막는다
MAX_TITLE = 40
MAX_OUTPUT_TOKENS = 1500
ENDPOINT = "https://api.openai.com/v1/responses"
DEFAULT_MODEL, DEFAULT_EFFORT = "gpt-6-luna", "none"  # 사용자 지정 2026-10-16(DEC-065)
EFFORTS = (
    "none",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
)  # OpenAI 모델 문서(cause_trials.py와 같은 값)
DEFAULT_LIMIT = 6  # IP당 1분 (유료 호출이라 /search(60)보다 훨씬 낮다)

# 제목에 들어가면 안 되는 표현 — 판정·단정(AGENTS.md 2-1). 못 걸러도 화면이 "도구가 붙인 제목"으로 표시한다
VERDICT_RE = re.compile(
    r"리콜\s*(대상|필요|불필요|해당)|해당(합니다|한다|됩니다|된다|함)|적용(됩니다|된다)|판정|결론"
    r"|(원인|결함)은\s*.{0,30}(입니다|이다|임)\b|\b(applies|verdict|recall required|root cause is|is applicable)\b",
    re.I,
)

# 제목은 "~라고 적은 선례" 꼴이어야 한다 — 원문이 말한 것을 말한 그대로 설명하는 문장만 허용하고, 원인·결과를 사실처럼 단정하는 제목을 막는다
TITLE_FORMAT_RE = re.compile(r"(적은|서술한|언급한) 선례$")

SCHEMA = {
    "type": "object",
    "properties": {
        "groups": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "quotes": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "source_id": {"type": "string"},
                                "text": {"type": "string"},
                            },
                            "required": ["source_id", "text"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["title", "quotes"],
                "additionalProperties": False,
            },
        },
        "ungrouped": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["groups", "ungrouped"],
    "additionalProperties": False,
}

COMMON_RULES = (
    "You organize quotes taken from NHTSA recall records. The input is a list of sources, each with an id and a text. "
    "Group the sources whose wording says similar things. For each group give a short title in Korean (at most 40 "
    "characters) that ONLY reports what the quoted wording says and MUST end with '적은 선례' (for example "
    "'납땜 플럭스가 오염됐을 수 있다고 적은 선례'). A title must keep the same level of certainty as its sources: if the "
    "sources say may, could, possible or suspected, the title says '~일 수 있다고'; never turn a possibility into a fact and "
    "never write a cause-and-effect conclusion such as '~로 인한 ~' in a title. "
    "For each group return the quotes: each quote is a continuous part of one source text copied EXACTLY, character for "
    "character (do not change capitalization, spelling, punctuation or spacing; do not shorten with '...'; do not "
    "translate). Prefer whole sentences. Use each source in at most one group. Sources that fit no group go to 'ungrouped' "
    "by id. Never judge whether a recall applies to anything, never state or infer a cause, remedy or conclusion yourself, "
    "never add facts that are not in the sources, and never put a verdict in a title."
)
TASKS = {
    "d2": "The sources are sentences from NHTSA recall summaries: each says what fails (defect) or what may result "
    "(consequence). Group sources that describe the same kind of failure or the same kind of consequence.",
    "d4": "The sources are 'Description of the Cause' texts that manufacturers wrote in Part 573 reports. Group sources that "
    "state the same kind of reason (for example the same material, process or assembly reason). Put texts that say the "
    "cause is unknown, not reported or under investigation together in one group.",
}

QUESTIONS = {
    "d2": [
        "우리 건의 불량 현상(무엇이·언제·어디서·몇 건)을 위 원문 표현과 나란히 놓고 비교했습니까?",
        "원문의 '결과' 문장(예: 위험 서술)이 우리 건에도 해당하는지 확인할 자료가 있습니까? 이 도구는 같다·다르다를 표시하지 않습니다.",
    ],
    "d4": [
        "위 원인 문장은 제조사가 쓴 공개 서술이며 우리 건의 원인이 아닙니다. 발생 원인과 유출 원인을 직접 분석했습니까?",
        "선례의 공급사·생산 기간(확인 항목)과 우리 건의 공급사·생산 기간이 겹칩니까?",
    ],
}
QUESTION_UNKNOWN = "원인 대신 '미보고·조사 중' 표현(N/A·NR 등)을 적은 선례는 원인 근거로 쓸 수 없습니다. 다른 근거가 있습니까?"


class LlmError(RuntimeError):
    """LLM 호출 실패 — kind: network·http·format·refusal·incomplete. 키·요청 머리글은 메시지에 싣지 않는다."""

    def __init__(self, kind: str, detail: str = ""):
        super().__init__(f"{kind}: {detail}" if detail else kind)
        self.kind = kind


@dataclass(frozen=True)
class LlmResult:
    text: str
    model: str
    input_tokens: int
    output_tokens: int
    seconds: float


@dataclass(frozen=True)
class Source:
    id: str
    campno: str
    field: str  # defect | consequence | cause
    text: str
    provenance: dict  # 말한 주체·출처 — 응답에 그대로 싣는다


def build_sources(step: str, cards: list[dict]) -> list[Source]:
    """검증을 마친 카드 뷰(`api.card_view` → `verify`)에서 원문 문장을 뽑는다. 원인 글이 없는 카드는 D4에서 빠진다."""
    out: list[Source] = []
    for card in cards:
        if step == "d2":
            prov = {
                "speaker": card["source"]["speaker"],
                "dataset": card["source"]["dataset"],
                "snapshot_date": card["source"]["snapshot_date"],
            }
            for field in ("defect", "consequence"):
                if card[field].strip():
                    out.append(Source(f"S{len(out) + 1}", card["campno"], field, card[field], prov))
        else:
            cause = card["cause"]
            if cause["status"] in ("filled", "stated_unknown"):
                prov = {
                    "speaker": cause["speaker"],
                    "cause_status": cause["status"],
                    "cause_source": cause["source"],
                }
                out.append(Source(f"S{len(out) + 1}", card["campno"], "cause", cause["text"], prov))
    return out


def prompt_for(step: str, sources: list[Source]) -> tuple[str, str]:
    body = "\n\n".join(f"[{s.id}] campno={s.campno} field={s.field}\n{s.text}" for s in sources)
    return f"{COMMON_RULES} {TASKS[step]}", f"Sources:\n\n{body}"


def locate(text: str, quote: str) -> tuple[int, int] | None:
    """quote가 있는 원문 구간(시작, 끝)을 찾는다. 글자가 그대로 있으면 그 자리, 공백(줄바꿈·이중 공백)만 다르면 원문 구간으로 되짚는다."""
    i = text.find(quote)
    if i >= 0 and quote:
        return i, i + len(quote)
    norm_chars: list[str] = []
    index: list[int] = []
    prev_space = False
    for k, ch in enumerate(text):
        if ch.isspace():
            if not prev_space and norm_chars:
                norm_chars.append(" ")
                index.append(k)
            prev_space = True
        else:
            norm_chars.append(ch)
            index.append(k)
            prev_space = False
    q = " ".join(quote.split())
    if not q:
        return None
    j = "".join(norm_chars).find(q)
    if j < 0:
        return None
    return index[j], index[j + len(q) - 1] + 1


def item(src: Source, start: int, end: int) -> dict:
    return {
        "campno": src.campno,
        "field": src.field,
        "quote": src.text[start:end],  # 언제나 원문에서 잘라 낸 글자
        "start": start,
        "end": end,
        **src.provenance,
    }


def title_ok(title: str) -> bool:
    t = title.strip()
    return (
        0 < len(t) <= MAX_TITLE
        and "\n" not in t
        and bool(TITLE_FORMAT_RE.search(t))
        and not VERDICT_RE.search(t)
    )


def assemble(sources: list[Source], parsed: dict) -> dict:
    """LLM 결과를 원문과 대조해 묶음을 만든다. 원문에 없는 인용·없는 출처·겹친 인용은 버리고 센다."""
    by_id = {s.id: s for s in sources}
    used: set[str] = set()
    rejected = {"unknown_source": 0, "not_in_source": 0, "duplicate_source": 0, "bad_title": 0}
    relocated = (
        0  # LLM이 공백만 바꿔 돌려줘 원문 구간으로 되짚은 인용 수(싣는 글자는 언제나 원문 것)
    )
    groups = []
    for g in parsed.get("groups", []):
        items = []
        for q in g.get("quotes", []):
            src = by_id.get(q.get("source_id"))
            if src is None:
                rejected["unknown_source"] += 1
                continue
            if src.id in used:
                rejected["duplicate_source"] += 1
                continue
            span = locate(src.text, q.get("text", "")) if isinstance(q.get("text"), str) else None
            if span is None:
                rejected["not_in_source"] += 1
                continue
            used.add(src.id)
            relocated += src.text.find(q["text"]) < 0
            items.append(item(src, *span))
        if not items:
            continue
        title = str(g.get("title", "")).strip()
        if not title_ok(title):
            rejected["bad_title"] += 1
            title = f"묶음 {len(groups) + 1}"
        groups.append({"title": title, "items": items})
    ungrouped = [item(s, 0, len(s.text)) for s in sources if s.id not in used]
    return {"groups": groups, "ungrouped": ungrouped, "rejected": rejected, "relocated": relocated}


def questions_for(step: str, sources: list[Source]) -> list[str]:
    qs = list(QUESTIONS[step])
    if step == "d4" and any(s.provenance.get("cause_status") == "stated_unknown" for s in sources):
        qs.append(QUESTION_UNKNOWN)
    return qs


def call_llm(
    instructions: str,
    input_text: str,
    *,
    api_key: str,
    model: str = DEFAULT_MODEL,
    effort: str | None = DEFAULT_EFFORT,
    timeout: float = 25.0,
    opener: Callable = urllib.request.urlopen,
) -> LlmResult:
    """OpenAI Responses API(POST /v1/responses, 구조화 출력 json_schema strict)를 부른다. 응답은 저장하지 않는다(store=false)."""
    body = {
        "model": model,
        "instructions": instructions,
        "input": input_text,
        "store": False,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "text": {
            "format": {
                "type": "json_schema",
                "name": "draft_groups",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    }
    if effort:
        body["reasoning"] = {"effort": effort}
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    t = time.perf_counter()
    try:
        with opener(req, timeout=timeout) as resp:
            raw = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise LlmError("http", f"status {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise LlmError("network") from None
    except ValueError:
        raise LlmError("format", "응답이 JSON이 아니다") from None
    if raw.get("status") not in (None, "completed"):
        raise LlmError("incomplete", str(raw.get("status")))
    text = None
    for out in raw.get("output", []):
        if out.get("type") != "message":
            continue
        for c in out.get("content", []):
            if c.get("type") == "refusal":
                raise LlmError("refusal")
            if c.get("type") == "output_text":
                text = (text or "") + c.get("text", "")
    if text is None:
        raise LlmError("format", "output_text가 없다")
    usage = raw.get("usage") or {}
    return LlmResult(
        text,
        raw.get("model") or model,
        usage.get("input_tokens", 0),
        usage.get("output_tokens", 0),
        time.perf_counter() - t,
    )


def generate(
    step: str, cards: list[dict], llm: Callable[[str, str], LlmResult] | None
) -> tuple[dict, LlmResult | None]:
    """초안 한 단계. llm이 None(꺼짐)이거나 호출·해석에 실패하면 묶음 없이 원문 목록만(`degraded`)."""
    if step not in STEPS:
        raise ValueError(f"step={step!r}")
    sources = build_sources(step, cards)
    base = {
        "step": step,
        "questions": questions_for(step, sources),
        "model": None,
        "degraded": None,
    }
    empty = {
        "groups": [],
        "ungrouped": [item(s, 0, len(s.text)) for s in sources],
        "rejected": {},
        "relocated": 0,
    }
    if not sources:
        return {**base, **empty}, None
    if llm is None:
        return {**base, **empty, "degraded": "disabled"}, None
    try:
        result = llm(*prompt_for(step, sources))
        parsed = json.loads(result.text)
        if not isinstance(parsed, dict):
            raise LlmError("format", "JSON 최상위가 객체가 아니다")
    except (LlmError, ValueError) as e:
        kind = e.kind if isinstance(e, LlmError) else "format"
        return {**base, **empty, "degraded": "llm_failed", "reason": kind}, None
    return {**base, **assemble(sources, parsed), "model": result.model}, result


@dataclass(frozen=True)
class DraftConfig:
    """`POST /draft` 설정 — 기본은 꺼짐이다. 켜려면 `DRAFT_ENABLED=1`과 서버 환경변수 `OPENAI_API_KEY`가 모두 있어야 한다."""

    enabled: bool = False
    api_key: str = ""
    model: str = DEFAULT_MODEL
    effort: str = DEFAULT_EFFORT
    limit: int = DEFAULT_LIMIT  # IP당 1분 호출 수 — 유료 호출이라 /search보다 훨씬 낮다

    @classmethod
    def from_env(cls, env=None) -> "DraftConfig":
        env = os.environ if env is None else env
        enabled = env.get("DRAFT_ENABLED", "").strip() == "1"
        key = env.get("OPENAI_API_KEY", "").strip()
        if enabled and not key:
            raise RuntimeError(
                "DRAFT_ENABLED=1에는 OPENAI_API_KEY가 필요하다 — 키 없이 켜지 않는다"
            )
        effort = env.get("DRAFT_REASONING_EFFORT", "").strip() or DEFAULT_EFFORT
        if effort not in EFFORTS:
            raise RuntimeError(
                f"DRAFT_REASONING_EFFORT={effort!r} — {', '.join(EFFORTS)} 중 하나만 쓴다"
            )
        raw = env.get("DRAFT_RATE_LIMIT_PER_MINUTE", "").strip()
        try:
            limit = int(raw) if raw else DEFAULT_LIMIT
        except ValueError:
            limit = 0
        if limit < 1:
            raise RuntimeError(f"DRAFT_RATE_LIMIT_PER_MINUTE={raw!r} — 1 이상의 정수만 쓴다")
        return cls(enabled, key, env.get("DRAFT_MODEL", "").strip() or DEFAULT_MODEL, effort, limit)

    def llm(self) -> Callable[[str, str], LlmResult] | None:
        if not self.enabled:
            return None
        return partial(call_llm, api_key=self.api_key, model=self.model, effort=self.effort)

"""영업·지원 도메인 PoC — 검색 3종(BM25 / 벡터 / 하이브리드 RRF) 비교 기준선.

설계 근거: docs/기획v1.md 4절 "영업 · 지원"·"데이터 처리 설계". 평가 질문은 FAQ(문서 유래) 세트뿐이며
**동작 확인용**이다 — 질문 문장이 정답 청크 안에 그대로 들어 있어 BM25가 유리하게 나오므로
이 점수만으로 모델을 고르지 않는다 (AGENTS.md 5절 1항, DEC-014·DEC-021).

사용법:
    uv run python scripts/sales_support_poc.py stats              # 청킹·FAQ 추출 개수만 (무료, 즉시)
    uv run python scripts/sales_support_poc.py index --limit 200  # 표본 임베딩 시간 측정 (로컬, 무료)
    uv run python scripts/sales_support_poc.py index              # 전체 임베딩 (로컬, 무료)
    uv run python scripts/sales_support_poc.py eval               # 3종 비교 (index 먼저)
"""

import argparse
import hashlib
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from importlib.metadata import version
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
HANDBOOK_DIR = ROOT / "docs" / "handbook" / "content" / "handbook"
OUT_DIR = ROOT / "data" / "processed" / "sales_support"
# 영업·지원 도메인 폴더 (기획v1 3절 매핑)
DOMAIN_DIRS = [
    "sales",
    "support",
    "customer-experience",
    "marketing",
    "solutions-architects",
    "resellers",
    "alliances",
]
# 데이터 버전 — docs/handbook/README.md의 원문 커밋(`suuuuuuungho/GitLab_Data`) 전체 SHA
COMMIT_SHA = "0ab0299ce073b847558867ae5abbc42c570bc8d5"
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"
MAX_CHUNK_CHARS = 2000
# 색인 설정 — 바뀌면 `index`를 다시 해야 한다(`eval`이 저장된 값과 비교해 다르면 중단)
CHUNKING = {"heading_levels": "H2-H4", "max_chunk_chars": MAX_CHUNK_CHARS, "preprocess": "v1"}
# 색인에서 뺄 폴더 — 신규 "고객"(제품 구독자)용 온보딩이라 직원 질문에 섞이면 안 된다 (기획v1 4절 데이터 처리 설계 4번)
EXCLUDE_DIRS = ["customer-experience/customer-onboarding"]
INDEX_META = "index_meta.json"
RRF_K = 60
TOP_K = (1, 3, 5, 10)
CANDIDATES = 100  # 하이브리드에 넘기는 각 검색기의 후보 수

HEADING_RE = re.compile(r"^(#{2,4})\s+(.+?)\s*#*\s*$")
FAQ_TITLE_RE = re.compile(r"faq|frequently asked", re.IGNORECASE)
# 굵은 글씨로 쓴 질문 한 줄: "1. **...?**", "- **...?**", "Q: **...?**"
BOLD_QUESTION_RE = re.compile(r"^\s*(?:(?:\d+[.)]|[-*])\s*)?(?:Q:\s*)?\*\*(.+?\?)\*\*\s*$")


@dataclass
class Chunk:
    chunk_id: int
    source_path: str
    heading_path: str
    commit_sha: str
    chunk_text: str
    chunk_hash: str

    @property
    def section_key(self) -> str:
        return f"{self.source_path}#{self.heading_path}"


def collapse_whitespace(text: str) -> str:
    """공백 정리 — 공백·탭·줄바꿈을 한 칸으로, 앞뒤 제거 (구두점·대소문자는 그대로)."""
    return re.sub(r"\s+", " ", text).strip()


def preprocess(text: str) -> str:
    """frontmatter·Hugo shortcode·HTML 태그 제거 (기획v1 4절 데이터 처리 설계 2번)."""
    text = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL)
    text = re.sub(r"\{\{<\s*member-by-name\s+\"([^\"]*)\"\s*>\}\}", r"\1", text)
    text = re.sub(r"\{\{[%<].*?[%>]\}\}", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>\n]+>", "", text)
    return text


def split_sections(text: str) -> list[tuple[str, list[str]]]:
    """본문을 H2~H4 헤딩 단위로 나눠 (heading_path, 줄 목록)을 돌려준다. 코드블록 안 `#`은 헤딩이 아니다."""
    sections: list[tuple[str, list[str]]] = []
    stack: dict[int, str] = {}
    path, lines, in_code = "", [], False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else HEADING_RE.match(line)
        if not m:
            lines.append(line)
            continue
        sections.append((path, lines))
        level = len(m.group(1))
        stack = {k: v for k, v in stack.items() if k < level}
        stack[level] = m.group(2)
        path = ">".join(stack[k] for k in sorted(stack))
        lines = []
    sections.append((path, lines))
    return sections


def split_long(body: str) -> list[str]:
    """MAX_CHUNK_CHARS를 넘는 섹션은 문단(빈 줄) 경계로 나눈다. 문단 하나가 더 길면 그대로 둔다."""
    if len(body) <= MAX_CHUNK_CHARS:
        return [body]
    parts, current = [], ""
    for para in re.split(r"\n\s*\n", body):
        if current and len(current) + len(para) + 2 > MAX_CHUNK_CHARS:
            parts.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    parts.append(current)
    return parts


def chunk_file(source_path: str, raw: str, first_id: int = 0) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading_path, lines in split_sections(preprocess(raw)):
        body = "\n".join(lines).strip()
        if not body:
            continue
        for part in split_long(body):
            normalized = collapse_whitespace(part)
            chunks.append(
                Chunk(
                    chunk_id=first_id + len(chunks),
                    source_path=source_path,
                    heading_path=heading_path,
                    commit_sha=COMMIT_SHA,
                    chunk_text=part,
                    chunk_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16],
                )
            )
    return chunks


def list_files(handbook_dir: Path) -> list[Path]:
    files: list[Path] = []
    for d in DOMAIN_DIRS:
        for path in sorted((handbook_dir / d).rglob("*.md")):
            rel = path.relative_to(handbook_dir).as_posix()
            if not any(rel.startswith(ex + "/") for ex in EXCLUDE_DIRS):
                files.append(path)
    return files


def build_chunks(handbook_dir: Path) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in list_files(handbook_dir):
        rel = path.relative_to(handbook_dir).as_posix()
        chunks.extend(chunk_file(rel, path.read_text(encoding="utf-8"), len(chunks)))
    return chunks


@dataclass
class EvalQuestion:
    """평가 질문 한 개. 정답은 섹션 키(`source_path#heading_path`) 목록이다 — 정답이 여러 개일 수 있다."""

    question_id: str
    question: str
    gold_section_keys: list[str]  # FAQ 유래는 질문이 들어 있던 섹션 (원문에 이미 있는 정보)


def make_question_id(question: str) -> str:
    return (
        "faq-"
        + hashlib.sha256(collapse_whitespace(question).lower().encode("utf-8")).hexdigest()[:10]
    )


def strip_markdown(text: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = collapse_whitespace(text.replace("**", "").replace("`", ""))
    return re.sub(r"^Q:\s*", "", text)


def _faq_question(question: str, source_path: str, heading_path: str) -> EvalQuestion:
    return EvalQuestion(make_question_id(question), question, [f"{source_path}#{heading_path}"])


def extract_faq(source_path: str, raw: str) -> list[EvalQuestion]:
    """FAQ 제목(H2~H4)의 하위 섹션에서 질문을 뽑는다 — 하위 헤딩이 `?`로 끝나거나, 굵은 글씨 한 줄 질문.

    정답 위치는 질문이 실제로 들어 있는 섹션이다(원문에 이미 있는 정보만 쓴다, AGENTS.md 5절 2항 ①).
    """
    questions: list[EvalQuestion] = []
    faq_level = 0  # 0이면 FAQ 구간 밖
    stack: dict[int, str] = {}
    in_code = False
    for line in preprocess(raw).splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
        m = None if in_code else HEADING_RE.match(line)
        if m:
            level = len(m.group(1))
            title = m.group(2)
            stack = {k: v for k, v in stack.items() if k < level}
            stack[level] = title
            path = ">".join(stack[k] for k in sorted(stack))
            if faq_level and level <= faq_level:
                faq_level = 0
            if not faq_level and FAQ_TITLE_RE.search(title):
                faq_level = level
            elif faq_level and level > faq_level and title.rstrip().endswith("?"):
                questions.append(_faq_question(strip_markdown(title), source_path, path))
            continue
        if faq_level and not in_code:
            q = BOLD_QUESTION_RE.match(line)
            if q:
                path = ">".join(stack[k] for k in sorted(stack))
                questions.append(_faq_question(strip_markdown(q.group(1)), source_path, path))
    return questions


def build_faq(handbook_dir: Path) -> list[EvalQuestion]:
    """같은 문장의 질문은 하나로 합치되 정답 섹션은 모두 남긴다 (AGENTS.md 5절 2항)."""
    faq: dict[str, EvalQuestion] = {}
    for path in list_files(handbook_dir):
        rel = path.relative_to(handbook_dir).as_posix()
        for q in extract_faq(rel, path.read_text(encoding="utf-8")):
            merged = faq.setdefault(q.question_id, q)
            if merged is not q:
                merged.gold_section_keys.extend(
                    k for k in q.gold_section_keys if k not in merged.gold_section_keys
                )
    return list(faq.values())


def retrieval_text(chunk: Chunk) -> str:
    """검색 대상 문자열 — 헤딩 경로 + 본문. BM25와 벡터가 같은 글을 본다 (비교를 공정하게)."""
    return f"{chunk.heading_path.replace('>', ' > ')}\n{collapse_whitespace(chunk.chunk_text)}"


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def rrf(rankings: list[list[int]], k: int = RRF_K) -> list[int]:
    """Reciprocal Rank Fusion — 각 순위표에서 1/(k+순위)를 더해 다시 정렬한다."""
    scores: dict[int, float] = {}
    for ranking in rankings:
        for rank, idx in enumerate(ranking, start=1):
            scores[idx] = scores.get(idx, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda i: (-scores[i], i))


def evaluate(
    ranked: list[list[int]], chunks: list[Chunk], questions: list[EvalQuestion]
) -> dict[str, dict[str, float]]:
    """질문마다 순위표(청크 인덱스)의 상위 k개에서 Hit@k(정답 하나라도 적중)·Recall@k(정답 중 찾은 비율)·MRR을 센다."""
    result: dict[str, dict[str, float]] = {}
    for unit in ("file", "section"):
        hit = {k: 0.0 for k in TOP_K}
        recall = {k: 0.0 for k in TOP_K}
        rr = 0.0
        for order, q in zip(ranked, questions, strict=True):
            golds = {g.split("#", 1)[0] if unit == "file" else g for g in q.gold_section_keys}
            keys = [
                chunks[i].source_path if unit == "file" else chunks[i].section_key for i in order
            ]
            for k in TOP_K:
                found = golds & set(keys[:k])
                hit[k] += bool(found)
                recall[k] += len(found) / len(golds)
            first = next((r for r, key in enumerate(keys, start=1) if key in golds), None)
            rr += 1.0 / first if first else 0.0
        n = len(questions)
        result[unit] = (
            {f"Hit@{k}": hit[k] / n for k in TOP_K}
            | {f"Recall@{k}": recall[k] / n for k in TOP_K}
            | {"MRR": rr / n}
        )
    return result


def chunks_digest(chunks: list[Chunk]) -> str:
    """청크 목록의 지문 — 경로·제목 위치·내용 해시를 순서대로 이어 해시한다 (벡터와 청크의 짝이 어긋나면 달라진다)."""
    lines = "\n".join(f"{c.source_path}\t{c.heading_path}\t{c.chunk_hash}" for c in chunks)
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def build_meta(chunks: list[Chunk], vector_shape: tuple[int, ...], fastembed_version: str) -> dict:
    return {
        "data_commit_sha": COMMIT_SHA,
        "embedding_model": EMBEDDING_MODEL,
        "fastembed_version": fastembed_version,
        "chunking": CHUNKING,
        "excluded_dirs": EXCLUDE_DIRS,
        "n_chunks": len(chunks),
        "chunks_digest": chunks_digest(chunks),
        "vectors_shape": list(vector_shape),
    }


def check_index(
    meta: dict,
    current_chunks: list[Chunk],
    saved_chunks: list[Chunk],
    vector_shape: tuple[int, ...],
    fastembed_version: str,
) -> list[str]:
    """저장된 색인 설명(meta)이 지금 설정·데이터와 같은지 비교해 다른 항목을 문장으로 돌려준다. 빈 목록이면 일치."""
    problems = []
    expected = {
        "data_commit_sha": COMMIT_SHA,
        "embedding_model": EMBEDDING_MODEL,
        "fastembed_version": fastembed_version,
        "chunking": CHUNKING,
        "excluded_dirs": EXCLUDE_DIRS,
    }
    for key, now in expected.items():
        if meta.get(key) != now:
            problems.append(f"{key}: 색인 {meta.get(key)!r} != 현재 {now!r}")
    if meta.get("chunks_digest") != chunks_digest(current_chunks):
        problems.append("chunks_digest: 색인 때와 지금 핸드북에서 만든 청크 목록이 다름")
    if meta.get("chunks_digest") != chunks_digest(saved_chunks):
        problems.append("chunks_digest: 저장된 chunks.jsonl이 색인 설명과 다름")
    if list(vector_shape) != meta.get("vectors_shape") or vector_shape[0] != len(saved_chunks):
        problems.append(
            f"vectors: embeddings.npy shape {tuple(vector_shape)} != 색인 {meta.get('vectors_shape')}"
            f" / 청크 {len(saved_chunks)}개"
        )
    return problems


def _write_chunks(chunks: list[Chunk], path: Path) -> None:
    with path.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(asdict(c), ensure_ascii=False) + "\n")


def _read_chunks(path: Path) -> list[Chunk]:
    with path.open(encoding="utf-8") as f:
        return [Chunk(**json.loads(line)) for line in f]


def cmd_stats(args: argparse.Namespace) -> None:
    chunks = build_chunks(args.handbook_dir)
    faq = build_faq(args.handbook_dir)
    sizes = sorted(len(c.chunk_text) for c in chunks)
    print(f"파일 {len(list_files(args.handbook_dir))}개 → 청크 {len(chunks)}개")
    if sizes:
        print(f"청크 길이(글자): 중앙값 {sizes[len(sizes) // 2]}, 최대 {sizes[-1]}")
    gold_files = {k.split("#", 1)[0] for q in faq for k in q.gold_section_keys}
    print(f"FAQ 질문 {len(faq)}개 / FAQ가 있는 파일 {len(gold_files)}개")
    print(f"정답이 둘 이상인 질문 {sum(len(q.gold_section_keys) > 1 for q in faq)}개")
    keys = {c.section_key for c in chunks}
    missing = [q for q in faq if not set(q.gold_section_keys) <= keys]
    print(f"정답 섹션이 청크로 존재하지 않는 질문 {len(missing)}개")


def cmd_index(args: argparse.Namespace) -> None:
    from fastembed import TextEmbedding

    chunks = build_chunks(args.handbook_dir)
    if args.limit:
        step = max(len(chunks) // args.limit, 1)
        chunks = chunks[::step][: args.limit]
    model = TextEmbedding(model_name=EMBEDDING_MODEL)
    start = time.time()
    vectors = np.array(list(model.passage_embed([retrieval_text(c) for c in chunks])))
    elapsed = time.time() - start
    vectors /= np.linalg.norm(vectors, axis=1, keepdims=True)
    print(
        f"{len(chunks)}개 임베딩 {elapsed:.1f}초 (청크당 {elapsed / len(chunks) * 1000:.0f}ms), shape={vectors.shape}"
    )
    if args.limit:
        total = len(build_chunks(args.handbook_dir))
        print(
            f"전체 {total}개 예상 소요: 약 {elapsed / len(chunks) * total / 60:.1f}분 — 표본이라 저장하지 않음"
        )
        return
    args.out_dir.mkdir(parents=True, exist_ok=True)
    np.save(args.out_dir / "embeddings.npy", vectors)
    _write_chunks(chunks, args.out_dir / "chunks.jsonl")
    meta = build_meta(chunks, vectors.shape, version("fastembed"))
    (args.out_dir / INDEX_META).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"저장: {args.out_dir} (색인 설명 {INDEX_META} 포함)")


def cmd_eval(args: argparse.Namespace) -> None:
    from fastembed import TextEmbedding
    from rank_bm25 import BM25Okapi

    meta_path = args.out_dir / INDEX_META
    if not meta_path.is_file():
        sys.exit(f"색인 설명 {meta_path}이 없습니다. `index`를 먼저 실행하세요.")
    chunks = _read_chunks(args.out_dir / "chunks.jsonl")
    vectors = np.load(args.out_dir / "embeddings.npy")
    problems = check_index(
        json.loads(meta_path.read_text(encoding="utf-8")),
        build_chunks(args.handbook_dir),
        chunks,
        vectors.shape,
        version("fastembed"),
    )
    if problems:
        sys.exit(
            "색인이 현재 설정·데이터와 다릅니다. `index`를 다시 실행하세요:\n- "
            + "\n- ".join(problems)
        )
    keys = {c.section_key for c in chunks}
    faq = [q for q in build_faq(args.handbook_dir) if set(q.gold_section_keys) <= keys]

    bm25 = BM25Okapi([tokenize(retrieval_text(c)) for c in chunks])
    model = TextEmbedding(model_name=EMBEDDING_MODEL)
    q_vecs = np.array(list(model.query_embed([q.question for q in faq])))
    q_vecs /= np.linalg.norm(q_vecs, axis=1, keepdims=True)

    bm25_rank, vec_rank, hybrid_rank = [], [], []
    for q, qv in zip(faq, q_vecs, strict=True):
        b = np.argsort(-bm25.get_scores(tokenize(q.question)), kind="stable")[:CANDIDATES].tolist()
        v = np.argsort(-(vectors @ qv), kind="stable")[:CANDIDATES].tolist()
        bm25_rank.append(b)
        vec_rank.append(v)
        hybrid_rank.append(rrf([b, v]))

    results = {
        "BM25": evaluate(bm25_rank, chunks, faq),
        "벡터(bge-small)": evaluate(vec_rank, chunks, faq),
        "하이브리드(RRF)": evaluate(hybrid_rank, chunks, faq),
    }
    print(f"질문 {len(faq)}개 (FAQ 유래, 동작 확인용 — 모델 선택 근거 아님), 청크 {len(chunks)}개")
    for unit, label in (("file", "파일 단위"), ("section", "섹션 단위")):
        header = [f"Hit@{k}" for k in TOP_K] + [f"Rec@{k}" for k in TOP_K] + ["MRR"]
        print(f"\n[{label}] " + " ".join(f"{m:>7}" for m in header))
        for name, r in results.items():
            row = " ".join(f"{v:7.3f}" for v in r[unit].values())
            print(f"{name:<16} {row}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "eval_result.json").write_text(
        json.dumps(
            {
                "n_questions": len(faq),
                "n_chunks": len(chunks),
                "index_meta": json.loads(meta_path.read_text(encoding="utf-8")),
                "results": results,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--handbook-dir", type=Path, default=HANDBOOK_DIR)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("stats").set_defaults(func=cmd_stats)
    p_index = sub.add_parser("index")
    p_index.add_argument("--limit", type=int, default=0, help="표본 청크 수 (0이면 전체)")
    p_index.set_defaults(func=cmd_index)
    sub.add_parser("eval").set_defaults(func=cmd_eval)
    args = parser.parse_args()
    if not args.handbook_dir.is_dir():
        sys.exit(
            f"핸드북 데이터가 없습니다: {args.handbook_dir} (scripts/fetch_handbook_dataset.py로 받으세요)"
        )
    args.func(args)


if __name__ == "__main__":
    main()

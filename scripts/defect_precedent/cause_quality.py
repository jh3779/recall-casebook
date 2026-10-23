"""원인 품질 표본 — 서버가 선례 카드에 붙여 보여 주는 원인 글이 실제로 원인을 말하는지 사람이 확인한다(기획 6절 표 "원인 품질").
원인 글 출처별로 30건씩 따로 뽑는다: 573 원인 칸(엔진 2 원인 문장 — 6절이 묻는 숫자) 30건, NHTSA 조사 요약 30건.

사용법:
    # 표시 시트 만들기 — 서버의 카드 벡터 로컬 사본(data/processed/defect/vector_cache/, 서버를 한 번 띄우면 생긴다)을 쓴다.
    # DB·유료 API 호출 없음
    uv run python -m scripts.defect_precedent.cause_quality sheet --out <폴더>   # cause_quality_573.csv·cause_quality_inv.csv
    # 사람이 표시한 뒤 비율 계산(시트마다)
    uv run python -m scripts.defect_precedent.cause_quality score --sheet <폴더>/cause_quality_573.csv

표본 규칙(2026-10-11, 표시를 보기 전에 고정 — 변경은 아래 "규칙 변경 기록". 표시 결과를 보고 고치지 않는다, AGENTS.md 5-2):
1. 749문항 대리 평가 질문을 시드 `SEED`로 섞는다.
2. 질문마다 서버 검색(`server.rag.search.Searcher`, DEC-039 — BM25 + bge-small RRF)의 결과 중 **서버 화면에 실제로 나오는
   카드**(`server.rag.customers.split` — 고객사 최대 5건 + 그 밖 10건)이면서 **합친 순위 10위 안**인 카드에서 **원인 글이 있는
   카드**를 모은다. 원인 글 = 573 원인 칸 원문
   (`server.rag.causes.cause_573`이 `filled`로 돌려주는 것 — 서버 응답과 같은 함수)
   또는 그 카드에 연결된 NHTSA 조사 요약(`server.rag.investigations`, 서버와 같은 연결 규칙). 단 **질문의 출처인 조사 자신의
   요약은 뺀다** — 질문 문장과 같은 글이라 원인 판단을 부풀린다.
3. 원인 글 출처(573 원인 칸 / 조사 요약)마다 따로: 그 출처의 (카드, 원인 글)만 모아 하나를 같은 시드의 난수로 고르고, 이미 고른 리콜 번호·이미 고른 원인 글(같은 573 보고서를 앞 6자리가
   같은 여러 리콜이 공유하고, 한 조사가 여러 리콜에 이어진다)은 건너뛴다. 출처마다 30건이 차면 멈춘다(두 시트는 서로 독립 — 같은 시드로 각각 처음부터).
4. 시트에는 질문·카드 원문·원인 글·말한 주체만 넣고 순위·검색 방식은 넣지 않는다. 표시(`label`)는 사람이 한다 — AI는 표시하지 않는다.

규칙 변경 기록: 처음 고정한 규칙(같은 날, 표본 지문 `9428e8162d635d85`)은 합친 순위 상위 10을 그대로 써서 서버가 고객사 카드를
5건만 보여 주는 질문에서 화면에 안 나오는 카드 2건(14·18번)이 섞였다(PR #73 리뷰). **누구도 표시하기 전에** 2번을 위처럼 고치고
같은 원인 글 중복 제외(3번)를 더해 다시 뽑았다 — 옛 시트는 쓰지 않는다. 바꾼 이유는 표본 결과가 아니라 "화면에 나오는 원인 글"이라는
정의와의 불일치다. 질문 30개는 그대로이고 **리콜 5건이 바뀌었다** — 화면 밖 카드 2건(PE02055·PE12027) + 2번 규칙으로 풀 크기가
달라져 같은 시드의 난수 선택이 연쇄로 바뀐 3건(PE11040·PE08020·PE04056). 3번 규칙만 켜면 옛 시트와 같다(리뷰 `c5dbc85` 분리 실험).
같은 날 시트 변조 검사 칸에 `maker`·`components`를 더해, 이어 573 원본 PDF 칸(`source_file`·`pdf_sha256`·`submission_date`)을
더해 같은 표본으로 두 번 더 다시 만들었다(표본 지문 `a0029d755f925dbe` 그대로, 표시 전).
**두 출처를 한 시트에 섞어 30건(573 13 · 조사 요약 17)을 뽑던 규칙은 표시 전에 바꿨다**(2026-10-11 사용자 결정 — 6절 "엔진 2 원인 문장"
숫자가 13건뿐이라 구간이 너무 넓어서, 이슈 #75). 섞은 시트는 쓰지 않는다(`score`가 거부한다). 바꾼 이유는 표시 결과가 아니라 표본 크기다.
같은 날 표시 기준도 기획 6절과 맞췄다: "원인이 맞는 문장인가"가 아니라 원인을 **말하는** 글인가(맞는지는 판정하지 않음 — 서비스 원칙 1).

표시 기준(시트의 `label`): `yes` = 이 글이 이 리콜의 결함 원인(왜 생겼나)을 말한다 / `no` = 원인을 말하지 않는다(현상·조사 경과·
"원인 미확인"만 등) / `unsure` = 판단하기 어렵다. 보고는 yes 비율(분모 = yes+no, unsure는 따로)과 Wilson 95% 구간을
시트마다(573 원인 칸 / 조사 요약) 따로 낸다 — 기획 6절 "엔진 2 원인 문장"에 해당하는 것은 573 시트 숫자다. 두 숫자를 합치지 않는다.
"""

import argparse
import csv
import hashlib
import json
import math
import random
import sys
from pathlib import Path

from scripts.defect_precedent.cause_trials import sample_sha, text_sha

SEED = 20261011
SOURCES = {"573": "cause_quality_573.csv", "조사 요약": "cause_quality_inv.csv"}
N = 30
TOP = 10
COLS = [
    "sample_no", "question_action", "question", "campno", "maker", "components", "defect",
    "cause_source", "speaker", "cause_ref", "source_file", "pdf_sha256", "submission_date", "cause_text",
    "text_sha256", "row_sha256", "label", "labeler_id", "note",
]  # fmt: skip
LABELS = ("yes", "no", "unsure")
# 표시자가 보는 칸 — 하나라도 바뀌면 채점을 멈춘다(원인 글은 text_sha256으로 따로 본다)
ROW_FIELDS = (
    "sample_no",
    "question_action",
    "question",
    "campno",
    "maker",
    "components",
    "defect",
    "cause_source",
    "speaker",
    "cause_ref",
    "source_file",
    "pdf_sha256",
    "submission_date",
    "cause_text",
)


def row_sha(r: dict) -> str:
    return text_sha("\n".join(r[k] for k in ROW_FIELDS))


def sample_fingerprint(rows: list[dict]) -> str:
    """표본 지문 — 줄 순서와 무관하다(표시자가 시트를 정렬해도 같은 표본이면 같다)."""
    return sample_sha(sorted((r["campno"] + ":" + r["cause_ref"], r["text_sha256"]) for r in rows))


def wilson(hits: int, n: int, z: float = 1.959963984540054) -> tuple[float, float] | None:
    if n == 0:
        return None
    p = hits / n
    center = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return round(max(0.0, center - half), 3), round(min(1.0, center + half), 3)


def cause_texts(
    card: dict, causes: dict, unreadable: dict, investigations: dict, question_action: str
) -> list[dict]:
    """서버가 이 카드에 붙여 보여 주는 원인 글들(573 원인 원문·조사 요약). 질문 출처 조사의 요약은 뺀다."""
    from server.rag.causes import SPEAKER_573, cause_573
    from server.rag.investigations import SPEAKER_INV

    out = []
    cause = cause_573(card, causes, unreadable)
    if cause["status"] == "filled":
        out.append(
            {
                "cause_source": "573",
                "speaker": SPEAKER_573,
                "cause_ref": cause["source"]["campaign"],
                # 어느 판본 PDF의 글인지(AGENTS.md 2-2·2-4) — 서버 응답의 cause.source와 같은 값
                "source_file": cause["source"]["file"],
                "pdf_sha256": cause["source"]["pdf_sha256"],
                "submission_date": cause["source"]["submission_date"],
                "cause_text": cause["text"],
            }  # fmt: skip
        )
    for inv in investigations.get(card["campno"], []):
        if inv["action"] != question_action:
            out.append(
                {
                    "cause_source": "조사 요약",
                    "speaker": SPEAKER_INV,
                    "cause_ref": inv["action"],
                    "source_file": "",  # 조사 요약은 cause_ref(조사 번호)로 되짚는다
                    "pdf_sha256": "",
                    "submission_date": "",
                    "cause_text": inv["summary"],
                }  # fmt: skip
            )
    return out


def draw(
    questions: list[dict],
    rankings: dict[str, list[str]],
    by_id: dict,
    causes: dict,
    unreadable: dict,
    investigations: dict,
    source: str,
) -> list[dict]:
    """표본 규칙 1~3을 원인 글 출처 하나(`source` = "573" 또는 "조사 요약")에 대해. rankings = 질문 번호 → 합친 순위."""
    from server.rag import customers

    rng = random.Random(SEED)
    order = list(questions)
    rng.shuffle(order)
    picked, seen, seen_text = [], set(), set()
    for q in order:
        ranking = rankings[q["action_no"]]
        cust, others = customers.split(ranking, by_id)
        shown = sorted(
            r for r in set(cust) | set(others) if r < TOP
        )  # 화면에 나오고 합친 순위 10위 안
        pool = [
            (cid, ct)
            for cid in (ranking[r] for r in shown)
            if cid not in seen
            for ct in cause_texts(by_id[cid], causes, unreadable, investigations, q["action_no"])
            if ct["cause_source"] == source and text_sha(ct["cause_text"]) not in seen_text
        ]
        if not pool:
            continue
        cid, ct = pool[rng.randrange(len(pool))]
        seen.add(cid)
        seen_text.add(text_sha(ct["cause_text"]))
        card = by_id[cid]
        row = {
            "sample_no": len(picked) + 1,
            "question_action": q["action_no"],
            "question": q["question"],
            "campno": cid,
            "maker": card["maker"],
            "components": "; ".join(card["components"]),
            "defect": card["defect"],
            **ct,
            "text_sha256": text_sha(ct["cause_text"]),
            "label": "",
            "labeler_id": "",
            "note": "",
        }
        row["sample_no"] = str(row["sample_no"])
        row["row_sha256"] = row_sha(row)
        picked.append(row)
        if len(picked) == N:
            break
    return picked


def cached_vectors(build_id: str, n: int):
    """서버가 쓴 카드 벡터 로컬 사본(`embeddings.load_vectors`). 옆의 sha256과 같을 때만 쓴다 — 값이 지금 모델과 같은지는
    `verify_probe`가 카드 16장을 다시 임베딩해 본다."""
    import numpy as np

    from server.rag import embeddings

    path = embeddings.CACHE_DIR / f"{build_id}_{embeddings.MODEL.replace('/', '_')}.npy"
    digest = path.with_suffix(".sha256")
    if not (path.exists() and digest.exists()):
        sys.exit(f"{path}가 없다 — 서버를 한 번 띄워(`uvicorn server.api:app`) 로컬 사본을 만든다")
    if digest.read_text().strip() != hashlib.sha256(path.read_bytes()).hexdigest():
        sys.exit(f"{path.name}이 옆의 sha256과 다르다 — 서버를 다시 띄워 사본을 새로 받는다")
    vecs = np.load(path)
    if vecs.shape != (n, 384):
        sys.exit(f"{path.name}의 모양 {vecs.shape}이 카드 수 {n}과 맞지 않는다")
    return vecs


def cmd_sheet(a) -> None:
    import fastembed
    from fastembed import TextEmbedding

    from scripts.defect_precedent.nhtsa import OUT_DIR
    from scripts.defect_precedent.retrieval_compare import card_text, load
    from server.rag import embeddings
    from server.rag.build import load_build
    from server.rag.investigations import load_investigations
    from server.rag.search import Searcher

    sheets = {src: a.out / name for src, name in SOURCES.items()}
    for sheet in sheets.values():
        if sheet.exists() or sheet.with_name(sheet.name + ".meta.json").exists():
            # 표시한 시트를 빈 시트로 덮어쓰지 않는다 — 다시 만들려면 사람이 폴더를 옮기거나 지운다
            sys.exit(
                f"{a.out}에 시트·메타가 이미 있다 — 표시를 덮어쓰지 않게 멈춘다(새 폴더를 쓴다)"
            )
    build = load_build()
    embeddings.check_fastembed()
    texts = [card_text(c) for c in build.cards]
    vecs = cached_vectors(build.build_id, len(texts))
    model = TextEmbedding(embeddings.MODEL)
    embeddings.verify_probe(model, texts, vecs)
    searcher = Searcher(build.cards, vecs, model)
    invs = load_investigations(build.raw_manifest_sha256, {c["campno"] for c in build.cards})
    _, questions = load()
    qv = searcher.query_vectors([q["question"] for q in questions])
    rankings = {
        q["action_no"]: searcher.search(q["question"], v).ranking
        for q, v in zip(questions, qv, strict=True)
    }
    by_id = {c["campno"]: c for c in build.cards}
    drawn = {
        src: draw(questions, rankings, by_id, build.causes, build.unreadable, invs, src)
        for src in SOURCES
    }
    short = {src: len(rows) for src, rows in drawn.items() if len(rows) != N}
    if short:
        sys.exit(
            f"표본이 {short}건뿐이다 — 규칙대로 출처마다 {N}건을 채우지 못해 시트를 만들지 않는다"
        )
    a.out.mkdir(parents=True, exist_ok=True)
    for src, rows in drawn.items():
        sheet = sheets[src]
        with sheet.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            w.writeheader()
            w.writerows(rows)
        meta = {
            "build_id": build.build_id,
            "seed": SEED,
            "source": src,
            "n": len(rows),
            "top": TOP,
            "sample_sha256": sample_fingerprint(rows),
            # 줄마다 읽기 전용 칸 — 채점 때 어느 줄의 어느 칸이 바뀌었는지 알려 주려고 둔다(스프레드시트가 21E027을 숫자로 바꾸는 등)
            "rows": [
                {k: r[k] for k in ("sample_no", *ROW_FIELDS[1:], "text_sha256")} for r in rows
            ],
            # 다시 뽑아 표본이 달라졌을 때 무엇이 달라졌는지 되짚는 입력(AGENTS.md 5-1)
            "eval_sha256": hashlib.sha256((OUT_DIR / "eval.jsonl").read_bytes()).hexdigest(),
            "raw_manifest_sha256": build.raw_manifest_sha256,
            "fastembed": fastembed.__version__,
            "model": embeddings.MODEL,
            "sheet_sha256": hashlib.sha256(sheet.read_bytes()).hexdigest(),
        }
        sheet.with_name(sheet.name + ".meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=1), "utf-8"
        )
        print(
            json.dumps(
                {k: v for k, v in meta.items() if k != "rows"} | {"sheet": str(sheet)},
                ensure_ascii=False,
            )
        )


def norm(label: str) -> str:
    return label.strip().lower()  # 스프레드시트가 첫 글자를 대문자로 바꾸는 경우(Yes)


def score(rows: list[dict]) -> dict:
    edited = [r["sample_no"] for r in rows if text_sha(r["cause_text"]) != r["text_sha256"]]
    if edited:
        sys.exit(f"시트의 cause_text가 text_sha256과 다르다(원문을 고치지 않는다): {edited[:5]}")
    changed = [r["sample_no"] for r in rows if row_sha(r) != r["row_sha256"]]
    if changed:
        sys.exit(
            f"질문·카드(회사·부품·결함)·원인 글·말한 주체 칸이 만들 때와 다르다(표시 칸만 고친다): {changed[:5]}"
        )
    bad = [r["sample_no"] for r in rows if norm(r["label"]) not in LABELS]
    if bad:
        sys.exit(f"표시가 비었거나 yes/no/unsure가 아닌 줄: {bad[:5]}")
    no_id = [r["sample_no"] for r in rows if not r["labeler_id"].strip()]
    if no_id:
        sys.exit(f"labeler_id가 빈 줄: {no_id[:5]}")

    def rate(sub: list[dict]) -> dict:
        count = {lab: sum(norm(r["label"]) == lab for r in sub) for lab in LABELS}
        decided = count["yes"] + count["no"]
        return {
            "n": len(sub),
            "counts": count,
            "yes_rate": round(count["yes"] / decided, 3) if decided else None,
            "yes_rate_wilson95": wilson(count["yes"], decided),
        }

    sources = sorted({r["cause_source"] for r in rows})
    return {
        **rate(rows),
        "by_source": {src: rate([r for r in rows if r["cause_source"] == src]) for src in sources},
        "note": "분모 = yes+no(unsure는 따로). 749문항 대리 평가 질문 30개에서, 서버 화면에 나오고 합친 순위 10위 안인 카드의 원인 글이"
        " 원인을 말하는 비율 — 서비스 전체 원인 품질이 아니고, 원인이 옳은지는 판정하지 않는다",
    }


def cmd_score(a) -> None:
    try:
        with a.sheet.open(encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
    except UnicodeDecodeError:  # 스프레드시트가 cp949 등으로 저장한 경우
        sys.exit(f"{a.sheet.name}을 UTF-8로 읽지 못한다 — 스프레드시트에서 'CSV UTF-8'로 저장한다")
    meta_path = a.sheet.with_name(a.sheet.name + ".meta.json")
    meta = json.loads(meta_path.read_text("utf-8")) if meta_path.exists() else None
    if meta is None:
        sys.exit(f"{meta_path.name}이 없다 — 시트를 만든 기록 없이 채점하지 않는다")
    # 출처별 시트만 채점한다 — 버린 섞인 시트(메타에 source 없음)·출처가 섞인 줄은 거부(리뷰 acaa624). 줄 수는 아래에서 n·N과 직접 대조한다
    if meta.get("source") not in SOURCES:
        sys.exit(
            f"메타에 출처(source)가 없거나 알 수 없다({meta.get('source')!r}) — 버린 옛 시트일 수 있다. 출처별 시트({list(SOURCES.values())})를 쓴다"
        )
    mixed = sorted({r.get("cause_source") for r in rows} - {meta["source"]})
    if mixed:
        sys.exit(f"시트에 다른 출처의 줄이 있다 {mixed} — 출처마다 따로 채점한다")
    changed = [
        f"{m['sample_no']}번 {k}: {m[k]!r} → {r.get(k)!r}"
        for m in meta.get("rows", [])
        for r in rows
        if r.get("sample_no") == m["sample_no"]
        for k in m
        if r.get(k) != m[k]
    ]
    if changed:
        sys.exit(
            "시트의 읽기 전용 칸이 만들 때와 다르다 — 스프레드시트가 값을 바꿨을 수 있다(모든 칸을 텍스트로 가져온다): "
            + "; ".join(changed[:5])
        )
    # 표본 지문도 줄 추가·삭제를 잡지만, 줄 수 불일치를 직접 알려 준다
    if not meta.get("n") == len(rows) == N:
        sys.exit(f"시트의 줄 수 {len(rows)}가 메타의 n={meta.get('n')!r}·표본 크기 {N}와 다르다")
    if sample_fingerprint(rows) != meta["sample_sha256"]:
        sys.exit(
            "시트의 표본이 만들 때와 다르다(줄을 빼거나 더했거나 리콜·원인 글이 바뀌었다 — 줄 순서는 상관없다)"
        )
    print(
        json.dumps(
            {**score(rows), "build_id": meta["build_id"], "seed": meta["seed"]},
            ensure_ascii=False,
            indent=1,
        )
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sh = sub.add_parser("sheet", help="표시 시트 만들기")
    sh.add_argument("--out", type=Path, required=True)
    sc = sub.add_parser("score", help="표시한 시트로 비율 계산")
    sc.add_argument("--sheet", type=Path, required=True)
    a = p.parse_args(argv)
    {"sheet": cmd_sheet, "score": cmd_score}[a.cmd](a)


if __name__ == "__main__":
    main()

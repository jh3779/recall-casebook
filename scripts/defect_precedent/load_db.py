"""결함 선례 데이터를 Supabase(Postgres)에 올린다. DEC-034.

사용법 (연결 문자열은 .env의 DATABASE_URL — 이 스크립트는 값을 출력하지 않는다):
    uv run python -m scripts.defect_precedent.load_db check                        # DB 없이 파일만 검증 (건수·날짜·해시·정답 대조)
    uv run --env-file .env python -m scripts.defect_precedent.load_db schema      # schema.sql 적용
    uv run --env-file .env python -m scripts.defect_precedent.load_db load        # 파일 검증 → 한 번의 트랜잭션으로 upsert → 건수 대조

- 올리기 전에 `build.json`의 sha256과 파일이 같은지 본다. 다르면 중단한다 (어느 원본에서 나온 데이터인지 잃지 않기 위해).
- 날짜는 YYYYMMDD(snapshot_date는 YYYY-MM-DD)를 엄격하게 읽는다. 틀리면 몇 번째 줄인지 알려 주고 중단한다 — 고쳐서 올리지 않는다.
- 빈 문자열은 NULL로 바꾸지 않고 원본 그대로 올린다.
- `load`는 여러 번 돌려도 된다 (upsert). 오류가 나면 트랜잭션 전체를 되돌린다.
"""

import hashlib
import json
import os
import re
import sys
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed" / "defect"
SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA = SCRIPT_DIR / "schema.sql"
BATCH = 2000


def parse_date(value: str, where: str) -> date:
    """YYYYMMDD 또는 YYYY-MM-DD만 받는다. 그 밖의 모양은 추측하지 않고 중단한다."""
    for pattern, fmt in ((r"\d{8}", "%Y%m%d"), (r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d")):
        if re.fullmatch(pattern, value):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                break
    sys.exit(f"날짜를 읽지 못했다: {where} 값 {value!r}")


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def causes_path() -> Path:
    full = PROCESSED / "causes.jsonl"
    return full if full.exists() else PROCESSED / "causes_sample.jsonl"


def load_files() -> dict:
    """파일을 읽어 검증하고 테이블별 행을 돌려준다. DB는 쓰지 않는다."""
    build = json.loads((PROCESSED / "build.json").read_text(encoding="utf-8"))
    for name, key in (("recalls.jsonl", "recalls_sha256"), ("eval.jsonl", "eval_sha256")):
        actual = sha256_of(PROCESSED / name)
        if actual != build[key]:
            sys.exit(
                f"{name}의 sha256이 build.json과 다르다 — 어느 원본에서 나온 파일인지 확인한다 (파일 {actual[:12]}…, 기록 {build[key][:12]}…)"
            )

    snapshot = parse_date(build["snapshot_date"], "build.json snapshot_date")
    builds = [
        {
            "snapshot_date": snapshot,
            "raw_manifest_sha256": build["raw_manifest_sha256"],
            "recalls_sha256": build["recalls_sha256"],
            "eval_sha256": build["eval_sha256"],
        }
    ]

    recalls = []
    for i, r in enumerate(read_jsonl(PROCESSED / "recalls.jsonl"), 1):
        if parse_date(r["snapshot_date"], f"recalls.jsonl {i}번째 줄 snapshot_date") != snapshot:
            sys.exit(f"recalls.jsonl {i}번째 줄의 snapshot_date가 build.json과 다르다")
        recalls.append(
            {
                "campno": r["campno"],
                "maker": r["maker"],
                "raw_maker": r["raw_maker"],
                "components": r["components"],
                "defect": r["defect"],
                "consequence": r["consequence"],
                "remedy": r["remedy"],
                "received_date": parse_date(
                    r["received_date"], f"recalls.jsonl {i}번째 줄 received_date"
                ),
                "recall_type": r["recall_type"],
                "influenced_by": r["influenced_by"],
                "dup_group": r["dup_group"],
                "snapshot_date": snapshot,
            }
        )
    campnos = {r["campno"] for r in recalls}
    if len(campnos) != len(recalls):
        sys.exit("recalls.jsonl에 campno가 겹치는 줄이 있다")

    questions = []
    for i, q in enumerate(read_jsonl(PROCESSED / "eval.jsonl"), 1):
        missing = [c for c in q["gold_campnos"] if c not in campnos]
        if missing:
            sys.exit(
                f"eval.jsonl {i}번째 줄 {q['action_no']}의 정답 리콜이 recalls에 없다: {missing[:3]}"
            )
        questions.append(
            {
                "action_no": q["action_no"],
                "question": q["question"],
                "open_date": parse_date(q["open_date"], f"eval.jsonl {i}번째 줄 open_date"),
                "gold_campnos": q["gold_campnos"],
                "sets": q["set"],
            }
        )
    if len({q["action_no"] for q in questions}) != len(questions):
        sys.exit("eval.jsonl에 action_no가 겹치는 줄이 있다")

    campaigns6 = {c[:6] for c in campnos}
    causes = []
    for i, c in enumerate(read_jsonl(causes_path()), 1):
        if c["campaign"] not in campaigns6:
            sys.exit(
                f"{causes_path().name} {i}번째 줄 {c['campaign']}이 recalls의 어느 campno 앞 6자리와도 맞지 않는다"
            )
        sub = c["submission_date"]
        causes.append(
            {
                "campaign": c["campaign"],
                "versions": c["versions"],
                "source_file": c["source_file"],
                "submission_date": parse_date(
                    sub, f"{causes_path().name} {i}번째 줄 submission_date"
                )
                if sub
                else None,
                "cause_text": c["cause_text"],
                "cause_status": c["cause_status"],
                "supplier_names": c["supplier_names"],
                "supplier_countries": c["supplier_countries"],
                "new_form": c["new_form"],
                "pdfs": json.dumps(c["pdfs"], ensure_ascii=False),
                "resolution": c["resolution"],
                "unresolved_reasons": c["unresolved_reasons"],
            }
        )
    if len({c["campaign"] for c in causes}) != len(causes):
        sys.exit("causes에 campaign이 겹치는 줄이 있다")

    return {
        "data_builds": builds,
        "recalls": recalls,
        "eval_questions": questions,
        "causes": causes,
    }


# 테이블별 (칸 목록, 기본키) — 순서가 외래 키 순서다
TABLES = {
    "data_builds": (
        ["snapshot_date", "raw_manifest_sha256", "recalls_sha256", "eval_sha256"],
        "snapshot_date",
    ),
    "recalls": (
        [
            "campno",
            "maker",
            "raw_maker",
            "components",
            "defect",
            "consequence",
            "remedy",
            "received_date",
            "recall_type",
            "influenced_by",
            "dup_group",
            "snapshot_date",
        ],
        "campno",
    ),  # fmt: skip
    "eval_questions": (["action_no", "question", "open_date", "gold_campnos", "sets"], "action_no"),
    "causes": (
        [
            "campaign",
            "versions",
            "source_file",
            "submission_date",
            "cause_text",
            "cause_status",
            "supplier_names",
            "supplier_countries",
            "new_form",
            "pdfs",
            "resolution",
            "unresolved_reasons",
        ],
        "campaign",
    ),  # fmt: skip
}


def upsert_sql(table: str) -> str:
    cols, key = TABLES[table]
    names = ", ".join(cols)
    marks = ", ".join(f"%({c})s" for c in cols)
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != key)
    return f"insert into {table} ({names}) values ({marks}) on conflict ({key}) do update set {updates}"


def connect():
    import psycopg

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit(
            "환경변수 DATABASE_URL이 없다 — .env에 넣고 `uv run --env-file .env …`로 실행한다 (.env.example 참고)"
        )
    return psycopg.connect(url)


def cmd_check() -> None:
    data = load_files()
    for table, rows in data.items():
        print(f"{table}: {len(rows):,}줄")
    print(f"causes 파일: {causes_path().name}")
    print("검증 통과 (해시·날짜·겹침·정답 리콜·캠페인 연결) — DB에는 아무것도 쓰지 않았다")


def cmd_schema() -> None:
    with connect() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    print("schema.sql 적용 완료")


def cmd_load() -> None:
    data = load_files()
    with connect() as conn:  # 블록이 정상 종료하면 commit, 예외면 rollback
        with conn.cursor() as cur:
            for table in TABLES:
                rows = data[table]
                sql = upsert_sql(table)
                for start in range(0, len(rows), BATCH):
                    cur.executemany(sql, rows[start : start + BATCH])
                print(f"{table}: {len(rows):,}줄 upsert")
            for table in TABLES:
                (n,) = cur.execute(f"select count(*) from {table}").fetchone()
                if n != len(data[table]):
                    sys.exit(f"{table}: DB {n:,}줄 ≠ 파일 {len(data[table]):,}줄 — 되돌린다")
    print("적재 완료 — 건수 대조 통과")


def main() -> None:
    commands = {"check": cmd_check, "schema": cmd_schema, "load": cmd_load}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()


if __name__ == "__main__":
    main()

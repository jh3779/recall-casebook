"""결함 선례 데이터를 Supabase(Postgres)에 올린다. DEC-034.

사용법 (연결 문자열은 .env의 DATABASE_URL — 이 스크립트는 값을 출력하지 않는다):
    uv run python -m scripts.defect_precedent.load_db check --causes sample
    uv run --env-file .env python -m scripts.defect_precedent.load_db schema
    uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes sample
    uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes full --expect-rows 12000
    uv run --env-file .env python -m scripts.defect_precedent.load_db prune --keep 2 [--apply]

- `check`는 DB 없이 파일만 검증한다 (해시·날짜·겹침·정답 리콜·캠페인 연결).
- 스냅샷별로 보관한다: 줄마다 snapshot_date를 두고 새 스냅샷을 올려도 지난 스냅샷은 그대로 둔다. 같은 스냅샷을 다시 올리면
  그 스냅샷의 줄만 통째로 바꾼다. 같은 날짜인데 원본·카드·시험지 해시가 다르면 덮어쓰지 않고 중단한다.
- `--causes`는 반드시 적는다 (파일을 자동으로 고르지 않는다). `sample`은 causes_sample.jsonl, `full`은 causes.jsonl이고
  `full`은 `--expect-rows N`(사람이 아는 기대 건수)이 같아야 올린다 — 중간까지만 만들어진 파일을 막는다.
- 올리기 전에 `build.json`의 sha256과 파일을 대조하고, 어느 원인 파일을 올렸는지(종류·이름·sha256·건수)를 data_builds에 남긴다.
- 직전 스냅샷과 비교해 새로 생김·바뀜(칸별)·사라짐·그대로 건수를 계산해 data_builds.change_summary에 남긴다.
- 날짜는 칸마다 정해진 형식(YYYYMMDD, snapshot_date는 YYYY-MM-DD)만 받는다. 틀리면 몇 번째 줄인지 알려 주고 중단한다.
- 빈 문자열은 NULL로 바꾸지 않고 원본 그대로 올린다.
- `prune`은 오래된 스냅샷의 데이터 줄만 지우고 data_builds 줄은 pruned_at 표시와 함께 남긴다. `--apply` 없이는 지우지 않는다.
- 오류가 나면 트랜잭션 전체를 되돌린다.
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import date, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed" / "defect"
SCHEMA = Path(__file__).resolve().parent / "schema.sql"
BATCH = 2000
CAUSES_FILES = {"sample": "causes_sample.jsonl", "full": "causes.jsonl"}

# 테이블별 기본키 칸과 데이터 칸. DB 칸은 snapshot_date + 데이터 칸 + row_sha256이다 (campaign6은 DB가 계산)
TABLES = {
    "recalls": {
        "key": "campno",
        "cols": [
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
        ],
    },  # fmt: skip
    "eval_questions": {
        "key": "action_no",
        "cols": ["action_no", "question", "open_date", "gold_campnos", "sets"],
    },
    "causes": {
        "key": "campaign",
        "cols": [
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
    },  # fmt: skip
}
BUILD_COLS = [
    "snapshot_date", "raw_manifest_sha256", "recalls_sha256", "eval_sha256", "causes_kind", "causes_file",
    "causes_sha256", "causes_rows", "causes_expected_rows", "change_summary",
]  # fmt: skip


def db_columns(table: str) -> list[str]:
    return ["snapshot_date", *TABLES[table]["cols"], "row_sha256"]


def _parse(value, pattern: str, fmt: str, where: str) -> date:
    if isinstance(value, str) and re.fullmatch(pattern, value):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    sys.exit(f"날짜를 읽지 못했다: {where} 값 {value!r} ({fmt} 형식만 받는다)")


def parse_compact(value, where: str) -> date:
    """YYYYMMDD만 받는다. 그 밖의 모양은 추측하지 않고 중단한다."""
    return _parse(value, r"\d{8}", "%Y%m%d", where)


def parse_iso(value, where: str) -> date:
    """YYYY-MM-DD만 받는다."""
    return _parse(value, r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d", where)


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_sha256(row: dict, cols: list[str]) -> str:
    """데이터 칸 전체의 해시. 같은 내용이면 항상 같은 값이다 (칸 순서·날짜 표기에 영향받지 않는다)."""
    plain = {c: row[c].isoformat() if isinstance(row[c], date) else row[c] for c in cols}
    return hashlib.sha256(
        json.dumps(plain, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _seal(rows: list[dict], table: str, snapshot: date) -> list[dict]:
    cols = TABLES[table]["cols"]
    return [{**r, "snapshot_date": snapshot, "row_sha256": row_sha256(r, cols)} for r in rows]


def causes_source(data_dir: Path, kind: str, expect_rows: int | None) -> Path:
    if kind == "full" and expect_rows is None:
        sys.exit(
            "--causes full은 --expect-rows N(기대 건수)이 필요하다 — 중간까지만 만들어진 파일을 막기 위해서다"
        )
    if kind == "sample" and expect_rows is not None:
        sys.exit("--expect-rows는 --causes full에서만 쓴다")
    path = data_dir / CAUSES_FILES[kind]
    if not path.exists():
        sys.exit(f"{path.name}이 없다 ({data_dir})")
    return path


def load_files(data_dir: Path, causes_kind: str, expect_rows: int | None = None) -> dict:
    """파일을 읽어 검증하고 테이블별 행을 돌려준다. DB는 쓰지 않는다."""
    causes_file = causes_source(data_dir, causes_kind, expect_rows)
    build = json.loads((data_dir / "build.json").read_text(encoding="utf-8"))
    for name, key in (("recalls.jsonl", "recalls_sha256"), ("eval.jsonl", "eval_sha256")):
        actual = sha256_of(data_dir / name)
        if actual != build[key]:
            sys.exit(
                f"{name}의 sha256이 build.json과 다르다 — 어느 원본에서 나온 파일인지 확인한다 "
                f"(파일 {actual[:12]}…, 기록 {build[key][:12]}…)"
            )
    snapshot = parse_iso(build["snapshot_date"], "build.json snapshot_date")

    recalls = []
    for i, r in enumerate(read_jsonl(data_dir / "recalls.jsonl"), 1):
        if parse_iso(r["snapshot_date"], f"recalls.jsonl {i}번째 줄 snapshot_date") != snapshot:
            sys.exit(f"recalls.jsonl {i}번째 줄의 snapshot_date가 build.json과 다르다")
        recalls.append(
            {
                **{c: r[c] for c in TABLES["recalls"]["cols"] if c != "received_date"},
                "received_date": parse_compact(
                    r["received_date"], f"recalls.jsonl {i}번째 줄 received_date"
                ),
            }
        )
    campnos = {r["campno"] for r in recalls}
    if len(campnos) != len(recalls):
        sys.exit("recalls.jsonl에 campno가 겹치는 줄이 있다")

    questions = []
    for i, q in enumerate(read_jsonl(data_dir / "eval.jsonl"), 1):
        missing = [c for c in q["gold_campnos"] if c not in campnos]
        if missing:
            sys.exit(
                f"eval.jsonl {i}번째 줄 {q['action_no']}의 정답 리콜이 recalls에 없다: {missing[:3]}"
            )
        questions.append(
            {
                "action_no": q["action_no"],
                "question": q["question"],
                "open_date": parse_compact(q["open_date"], f"eval.jsonl {i}번째 줄 open_date"),
                "gold_campnos": q["gold_campnos"],
                "sets": q["set"],
            }
        )
    if len({q["action_no"] for q in questions}) != len(questions):
        sys.exit("eval.jsonl에 action_no가 겹치는 줄이 있다")

    campaigns6 = {c[:6] for c in campnos}
    causes = []
    for i, c in enumerate(read_jsonl(causes_file), 1):
        if c["campaign"] not in campaigns6:
            sys.exit(
                f"{causes_file.name} {i}번째 줄 {c['campaign']}이 recalls의 어느 campno 앞 6자리와도 맞지 않는다"
            )
        sub = c["submission_date"]
        causes.append(
            {
                **{k: c[k] for k in TABLES["causes"]["cols"] if k != "submission_date"},
                "submission_date": parse_compact(
                    sub, f"{causes_file.name} {i}번째 줄 submission_date"
                )
                if sub
                else None,
            }
        )
    if len({c["campaign"] for c in causes}) != len(causes):
        sys.exit("causes에 campaign이 겹치는 줄이 있다")
    if expect_rows is not None and len(causes) != expect_rows:
        sys.exit(
            f"{causes_file.name}이 {len(causes):,}줄이다 — 기대 건수 {expect_rows:,}줄과 다르다 "
            "(중간까지만 만들어진 파일인지 확인한다)"
        )

    return {
        "build": {
            "snapshot_date": snapshot,
            "raw_manifest_sha256": build["raw_manifest_sha256"],
            "recalls_sha256": build["recalls_sha256"],
            "eval_sha256": build["eval_sha256"],
            "causes_kind": causes_kind,
            "causes_file": causes_file.name,
            "causes_sha256": sha256_of(causes_file),
            "causes_rows": len(causes),
            "causes_expected_rows": expect_rows,
        },
        "recalls": _seal(recalls, "recalls", snapshot),
        "eval_questions": _seal(questions, "eval_questions", snapshot),
        "causes": _seal(causes, "causes", snapshot),
    }


def diff_rows(prev: dict[str, dict], new: dict[str, dict], cols: list[str]) -> dict:
    """같은 번호끼리 비교해 새로 생김·바뀜·사라짐·그대로 건수와, 바뀐 줄에서 달라진 칸별 건수를 센다."""
    changed = unchanged = 0
    columns: Counter = Counter()
    for key in new.keys() & prev.keys():
        if new[key]["row_sha256"] == prev[key]["row_sha256"]:
            unchanged += 1
            continue
        changed += 1
        columns.update(c for c in cols if new[key][c] != prev[key][c])
    return {
        "new": len(new.keys() - prev.keys()),
        "changed": changed,
        "removed": len(prev.keys() - new.keys()),
        "unchanged": unchanged,
        "changed_columns": dict(sorted(columns.items())),
    }


def summarize_changes(prev_date: date | None, prev: dict[str, dict], data: dict) -> dict:
    if prev_date is None:
        return {"vs": None, "note": "첫 스냅샷 — 비교할 이전 스냅샷이 없다"}
    summary: dict = {"vs": prev_date.isoformat()}
    for table, spec in TABLES.items():
        new = {r[spec["key"]]: r for r in data[table]}
        summary[table] = diff_rows(prev[table], new, spec["cols"])
    return summary


def describe_changes(summary: dict) -> list[str]:
    if summary.get("vs") is None:
        return [summary["note"]]
    lines = [f"직전 스냅샷({summary['vs']}) 대비"]
    for table in TABLES:
        d = summary[table]
        cols = ", ".join(f"{c} {n:,}" for c, n in d["changed_columns"].items())
        lines.append(
            f"  {table}: 새로 생김 {d['new']:,} · 바뀜 {d['changed']:,} · 사라짐 {d['removed']:,} · 그대로 {d['unchanged']:,}"
            + (f" (바뀐 칸: {cols})" if cols else "")
        )
    return lines


def upsert_build_sql() -> str:
    names = ", ".join(BUILD_COLS)
    marks = ", ".join(f"%({c})s" for c in BUILD_COLS)
    updates = ", ".join(f"{c} = excluded.{c}" for c in BUILD_COLS if c != "snapshot_date")
    return (
        f"insert into data_builds ({names}) values ({marks}) "
        f"on conflict (snapshot_date) do update set {updates}, loaded_at = now(), pruned_at = null"
    )


def insert_sql(table: str) -> str:
    cols = db_columns(table)
    return f"insert into {table} ({', '.join(cols)}) values ({', '.join(f'%({c})s' for c in cols)})"


def _params(row: dict) -> dict:
    from psycopg.types.json import Jsonb

    return {k: Jsonb(v) if k in ("pdfs", "change_summary") else v for k, v in row.items()}


def connect():
    import psycopg

    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit(
            "환경변수 DATABASE_URL이 없다 — .env에 넣고 `uv run --env-file .env …`로 실행한다 (.env.example 참고)"
        )
    return psycopg.connect(url)


def _data_dir(args) -> Path:
    return Path(args.data_dir) if args.data_dir else PROCESSED


def cmd_check(args) -> None:
    data = load_files(_data_dir(args), args.causes, args.expect_rows)
    print(
        f"data_builds: 1줄 (스냅샷 {data['build']['snapshot_date']}, 원인 파일 {data['build']['causes_file']})"
    )
    for table in TABLES:
        print(f"{table}: {len(data[table]):,}줄")
    print("검증 통과 (해시·날짜·겹침·정답 리콜·캠페인 연결) — DB에는 아무것도 쓰지 않았다")


def cmd_schema(args) -> None:
    with connect() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    print("schema.sql 적용 완료")


def cmd_load(args) -> None:
    from psycopg.rows import dict_row

    data = load_files(_data_dir(args), args.causes, args.expect_rows)
    build = data["build"]
    snapshot = build["snapshot_date"]
    with connect() as conn:  # 블록이 정상 종료하면 commit, 예외(SystemExit 포함)면 rollback
        with conn.cursor(row_factory=dict_row) as cur:
            same = cur.execute(
                "select raw_manifest_sha256, recalls_sha256, eval_sha256 from data_builds where snapshot_date = %s",
                (snapshot,),
            ).fetchone()
            hashes = (build["raw_manifest_sha256"], build["recalls_sha256"], build["eval_sha256"])
            if same and tuple(same.values()) != hashes:
                sys.exit(
                    f"스냅샷 {snapshot}이 이미 올라가 있는데 원본·카드·시험지 해시가 다르다 — "
                    "같은 날짜의 다른 빌드를 덮어쓰지 않는다 (날짜가 다르게 새로 받거나 prune으로 지운 뒤 올린다)"
                )
            prev_date = cur.execute(
                "select max(snapshot_date) as d from data_builds where snapshot_date < %s and pruned_at is null",
                (snapshot,),
            ).fetchone()["d"]
            prev: dict[str, dict] = {}
            if prev_date:
                for table, spec in TABLES.items():
                    cols = [c for c in db_columns(table) if c != "snapshot_date"]
                    rows = cur.execute(
                        f"select {', '.join(cols)} from {table} where snapshot_date = %s",
                        (prev_date,),
                    ).fetchall()
                    prev[table] = {r[spec["key"]]: r for r in rows}
            summary = summarize_changes(prev_date, prev, data)

            cur.execute(upsert_build_sql(), _params({**build, "change_summary": summary}))
            for table in TABLES:
                rows = data[table]
                cur.execute(
                    f"delete from {table} where snapshot_date = %s", (snapshot,)
                )  # 이 스냅샷만 통째로 바꾼다
                sql = insert_sql(table)
                for start in range(0, len(rows), BATCH):
                    cur.executemany(sql, [_params(r) for r in rows[start : start + BATCH]])
                print(f"{table}: {len(rows):,}줄")
            for table in TABLES:
                n = cur.execute(
                    f"select count(*) as n from {table} where snapshot_date = %s", (snapshot,)
                ).fetchone()["n"]
                if n != len(data[table]):
                    sys.exit(f"{table}: DB {n:,}줄 ≠ 파일 {len(data[table]):,}줄 — 되돌린다")
    print(f"스냅샷 {snapshot} 적재 완료 — 건수 대조 통과")
    print("\n".join(describe_changes(summary)))


def cmd_prune(args) -> None:
    if args.keep < 1:
        sys.exit("--keep은 1 이상이다 (최신 스냅샷은 남긴다)")
    with connect() as conn:
        snaps = [
            r[0]
            for r in conn.execute(
                "select snapshot_date from data_builds where pruned_at is null order by snapshot_date desc"
            ).fetchall()
        ]
        old = snaps[args.keep :]
        if not old:
            print(f"데이터가 남아 있는 스냅샷 {len(snaps)}개 — 지울 것이 없다 (--keep {args.keep})")
            return
        for snap in old:
            counts = {
                t: conn.execute(
                    f"select count(*) from {t} where snapshot_date = %s", (snap,)
                ).fetchone()[0]
                for t in TABLES
            }
            print(f"{snap}: " + " · ".join(f"{t} {n:,}줄" for t, n in counts.items()))
        if not args.apply:
            print(
                f"위 스냅샷 {len(old)}개의 데이터 줄을 지우고 data_builds에는 pruned_at을 표시한다 — 실행하려면 --apply"
            )
            return
        for table in TABLES:
            conn.execute(f"delete from {table} where snapshot_date = any(%s)", (old,))
        conn.execute(
            "update data_builds set pruned_at = now() where snapshot_date = any(%s)", (old,)
        )
    print(f"스냅샷 {len(old)}개 정리 완료 — data_builds 줄은 pruned_at 표시와 함께 남아 있다")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="load_db", description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    def add_source_args(p):
        p.add_argument(
            "--causes",
            required=True,
            choices=sorted(CAUSES_FILES),
            help="올릴 원인 파일 종류 (자동으로 고르지 않는다)",
        )
        p.add_argument("--expect-rows", type=int, help="--causes full일 때 기대 건수")
        p.add_argument("--data-dir", help=f"파일 폴더 (기본 {PROCESSED.relative_to(REPO_ROOT)})")

    add_source_args(sub.add_parser("check", help="DB 없이 파일만 검증"))
    sub.add_parser("schema", help="schema.sql 적용")
    add_source_args(sub.add_parser("load", help="스냅샷 1개를 올린다"))
    prune = sub.add_parser("prune", help="오래된 스냅샷의 데이터 줄을 지운다")
    prune.add_argument("--keep", type=int, required=True, help="남길 스냅샷 개수 (최신부터)")
    prune.add_argument(
        "--apply", action="store_true", help="실제로 지운다 (없으면 목록만 보여 준다)"
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    {"check": cmd_check, "schema": cmd_schema, "load": cmd_load, "prune": cmd_prune}[args.command](
        args
    )


if __name__ == "__main__":
    main()

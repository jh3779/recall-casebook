"""결함 선례 데이터를 Supabase(Postgres)에 올린다. DEC-034.

사용법 (연결 문자열은 .env의 DATABASE_URL — 이 스크립트는 값을 출력하지 않는다):
    uv run python -m scripts.defect_precedent.load_db check --causes sample
    uv run --env-file .env python -m scripts.defect_precedent.load_db schema
    uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes sample
    uv run --env-file .env python -m scripts.defect_precedent.load_db load --causes full

- `check`는 DB 없이 파일만 검증한다 (해시·날짜·겹침·정답 리콜·캠페인 연결·원인 파일 명세 대조).
- **build 단위로 보관한다.** build_id는 입력 파일 4개(원본 명세·카드·시험지·원인 파일)의 sha256으로 정해지는 불변 식별자다.
  내용이 하나라도 다르면 다른 build라서, 같은 날짜(snapshot_date)라도 덮어쓰지 않고 둘 다 보관한다
  (예: 같은 날짜의 표본 build와 전체 build). 같은 build를 다시 올리면 그 build의 줄만 통째로 바꾼다 (내용이 같다).
  조회용 `*_latest` 뷰는 가장 최근 날짜의 build를 고르고, 같은 날짜면 전체본이 표본보다 우선한다.
- 원인 파일의 완전성은 **사람이 입력한 숫자가 아니라 독립된 명세**와 대조한다. `--causes`는 반드시 적는다 (자동으로 고르지 않는다).
  - `sample`: 커밋된 기준 파일(`baseline_2026-10-06.json`)의 `rclrpt_sample` 캠페인 목록과 정확히 같아야 한다.
  - `full`: `rclrpt all`이 완성본과 함께 만드는 `causes.manifest.json`(줄 수·파일 sha256·캠페인 목록 sha256·기대 캠페인 수)과
    같아야 한다. 명세가 없으면 올리지 않는다 — 중간까지만 만들어진 파일에는 명세가 없다.
- 올리기 전에 `build.json`의 sha256과 파일을 대조하고, 어느 원인 파일·명세로 올렸는지를 data_builds에 남긴다.
- 직전 날짜의 build와 비교해 새로 생김·바뀜(칸별)·사라짐·그대로 건수를 계산해 data_builds.change_summary에 남긴다.
- 날짜는 칸마다 정해진 형식(YYYYMMDD, snapshot_date는 YYYY-MM-DD)만 받는다. 틀리면 몇 번째 줄인지 알려 주고 중단한다.
- 빈 문자열은 NULL로 바꾸지 않고 원본 그대로 올린다.
- build를 지우는 명령은 두지 않는다. 지운 데이터를 되살릴 보관소(아카이브)가 없으면 NHTSA가 옛 파일을 다시 주지 않아
  근거를 잃는다 — 보관소와 복원 절차가 생길 때 추가한다 (DEC-034 미결).
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
SCRIPT_DIR = Path(__file__).resolve().parent
SCHEMA = SCRIPT_DIR / "schema.sql"
BASELINE = SCRIPT_DIR / "baseline_2026-10-06.json"
BATCH = 2000
CAUSES_FILES = {"sample": "causes_sample.jsonl", "full": "causes.jsonl"}
MANIFEST_NAME = "causes.manifest.json"

# 테이블별 기본키 칸과 데이터 칸. DB 칸은 build_id + snapshot_date + 데이터 칸 + row_sha256이다 (campaign6은 DB가 계산)
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
    "build_id", "snapshot_date", "raw_manifest_sha256", "recalls_sha256", "eval_sha256", "causes_kind",
    "causes_file", "causes_sha256", "causes_rows", "causes_expected_rows", "causes_spec", "change_summary",
]  # fmt: skip
JSON_COLS = ("pdfs", "change_summary", "causes_spec")


def db_columns(table: str) -> list[str]:
    return ["build_id", "snapshot_date", *TABLES[table]["cols"], "row_sha256"]


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


def campaigns_digest(campaigns) -> str:
    """캠페인 번호 목록의 지문 — 정렬한 번호를 줄바꿈으로 이은 문자열의 sha256. rclrpt.campaigns_digest와 같은 규칙이다 (골든 테스트로 고정)."""
    return hashlib.sha256("\n".join(sorted(campaigns)).encode()).hexdigest()


def build_id_of(
    raw_manifest_sha256: str, recalls_sha256: str, eval_sha256: str, causes_sha256: str
) -> str:
    """입력 파일 4개의 해시로 정해지는 불변 식별자 — 내용이 하나라도 다르면 다른 build다."""
    joined = "|".join([raw_manifest_sha256, recalls_sha256, eval_sha256, causes_sha256])
    return hashlib.sha256(joined.encode()).hexdigest()[:16]


def row_sha256(row: dict, cols: list[str]) -> str:
    """데이터 칸 전체의 해시. 같은 내용이면 항상 같은 값이다 (칸 순서·날짜 표기에 영향받지 않는다)."""
    plain = {c: row[c].isoformat() if isinstance(row[c], date) else row[c] for c in cols}
    return hashlib.sha256(
        json.dumps(plain, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def _seal(rows: list[dict], table: str, build_id: str, snapshot: date) -> list[dict]:
    cols = TABLES[table]["cols"]
    return [
        {**r, "build_id": build_id, "snapshot_date": snapshot, "row_sha256": row_sha256(r, cols)}
        for r in rows
    ]


def causes_spec(data_dir: Path, kind: str, baseline: Path) -> dict:
    """원인 파일의 완전성을 따질 독립된 명세. 사람이 입력한 숫자가 아니라 기준 파일(표본)이나 rclrpt가 만든 명세(전체)에서 온다."""
    if kind == "sample":
        base = json.loads(baseline.read_text(encoding="utf-8"))
        campaigns = [s["campaign"] for s in base["rclrpt_sample"]]
        return {
            "kind": "sample",
            "source": baseline.name,
            "rows": len(campaigns),
            "campaigns_sha256": campaigns_digest(campaigns),
            "campaigns": campaigns,
        }
    path = data_dir / MANIFEST_NAME
    if not path.exists():
        sys.exit(
            f"{MANIFEST_NAME}이 없다 — `rclrpt all`이 완성본과 함께 만드는 명세다. "
            "중간까지만 만들어진 파일이거나 명세 없이 옮긴 파일은 올리지 않는다"
        )
    manifest = json.loads(path.read_text(encoding="utf-8"))
    for key in ("kind", "rows", "file_sha256", "campaigns_sha256", "expect_campaigns"):
        if key not in manifest:
            sys.exit(f"{MANIFEST_NAME}에 {key} 칸이 없다")
    if manifest["kind"] != "full":
        sys.exit(f"{MANIFEST_NAME}의 종류가 full이 아니다 ({manifest['kind']})")
    if manifest["rows"] != manifest["expect_campaigns"]:
        sys.exit(
            f"{MANIFEST_NAME}: 줄 수 {manifest['rows']:,}이 기대 캠페인 수 {manifest['expect_campaigns']:,}와 다르다 — 완성본이 아니다"
        )
    return {**manifest, "source": MANIFEST_NAME}


def causes_source(data_dir: Path, kind: str) -> Path:
    path = data_dir / CAUSES_FILES[kind]
    if not path.exists():
        sys.exit(f"{path.name}이 없다 ({data_dir})")
    return path


def load_files(data_dir: Path, causes_kind: str, baseline: Path = BASELINE) -> dict:
    """파일을 읽어 검증하고 테이블별 행을 돌려준다. DB는 쓰지 않는다."""
    causes_file = causes_source(data_dir, causes_kind)
    spec = causes_spec(data_dir, causes_kind, baseline)
    causes_sha = sha256_of(causes_file)
    if causes_kind == "full" and causes_sha != spec["file_sha256"]:
        sys.exit(
            f"{causes_file.name}의 sha256이 {MANIFEST_NAME}과 다르다 — 명세를 만든 뒤 파일이 바뀌었거나 다른 실행의 파일이다 "
            f"(파일 {causes_sha[:12]}…, 명세 {spec['file_sha256'][:12]}…)"
        )
    build = json.loads((data_dir / "build.json").read_text(encoding="utf-8"))
    for name, key in (("recalls.jsonl", "recalls_sha256"), ("eval.jsonl", "eval_sha256")):
        actual = sha256_of(data_dir / name)
        if actual != build[key]:
            sys.exit(
                f"{name}의 sha256이 build.json과 다르다 — 어느 원본에서 나온 파일인지 확인한다 "
                f"(파일 {actual[:12]}…, 기록 {build[key][:12]}…)"
            )
    snapshot = parse_iso(build["snapshot_date"], "build.json snapshot_date")
    build_id = build_id_of(
        build["raw_manifest_sha256"], build["recalls_sha256"], build["eval_sha256"], causes_sha
    )

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

    # 원인 파일 완전성: 독립된 명세와 대조한다 (줄 수 → 캠페인 목록)
    if len(causes) != spec["rows"]:
        sys.exit(
            f"{causes_file.name}이 {len(causes):,}줄이다 — 명세({spec['source']})의 {spec['rows']:,}줄과 다르다 "
            "(중간까지만 만들어진 파일인지 확인한다)"
        )
    found = {c["campaign"] for c in causes}
    if causes_kind == "sample":
        expected = set(spec["campaigns"])
        if found != expected:
            sys.exit(
                f"{causes_file.name}의 캠페인이 기준 파일의 표본 목록과 다르다 — 빠진 캠페인 {len(expected - found)}개 "
                f"{sorted(expected - found)[:5]}, 목록에 없는 캠페인 {len(found - expected)}개 {sorted(found - expected)[:5]}"
            )
    elif campaigns_digest(found) != spec["campaigns_sha256"]:
        sys.exit(f"{causes_file.name}의 캠페인 목록이 {MANIFEST_NAME}의 campaigns_sha256과 다르다")

    return {
        "build": {
            "build_id": build_id,
            "snapshot_date": snapshot,
            "raw_manifest_sha256": build["raw_manifest_sha256"],
            "recalls_sha256": build["recalls_sha256"],
            "eval_sha256": build["eval_sha256"],
            "causes_kind": causes_kind,
            "causes_file": causes_file.name,
            "causes_sha256": causes_sha,
            "causes_rows": len(causes),
            "causes_expected_rows": spec["rows"],
            "causes_spec": {k: v for k, v in spec.items() if k != "campaigns"},
        },
        "recalls": _seal(recalls, "recalls", build_id, snapshot),
        "eval_questions": _seal(questions, "eval_questions", build_id, snapshot),
        "causes": _seal(causes, "causes", build_id, snapshot),
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


def summarize_changes(prev: dict | None, prev_tables: dict[str, dict], data: dict) -> dict:
    """prev = 비교할 직전 build({"build_id", "snapshot_date"}) 또는 None."""
    if prev is None:
        return {"vs": None, "note": "첫 build — 비교할 이전 날짜의 build가 없다"}
    summary: dict = {"vs": prev["snapshot_date"].isoformat(), "vs_build": prev["build_id"]}
    for table, spec in TABLES.items():
        new = {r[spec["key"]]: r for r in data[table]}
        summary[table] = diff_rows(prev_tables[table], new, spec["cols"])
    return summary


def describe_changes(summary: dict) -> list[str]:
    if summary.get("vs") is None:
        return [summary["note"]]
    lines = [f"직전 날짜({summary['vs']}, build {summary['vs_build']}) 대비"]
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
    # build_id가 같으면 입력 파일이 모두 같다 — 바뀌는 것은 비교 결과와 올린 시각뿐이다
    return (
        f"insert into data_builds ({names}) values ({marks}) "
        "on conflict (build_id) do update set change_summary = excluded.change_summary, loaded_at = now()"
    )


def insert_sql(table: str) -> str:
    cols = db_columns(table)
    return f"insert into {table} ({', '.join(cols)}) values ({', '.join(f'%({c})s' for c in cols)})"


def _params(row: dict) -> dict:
    from psycopg.types.json import Jsonb

    return {k: Jsonb(v) if k in JSON_COLS else v for k, v in row.items()}


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
    data = load_files(_data_dir(args), args.causes, Path(args.baseline))
    b = data["build"]
    print(
        f"data_builds: 1줄 (build {b['build_id']}, 스냅샷 {b['snapshot_date']}, 원인 파일 {b['causes_file']}, 명세 {b['causes_spec']['source']})"
    )
    for table in TABLES:
        print(f"{table}: {len(data[table]):,}줄")
    print(
        "검증 통과 (해시·날짜·겹침·정답 리콜·캠페인 연결·원인 파일 명세) — DB에는 아무것도 쓰지 않았다"
    )


def cmd_schema(args) -> None:
    with connect() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    print("schema.sql 적용 완료")


def cmd_load(args) -> None:
    from psycopg.rows import dict_row

    data = load_files(_data_dir(args), args.causes, Path(args.baseline))
    build = data["build"]
    build_id, snapshot = build["build_id"], build["snapshot_date"]
    with connect() as conn:  # 블록이 정상 종료하면 commit, 예외(SystemExit 포함)면 rollback
        with conn.cursor(row_factory=dict_row) as cur:
            # 직전 날짜의 build (같은 날짜면 전체본 우선, 그다음 최근에 올린 것)
            prev = cur.execute(
                "select build_id, snapshot_date from data_builds where snapshot_date < %s "
                "order by snapshot_date desc, (causes_kind = 'full') desc, loaded_at desc limit 1",
                (snapshot,),
            ).fetchone()
            prev_tables: dict[str, dict] = {}
            if prev:
                for table, spec in TABLES.items():
                    cols = [c for c in db_columns(table) if c not in ("build_id", "snapshot_date")]
                    rows = cur.execute(
                        f"select {', '.join(cols)} from {table} where build_id = %s",
                        (prev["build_id"],),
                    ).fetchall()
                    prev_tables[table] = {r[spec["key"]]: r for r in rows}
            summary = summarize_changes(prev, prev_tables, data)

            cur.execute(upsert_build_sql(), _params({**build, "change_summary": summary}))
            for table in TABLES:
                rows = data[table]
                cur.execute(
                    f"delete from {table} where build_id = %s", (build_id,)
                )  # 같은 build(내용이 같다)만 통째로 바꾼다
                sql = insert_sql(table)
                for start in range(0, len(rows), BATCH):
                    cur.executemany(sql, [_params(r) for r in rows[start : start + BATCH]])
                print(f"{table}: {len(rows):,}줄")
            for table in TABLES:
                n = cur.execute(
                    f"select count(*) as n from {table} where build_id = %s", (build_id,)
                ).fetchone()["n"]
                if n != len(data[table]):
                    sys.exit(f"{table}: DB {n:,}줄 ≠ 파일 {len(data[table]):,}줄 — 되돌린다")
    print(
        f"build {build_id} (스냅샷 {snapshot}, 원인 {build['causes_kind']}) 적재 완료 — 건수 대조 통과"
    )
    print("\n".join(describe_changes(summary)))


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
        p.add_argument("--data-dir", help=f"파일 폴더 (기본 {PROCESSED.relative_to(REPO_ROOT)})")
        p.add_argument(
            "--baseline",
            default=str(BASELINE),
            help="표본 원인 파일의 기대 캠페인 목록이 든 기준 파일 (기본: 커밋된 baseline_2026-10-06.json)",
        )

    add_source_args(sub.add_parser("check", help="DB 없이 파일만 검증"))
    sub.add_parser("schema", help="schema.sql 적용")
    add_source_args(sub.add_parser("load", help="build 1개를 올린다"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    {"check": cmd_check, "schema": cmd_schema, "load": cmd_load}[args.command](args)


if __name__ == "__main__":
    main()

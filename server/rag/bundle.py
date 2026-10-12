"""서빙 묶음 — 배포 서버가 시작할 때 읽을 build 한 벌을 파일 하나로 만든다 (DEC-048 ⑤, DEC-049).

로컬 서버는 시작할 때 로컬 파일(카드·원인·명세·조사 원본)을 검사해 쓴다. 배포 환경(Vercel)에는 그 파일이 없으므로(원본 데이터는
저장소에 넣지 않는다 — AGENTS.md 7절), 로컬에서 **같은 검사를 통과한 결과**를 묶어 Supabase Storage에 올린다.

- 카드는 `recalls.jsonl`의 순서 그대로 둔다 — 벡터 줄·탐침 위치·BM25 동점 처리가 이 순서에 걸려 있다(DB에는 순서 칸이 없다).
- 조사 요약은 원본 대조(`load_investigations`)를 마친, 카드에 연결된 것만 담는다(원본 전체를 서버에서 풀지 않는다).
- 묶음은 같은 입력이면 바이트까지 같다(파일 순서·시각·소유자를 고정) — DB의 `serving_bundles.bundle_sha256`으로 되짚는다.

사용법:
    uv run --env-file .env python -m server.rag.bundle schema     # serving_bundles 테이블
    uv run --env-file .env python -m server.rag.bundle build      # 로컬 build → data/processed/defect/serving/serving_<build_id>.tar
    uv run --env-file .env python -m server.rag.bundle upload     # Storage에 올리고 serving_bundles에 sha256 기록
    uv run --env-file .env python -m server.rag.bundle verify     # 공개 주소에서 받아 기록과 대조
"""

import argparse
import hashlib
import io
import json
import os
import shutil
import sys
import tarfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from scripts.defect_precedent.load_db import PROCESSED, connect
from scripts.defect_precedent.retrieval_compare import FASTEMBED_VERSION, card_text
from server.rag import embeddings
from server.rag.build import Build

FORMAT = 1
BUCKET = "serving-bundles"
SCHEMA = Path(__file__).with_name("bundle.sql")
OUT_DIR = PROCESSED / "serving"  # gitignore된 data/ 아래


class BundleMismatch(RuntimeError):
    """묶음이 기록·자기 명세와 다르다."""


@dataclass(frozen=True)
class Loaded:
    build: Build
    investigations: dict[str, list[dict]]
    vectors: "object"  # numpy float32 (카드 수, 384), 정규화 전
    model_dir: Path
    meta: dict


def _jsonl(rows) -> bytes:
    return "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows).encode("utf-8")


def _json(obj) -> bytes:
    return (json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def _npy(vecs) -> bytes:
    import numpy as np

    buf = io.BytesIO()
    np.save(buf, np.ascontiguousarray(vecs, dtype="float32"))
    return buf.getvalue()


def _add(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(data), 0, 0o644
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    tar.addfile(info, io.BytesIO(data))


def write_bundle(build: Build, investigations: dict, vecs, model_dir: Path, out_dir: Path) -> Path:
    """검사를 마친 build 한 벌을 tar 하나로 쓴다. 같은 입력이면 같은 바이트."""
    texts = [card_text(c) for c in build.cards]
    if len(vecs) != len(build.cards):
        raise BundleMismatch(f"벡터 {len(vecs):,}줄 ≠ 카드 {len(build.cards):,}장")
    members: dict[str, bytes] = {
        "cards.jsonl": _jsonl(build.cards),
        "causes.jsonl": _jsonl(build.causes.values()),
        "unreadable.json": _json(build.unreadable),
        "investigations.json": _json(investigations),
        "vectors.npy": _npy(vecs),
    }
    for p in sorted(model_dir.rglob("*")):
        if p.is_file():
            members[f"model/{p.relative_to(model_dir).as_posix()}"] = p.read_bytes()
    meta = {
        "format": FORMAT,
        "build_id": build.build_id,
        "snapshot_date": build.snapshot_date,
        "raw_manifest_sha256": build.raw_manifest_sha256,
        "causes_spec": build.causes_spec,
        "texts_sha256": embeddings.texts_sha256(texts),
        "fastembed_version": FASTEMBED_VERSION,
        "model": embeddings.MODEL,
        "files": {k: hashlib.sha256(v).hexdigest() for k, v in members.items()},
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"serving_{build.build_id}.tar"
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    with tarfile.open(tmp, "w", format=tarfile.USTAR_FORMAT) as tar:
        _add(tar, "meta.json", _json(meta))
        for name in sorted(members):
            _add(tar, name, members[name])
    tmp.replace(path)
    return path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check_sha(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise BundleMismatch(
            f"묶음 sha256이 기록과 다르다(파일 {actual[:12]}…, 기록 {expected[:12]}…) — 다른 묶음으로 띄우지 않는다"
        )


def load_bundle(path: Path, work_dir: Path) -> Loaded:
    """묶음을 풀어 자기 명세(meta.json)와 대조한 뒤 서버가 쓰는 모양으로 되살린다."""
    import numpy as np

    with tarfile.open(path) as tar:
        names = [m.name for m in tar.getmembers()]
        if "meta.json" not in names:
            raise BundleMismatch("묶음에 meta.json이 없다")
        meta = json.loads(tar.extractfile("meta.json").read())
        if meta.get("format") != FORMAT:
            raise BundleMismatch(f"묶음 형식 {meta.get('format')} ≠ {FORMAT}")
        body = {n: tar.extractfile(n).read() for n in names if n != "meta.json"}
    if set(body) != set(meta["files"]):
        raise BundleMismatch(
            f"묶음 파일 목록이 meta.json과 다르다: {sorted(set(body) ^ set(meta['files']))[:3]}"
        )
    for name, data in body.items():
        if hashlib.sha256(data).hexdigest() != meta["files"][name]:
            raise BundleMismatch(f"묶음의 {name}이 meta.json의 sha256과 다르다")
    cards = [json.loads(line) for line in body["cards.jsonl"].decode("utf-8").splitlines()]
    if embeddings.texts_sha256([card_text(c) for c in cards]) != meta["texts_sha256"]:
        raise BundleMismatch(
            "카드 글 해시(texts_sha256)가 meta.json과 다르다 — 카드 순서나 글이 바뀌었다"
        )
    causes = {
        r["campaign"]: r
        for r in (json.loads(line) for line in body["causes.jsonl"].decode("utf-8").splitlines())
    }
    model_dir = work_dir / "model"
    if model_dir.exists():
        shutil.rmtree(model_dir)
    for name, data in body.items():
        if name.startswith("model/"):
            dst = work_dir / name
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(data)
    build = Build(
        meta["build_id"],
        meta["snapshot_date"],
        cards,
        causes,
        json.loads(body["unreadable.json"]),
        meta["causes_spec"],
        meta["raw_manifest_sha256"],
    )
    vecs = np.load(io.BytesIO(body["vectors.npy"]))
    if vecs.shape != (len(cards), 384):
        raise BundleMismatch(f"벡터 모양 {vecs.shape} ≠ ({len(cards)}, 384)")
    return Loaded(build, json.loads(body["investigations.json"]), vecs, model_dir, meta)


def register(
    conn,
    build_id: str,
    sha: str,
    storage_path: str,
    model: str = embeddings.MODEL,
    fmt: int = FORMAT,
) -> None:
    """serving_bundles에 기록한다 — (build, 모델, 묶음 형식)마다 하나. 이미 있으면 같을 때만 그대로 두고, 다르면 덮어쓰지 않는다."""
    row = recorded(conn, build_id, model, fmt)
    if row is not None:
        if row != (sha, storage_path):
            raise BundleMismatch(
                f"build {build_id}·{model}·형식 {fmt}의 묶음 기록이 이미 있고 다르다(기록 {row[0][:12]}…) — 덮어쓰지 않는다"
            )
        return
    conn.execute(
        "insert into serving_bundles (build_id, model, bundle_sha256, storage_path, format) "
        "values (%s, %s, %s, %s, %s)",
        (build_id, model, sha, storage_path, fmt),
    )


def recorded(
    conn, build_id: str, model: str = embeddings.MODEL, fmt: int = FORMAT
) -> tuple[str, str] | None:
    row = conn.execute(
        "select bundle_sha256, storage_path from serving_bundles "
        "where build_id = %s and model = %s and format = %s",
        (build_id, model, fmt),
    ).fetchone()
    return None if row is None else (row[0], row[1])


def public_url(supabase_url: str, storage_path: str) -> str:
    return f"{supabase_url.rstrip('/')}/storage/v1/object/public/{BUCKET}/{storage_path}"


def _env(name: str) -> str:
    v = os.environ.get(name, "").strip()
    if not v:
        sys.exit(f"{name}이 없다 — .env에 넣는다(값은 출력하지 않는다)")
    return v


def cmd_schema(_a) -> None:
    with connect() as conn:
        conn.execute(SCHEMA.read_text(encoding="utf-8"))
    print("bundle.sql 적용 완료")


def cmd_build(_a) -> None:
    from fastembed import TextEmbedding

    from server.rag.build import check_against_db, load_build
    from server.rag.investigations import load_investigations

    build = load_build()
    campnos = [c["campno"] for c in build.cards]
    texts = [card_text(c) for c in build.cards]
    embeddings.check_fastembed()
    with connect() as conn:  # 서버 시작과 같은 대조 — 명세·벡터 기록이 DB와 같아야 묶는다
        check_against_db(conn, build)
        vecs = embeddings.load_vectors(conn, build.build_id, campnos, texts)
    model = TextEmbedding(embeddings.MODEL)
    embeddings.verify_probe(model, texts, vecs)
    invs = load_investigations(build.raw_manifest_sha256, set(campnos))
    path = write_bundle(build, invs, vecs, Path(model.model._model_dir), OUT_DIR)
    print(f"{path} ({path.stat().st_size / 1e6:.1f}MB) sha256 {sha256_file(path)}")


def cmd_upload(_a) -> None:
    from server.rag.build import load_build

    build = load_build()
    path = OUT_DIR / f"serving_{build.build_id}.tar"
    if not path.exists():
        sys.exit(f"{path.name}이 없다 — 먼저 build")
    sha = sha256_file(path)
    storage_path = (
        f"{build.build_id}/{sha}.tar"  # 내용 해시가 이름이라 같은 이름으로 다른 묶음을 올릴 수 없다
    )
    with connect() as conn:
        row = recorded(conn, build.build_id)
    if row is not None and row != (sha, storage_path):
        sys.exit(
            f"build {build.build_id}의 묶음 기록이 이미 있고 다르다(기록 {row[0][:12]}…) — 덮어쓰지 않는다"
        )
    url = f"{_env('SUPABASE_URL').rstrip('/')}/storage/v1/object/{BUCKET}/{storage_path}"
    req = urllib.request.Request(
        url,
        data=path.read_bytes(),
        method="POST",
        headers={
            "Authorization": f"Bearer {_env('SUPABASE_SERVICE_ROLE_KEY')}",
            "Content-Type": "application/x-tar",
            "x-upsert": "false",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=600).read()
    except urllib.error.HTTPError as e:
        if e.code not in (400, 409):  # 이미 있음(내용 해시 이름이라 같은 파일) — 그 외는 멈춘다
            sys.exit(f"Storage 업로드 실패: HTTP {e.code}")
        print("Storage에 같은 이름의 묶음이 이미 있다 — 기록 단계에서 공개 주소로 대조한다")
    with connect() as conn:
        register(conn, build.build_id, sha, storage_path)
    print(f"올림: {BUCKET}/{storage_path} — serving_bundles에 sha256 {sha[:12]}… 기록")


def cmd_verify(_a) -> None:
    from server.rag.build import load_build

    build = load_build()
    with connect() as conn:
        row = recorded(conn, build.build_id)
    if row is None:
        sys.exit(f"build {build.build_id}의 묶음 기록이 없다 — 먼저 upload")
    dst = OUT_DIR / "verify.tar"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(public_url(_env("SUPABASE_URL"), row[1]), timeout=600) as r:
        dst.write_bytes(r.read())
    check_sha(dst, row[0])
    loaded = load_bundle(dst, OUT_DIR / "verify")
    print(
        f"확인: 공개 주소의 묶음 sha256 {row[0][:12]}…이 기록과 같고 build {loaded.build.build_id}로 되살아난다"
    )


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="bundle", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    for name, helptext in (
        ("schema", "serving_bundles 테이블"),
        ("build", "로컬 build를 검사해 묶음을 만든다"),
        ("upload", "Storage에 올리고 sha256을 기록한다"),
        ("verify", "공개 주소의 묶음을 받아 기록과 대조한다"),
    ):
        sub.add_parser(name, help=helptext)
    a = p.parse_args(argv)
    {"schema": cmd_schema, "build": cmd_build, "upload": cmd_upload, "verify": cmd_verify}[
        a.command
    ](a)


if __name__ == "__main__":
    main()

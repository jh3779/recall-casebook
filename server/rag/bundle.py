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
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath

from scripts.defect_precedent.load_db import PROCESSED, connect
from scripts.defect_precedent.retrieval_compare import FASTEMBED_VERSION, card_text
from server.rag import embeddings
from server.rag.build import Build

FORMAT = 1
BUCKET = "serving-bundles"
SCHEMA = Path(__file__).with_name("bundle.sql")
OUT_DIR = PROCESSED / "serving"  # gitignore된 data/ 아래
SERVE_DIR = Path(
    "/tmp/serving"
)  # 배포 서버가 묶음을 받는 곳 — Vercel에서 실행 중 쓸 수 있는 곳은 /tmp뿐
DATA_FILES = (
    "cards.jsonl",
    "causes.jsonl",
    "unreadable.json",
    "investigations.json",
    "vectors.npy",
)  # 묶음에 반드시 있는 파일 — 그 밖에는 meta.json과 model/ 아래 파일만 허용한다
MODEL_FILE = "model/model_optimized.onnx"  # fastembed가 Qdrant/bge-small-en-v1.5-onnx-Q에서 여는 파일 — 없으면 모델 없는 묶음


class BundleMismatch(RuntimeError):
    """묶음이 기록·자기 명세와 다르다."""


@dataclass(frozen=True)
class Loaded:
    build: Build
    investigations: dict[str, list[dict]]
    vectors: "object"  # numpy float32 (카드 수, 384), 정규화 전
    model_dir: Path
    meta: dict
    sha256: str = ""  # 배포 서버가 DB 기록과 대조한 묶음 파일 sha256 (load_from_bundle만 채운다)


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
    if MODEL_FILE not in members:  # 모델 폴더를 못 찾거나 비었으면 rglob은 조용히 빈 결과를 낸다
        raise BundleMismatch(f"모델 폴더 {model_dir}에 {MODEL_FILE[len('model/') :]}이 없다")
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


def _lines(data: bytes) -> list[str]:
    """줄바꿈(\\n)으로만 나눈다 — str.splitlines는 글 안의 U+2028·U+0085도 줄 끝으로 쳐서 JSON 줄을 깨뜨린다."""
    return [line for line in data.decode("utf-8").split("\n") if line]


def _check_member(m: tarfile.TarInfo) -> None:
    """일반 파일이고, 정해진 이름이거나 model/ 아래의 상대 경로(.. 없음)일 때만 받는다 — 작업 폴더 밖에 쓰지 않게."""
    parts = PurePosixPath(m.name).parts
    ok_name = m.name in ("meta.json", *DATA_FILES) or (
        len(parts) >= 2
        and parts[0] == "model"
        and not PurePosixPath(m.name).is_absolute()
        and ".." not in parts
        and "" not in parts
    )
    if not m.isreg() or not ok_name:
        raise BundleMismatch(f"묶음에 허용하지 않는 항목이 있다: {m.name!r}")


def load_bundle(path: Path, work_dir: Path, expected_sha256: str) -> Loaded:
    """기록된 sha256과 같은 묶음만 열고, 풀어서 자기 명세(meta.json)와 대조한 뒤 서버가 쓰는 모양으로 되살린다.
    sha256을 인자로 받는 이유: 대조 없이 묶음을 여는 경로를 두지 않는다(meta.json 자체는 어떤 해시에도 묶여 있지 않다)."""
    import numpy as np

    check_sha(path, expected_sha256)
    with tarfile.open(path) as tar:
        members = tar.getmembers()
        for m in members:
            _check_member(m)
        names = [m.name for m in members]
        if len(set(names)) != len(names):
            raise BundleMismatch("묶음에 같은 이름의 항목이 둘 이상 있다")
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
    missing = [n for n in (*DATA_FILES, MODEL_FILE) if n not in body]
    if missing:
        raise BundleMismatch(f"묶음에 {missing}이 없다")
    for name, data in body.items():
        if hashlib.sha256(data).hexdigest() != meta["files"][name]:
            raise BundleMismatch(f"묶음의 {name}이 meta.json의 sha256과 다르다")
    cards = [json.loads(line) for line in _lines(body["cards.jsonl"])]
    if embeddings.texts_sha256([card_text(c) for c in cards]) != meta["texts_sha256"]:
        raise BundleMismatch(
            "카드 글 해시(texts_sha256)가 meta.json과 다르다 — 카드 순서나 글이 바뀌었다"
        )
    causes = {r["campaign"]: r for r in (json.loads(line) for line in _lines(body["causes.jsonl"]))}
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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """업로드는 리디렉션을 따라가지 않는다 — urllib은 따라가면서 Authorization(관리자 키)을 새 주소로 그대로 보낸다."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _send(req: urllib.request.Request) -> None:
    """관리자 키가 든 요청을 보낸다. 3xx는 HTTPError로 올라와 멈춘다."""
    urllib.request.build_opener(_NoRedirect).open(req, timeout=600).read()


def _download(url: str, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.chmod(
        dst.parent, 0o700
    )  # 받은 묶음 폴더는 이 사용자만 — 이미 있던 폴더도(남의 폴더면 여기서 멈춘다)
    tmp = dst.with_name(f"{dst.name}.{os.getpid()}.tmp")
    try:
        with urllib.request.urlopen(url, timeout=600) as r, tmp.open("wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    except BaseException:
        tmp.unlink(missing_ok=True)  # 끊긴 조각 파일(최대 묶음 크기)을 /tmp에 남기지 않는다
        raise
    tmp.replace(dst)  # 다 받은 뒤에만 이름을 바꾼다 — 중간에 끊겨도 반쯤 받은 파일을 쓰지 않는다


def load_from_bundle(conn, build_id: str, supabase_url: str, work_dir: Path = SERVE_DIR) -> Loaded:
    """배포 서버의 시작 (RAG_SOURCE=bundle). DB `serving_bundles`에 기록된 sha256과 같은 묶음만 쓴다 —
    받은 파일이 다르면 지우고 멈춘다(다음 시작 때 다시 받는다). 묶음의 build·모델·fastembed 판본도 지금 서버와 같아야 한다."""
    if not supabase_url.startswith("https://"):
        raise BundleMismatch(
            "SUPABASE_URL이 https://로 시작하지 않는다 — 묶음을 암호화 없이 받지 않는다"
        )
    row = recorded(conn, build_id)
    if row is None:
        raise BundleMismatch(
            f"build {build_id}의 묶음 기록(serving_bundles)이 없다 — 로컬에서 `bundle upload`를 먼저 한다"
        )
    sha, storage_path = row
    path = work_dir / f"{sha}.tar"
    if not path.exists():
        _download(public_url(supabase_url, storage_path), path)
    try:
        check_sha(path, sha)
    except BundleMismatch:
        path.unlink(missing_ok=True)
        raise
    loaded = load_bundle(path, work_dir / sha, sha)
    got = (loaded.build.build_id, loaded.meta["model"], loaded.meta["fastembed_version"])
    if got != (build_id, embeddings.MODEL, FASTEMBED_VERSION):
        raise BundleMismatch(
            f"묶음의 build·모델·fastembed 판본 {got}이 지금 서버({build_id}, {embeddings.MODEL}, {FASTEMBED_VERSION})와 다르다"
        )
    return replace(loaded, sha256=sha)


def check_identity(loaded: Loaded, build: Build) -> None:
    """묶음 안의 build가 이 build와 같은지 — 파일 이름만 이 build로 바꾼 다른 build의 묶음을 막는다."""
    if loaded.build != build:
        raise BundleMismatch(
            f"묶음 안의 build {loaded.build.build_id}가 이 build {build.build_id}와 다르다(카드·원인·명세 중 하나 이상)"
        )
    got = (loaded.meta["model"], loaded.meta["fastembed_version"])
    if got != (embeddings.MODEL, FASTEMBED_VERSION):
        raise BundleMismatch(
            f"묶음의 모델·fastembed 판본 {got} ≠ ({embeddings.MODEL}, {FASTEMBED_VERSION})"
        )


def confirm_and_register(
    conn, build: Build, sha: str, storage_path: str, supabase_url: str, work_dir: Path
) -> None:
    """공개 주소에서 실제로 받은 파일이 올린 묶음(sha256)이고 이 build의 묶음일 때만 DB에 기록한다."""
    dst = work_dir / "confirm.tar"
    _download(public_url(supabase_url, storage_path), dst)
    check_identity(load_bundle(dst, work_dir / "confirm", sha), build)
    register(conn, build.build_id, sha, storage_path)


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
    check_identity(
        load_bundle(path, OUT_DIR / "check", sha), build
    )  # 이름만 바꾼 다른 build의 묶음·옛 형식 묶음을 올리지 않는다
    storage_path = (
        f"{build.build_id}/{sha}.tar"  # 내용 해시가 이름이라 같은 이름으로 다른 묶음을 올릴 수 없다
    )
    with connect() as conn:
        row = recorded(conn, build.build_id)
    if row is not None and row != (sha, storage_path):
        sys.exit(
            f"build {build.build_id}의 묶음 기록이 이미 있고 다르다(기록 {row[0][:12]}…) — 덮어쓰지 않는다"
        )
    base = _env("SUPABASE_URL").rstrip("/")
    if not base.startswith("https://"):
        sys.exit(
            "SUPABASE_URL이 https://로 시작하지 않는다 — 관리자 키를 암호화 없이 보내지 않는다"
        )
    url = f"{base}/storage/v1/object/{BUCKET}/{storage_path}"
    key = _env("SUPABASE_SERVICE_ROLE_KEY")
    req = urllib.request.Request(
        url,
        data=path.read_bytes(),
        method="POST",
        headers={
            # 새 형식 Secret 키(sb_secret_…)는 JWT가 아니라 apikey 머리글이 있어야 받아 준다(Authorization만이면 400)
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/x-tar",
            "x-upsert": "false",
        },
    )
    try:
        _send(req)
    except urllib.error.HTTPError as e:
        # Supabase는 같은 이름이 이미 있으면 400·409로 거부한다. 다른 이유의 400일 수도 있으므로 여기서 성공으로 보지 않고,
        # 아래에서 공개 주소의 실제 파일을 받아 sha256·build를 대조한 뒤에만 기록한다(없거나 다르면 기록하지 않고 멈춘다)
        # 거부 이유를 보이려고 Storage 응답 본문을 출력한다 — 본문에 키가 되돌아와도 찍히지 않게 지운다
        reason = e.read()[:300].decode("utf-8", "replace").replace(key, "***")
        if e.code not in (400, 409):
            sys.exit(f"Storage 업로드 실패: HTTP {e.code} {reason}")
        print(
            f"Storage가 HTTP {e.code}로 거부했다({reason}) — 같은 이름이 이미 있을 수 있어 공개 주소의 파일로 확인한다"
        )
    with connect() as conn:
        confirm_and_register(
            conn, build, sha, storage_path, _env("SUPABASE_URL"), OUT_DIR / "confirm"
        )
    print(f"올림: {BUCKET}/{storage_path} — serving_bundles에 sha256 {sha[:12]}… 기록")


def cmd_verify(_a) -> None:
    from server.rag.build import load_build

    build = load_build()
    with connect() as conn:
        row = recorded(conn, build.build_id)
    if row is None:
        sys.exit(f"build {build.build_id}의 묶음 기록이 없다 — 먼저 upload")
    dst = OUT_DIR / "verify.tar"
    _download(public_url(_env("SUPABASE_URL"), row[1]), dst)
    loaded = load_bundle(dst, OUT_DIR / "verify", row[0])
    check_identity(loaded, build)
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

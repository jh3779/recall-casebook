"""서빙 묶음(DEC-048 ⑤) — 로컬 검사를 통과한 build를 파일 하나로 만들고, 그대로 되살리는지."""

import hashlib
import io
import json
import tarfile
from types import SimpleNamespace

import numpy as np
import pytest

from server.rag import bundle
from server.rag.build import load_build
from tests.test_load_db import cause, pg, pgconn, recall  # noqa: F401
from tests.test_rag_server import CARDS, full_data_dir

PDFS = {"odi/rcl/2023/RCLRPT-24V001-0001.PDF": "cd" * 32}
INV = {
    "24V001000": [
        {
            "action": "PE24001",
            "subject": "Airbag",
            "summary": "Owners report the airbag inflator ruptured.",
            "open_date": "20240101",
            "close_date": "",
        }
    ]
}


def _inputs(tmp_path):
    b = load_build(full_data_dir(tmp_path / "d", CARDS, [cause("24V001", pdfs=PDFS)]))
    vecs = np.arange(len(b.cards) * 384, dtype="float32").reshape(len(b.cards), 384) / 7
    model_dir = tmp_path / "model"
    (model_dir / "sub").mkdir(parents=True)
    (model_dir / "model_optimized.onnx").write_bytes(b"\x00onnx\x01" * 10)
    (model_dir / "tokenizer.json").write_text('{"v": 1}', encoding="utf-8")
    (model_dir / "sub" / "config.json").write_text("{}", encoding="utf-8")
    return b, vecs, model_dir


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_bundle_round_trip_keeps_card_order_causes_investigations_vectors_and_model(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    assert out.name == f"serving_{b.build_id}.tar"
    got = bundle.load_bundle(out, tmp_path / "x", _sha(out))
    assert (
        got.build == b
    )  # 카드 순서·원인 행(text_basis 포함)·실패 사유·명세·원본 명세 해시까지 같다
    assert [c["campno"] for c in got.build.cards] == [c["campno"] for c in CARDS]
    assert got.investigations == INV
    assert got.vectors.dtype == np.float32 and np.array_equal(got.vectors, vecs)
    for rel in ("model_optimized.onnx", "tokenizer.json", "sub/config.json"):
        assert (got.model_dir / rel).read_bytes() == (model_dir / rel).read_bytes()


def test_bundle_bytes_are_the_same_for_the_same_input(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    one = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "a")
    two = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "b")
    assert _sha(one) == _sha(two)  # DB에 적는 sha256이 다시 만들어도 같아야 되짚을 수 있다


def _rewrite(src, dst, member, data):
    """묶음의 한 파일만 바꾼 사본 — meta.json은 그대로 둔다."""
    with tarfile.open(src) as tin, tarfile.open(dst, "w") as tout:
        for info in tin.getmembers():
            body = data if info.name == member else tin.extractfile(info).read()
            info.size = len(body)
            tout.addfile(info, io.BytesIO(body))


@pytest.mark.parametrize("member", ["cards.jsonl", "investigations.json", "model/tokenizer.json"])
def test_load_bundle_refuses_a_member_that_differs_from_meta(tmp_path, member):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    bad = tmp_path / "bad.tar"
    _rewrite(out, bad, member, b"changed")
    with pytest.raises(bundle.BundleMismatch, match=member):
        bundle.load_bundle(
            bad, tmp_path / "x", _sha(bad)
        )  # 기록이 이 파일이라 해도 내용 대조에서 막힌다


def test_load_bundle_refuses_cards_whose_order_changed(tmp_path):
    """카드 순서가 바뀌면 벡터 줄·탐침 위치가 어긋난다 — meta의 카드 글 해시와 다시 계산한 값으로 막는다."""
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    with tarfile.open(out) as t:
        meta = json.loads(t.extractfile("meta.json").read())
        cards = t.extractfile("cards.jsonl").read().decode().splitlines()
    swapped = ("\n".join([cards[1], cards[0], *cards[2:]]) + "\n").encode()
    meta["files"]["cards.jsonl"] = hashlib.sha256(swapped).hexdigest()
    tmp = tmp_path / "t.tar"
    _rewrite(out, tmp, "cards.jsonl", swapped)
    bad = tmp_path / "bad.tar"
    _rewrite(tmp, bad, "meta.json", json.dumps(meta).encode())
    with pytest.raises(bundle.BundleMismatch, match="texts_sha256"):
        bundle.load_bundle(
            bad, tmp_path / "x", _sha(bad)
        )  # 기록이 이 파일이라 해도 내용 대조에서 막힌다


def test_check_sha_refuses_a_bundle_other_than_the_recorded_one(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    bundle.check_sha(out, _sha(out))
    with pytest.raises(bundle.BundleMismatch, match="sha256"):
        bundle.check_sha(out, "ab" * 32)


@pg
def test_pg_serving_bundles_record_is_written_once(pgconn, tmp_path):  # noqa: F811
    from scripts.defect_precedent import load_db

    d = full_data_dir(tmp_path / "d", CARDS, [cause("24V001", pdfs=PDFS)])
    load_db.main(["load", "--causes", "full", "--data-dir", str(d)])
    b = load_build(d)
    from server.rag import embeddings

    embeddings.main(["schema"])
    pgconn.execute(
        "insert into embedding_sets (build_id, model, fastembed_version, texts_sha256, model_fingerprint, rows) "
        "values (%s, %s, '0.9.0', 'x', 'x', 3)",
        (b.build_id, embeddings.MODEL),
    )
    pgconn.execute(bundle.SCHEMA.read_text(encoding="utf-8"))
    pgconn.execute(bundle.SCHEMA.read_text(encoding="utf-8"))  # 여러 번 적용해도 된다
    bundle.register(pgconn, b.build_id, "aa" * 32, "x/serving.tar")
    bundle.register(pgconn, b.build_id, "aa" * 32, "x/serving.tar")  # 같으면 그대로
    with pytest.raises(bundle.BundleMismatch, match="덮어쓰지 않는다"):
        bundle.register(pgconn, b.build_id, "bb" * 32, "x/serving.tar")
    assert bundle.recorded(pgconn, b.build_id) == ("aa" * 32, "x/serving.tar")
    assert bundle.recorded(pgconn, "nope") is None
    # 데이터가 같아도 묶음 형식이 바뀌면 새 기록 — 옛 형식 기록은 그대로 남는다
    bundle.register(pgconn, b.build_id, "cc" * 32, "x/v2.tar", fmt=bundle.FORMAT + 1)
    assert bundle.recorded(pgconn, b.build_id, fmt=bundle.FORMAT + 1) == ("cc" * 32, "x/v2.tar")
    assert bundle.recorded(pgconn, b.build_id) == ("aa" * 32, "x/serving.tar")


class RecordingConn:
    """serving_bundles 조회는 없음으로, 기록(insert)은 모아 두는 가짜 연결."""

    def __init__(self):
        self.inserts = []

    def execute(self, sql, params=None):
        if sql.lstrip().startswith("insert"):
            self.inserts.append(params)
        return SimpleNamespace(fetchone=lambda: None)


def _other_build_bundle(tmp_path):
    """카드 하나가 다른 build의 정상 묶음."""
    cards = [dict(CARDS[0], defect="A different defect text.")] + CARDS[1:]
    other = load_build(full_data_dir(tmp_path / "o", cards, [cause("24V001", pdfs=PDFS)]))
    vecs = np.zeros((len(other.cards), 384), dtype="float32")
    _, _, model_dir = _inputs(tmp_path / "m")
    return other, bundle.write_bundle(other, INV, vecs, model_dir, tmp_path / "other")


def test_check_identity_refuses_a_bundle_of_another_build_renamed_as_this_one(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    own_tar = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "own")
    own = bundle.load_bundle(own_tar, tmp_path / "x", _sha(own_tar))
    bundle.check_identity(own, b)
    other, tar = _other_build_bundle(tmp_path)
    assert other.build_id != b.build_id
    renamed = tmp_path / f"serving_{b.build_id}.tar"
    renamed.write_bytes(tar.read_bytes())  # 이름만 이 build로 바꾼 다른 build의 묶음
    with pytest.raises(bundle.BundleMismatch, match="build"):
        bundle.check_identity(bundle.load_bundle(renamed, tmp_path / "y", _sha(renamed)), b)


def test_confirm_and_register_writes_db_only_after_the_public_file_matches(tmp_path, monkeypatch):
    b, vecs, model_dir = _inputs(tmp_path)
    tar = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    sha = _sha(tar)
    _, other_tar = _other_build_bundle(tmp_path)

    def serve(src):
        def f(url, dst):
            if src is None:
                raise OSError("404 — 공개 주소에 파일이 없다")
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())

        return f

    other_sha = _sha(other_tar)
    for src, want, err, why in (
        (None, sha, OSError, "공개 주소에 파일이 없다"),
        (tar, "ab" * 32, bundle.BundleMismatch, "sha256"),
        (
            other_tar,
            other_sha,
            bundle.BundleMismatch,
            "build",
        ),  # 이름만 바꿔 올린 다른 build — sha256은 그 파일 것
    ):
        conn = RecordingConn()
        monkeypatch.setattr(bundle, "_download", serve(src))
        with pytest.raises(err, match=why):
            bundle.confirm_and_register(
                conn, b, want, f"{b.build_id}/{want}.tar", "https://x", tmp_path / "c"
            )
        assert conn.inserts == []  # 공개 파일이 없거나 다르면 DB에 쓰지 않는다
    conn = RecordingConn()
    monkeypatch.setattr(bundle, "_download", serve(tar))
    bundle.confirm_and_register(
        conn, b, sha, f"{b.build_id}/{sha}.tar", "https://x", tmp_path / "c"
    )
    assert len(conn.inserts) == 1 and conn.inserts[0][2] == sha


def _with_members(src, dst, add=(), drop=(), meta_edit=None):
    """묶음에 항목을 더하거나 빼고, meta.json도 그에 맞게 고친 사본 — 내용 해시 대조는 통과하게 만든다."""
    with tarfile.open(src) as tin:
        items = [(m, tin.extractfile(m).read()) for m in tin.getmembers()]
    meta = json.loads(dict((m.name, d) for m, d in items)["meta.json"])
    for name, info, data in add:
        if info.isreg():
            meta["files"][name] = hashlib.sha256(data).hexdigest()
    for name in drop:
        meta["files"].pop(name, None)
    if meta_edit:
        meta_edit(meta)
    with tarfile.open(dst, "w") as tout:
        for m, d in items:
            if m.name in drop:
                continue
            if m.name == "meta.json":
                d = json.dumps(meta).encode()
                m.size = len(d)
            tout.addfile(m, io.BytesIO(d))
        for _, info, data in add:
            info.size = len(data) if info.isreg() else 0
            tout.addfile(info, io.BytesIO(data) if info.isreg() else None)
    return dst


def test_load_bundle_refuses_members_outside_model_dir_or_not_regular_files(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    work = tmp_path / "w" / "x"
    escape = tarfile.TarInfo("model/../../escaped.txt")
    folder = tarfile.TarInfo("model/sub2")
    folder.type = tarfile.DIRTYPE
    link = tarfile.TarInfo("model/link")
    link.type, link.linkname = tarfile.SYMTYPE, "/etc/passwd"
    stray = tarfile.TarInfo("notes.txt")
    for i, info in enumerate((escape, folder, link, stray)):
        bad = _with_members(out, tmp_path / f"bad{i}.tar", add=[(info.name, info, b"x")])
        with pytest.raises(bundle.BundleMismatch, match="허용하지 않는"):
            bundle.load_bundle(bad, work, _sha(bad))
    assert not (tmp_path / "w" / "escaped.txt").exists() and not (tmp_path / "escaped.txt").exists()


def test_load_bundle_refuses_missing_files_other_format_and_other_sha(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    with pytest.raises(bundle.BundleMismatch, match="sha256"):
        bundle.load_bundle(out, tmp_path / "x", "ab" * 32)
    gone = _with_members(out, tmp_path / "gone.tar", drop=["investigations.json"])
    with pytest.raises(bundle.BundleMismatch, match="investigations.json"):
        bundle.load_bundle(gone, tmp_path / "x", _sha(gone))
    extra = tarfile.TarInfo("model/extra.bin")
    unlisted = _with_members(
        out,
        tmp_path / "unlisted.tar",
        add=[("model/extra.bin", extra, b"x")],
        meta_edit=lambda m: m["files"].pop("model/extra.bin"),
    )
    with pytest.raises(bundle.BundleMismatch, match="파일 목록"):
        bundle.load_bundle(unlisted, tmp_path / "x", _sha(unlisted))
    old = _with_members(
        out, tmp_path / "old.tar", meta_edit=lambda m: m.update(format=bundle.FORMAT + 1)
    )
    with pytest.raises(bundle.BundleMismatch, match="형식"):
        bundle.load_bundle(old, tmp_path / "x", _sha(old))
    narrow = bundle.write_bundle(b, INV, vecs[:, :383], model_dir, tmp_path / "narrow")
    with pytest.raises(bundle.BundleMismatch, match="벡터 모양"):
        bundle.load_bundle(narrow, tmp_path / "x", _sha(narrow))


def test_bundle_round_trips_text_with_unicode_line_separators(tmp_path):
    cards = [dict(CARDS[0], defect="Line one line two\u0085end.")] + CARDS[1:]
    b = load_build(full_data_dir(tmp_path / "d", cards, [cause("24V001", pdfs=PDFS)]))
    _, _, model_dir = _inputs(tmp_path / "m")
    vecs = np.zeros((len(b.cards), 384), dtype="float32")
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    assert bundle.load_bundle(out, tmp_path / "x", _sha(out)).build == b


def test_bundle_tar_headers_are_fixed_and_members_sorted(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    with tarfile.open(out) as t:
        members = t.getmembers()
    names = [m.name for m in members]
    assert names[0] == "meta.json" and names[1:] == sorted(names[1:])
    for m in members:  # 시각·소유자·권한이 실행 환경에 따라 달라지면 같은 입력의 sha256이 달라진다
        assert (m.mtime, m.uid, m.gid, m.uname, m.gname, m.mode) == (0, 0, 0, "", "", 0o644)


@pytest.mark.parametrize(
    "field, value", [("fastembed_version", "0.0.0"), ("model", "BAAI/other-model")]
)
def test_check_identity_refuses_other_model_or_fastembed_version(tmp_path, field, value):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    bad = _with_members(out, tmp_path / "bad.tar", meta_edit=lambda m: m.update({field: value}))
    with pytest.raises(bundle.BundleMismatch, match="fastembed"):
        bundle.check_identity(bundle.load_bundle(bad, tmp_path / "x", _sha(bad)), b)


def test_load_bundle_refuses_duplicate_names_and_names_outside_model(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    dup = tarfile.TarInfo("cards.jsonl")
    with tarfile.open(out) as t:
        cards = t.extractfile("cards.jsonl").read()
    twice = _with_members(out, tmp_path / "dup.tar", add=[("cards.jsonl", dup, cards)])
    with pytest.raises(bundle.BundleMismatch, match="같은 이름"):
        bundle.load_bundle(twice, tmp_path / "x", _sha(twice))
    other = tarfile.TarInfo("other/x.bin")
    side = _with_members(out, tmp_path / "side.tar", add=[("other/x.bin", other, b"x")])
    with pytest.raises(bundle.BundleMismatch, match="허용하지 않는"):
        bundle.load_bundle(side, tmp_path / "x", _sha(side))


def test_bundle_needs_the_model_file_when_writing_and_reading(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    with pytest.raises(bundle.BundleMismatch, match="model_optimized.onnx"):
        bundle.write_bundle(b, INV, vecs, tmp_path / "no-such-dir", tmp_path / "o1")
    out = bundle.write_bundle(b, INV, vecs, model_dir, tmp_path / "out")
    gone = _with_members(out, tmp_path / "gone.tar", drop=["model/model_optimized.onnx"])
    with pytest.raises(bundle.BundleMismatch, match="model_optimized.onnx"):
        bundle.load_bundle(gone, tmp_path / "x", _sha(gone))


def test_bundle_bytes_do_not_depend_on_dict_key_order(tmp_path):
    b, vecs, model_dir = _inputs(tmp_path)
    a = {"24V001000": INV["24V001000"], "24V002000": []}
    z = {"24V002000": [], "24V001000": INV["24V001000"]}
    one = bundle.write_bundle(b, a, vecs, model_dir, tmp_path / "a")
    two = bundle.write_bundle(b, z, vecs, model_dir, tmp_path / "z")
    assert _sha(one) == _sha(two)


class FakeStore:
    """cmd_upload·cmd_verify를 네트워크·DB 없이 부른다 — 묶음 파일·build는 진짜, Storage·연결은 가짜."""

    def __init__(self, tmp_path, monkeypatch, row, url, send=None):
        import contextlib

        from server.rag import build as build_mod

        self.b, vecs, model_dir = _inputs(tmp_path)
        monkeypatch.setattr(bundle, "OUT_DIR", tmp_path / "serving")
        self.tar = bundle.write_bundle(self.b, INV, vecs, model_dir, tmp_path / "serving")
        self.sha = _sha(self.tar)
        monkeypatch.setattr(build_mod, "load_build", lambda: self.b)
        self.row, self.inserts, self.sent, self.served = row, [], [], self.tar

        def execute(sql, params=None):
            if sql.lstrip().startswith("insert"):
                self.inserts.append(params)
            return SimpleNamespace(fetchone=lambda: self.row)

        @contextlib.contextmanager
        def conn():
            yield SimpleNamespace(execute=execute)

        def download(url, dst):
            self.downloaded = url
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(self.served.read_bytes())

        monkeypatch.setattr(bundle, "connect", conn)
        monkeypatch.setattr(bundle, "_download", download)
        monkeypatch.setattr(bundle, "_send", send or self.sent.append)
        monkeypatch.setenv("SUPABASE_URL", url)
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-only-not-a-key")


def _upload_env(tmp_path, monkeypatch, row, url):
    return FakeStore(tmp_path, monkeypatch, row, url).sent


def test_cmd_upload_refuses_plain_http_before_sending_the_key(tmp_path, monkeypatch):
    opened = _upload_env(tmp_path, monkeypatch, None, "http://x.supabase.co")
    with pytest.raises(SystemExit, match="https"):
        bundle.main(["upload"])
    assert opened == []


def test_cmd_upload_refuses_when_a_different_record_exists(tmp_path, monkeypatch):
    opened = _upload_env(tmp_path, monkeypatch, ("ab" * 32, "x/other.tar"), "https://x.supabase.co")
    with pytest.raises(SystemExit, match="덮어쓰지 않는다"):
        bundle.main(["upload"])
    assert opened == []


def test_cmd_upload_records_only_after_the_public_file_matches(tmp_path, monkeypatch):
    s = FakeStore(tmp_path, monkeypatch, None, "https://x.supabase.co")
    bundle.main(["upload"])
    (req,) = s.sent
    want = f"{s.b.build_id}/{s.sha}.tar"  # 내용 해시가 저장 이름
    assert req.full_url.endswith(f"/storage/v1/object/serving-bundles/{want}")
    assert req.get_header("X-upsert") == "false"
    assert s.downloaded.endswith(f"/object/public/serving-bundles/{want}")
    assert [(p[0], p[2], p[3]) for p in s.inserts] == [(s.b.build_id, s.sha, want)]
    # Storage가 거부했고(409) 공개 주소에 다른 build의 묶음이 있으면 기록하지 않는다
    _, other = _other_build_bundle(tmp_path / "o")
    s2 = FakeStore(
        tmp_path / "2",
        monkeypatch,
        None,
        "https://x.supabase.co",
        send=lambda req: (_ for _ in ()).throw(
            bundle.urllib.error.HTTPError(req.full_url, 409, "Duplicate", {}, None)
        ),
    )
    s2.served = other
    with pytest.raises(bundle.BundleMismatch):
        bundle.main(["upload"])
    assert s2.inserts == []


def test_cmd_upload_sends_the_key_as_apikey_too(tmp_path, monkeypatch):
    # 새 형식 Secret 키(sb_secret_…)는 JWT가 아니라 Authorization만 보내면 Storage가 400("Invalid Compact JWS")으로 거부한다
    s = FakeStore(tmp_path, monkeypatch, None, "https://x.supabase.co")
    bundle.main(["upload"])
    (req,) = s.sent
    assert req.get_header("Apikey") == "test-only-not-a-key"
    assert req.get_header("Authorization") == "Bearer test-only-not-a-key"


def test_cmd_upload_shows_the_storage_reason_when_rejected(tmp_path, monkeypatch, capsys):
    # 400 이유가 키 형식("Invalid Compact JWS")이어도 "이미 있을 수 있음"만 보이면 원인을 놓친다 — 응답 본문을 함께 보인다
    import io

    def reject(req):
        raise bundle.urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"message":"Invalid Compact JWS"}')
        )

    s = FakeStore(tmp_path, monkeypatch, None, "https://x.supabase.co", send=reject)
    bundle.main(["upload"])  # 공개 주소의 파일이 같으면 그대로 기록까지 간다
    assert "Invalid Compact JWS" in capsys.readouterr().out
    assert len(s.inserts) == 1


def test_cmd_upload_checks_the_local_bundle_before_sending(tmp_path, monkeypatch):
    s = FakeStore(tmp_path, monkeypatch, None, "https://x.supabase.co")
    _, other = _other_build_bundle(tmp_path / "o")
    s.tar.write_bytes(other.read_bytes())  # 다른 build의 묶음을 이 build 이름으로 복사해 둠
    with pytest.raises(bundle.BundleMismatch, match="build"):
        bundle.main(["upload"])
    assert s.sent == [] and s.inserts == []


def test_cmd_upload_stops_on_redirect_and_does_not_follow_it(tmp_path, monkeypatch):
    def redirect(req):
        raise bundle.urllib.error.HTTPError(
            req.full_url, 301, "Moved", {"Location": "https://elsewhere"}, None
        )

    s = FakeStore(tmp_path, monkeypatch, None, "https://x.supabase.co", send=redirect)
    with pytest.raises(SystemExit, match="301"):
        bundle.main(["upload"])
    assert s.inserts == []
    req = bundle.urllib.request.Request(
        "https://x.supabase.co/a", headers={"Authorization": "Bearer k"}
    )
    assert (
        bundle._NoRedirect().redirect_request(req, None, 301, "Moved", {}, "https://elsewhere/a")
        is None
    )


@pytest.mark.parametrize("case", ["other_sha", "other_build"])
def test_cmd_verify_refuses_a_public_file_other_than_the_record(tmp_path, monkeypatch, case):
    s = FakeStore(tmp_path, monkeypatch, None, "https://x.supabase.co")
    s.row = (s.sha, f"{s.b.build_id}/{s.sha}.tar")
    bundle.main(["verify"])  # 기록과 같은 파일이면 통과
    _, other = _other_build_bundle(tmp_path / "o")
    s.served = other
    if case == "other_build":
        s.row = (
            _sha(other),
            f"{s.b.build_id}/{_sha(other)}.tar",
        )  # 기록까지 그 파일이라도 build가 다르면 거부
    with pytest.raises(bundle.BundleMismatch, match="sha256" if case == "other_sha" else "build"):
        bundle.main(["verify"])


def test_send_uses_an_opener_that_does_not_follow_redirects(monkeypatch):
    """관리자 키가 든 요청은 리디렉션을 따라가지 않는 열기 도구로만 보낸다 — 기본 urlopen은 따라가며 키를 넘긴다."""
    used = []

    def build_opener(*handlers):
        used.extend(handlers)
        return SimpleNamespace(open=lambda req, timeout: SimpleNamespace(read=lambda: b""))

    monkeypatch.setattr(bundle.urllib.request, "build_opener", build_opener)
    monkeypatch.setattr(bundle.urllib.request, "urlopen", lambda *a, **k: pytest.fail("urlopen"))
    bundle._send(bundle.urllib.request.Request("https://x.supabase.co/a"))
    assert bundle._NoRedirect in used

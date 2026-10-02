"""scripts/fetch_handbook_dataset.py 의 교체 단계 테스트 — 복사가 실패해도 기존 데이터가 남아야 한다."""

import shutil

import pytest

from scripts import fetch_handbook_dataset as fetch


def _make_dir(path, files):
    path.mkdir(parents=True)
    for name, text in files.items():
        (path / name).write_text(text, encoding="utf-8")


def test_install_content_replaces_existing(tmp_path):
    new = tmp_path / "new"
    target = tmp_path / "handbook" / "content"
    _make_dir(new, {"a.md": "new"})
    _make_dir(target, {"old.md": "old"})

    fetch.install_content(new, target)

    assert [p.name for p in target.iterdir()] == ["a.md"]
    assert not (tmp_path / "handbook" / "content.old").exists()
    assert not (tmp_path / "handbook" / "content.new").exists()


def test_install_content_works_without_existing_target(tmp_path):
    new = tmp_path / "new"
    target = tmp_path / "handbook" / "content"
    _make_dir(new, {"a.md": "new"})

    fetch.install_content(new, target)

    assert (target / "a.md").read_text(encoding="utf-8") == "new"


def test_install_content_keeps_existing_when_copy_fails(tmp_path, monkeypatch):
    new = tmp_path / "new"
    target = tmp_path / "handbook" / "content"
    _make_dir(new, {"a.md": "new"})
    _make_dir(target, {"old.md": "old"})

    real_copytree = shutil.copytree

    def broken_copytree(src, dst):
        real_copytree(src, dst)
        raise OSError("디스크 공간 부족")

    monkeypatch.setattr(fetch.shutil, "copytree", broken_copytree)

    with pytest.raises(OSError):
        fetch.install_content(new, target)

    assert (target / "old.md").read_text(encoding="utf-8") == "old"
    assert not (tmp_path / "handbook" / "content.new").exists()


def test_install_content_restores_backup_when_swap_fails(tmp_path, monkeypatch):
    new = tmp_path / "new"
    target = tmp_path / "handbook" / "content"
    _make_dir(new, {"a.md": "new"})
    _make_dir(target, {"old.md": "old"})

    real_rename = fetch.Path.rename

    def flaky_rename(self, dest):
        if self.name == "content.new":
            raise OSError("권한 없음")
        return real_rename(self, dest)

    monkeypatch.setattr(fetch.Path, "rename", flaky_rename)

    with pytest.raises(OSError):
        fetch.install_content(new, target)

    assert (target / "old.md").read_text(encoding="utf-8") == "old"

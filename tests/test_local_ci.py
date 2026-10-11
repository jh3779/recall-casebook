"""scripts/local_ci.sh의 종료 처리 회귀 테스트 — 중간에 멈추면 실패(0이 아님)로 끝나야 한다(PR #74).

macOS 기본 bash 3.2는 `set -u` 오류(unbound variable)로 끝날 때 종료 코드가 EXIT trap의 결과(0)가 된다. local_ci.sh는
맨 끝에 도달했을 때만 DONE=1이고 그 전에 끝나면 trap이 실패로 바꾼다. 실제 스크립트의 trap 부분을 그대로 떼어 돌려 본다.
"""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "local_ci.sh"
BASH = "/bin/bash" if Path("/bin/bash").exists() else shutil.which("bash")


def _trap_block() -> str:
    """local_ci.sh에서 `DONE=0`부터 `trap cleanup EXIT`까지(종료 처리 정의)를 그대로 가져온다."""
    s = SCRIPT.read_text(encoding="utf-8")
    start, end = s.index("DONE=0\n"), s.index("trap cleanup EXIT\n") + len("trap cleanup EXIT\n")
    return s[start:end]


def _run(body: str, tmp_path: Path) -> subprocess.CompletedProcess:
    script = tmp_path / "probe.sh"
    script.write_text(
        "set -euo pipefail\n"
        f'ROOT="{tmp_path}"\nTMP="{tmp_path}/wt"\nmkdir -p "$TMP"\n' + _trap_block() + body,
        encoding="utf-8",
    )
    return subprocess.run([BASH, str(script)], capture_output=True, text=True, errors="replace")


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_unbound_variable_midway_is_a_failure(tmp_path):
    """중간에 정의되지 않은 변수(한글이 붙은 $VAR 포함)로 멈추면 종료 코드가 0이 아니다."""
    r = _run('X=1\necho "a $X에 b"\necho "$UNDEFINED_PROBE_VAR"\nDONE=1\n', tmp_path)
    assert r.returncode != 0, r.stdout + r.stderr


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_reaching_the_end_is_success(tmp_path):
    r = _run("echo ok\nDONE=1\n", tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr


@pytest.mark.skipif(BASH is None, reason="bash 없음")
def test_explicit_failure_keeps_its_code(tmp_path):
    r = _run("exit 3\n", tmp_path)
    assert r.returncode == 3


def test_script_ends_with_done_marker():
    """성공 경로의 맨 끝이 DONE=1이어야 한다 — 이 줄이 빠지거나 앞으로 옮겨지면 정상 종료도 실패가 되거나 보호가 사라진다."""
    lines = [line for line in SCRIPT.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert lines[-1] == "DONE=1"
    assert sum(line.strip() == "DONE=1" for line in lines) == 1


def test_no_shell_variable_directly_followed_by_non_ascii():
    """bash는 `$VAR한글`의 한글 바이트를 변수 이름으로 읽는다 — `${VAR}한글`로 쓴다."""
    bad = [
        f"{p.name}:{i}"
        for p in SCRIPT.parent.glob("*.sh")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if re.search(r"\$[A-Za-z_][A-Za-z0-9_]*[^\x00-\x7f]", line)
    ]
    assert bad == []

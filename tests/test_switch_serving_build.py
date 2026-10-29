"""scripts/switch_serving_build.sh — 공개 서비스를 바꾸는 스크립트라 실패 경로를 가짜 명령으로 시험한다.

가짜 `vercel`·`curl`을 PATH 앞에 두고 상태(환경변수 값·공개 서버 build)를 파일로 흉내 낸다.
진짜 Vercel에는 아무것도 하지 않는다.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "switch_serving_build.sh"
OLD = "f1fe1843ed0f2c66"
NEW = "5e32c164b15a544a"
SHA = {
    OLD: "dd0efac013a47dd9cb5b303d4d7958724e9cba21254f4bb9bc6f7f87a190bc1a",
    NEW: "b466430d989b55e1d623346f70461428b6ec83bfbb0508eff40bbf4d98c25127",
}

FAKE_VERCEL = r"""#!/usr/bin/env bash
# 상태: $FAKE/env(환경변수 값), $FAKE/live(공개 서버 build), $FAKE/calls(호출 기록)
echo "vercel $*" >> "$FAKE/calls"
case "$1 $2" in
  "whoami "*) [ -n "${FAIL_WHOAMI:-}" ] && exit 1; echo tester ;;
  "env ls") [ -n "${FAIL_ENV_LS:-}" ] && exit 1; echo "SERVING_BUILD_ID Production" ;;
  "env rm")
    [ -f "$FAKE/env" ] || exit 1
    rm -f "$FAKE/env" ;;
  "env add")
    v=$(cat)
    [ "${FAIL_ADD_FOR:-}" = "$v" ] && exit 1
    printf '%s' "$v" > "$FAKE/env" ;;
  "deploy --prod")
    n=$(grep -c "^vercel deploy" "$FAKE/calls")
    if [ -n "${PROMOTE_THEN_FAIL:-}" ] && [ "$n" -eq 1 ]; then cp "$FAKE/env" "$FAKE/live"; exit 1; fi
    [ -n "${FAIL_DEPLOY_FROM:-}" ] && [ "$n" -ge "$FAIL_DEPLOY_FROM" ] && exit 1
    printf '%s' "$(cat "$FAKE/env")" > "$FAKE/live" ;;
  *) exit 2 ;;
esac
"""

FAKE_CURL = r"""#!/usr/bin/env bash
live=$(cat "$FAKE/live")
[ -n "${BAD_HEALTH:-}" ] && [ "$live" = "$BAD_HEALTH" ] && { echo '{"build_id":"broken","bundle_sha256":"x"}'; exit 0; }
echo "{\"build_id\":\"$live\",\"bundle_sha256\":\"$(grep "^$live " "$FAKE/sha" | cut -d' ' -f2)\"}"
"""


@pytest.fixture
def sandbox(tmp_path):
    fake = tmp_path / "fake"
    bin_dir = tmp_path / "bin"
    repo = tmp_path / "repo"
    fake.mkdir()
    bin_dir.mkdir()
    (repo / ".vercel").mkdir(parents=True)
    (repo / ".vercel" / "project.json").write_text('{"projectId":"p","projectName":"lg-cns-rag"}')
    (repo / ".gitignore").write_text(".vercel/\n")
    # pre-push 훅이 GIT_DIR 등을 둔 채 시험을 돌려도 이 임시 저장소만 건드리게 한다
    genv = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    genv.update(
        GIT_AUTHOR_NAME="t",
        GIT_AUTHOR_EMAIL="t@t",
        GIT_COMMITTER_NAME="t",
        GIT_COMMITTER_EMAIL="t@t",
    )

    def git(*a):
        subprocess.run(["git", "-C", str(repo), *a], check=True, env=genv, capture_output=True)

    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True, env=genv)
    git("init", "-q", "-b", "main")
    git("add", ".gitignore")
    git("commit", "-q", "-m", "init")
    git("remote", "add", "origin", str(origin))
    git("push", "-q", "origin", "main")
    for name, body in (("vercel", FAKE_VERCEL), ("curl", FAKE_CURL)):
        (bin_dir / name).write_text(body)
        (bin_dir / name).chmod(0o755)
    (fake / "calls").write_text("")
    (fake / "sha").write_text("".join(f"{b} {s}\n" for b, s in SHA.items()))
    (fake / "env").write_text(OLD)
    (fake / "live").write_text(OLD)

    def run(*args, answer="y\n", **env):
        e = {
            **genv,
            **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            "FAKE": str(fake),
            "SWITCH_SLEEP": "0",
        }
        e["PATH"] = f"{bin_dir}:{e['PATH']}"
        e.update(env)
        r = subprocess.run(
            ["bash", str(SCRIPT), *args],
            cwd=repo,
            env=e,
            input=answer,
            capture_output=True,
            text=True,
            timeout=60,
        )
        calls = (fake / "calls").read_text().splitlines()
        state = {
            "env": (fake / "env").read_text() if (fake / "env").exists() else None,
            "live": (fake / "live").read_text(),
            "calls": calls,
            "deploys": sum(1 for c in calls if c.startswith("vercel deploy")),
            "writes": sum(
                1
                for c in calls
                if c.startswith(("vercel env rm", "vercel env add", "vercel deploy"))
            ),
        }
        return r, state

    run.fake = fake
    run.repo = repo
    run.git = git
    return run


needs_bash = pytest.mark.skipif(shutil.which("bash") is None, reason="bash 필요")


@needs_bash
def test_switch_succeeds(sandbox):
    r, s = sandbox(NEW)
    assert r.returncode == 0, r.stdout + r.stderr
    assert s["env"] == NEW and s["live"] == NEW and s["deploys"] == 1


@needs_bash
def test_unknown_build_is_rejected_before_any_call(sandbox):
    r, s = sandbox("deadbeefdeadbeef")
    assert r.returncode != 0 and s["calls"] == []


@needs_bash
def test_check_changes_nothing(sandbox):
    r, s = sandbox(NEW, "--check")
    assert r.returncode == 0 and "사전 점검 통과" in r.stdout
    assert s["writes"] == 0 and s["env"] == OLD and s["live"] == OLD


@needs_bash
def test_check_fails_when_logged_out(sandbox):
    """/health는 로그인 없이 읽히므로, 로그인 확인이 없으면 --check가 거짓으로 통과한다."""
    r, s = sandbox(NEW, "--check", FAIL_WHOAMI="1")
    assert r.returncode != 0 and "로그인" in r.stdout
    assert s["writes"] == 0


@needs_bash
def test_check_fails_when_env_list_unreadable(sandbox):
    r, s = sandbox(NEW, "--check", FAIL_ENV_LS="1")
    assert r.returncode != 0 and s["writes"] == 0


@needs_bash
def test_declining_the_prompt_changes_nothing(sandbox):
    r, s = sandbox(NEW, answer="n\n")
    assert r.returncode == 0 and s["writes"] == 0 and s["env"] == OLD


@needs_bash
def test_env_add_failure_restores_old_value_and_does_not_deploy(sandbox):
    r, s = sandbox(NEW, FAIL_ADD_FOR=NEW)
    assert r.returncode != 0
    assert s["env"] == OLD and s["deploys"] == 0 and s["live"] == OLD


@needs_bash
def test_deploy_failure_restores_old_env(sandbox):
    r, s = sandbox(NEW, FAIL_DEPLOY_FROM="1")
    assert r.returncode != 0
    assert s["env"] == OLD and s["live"] == OLD and s["deploys"] == 1


@needs_bash
def test_bad_health_after_deploy_rolls_back_and_redeploys(sandbox):
    r, s = sandbox(NEW, BAD_HEALTH=NEW)
    assert r.returncode != 0
    assert s["env"] == OLD and s["live"] == OLD and s["deploys"] == 2
    assert "이전 build" in r.stdout


@needs_bash
def test_rollback_deploy_failure_is_reported_and_env_is_still_old(sandbox):
    """새 build가 안 뜨고 되돌리는 배포마저 실패하면, 환경변수는 이전 값이고 종료 코드는 실패이며 안내가 나온다."""
    r, s = sandbox(NEW, BAD_HEALTH=NEW, FAIL_DEPLOY_FROM="2")
    assert r.returncode != 0
    assert s["env"] == OLD and s["deploys"] == 2
    assert "되돌린 배포도" in r.stdout


@needs_bash
def test_already_live_but_env_left_over_is_realigned_without_deploy(sandbox):
    """배포가 실패해 환경변수만 새 값으로 남은 상태에서 옛 build로 '되돌리기'를 눌러도 환경변수를 고친다."""
    (sandbox.fake / "env").write_text(NEW)
    r, s = sandbox(OLD)
    assert r.returncode == 0, r.stdout + r.stderr
    assert s["env"] == OLD and s["live"] == OLD and s["deploys"] == 0


@needs_bash
def test_env_rm_failure_is_tolerated_when_variable_is_missing(sandbox):
    """이전 실패로 변수가 없는 상태에서도 넣기만 성공하면 바뀐다."""
    (sandbox.fake / "env").unlink()
    r, s = sandbox(NEW)
    assert r.returncode == 0 and s["env"] == NEW and s["live"] == NEW


@needs_bash
def test_deploy_command_failure_after_remote_promotion_redeploys_old(sandbox):
    """명령은 실패했지만 원격에서는 새 build가 올라간 경우 — 공개 서버를 이전 build로 되돌려 확인한다."""
    r, s = sandbox(NEW, PROMOTE_THEN_FAIL="1")
    assert r.returncode != 0
    assert s["env"] == OLD and s["live"] == OLD and s["deploys"] == 2


@needs_bash
def test_old_value_restore_failure_never_triggers_a_redeploy(sandbox):
    """이전 값을 못 넣었으면 변수 없이 재배포하지 않는다(변수가 없으면 서버가 시작하지 못한다)."""
    r, s = sandbox(NEW, BAD_HEALTH=NEW, FAIL_ADD_FOR=OLD)
    assert r.returncode != 0
    assert s["deploys"] == 1
    assert "재배포하지 않는다" in r.stdout


@needs_bash
def test_dirty_working_tree_is_rejected_even_for_check(sandbox):
    """vercel deploy --prod는 작업 폴더 전체를 올리므로 커밋하지 않은 변경이 있으면 --check도 중단한다."""
    (sandbox.repo / "stray.txt").write_text("x")
    for args in ((NEW,), (NEW, "--check")):
        r, s = sandbox(*args)
        assert r.returncode != 0 and "커밋하지 않은 변경" in r.stdout
        assert s["writes"] == 0 and s["env"] == OLD and s["live"] == OLD


@needs_bash
def test_head_behind_origin_main_is_rejected(sandbox):
    """로컬 main이 origin/main보다 뒤처졌으면(다른 사람이 더 병합함) 낡은 코드가 올라가므로 중단한다."""
    sandbox.git("commit", "-q", "--allow-empty", "-m", "newer")
    sandbox.git("push", "-q", "origin", "main")
    sandbox.git("reset", "-q", "--hard", "HEAD~1")
    r, s = sandbox(NEW)
    assert r.returncode != 0 and "origin/main과 다르다" in r.stdout
    assert s["writes"] == 0 and s["env"] == OLD and s["live"] == OLD

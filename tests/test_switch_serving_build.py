"""scripts/switch_serving_build.sh — 공개 서비스를 바꾸는 스크립트라 실패 경로를 가짜 명령으로 시험한다.

가짜 `vercel`·`curl`을 PATH 앞에 두고 상태(환경변수 값·공개 서버 build)를 파일로 흉내 낸다.
진짜 Vercel에는 아무것도 하지 않는다.
"""

import os
import shutil
import signal
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
    [ -n "${PROMOTE_FIRST:-}" ] && cp "$FAKE/env" "$FAKE/live"
    [ -n "${DEPLOY_SLEEP:-}" ] && [ "$n" -ge "${DEPLOY_SLEEP_FROM:-1}" ] && sleep "$DEPLOY_SLEEP"
    if [ -n "${PROMOTE_THEN_FAIL:-}" ] && [ "$n" -eq 1 ]; then cp "$FAKE/env" "$FAKE/live"; exit 1; fi
    [ -n "${FAIL_DEPLOY_FROM:-}" ] && [ "$n" -ge "$FAIL_DEPLOY_FROM" ] && exit 1
    printf '%s' "$(cat "$FAKE/env")" > "$FAKE/live" ;;
  *) exit 2 ;;
esac
"""

FAKE_CURL = r"""#!/usr/bin/env bash
live=$(cat "$FAKE/live")
n=$(grep -c "^vercel deploy" "$FAKE/calls")
# 배포를 N번 한 뒤부터 응답이 비거나(읽지 못함) 이상해지는 흉내 — 이전 build로 되돌린 뒤 확인 단계를 시험한다
[ -n "${EMPTY_AFTER_DEPLOYS:-}" ] && [ "$n" -ge "$EMPTY_AFTER_DEPLOYS" ] && exit 7
[ -n "${BAD_AFTER_DEPLOYS:-}" ] && [ "$n" -ge "$BAD_AFTER_DEPLOYS" ] && { echo '{"build_id":"broken","bundle_sha256":"x"}'; exit 0; }
# build_id는 맞고 묶음 sha256만 틀린 응답
[ -n "${WRONG_SHA_FOR:-}" ] && [ "$live" = "$WRONG_SHA_FOR" ] && { echo "{\"build_id\":\"$live\",\"bundle_sha256\":\"0000\"}"; exit 0; }
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

    def build_env(**env):
        e = {
            **genv,
            **{k: v for k, v in os.environ.items() if not k.startswith("GIT_")},
            "FAKE": str(fake),
            "SWITCH_SLEEP": "0",
        }
        e["PATH"] = f"{bin_dir}:{e['PATH']}"
        e.update(env)
        return e

    def snapshot():
        calls = (fake / "calls").read_text().splitlines()
        return {
            "env": (fake / "env").read_text() if (fake / "env").exists() else None,
            "live": (fake / "live").read_text(),
            "calls": calls,
            "deploys": sum(1 for c in calls if c.startswith("vercel deploy")),
        }

    def run(*args, answer="y\n", **env):
        e = build_env(**env)
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
    run.build_env = build_env
    run.snapshot = snapshot
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
    # 공개 서버가 아직 이전 build여도 실패한 배포가 늦게 완료될 수 있다는 안내를 빼먹지 않는다
    assert "늦게 완료" in r.stdout


@needs_bash
def test_bad_health_after_deploy_rolls_back_and_redeploys(sandbox):
    r, s = sandbox(NEW, BAD_HEALTH=NEW)
    assert r.returncode != 0
    assert s["env"] == OLD and s["live"] == OLD and s["deploys"] == 2
    assert "이전 build" in r.stdout
    assert "늦게 완료" in r.stdout  # 되돌린 재배포가 성공한 경로에도 안내가 있다


@needs_bash
def test_rollback_deploy_failure_is_reported_and_env_is_still_old(sandbox):
    """새 build가 안 뜨고 되돌리는 배포마저 실패하면, 환경변수는 이전 값이고 종료 코드는 실패이며 안내가 나온다."""
    r, s = sandbox(NEW, BAD_HEALTH=NEW, FAIL_DEPLOY_FROM="2")
    assert r.returncode != 0
    assert s["env"] == OLD and s["deploys"] == 2
    assert "되돌린 배포도" in r.stdout
    assert "늦게 완료" in r.stdout  # 되돌린 배포가 실패한 경로에도 안내가 있다


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
    # 복구가 실패한 경로에도 늦은 완료 안내와 수동 복구 절차(다시 실행)가 있다
    assert "늦게 완료" in r.stdout and "다시 실행" in r.stdout


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


@needs_bash
def test_rollback_redeploy_must_verify_the_old_build(sandbox):
    """되돌린 배포 뒤 /health가 이전 build로 확인되지 않으면 성공이라고 하지 않는다(목표 일치 비교를 느슨하게 하면 실패해야 한다)."""
    r, s = sandbox(NEW, BAD_HEALTH=NEW, BAD_AFTER_DEPLOYS="2")
    assert r.returncode != 0
    assert s["env"] == OLD and s["deploys"] == 2
    assert (
        "되돌린 배포도" in r.stdout
        and "이전 build" in r.stdout
        and "로 되돌렸습니다" not in r.stdout
    )


@needs_bash
def test_unreadable_health_after_deploy_is_a_failure_and_rolls_back(sandbox):
    """네트워크 실패·시간 초과로 /health가 비어도(읽지 못함) 성공으로 끝나지 않고 이전 값으로 되돌린다."""
    r, s = sandbox(NEW, EMPTY_AFTER_DEPLOYS="1")
    assert r.returncode != 0
    assert s["env"] == OLD
    assert "읽지 못함" in r.stdout


@needs_bash
def test_matching_build_id_with_wrong_bundle_sha_is_not_success(sandbox):
    """build_id만 맞고 묶음 sha256이 틀리면 바뀐 것이 아니다."""
    r, s = sandbox(NEW, WRONG_SHA_FOR=NEW)
    assert r.returncode != 0
    assert s["env"] == OLD and s["deploys"] == 2


def _run_and_signal(sandbox, sig, wait_for, deploys=1, **env):
    """스크립트를 띄워 wait_for 문구가 호출 기록에 나타나면 프로세스 그룹에 신호를 보내고 (종료 코드, 출력)을 돌려준다."""
    import time

    proc = subprocess.Popen(
        ["bash", str(SCRIPT), NEW],
        cwd=sandbox.repo,
        env=sandbox.build_env(**env),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    proc.stdin.write("y\n")
    proc.stdin.flush()
    calls = sandbox.fake / "calls"
    deadline = time.time() + 20
    while time.time() < deadline and calls.read_text().count(wait_for) < deploys:
        time.sleep(0.1)
    assert calls.read_text().count(wait_for) >= deploys, "목표 단계에 이르지 못했다"
    time.sleep(0.5)  # 배포 명령이 끝났다면 /health 대기에 들어갈 시간을 준다
    os.killpg(proc.pid, sig)
    out, _ = proc.communicate(timeout=60)
    return proc.returncode, out, sandbox.snapshot()


@needs_bash
@pytest.mark.parametrize("sig", [signal.SIGINT, signal.SIGTERM, signal.SIGHUP])
def test_interrupt_during_deploy_restores_old_env_and_tells_to_recheck(sandbox, sig):
    """배포 도중 Ctrl-C·종료·터미널 닫힘으로 끊겨도 환경변수를 이전 값으로 되돌리고, 공개 상태를 다시 보라고 알린다."""
    rc, out, s = _run_and_signal(sandbox, sig, "vercel deploy", DEPLOY_SLEEP="30")
    assert rc == 130, out
    assert s["env"] == OLD and s["deploys"] == 1
    assert "다시 실행" in out and "신호를 무시" in out


@needs_bash
def test_interrupt_never_redeploys_even_if_remote_already_promoted(sandbox):
    """끊은 시점에 원격이 이미 새 build였어도 핸들러는 재배포하지 않는다(재배포하면 recover로 바뀐 것)."""
    rc, out, s = _run_and_signal(
        sandbox, signal.SIGINT, "vercel deploy", DEPLOY_SLEEP="30", PROMOTE_FIRST="1"
    )
    assert rc == 130, out
    assert s["deploys"] == 1 and s["live"] == NEW and s["env"] == OLD


@needs_bash
def test_interrupt_while_waiting_for_health_keeps_new_env(sandbox):
    """배포가 끝난 뒤 /health 확인 중에 끊으면 환경변수를 이전 값으로 되돌리지 않는다 — 서버(새 build)와 어긋나지 않게."""
    proc_env = dict(WRONG_SHA_FOR=NEW, SWITCH_SLEEP="30")
    rc, out, s = _run_and_signal(sandbox, signal.SIGINT, "vercel deploy", **proc_env)
    assert s["live"] == NEW and s["env"] == NEW and s["deploys"] == 1, out
    assert rc != 0


@needs_bash
def test_interrupt_during_recovery_is_ignored_and_recovery_completes(sandbox):
    """/health 확인이 실패해 이전 build를 되돌려 배포하는 도중 끊어도 복구는 끝까지 간다(환경변수와 공개 서버가 어긋나지 않는다)."""
    rc, out, s = _run_and_signal(
        sandbox,
        signal.SIGINT,
        "vercel deploy",
        deploys=2,
        BAD_HEALTH=NEW,
        DEPLOY_SLEEP="3",
        DEPLOY_SLEEP_FROM="2",
    )
    assert s["env"] == OLD and s["live"] == OLD and s["deploys"] == 2, out
    assert "신호를 무시" in out and rc != 0


@needs_bash
def test_closed_terminal_still_restores_env_before_any_output(sandbox):
    """터미널 창을 닫아 화면 출력이 실패(EIO)해도 SIGHUP 처리에서 환경변수를 이전 값으로 되돌린다(set -e로 멈추지 않는다)."""
    import pty
    import time

    master, slave = pty.openpty()
    proc = subprocess.Popen(
        ["bash", str(SCRIPT), NEW],
        cwd=sandbox.repo,
        env=sandbox.build_env(DEPLOY_SLEEP="30"),
        stdin=subprocess.PIPE,
        stdout=slave,
        stderr=slave,
        text=True,
        start_new_session=True,
    )
    os.close(slave)
    proc.stdin.write("y\n")
    proc.stdin.flush()
    calls = sandbox.fake / "calls"
    deadline = time.time() + 20
    while time.time() < deadline and "vercel deploy" not in calls.read_text():
        time.sleep(0.1)
    assert "vercel deploy" in calls.read_text(), "배포 단계에 이르지 못했다"
    os.close(master)  # 터미널 닫기 — 이후 화면 쓰기는 실패한다
    time.sleep(0.3)
    os.killpg(proc.pid, signal.SIGHUP)
    proc.wait(timeout=30)
    s = sandbox.snapshot()
    assert s["env"] == OLD and s["deploys"] == 1

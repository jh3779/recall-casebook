"""DB 테스트 대상이 일회용 로컬 Postgres인지 본다 — DB 테스트는 대상 DB의 public 스키마를 지운다.

URL의 겉모양(`urlparse().hostname`)이 아니라 libpq가 실제로 접속할 `host`·`hostaddr`를 본다
(`postgresql://…@localhost/db?host=prod.example.com`은 겉으로는 localhost지만 prod에 접속한다, PR #74 리뷰).
호스트를 적지 않은 주소는 환경변수(PGHOST)·소켓에 따라 대상이 달라지므로 받지 않는다. URL에 `hostaddr`가 없으면
libpq는 환경변수 `PGHOSTADDR`를 쓰므로 그것도 본다(PR #74 리뷰). 한계: `PGSERVICE`(서비스 파일)로 대상을 바꾸는 경우는 보지
않는다 — 그 변수가 있으면 로컬로 보지 않는다.

    uv run python -m scripts.ci.db_guard "$TEST_DATABASE_URL"   # 로컬이면 종료 코드 0
"""

import os
import sys

LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1"})


def is_local_test_db(url: str) -> bool:
    from psycopg.conninfo import conninfo_to_dict

    try:
        info = conninfo_to_dict(url)
    except Exception:  # 읽지 못하는 주소는 로컬로 보지 않는다
        return False
    if os.environ.get("PGSERVICE") or info.get("service"):
        return False  # 서비스 파일이 대상을 바꿀 수 있다
    hosts = [h for h in str(info.get("host", "")).split(",") if h]
    hostaddr = info.get("hostaddr") or os.environ.get("PGHOSTADDR", "")
    addrs = [a for a in str(hostaddr).split(",") if a]
    return bool(hosts) and all(h in LOCAL_HOSTS for h in hosts + addrs)


if __name__ == "__main__":
    sys.exit(0 if len(sys.argv) == 2 and is_local_test_db(sys.argv[1]) else 1)

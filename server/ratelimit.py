"""IP별 호출 상한 (이슈 #63) — 비밀 키 없이 공개 API를 지키는 앱 쪽 장치.

- 기본은 `POST /search`만 센다(`route`로 다른 경로를 따로 센다 — `POST /draft`는 유료 호출이라 별도 상한). `/health`와 CORS 사전 요청(OPTIONS)은 세지 않는다.
- 최근 `window`초 안의 호출이 `limit`번이면 429와 `Retry-After`를 낸다. 상한에 걸린 호출은 세지 않아 기다리면 풀린다.
- 서버리스는 인스턴스마다 메모리가 따로라 인스턴스 수만큼 상한이 느슨해진다 → 폭주는 Vercel WAF 규칙이 막는다
  (앱 60/분보다 느슨한 안전망, `docs/guides/배포_Vercel.md`).
- CORS 미들웨어 **안쪽**에 둬야 429 응답에도 `Access-Control-Allow-Origin`이 붙는다(`server/api.py` `create_app`).
"""

import ipaddress
import math
import os
import time
from collections import deque
from collections.abc import Callable

from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

DEFAULT_LIMIT = 60  # IP당 1분 (사용자 결정 2026-10-13)
WINDOW_SECONDS = 60.0
MAX_KEYS = 10_000  # 메모리 상한 — 넘으면 창이 지난 IP부터 지운다
LIMITED_ROUTE = ("POST", "/search")


def limit_from_env() -> int:
    """`RATE_LIMIT_PER_MINUTE`. 비어 있으면 기본값, 1 이상의 정수가 아니면 짐작하지 않고 멈춘다."""
    raw = os.environ.get("RATE_LIMIT_PER_MINUTE", "").strip()
    if not raw:
        return DEFAULT_LIMIT
    try:
        n = int(raw)
    except ValueError:
        n = 0
    if n < 1:
        raise RuntimeError(f"RATE_LIMIT_PER_MINUTE={raw!r} — 1 이상의 정수만 쓴다")
    return n


class RateLimiter:
    def __init__(
        self,
        limit: int = DEFAULT_LIMIT,
        window: float = WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.limit, self.window, self._clock = limit, window, clock
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str) -> int:
        """호출 하나를 센다. 허용이면 0, 상한이면 다시 시도할 수 있을 때까지 남은 초(올림, 1 이상)."""
        now = self._clock()
        q = self._hits.setdefault(key, deque())
        while q and q[0] <= now - self.window:
            q.popleft()
        if len(q) >= self.limit:
            return max(1, math.ceil(q[0] + self.window - now))
        q.append(now)
        if len(self._hits) > MAX_KEYS:
            self._purge(now)
        return 0

    def _purge(self, now: float) -> None:
        for k in [k for k, q in self._hits.items() if not q or q[-1] <= now - self.window]:
            del self._hits[k]
        extra = len(self._hits) - MAX_KEYS
        if extra > 0:  # 창 안의 IP만 남았는데도 많으면 가장 오래 조용한 IP부터 지운다
            for k in sorted(self._hits, key=lambda k: self._hits[k][-1])[:extra]:
                del self._hits[k]


def counting_key(ip: str) -> str:
    """IPv6는 한 가입자가 /64 안의 주소를 마음대로 바꿀 수 있어, 주소 하나가 아니라 앞 64비트(/64)로 묶어 센다(이슈 #118).
    IPv4와 IPv4-매핑 IPv6(`::ffff:1.2.3.4`)는 IPv4 주소 하나, IP로 읽히지 않는 값은 그대로 쓴다."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return ip
    if isinstance(addr, ipaddress.IPv6Address):
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network((addr, 64), strict=False))
    return str(addr)


def client_ip(request: Request) -> str:
    """Vercel은 외부에서 온 X-Forwarded-For를 전달하지 않고 덮어써서 위조할 수 없다(Vercel 요청 머리글 문서).
    그 밖의 환경에서는 이 머리글을 믿지 않고 소켓 주소를 쓴다."""
    if os.environ.get("VERCEL"):
        first = request.headers.get("x-forwarded-for", "").split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


def route_path(scope: Scope) -> str:
    """라우터가 보는 경로 — `root_path` 접두어를 뺀 `scope["path"]`(Starlette `get_route_path`와 같은 규칙).
    원문 `scope["path"]`로 비교하면 서버가 `root_path` 아래에서 돌 때 앱 상한이 말없이 꺼진다(이슈 #118)."""
    path, root = scope["path"], scope.get("root_path", "")
    if not root or not path.startswith(root):
        return path
    if path == root:
        return ""
    return path[len(root) :] if path[len(root)] == "/" else path


class RateLimitMiddleware:
    def __init__(self, app: ASGIApp, limiter: RateLimiter, route: tuple[str, str] = LIMITED_ROUTE):
        self.app, self.limiter, self.route = app, limiter, route

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and (scope["method"], route_path(scope)) == self.route:
            wait = self.limiter.hit(counting_key(client_ip(Request(scope))))
            if wait:
                response = JSONResponse(
                    {"detail": f"호출이 너무 잦습니다. {wait}초 뒤에 다시 시도해 주세요."},
                    status_code=429,
                    headers={"Retry-After": str(wait)},
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)

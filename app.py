"""Vercel 진입점 — 앱 정본은 `server/api.py`. 배포 서버는 서빙 묶음에서 시작한다(`RAG_SOURCE=bundle`, DEC-050).

배포 환경변수는 `.env.example`의 배포 서버 절과 `docs/guides/배포_Vercel.md`를 따른다(관리자 키·`DATABASE_URL`은 두지 않는다).
"""

from server.api import app

__all__ = ["app"]

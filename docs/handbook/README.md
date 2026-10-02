# docs/handbook — GitLab 공개 핸드북 데이터셋

> 이 폴더는 `.gitignore`에 등록돼 있어 **커밋되지 않는다**. 팀원 각자 로컬에 받아서 쓴다.
> 원문: [`suuuuuuungho/GitLab_Data`](https://github.com/suuuuuuungho/GitLab_Data) 커밋 `0ab0299`.
> 원본은 [gitlab.com/gitlab-com/content-sites/handbook](https://gitlab.com/gitlab-com/content-sites/handbook). 영어 원문 그대로 쓴다.
> 실측·토큰 추정치의 전체 맥락은 [`../기획v1.md`](../기획v1.md) 3절을 본다.

## 구조

```
docs/handbook/
  content/
    handbook/                   ← 실질 콘텐츠 (36개 하위 디렉토리, 아래 표)
    job-description-library/    ← 직무기술서 라이브러리 (431개 md, 조직 부서 아님)
    teamops/                    ← 협업 방법론 문서 (5개 md, 조직 부서 아님)
```

`content/handbook/`과 `content/job-description-library/`, `content/teamops/`는 서로 다른 사이트 섹션이다 — `content/handbook/job-description-library/`·`content/handbook/teamops/`는 각각 1개 md짜리 스텁(리다이렉트용)이고, 실제 내용은 위 최상위 두 폴더에 있다.

## 실측 수치 (2026-10-02, 비문서 파일 정리 후 기준)

| 항목 | 값 |
|---|---|
| 전체 용량 | 56MB |
| 전체 md 파일 | 4,612개 (전부 `.md` — zip·이미지·스크립트 등 13개는 정리함) |
| `handbook/` 하위 1단계 디렉토리 | 36개 |
| 핵심 부서(스텁 2개 제외) | 34개 |
| 추정 토큰 수 | 약 1,175만 (글자수 ÷ 4 경험칙, 정밀 토크나이저 미설치) |

## 부서별 md 수 (상위 10개)

| 부서 | md 수 |
|---|---|
| engineering | 1,272 |
| security | 425 |
| marketing | 366 |
| support | 309 |
| customer-experience | 306 |
| company | 246 |
| sales | 188 |
| eta | 186 |
| legal | 113 |
| upstream-studios | 109 |

전체 34개 부서의 md 수·추정 토큰 수는 [`../기획v1.md`](../기획v1.md) 3절 표에 있다.

## 이미 정리한 것

원본 스냅샷에는 RAG 코퍼스(텍스트)에 불필요한 비문서 파일 13개가 있었다 — 전부 삭제했다.

- `handbook.zip` (16MB) — `handbook/` 폴더 전체를 담은 중복 압축본
- `_index.html` — Hugo 사이트 템플릿 조각
- 이미지 4개(`featured-background.png`, teamops 일러스트 3개)
- `check-files.sh`, `720p.scpt` — 유지보수용 스크립트
- `diagrams.drawio` 2개 — 다이어그램 소스
- `www-gitlab-com.code-workspace` — VSCode 워크스페이스 설정
- `placeholder.txt` 2개 — 빈 파일

## 재현 방법

이 폴더가 로컬에 없으면 위 GitHub 저장소를 받아 `content/` 디렉토리를 `docs/handbook/content/`에 두면 된다. 받는 스크립트는 아직 없다 — 필요해지면 `scripts/`에 추가한다 (AGENTS.md 7절: 원본 데이터는 커밋하지 않고 재현 스크립트를 커밋한다).

# 검색 화면 시험 응답

- `search_airbag.json`·`health.json`: `docs/design-system/mockup.html`의 `data-search`·`data-health` 스크립트 본문을 그대로 복사했다. 2026-10-13 공개 API 응답, build `f1fe1843ed0f2c66`. 질문 `airbag inflator rupture during deployment`. 테스트에서만 읽으며 서비스의 대체 응답으로 쓰지 않는다.
- `cause_statuses_synthetic.json`: **합성 — 형식 확인용** 원인 상태. 실제 리콜·평가 질문·정답이 아니다. 공개 응답에 없는 5종과 모르는 상태 처리만 검사한다.

갱신할 때는 같은 `<script type="application/json">` 본문을 추출하거나 공개 API 응답을 저장한 뒤 수집일·질문·build를 이 파일에 기록한다. 원문을 다듬거나 정답을 붙이지 않는다.

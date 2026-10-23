/**
 * 검색 요청 하나만 "지금 요청"으로 인정하는 관리자. 새 요청을 시작하거나 무효로 하면 이전 요청은 취소 신호를 받고 그 응답은 버려진다 —
 * 취소 신호를 무시하고 늦게 끝난 이전 응답이 새 질문 밑에 들어가지 않게 하는 판단을 화면에서 떼어 시험한다(PR #164 Codex 리뷰).
 */
export class RequestGate {
  private current: AbortController | null = null;

  /** 새 요청을 시작한다. 진행 중이던 요청은 취소하고 더는 인정하지 않는다 */
  begin(): AbortController {
    this.current?.abort();
    this.current = new AbortController();
    return this.current;
  }

  /** 지금 요청을 취소하고 무효로 한다(새 질문이 왔을 때·화면이 사라질 때). 그 응답은 나중에 도착해도 버려진다 */
  invalidate(): void {
    this.current?.abort();
    this.current = null;
  }

  /** 이 요청의 응답을 화면에 넣어도 되는가 — 아직 지금 요청일 때만. 요청이 끝났는지는 모른다: `begin` 뒤 `invalidate`나 다음 `begin` 전까지는 계속 인정한다 */
  accepts(request: AbortController): boolean {
    return this.current === request;
  }
}

export type View = "landing" | "search" | "showroom" | "8d" | "casebook";

/** 화면을 주소 해시로 — 랜딩은 해시를 비운다 */
export const hashOfView = (view: View) => (view === "landing" ? "" : view);

/** 주소 해시로 화면을 고른다. 해시가 없으면 랜딩이고, 모르는 해시는 예전처럼 검색 화면이다 (DEC-074) */
export function viewOfHash(hash: string): View {
  if (hash === "" || hash === "#") return "landing";
  return hash === "#showroom" ? "showroom" : hash === "#8d" ? "8d" : hash === "#casebook" ? "casebook" : "search";
}

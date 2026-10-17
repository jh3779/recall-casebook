import { ApiError } from "../api";

/** 화면이 영어라서 서버·api.ts의 한국어 오류 문구 대신 종류별 영어 안내를 쓴다 */
export function errorText(e: unknown, what: "search" | "grouping"): string {
  if (!(e instanceof ApiError)) return "Could not reach the server.";
  if (e.status === 404 && what === "grouping") return "Grouping is not available on this server.";
  switch (e.kind) {
    case "validation": return what === "search" ? "The question was rejected. Write the defect in English (at most 4,000 characters)." : "The server rejected the request. Search again and check the precedents again.";
    case "rate_limit": return `Too many requests. Try again in ${e.retryAfter ?? 60} seconds.`;
    case "timeout": return "No response within 60 seconds.";
    case "network": return "Could not reach the server.";
    case "shape": return "The server answered in an unexpected format.";
    default: return `The server returned an error${e.status ? ` (${e.status})` : ""}.`;
  }
}

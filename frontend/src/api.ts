import type { Card, Cause, HealthResponse, ProvenanceData, SearchResponse } from "./search/types";

export const API_BASE = (import.meta.env.VITE_API_BASE || "https://lg-cns-rag.vercel.app").replace(/\/+$/, "");
export type ApiErrorKind = "validation" | "rate_limit" | "network" | "timeout" | "server" | "shape";
export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly status?: number;
  readonly buildId?: string;
  readonly retryAfter?: number; // 호출 상한(429)일 때 다시 보낼 수 있을 때까지 남은 초(DEC-057)
  readonly retryAt?: number; // 그 초를 받은 시각 기준 마감(ms) — 화면이 남은 초를 셀 때 쓴다
  constructor(kind: ApiErrorKind, message: string, status?: number, buildId?: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.status = status;
    this.buildId = buildId;
    this.retryAfter = retryAfter;
    this.retryAt = retryAfter === undefined ? undefined : Date.now() + retryAfter * 1000;
  }
}
const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const strings = (v: Record<string, unknown>, keys: string[]) => keys.every((key) => typeof v[key] === "string");
const nullableString = (v: unknown) => v === null || typeof v === "string";
const arrayOf = (v: unknown, guard: (item: unknown) => boolean) => Array.isArray(v) && v.every(guard);

function isCause(v: unknown): v is Cause {
  if (!record(v) || typeof v.status !== "string") return false;
  if (v.status === "filled" || v.status === "stated_unknown") {
    return strings(v, ["text", "speaker"]) && record(v.source)
      && strings(v.source, ["campaign", "file", "pdf_sha256", "submission_date", "text_basis"])
      && arrayOf(v.flags, (f) => record(f) && ["unknown_expression", "hedge_expression"].includes(String(f.kind))
        && typeof f.label === "string" && arrayOf(f.spans, (s) => record(s) && Number.isInteger(s.start)
          && Number.isInteger(s.end) && typeof s.text === "string"));
  }
  if (v.status === "report_unreadable") return strings(v, ["campaign", "reason"]);
  if (["report_status_unknown", "version_unresolved", "cause_empty", "cause_no_field", "verify_failed"].includes(v.status)) return typeof v.campaign === "string";
  return true;
}
function isCard(v: unknown): v is Card {
  return record(v) && Number.isInteger(v.rank) && strings(v, ["campno", "maker", "received_date", "defect", "consequence", "remedy", "dup_group"])
    && nullableString(v.maker_group) && arrayOf(v.components, (c) => typeof c === "string")
    && record(v.source) && strings(v.source, ["dataset", "snapshot_date", "speaker"]) && isCause(v.cause)
    && arrayOf(v.investigations, (i) => record(i) && strings(i, ["action", "speaker", "subject", "summary", "open_date", "close_date"]))
    && arrayOf(v.checklist, (c) => record(c) && strings(c, ["item", "label"])
      && arrayOf(c.evidence, (e) => record(e) && strings(e, ["field", "text"])));
}
function isProvenance(v: unknown): v is ProvenanceData & Record<string, unknown> {
  return record(v) && strings(v, ["build_id", "snapshot_date", "model"]) && nullableString(v.bundle_sha256);
}
const isSearch = (v: unknown): v is SearchResponse => isProvenance(v) && typeof v.question === "string"
  && arrayOf(v.customer_precedents, isCard) && arrayOf(v.precedents, isCard);
const isHealth = (v: unknown): v is HealthResponse => isProvenance(v) && Number.isInteger(v.cards) && Number(v.cards) >= 0;

async function request<T>(path: string, init: RequestInit, guard: (v: unknown) => v is T): Promise<T> {
  try {
    const response = await fetch(`${API_BASE}${path}`, init);
    if (!response.ok) {
      if (response.status === 422) {
        const body: unknown = await response.json().catch(() => null);
        const detail = record(body) && Array.isArray(body.detail) ? body.detail[0] : null;
        const message = record(detail) && typeof detail.msg === "string" ? detail.msg.replace(/^Value error, /, "") : "질문을 다시 확인해 주세요";
        throw new ApiError("validation", message, 422);
      }
      if (response.status === 429) {
        // 서버 상한은 IP당 1분이라 머리글이 없거나 이상하면 60초를 기다린다
        const seconds = Number.parseInt(response.headers.get("Retry-After") ?? "", 10);
        const wait = Number.isInteger(seconds) && seconds > 0 ? seconds : 60;
        throw new ApiError("rate_limit", "호출이 너무 잦습니다. 잠시 뒤에 다시 시도해 주세요.", 429, undefined, wait);
      }
      throw new ApiError("server", `서버 오류가 났습니다 (${response.status})`, response.status);
    }
    let body: unknown;
    try { body = await response.json(); }
    catch (error) {
      if (error instanceof SyntaxError) throw new ApiError("shape", "응답이 JSON 형식이 아닙니다");
      throw error;
    }
    if (!guard(body)) throw new ApiError("shape", "응답 형식이 예상과 다릅니다", undefined, record(body) && typeof body.build_id === "string" ? body.build_id : undefined);
    return body;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (init.signal?.aborted || (error instanceof Error && ["AbortError", "TimeoutError"].includes(error.name))) throw new ApiError("timeout", "응답이 60초 안에 오지 않았습니다");
    throw new ApiError("network", `네트워크 또는 허용 주소(CORS) 설정을 확인해 주세요. API 주소: ${API_BASE}`);
  }
}
export const search = (question: string, signal?: AbortSignal) => request("/search", {
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question }), signal,
}, isSearch);
export const health = (signal?: AbortSignal) => request("/health", { signal }, isHealth);

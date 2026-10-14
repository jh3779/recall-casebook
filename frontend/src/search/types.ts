export interface Flag {
  kind: "unknown_expression" | "hedge_expression";
  label: string;
  spans: { start: number; end: number; text: string }[];
}
export interface CauseSource {
  campaign: string;
  file: string;
  pdf_sha256: string;
  submission_date: string;
  text_basis: string;
}
export interface TextCause {
  status: "filled" | "stated_unknown";
  text: string;
  speaker: string;
  source: CauseSource;
  flags: Flag[];
}
export type Cause = TextCause
  | { status: "no_573_report" }
  | { status: "report_unreadable"; campaign: string; reason: string }
  | { status: "report_status_unknown" | "version_unresolved" | "cause_empty" | "cause_no_field" | "verify_failed"; campaign: string }
  | { status: string; campaign?: string };

export function hasCauseText(cause: Cause): cause is TextCause {
  return (cause.status === "filled" || cause.status === "stated_unknown") && "text" in cause;
}
export interface Investigation {
  action: string;
  speaker: string;
  subject: string;
  summary: string;
  open_date: string;
  close_date: string;
}
interface CheckBase {
  label: string;
  evidence: { field: string; text: string }[];
}
export interface PlainCheckItem extends CheckBase {
  item: "same_part" | "failure_mode" | "remedy" | "supplier" | "cause_speaker";
}
/** 생산 기간 항목: 읽은 573 보고서 판본(`source`)이 반드시 있고, 싣지 못한 블록 수(`omitted`)를 알린다(최대 5개만 싣는다) */
export interface ProductionCheckItem extends CheckBase {
  item: "production_period";
  omitted: number;
  /** 날짜까지 읽히지 않아 싣지 않은 블록 수 */
  unread: number;
  source: { campaign: string; file: string; pdf_sha256: string; submission_date: string };
}
export type CheckItem = PlainCheckItem | ProductionCheckItem;
export interface Card {
  rank: number;
  campno: string;
  maker: string;
  maker_group: string | null;
  received_date: string;
  components: string[];
  defect: string;
  consequence: string;
  remedy: string;
  dup_group: string;
  source: { dataset: string; snapshot_date: string; speaker: string };
  cause: Cause;
  investigations: Investigation[];
  checklist: CheckItem[];
}
export interface ProvenanceData {
  build_id: string;
  bundle_sha256: string | null;
  snapshot_date: string;
  model: string;
}
export interface SearchResponse extends ProvenanceData {
  question: string;
  customer_precedents: Card[];
  precedents: Card[];
}
export interface HealthResponse extends ProvenanceData { cards: number }
export type HealthState = HealthResponse | "loading" | "error";

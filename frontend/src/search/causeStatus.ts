import type { Cause } from "./types";

export function causeStatus(cause: Cause) {
  const campaign = "campaign" in cause ? cause.campaign : "";
  const reason = "reason" in cause ? cause.reason : "";
  const messages: Record<string, string> = {
    filled: "Part 573 원인 칸 원문입니다.",
    stated_unknown: "Part 573 원인 칸 원문입니다. 원인 서술 대신 미보고·조사 중 등의 표현으로 시작하는 글로 분류됐습니다(DEC-047). 원인을 모른다는 뜻으로 단정하지 않습니다.",
    no_573_report: "접수일이 2014-08-20 이전이라 Part 573 원문 수집 범위 밖입니다. 원인 원문을 싣지 않습니다.",
    report_unreadable: `Part 573 보고서(${campaign})를 읽지 못했습니다. 사유: ${reason}`,
    report_status_unknown: `Part 573 보고서(${campaign})를 수집했는지 확인하지 못했습니다.`,
    version_unresolved: `Part 573 보고서(${campaign})의 판본이 여럿이고 최신판을 정하지 못해 원인 원문을 싣지 않습니다.`,
    cause_empty: `Part 573 보고서(${campaign})의 원인 칸이 비어 있습니다.`,
    cause_no_field: `Part 573 보고서(${campaign})에서 원인 칸을 찾지 못했습니다.`,
    verify_failed: `원인 원문이 글자 대조를 통과하지 못해 싣지 않습니다(${campaign}).`,
  };
  const level = cause.status === "filled" ? "text" : cause.status === "stated_unknown" ? "stated" : "none";
  const label = { text: "원인 원문 있음", stated: "미보고·조사 중 표현", none: "원인 원문 없음" }[level];
  return { level, label, message: Object.hasOwn(messages, cause.status) ? messages[cause.status] : `원인 상태: ${cause.status}` };
}

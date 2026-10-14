const labels: Record<string, string> = {
  components: "부품", defect: "결함", consequence: "결과", remedy: "시정",
  "573.supplier_names": "573 공급사 칸", "573.production_dates": "573 생산 기간 칸", "cause.speaker": "원인을 말한 주체",
  "investigations.speaker": "조사 요약을 말한 주체", "investigations.action": "조사 번호",
};
export const fieldLabel = (field: string) => Object.hasOwn(labels, field) ? labels[field] : field;

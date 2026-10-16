import { shortLabel, STEPS, type Step } from "./document";

/** 칸 안의 글 — 칸에 쓴 글 그대로, 여러 칸이 한 단계에 있으면 칸 이름을 굵게 앞에 붙인다(실제 .docx 삽입 결과와 같은 모양) */
function cell(step: Step, values: Record<string, string>) {
  return step.fields.flatMap((f) => {
    const value = values[f.key]?.trim();
    if (!value) return [];
    return [<p key={f.key}>{step.fields.length > 1 && <b>{shortLabel(f.label)}: </b>}{value}</p>];
  });
}

/** 양식에 적용된 모습 — 검증용 샘플 .docx(09_샘플8D)의 표 구조를 따른다. 고객사 양식 자체는 다음 단계(DEC-064) */
export function FormPreview({ subject, values, evidenceNote }: { subject: string; values: Record<string, string>; evidenceNote: string | null }) {
  return <div className="fp-page" role="document" aria-label="8D 양식 미리보기">
    <div className="fp-top">[가상 샘플] 고객사 협력사용 8D 양식 — 내부 문서</div>
    <h3 className="fp-title">CORRECTIVE ACTION REPORT</h3>
    <table className="fp-table fp-meta"><colgroup><col className="fp-m1" /><col /><col className="fp-m1" /><col /></colgroup><tbody>
      <tr><th>TO</th><td /><th>DATE</th><td /></tr>
      <tr><th>ATTN.</th><td /><th>CAR NO.</th><td /></tr>
      <tr><th>SUBJECT</th><td colSpan={3} lang="en">{subject}</td></tr>
    </tbody></table>
    <table className="fp-table fp-body"><colgroup><col className="fp-c1" /><col /></colgroup><tbody>
      <tr><th colSpan={2} className="fp-band">8-DISCIPLINE REPORT</th></tr>
      {STEPS.map((step) => <tr key={step.n}><th className="fp-label"><div>DISCIPLINE {step.n}</div><div className="fp-name">{step.name}</div></th><td className="fp-cell">{cell(step, values)}</td></tr>)}
    </tbody></table>
    {evidenceNote && <p className="fp-note">{evidenceNote}</p>}
    <div className="fp-foot">Form No. QA-8D-001 Rev.3</div>
  </div>;
}

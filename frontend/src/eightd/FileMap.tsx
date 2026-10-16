import { STEPS } from "./document";
import type { Inspection, Place } from "./docxPatch";

const keyOf = (p: Place) => `${p.table}.${p.row}.${p.col}`;
const short = (text: string) => (text.length > 28 ? `${text.slice(0, 28)}…` : text);

/**
 * 올린 .docx에서 단계마다 글이 들어갈 칸을 보여 주고 바꿀 수 있게 한다(DEC-064 보완).
 * 라벨이 맞은 칸이 하나면 자동, 여럿이면 짐작하지 않고 고르게 하며, 못 찾았거나 틀렸으면 문서의 어느 칸이든 직접 고른다.
 */
export function FileMap({ view, choice, applied, onChoose }: { view: Inspection; choice: Readonly<Record<number, Place>>; applied: ReadonlySet<number>; onChoose: (step: number, place: Place | null) => void }) {
  const labelAt = (p: Place) => view.cells.find((c) => keyOf(c) === keyOf(p))?.label ?? "";
  const where = (p: Place) => `표 ${p.table} · ${p.row}행 · ${p.col}열 — “${short(labelAt(p))}”`;
  return <table className="ed-map"><thead><tr><th>단계</th><th>양식에서 글이 들어갈 칸</th></tr></thead><tbody>{STEPS.map((st) => {
    const on = applied.has(st.n);
    const mine = choice[st.n];
    const auto = view.matches[st.n] ?? [];
    const status = mine ? <span className="ed-ok">내가 고른 칸 ✓ {where(mine)}</span>
      : auto.length === 1 ? <span className="ed-ok">자동 인식 ✓ {where(auto[0])}</span>
      : auto.length > 1 ? <span className="ed-warn" role="alert">후보 {auto.length}곳 — 아래에서 칸을 고르기 전에는 이 단계 글을 넣지 않습니다</span>
      : <span className="note">찾지 못함 — 아래에서 칸을 고를 수 있습니다</span>;
    const ordered = [...view.cells.filter((c) => c.guess === st.n), ...view.cells.filter((c) => c.guess !== st.n)];
    return <tr key={st.n} className={on ? "" : "off"}>
      <td>D{st.n} {st.name}{on ? "" : " (적용 안 함)"}</td>
      <td>{on ? <>{status}
        <select aria-label={`D${st.n} 칸 고르기`} value={mine ? keyOf(mine) : ""} onChange={(e) => { const c = view.cells.find((x) => keyOf(x) === e.target.value); onChoose(st.n, c ? { table: c.table, row: c.row, col: c.col } : null); }}>
          <option value="">자동(라벨로 인식)</option>
          {ordered.map((c) => <option key={keyOf(c)} value={keyOf(c)}>표 {c.table} · {c.row}행 · “{short(c.label)}”{c.guess === st.n ? " — 라벨이 맞음" : ""}</option>)}
        </select></> : <span className="note">—</span>}</td>
    </tr>;
  })}</tbody></table>;
}

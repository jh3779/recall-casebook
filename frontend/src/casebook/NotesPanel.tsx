import type { Card } from "../search/types";
import { notesText, SHARED_BROWSER_NOTE, storageState } from "./notes";

/** 선례별 메모 — 서버·LLM에 보내지 않는다. 사건 이름이 있으면 이 브라우저에 저장한다 */
export function NotesPanel({ cards, notes, onChange, caseName, persistent, storageBlocked, onCopy, onClear, copyMessage }: {
  cards: readonly Card[]; caseName: string; notes: Readonly<Record<string, string>>; onChange: (campno: string, text: string) => void;
  persistent: boolean; storageBlocked: boolean; onCopy: () => void; onClear: () => void; copyMessage: string;
}) {
  const state = storageState(caseName, persistent, storageBlocked);
  return <section className="cb-notes" aria-label="Notes per precedent">
    <h2>Notes</h2>
    <p className={`cb-note-state${state.warn ? " warn" : ""}`} role="status">{state.text}</p>
    <p className="cb-muted">{SHARED_BROWSER_NOTE}</p>
    {!cards.length && <p className="cb-muted">Check a precedent on the left to write a note for it.</p>}
    {cards.map((card) => <label key={card.campno} className="cb-note">
      <span><b className="cb-id">{card.campno}</b> · {card.maker}</span>
      <textarea maxLength={10000} value={notes[card.campno] ?? ""} onChange={(e) => onChange(card.campno, e.target.value)} rows={4} placeholder="Your note on this precedent" />
    </label>)}
    <div className="cb-actions">
      <button type="button" className="cb-btn ghost" onClick={onCopy} disabled={!notesText(cards, notes)}>Copy all notes</button>
      <button type="button" className="cb-btn ghost" onClick={onClear} disabled={!Object.keys(notes).length}>Clear notes and D4 text of this case</button>
      <span role="status" className="cb-muted">{copyMessage}</span>
    </div>
  </section>;
}

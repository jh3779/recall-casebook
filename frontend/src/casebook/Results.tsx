import type { Card, SearchResponse } from "../search/types";
import { CaseDetail } from "./CaseDetail";
import { CaseList } from "./CaseList";
import { D4Panel } from "./D4Panel";
import { GroupPanel } from "./GroupPanel";
import { storageProblem } from "./notes";
import { NotesPanel } from "./NotesPanel";
import { pickedFor } from "./questions";
import { Provenance } from "./Provenance";
import { Write8dBar } from "./Write8dBar";

interface Props {
  response: SearchResponse;
  checked: readonly Card[];
  checkedKey: string;
  onToggle: (card: Card) => void;
  on3d: (card: Card, button: HTMLElement) => void;
  notes: Record<string, string>;
  onNoteChange: (campno: string, text: string) => void;
  caseName: string;
  persistent: boolean;
  storageBlocked: ReturnType<typeof storageProblem>;
  onCopy: () => void;
  onClear: () => void;
  copyMessage: string;
  storeMessage: string;
  onGroupPicked: (ids: string[]) => void;
  picked: ReturnType<typeof pickedFor>;
  onWrite8d?: (cards: readonly Card[], response: SearchResponse) => void;
}

/** 검색 결과가 나온 뒤의 화면 — 목록·쌓이는 상세·메모와 묶기·D4 칸·응답 출처. 조립이 시험에 잡히도록 CasebookView에서 떼어 냈다(DEC-075) */
export function Results({ response, checked, checkedKey, onToggle, on3d, notes, onNoteChange, caseName, persistent, storageBlocked, onCopy, onClear, copyMessage, storeMessage, onGroupPicked, picked, onWrite8d }: Props) {
  return <>
    <div className="cb-grid">
      <CaseList response={response} checked={checked} onToggle={onToggle} />
      <section className="cb-stack" aria-label="Checked precedents">
        <h2 className="sr-only">Checked precedents</h2>
        {onWrite8d && <Write8dBar checked={checked} response={response} onWrite8d={onWrite8d} />}
        {!checked.length && <p className="cb-empty">Check precedents on the left. Each one stacks here with its original wording, who said it, and the report it came from.</p>}
        {checked.map((card) => <CaseDetail key={card.campno} card={card} response={response} onRemove={() => onToggle(card)} on3d={(button) => on3d(card, button)} />)}
      </section>
      <div className="cb-side">
        <NotesPanel cards={checked} notes={notes} onChange={onNoteChange} caseName={caseName} persistent={persistent} storageBlocked={storageBlocked} onCopy={onCopy} onClear={onClear} copyMessage={copyMessage} />
        <GroupPanel key={checkedKey} question={response.question} build={response} cards={checked} onPicked={onGroupPicked} />
      </div>
    </div>
    <D4Panel cards={checked} response={response} notes={notes} onChange={onNoteChange} caseName={caseName} persistent={persistent} storageBlocked={storageBlocked} storeMessage={storeMessage} picked={picked} />
    <Provenance data={response} />
  </>;
}

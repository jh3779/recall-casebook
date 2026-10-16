import JSZip from "jszip";
import type { ParaSpec } from "./document";

/**
 * 올린 8D .docx의 칸 끝에 글을 덧붙인다(DEC-064). word/document.xml을 DOM으로 다시 쓰지 않고 문자열 위치만 찾아
 * 삽입하므로, 덧붙인 문단 밖은 원본과 바이트가 같다. 파일은 이 기기 밖으로 나가지 않는다.
 */
export const DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";
export class DocxError extends Error {}

interface Span { start: number; end: number }
interface Cell extends Span { close: number; text: string; paragraphs: Span[] }
interface Table extends Span { rows: Cell[][] }
interface Frame { name: string; start: number; rows: Cell[][]; cells: Cell[]; paragraphs: Span[] }

const ENTITIES: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };
const decode = (s: string) => s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (all, e: string) => e[0] === "#" ? String.fromCodePoint(e[1].toLowerCase() === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10)) : (ENTITIES[e.toLowerCase()] ?? all));
const T = /<w:t(?:\s[^>]*)?>([^<]*)<\/w:t>/g;
/** 칸 글자 — 한 문단 안의 run은 붙이고(글자가 run 사이에서 끊겨도 한 단어), 문단 사이는 공백 */
const textOf = (xml: string) => xml.split("</w:p>").map((chunk) => [...chunk.matchAll(T)].map((m) => decode(m[1])).join("")).join(" ").replace(/\s+/g, " ").trim();

/** 표·행·칸·문단의 위치를 찾는다 — 중첩 표도 처리하고, 칸의 직속 문단만 기록한다 */
function scan(xml: string): Table[] {
  const tables: Table[] = [];
  const stack: Frame[] = [];
  const re = /<(\/?)w:(tbl|tr|tc|p)(?=[\s/>])[^>]*?(\/?)>/g;
  const top = () => stack[stack.length - 1];
  for (let m = re.exec(xml); m; m = re.exec(xml)) {
    const [tag, closing, name, selfClose] = m;
    const end = m.index + tag.length;
    if (closing) {
      const f = stack.pop();
      if (!f || f.name !== name) throw new DocxError("문서 구조(word/document.xml)를 읽지 못했습니다");
      if (name === "p") { if (top()?.name === "tc") top().paragraphs.push({ start: f.start, end }); }
      else if (name === "tc") { if (top()?.name === "tr") top().cells.push({ start: f.start, end, close: m.index, text: textOf(xml.slice(f.start, end)), paragraphs: f.paragraphs }); }
      else if (name === "tr") { if (top()?.name === "tbl") top().rows.push(f.cells); }
      else tables.push({ start: f.start, end, rows: f.rows });
    } else if (selfClose) {
      if (name === "p" && top()?.name === "tc") top().paragraphs.push({ start: m.index, end });
    } else stack.push({ name, start: m.index, rows: [], cells: [], paragraphs: [] });
  }
  return tables.sort((a, b) => a.start - b.start);
}

/** 행 라벨로 8D 단계를 가른다 — "DEFINE THE PROBLEM CAUSE"가 문제 기술이 아니라 원인이 되도록 원인을 먼저 본다 */
const ORDER: [number, RegExp][] = [
  [3, /contain|임시|봉쇄|잠정/i], [5, /permanent|영구|상용/i], [6, /verif|효과|검증/i], [7, /prevent|recurrence|재발|수평/i],
  [4, /cause|원인/i], [2, /problem|description|문제/i], [1, /team|팀/i], [8, /close|종료|마무리/i],
];
export const stepOfLabel = (text: string): number | null => (text.length > 0 && text.length <= 120 ? ORDER.find(([, re]) => re.test(text))?.[0] ?? null : null);

export interface Place { table: number; row: number; col: number }
/** 라벨 칸 바로 오른쪽의 내용 칸 — label은 그 라벨 글, guess는 라벨이 가리키는 단계(없으면 null) */
interface Target extends Place { cell: Cell; tableEnd: number; label: string; guess: number | null }
/** cells: 라벨이 있는 모든 내용 칸(사용자가 직접 고를 수 있는 후보), matches: 단계별로 라벨이 맞은 칸들 */
interface Recognition { cells: Target[]; matches: Map<number, Target[]>; subject?: Target; tables: Table[]; lastTableEnd?: number }

function recognize(xml: string): Recognition {
  const cellsOut: Target[] = [];
  const matches = new Map<number, Target[]>();
  let subject: Target | undefined;
  const tables = scan(xml);
  tables.forEach((table, ti) => table.rows.forEach((cells, ri) => cells.forEach((label, ci) => {
    const cell = cells[ci + 1];
    if (!cell || !label.text) return;
    const guess = stepOfLabel(label.text);
    const target: Target = { table: ti + 1, row: ri + 1, col: ci + 2, cell, tableEnd: table.end, label: label.text, guess };
    cellsOut.push(target);
    if (/^subject\b/i.test(label.text)) subject ??= target;
    if (guess !== null) matches.set(guess, [...(matches.get(guess) ?? []), target]);
  })));
  return { cells: cellsOut, matches, subject, tables, lastTableEnd: tables.length ? Math.max(...tables.map((t) => t.end)) : undefined };
}

const samePlace = (a: Place, b: Place) => a.table === b.table && a.row === b.row && a.col === b.col;
/** 단계의 칸 — 사용자가 고른 칸이 우선이고, 고르지 않았으면 라벨이 맞은 칸이 하나뿐일 때만 자동으로 정한다(후보가 여럿이면 짐작하지 않는다) */
function resolve(found: Recognition, step: number, chosen?: Place): { target?: Target; ambiguous?: boolean } {
  if (chosen) return { target: found.cells.find((c) => samePlace(c, chosen)) };
  const matched = found.matches.get(step) ?? [];
  return matched.length === 1 ? { target: matched[0] } : matched.length > 1 ? { ambiguous: true } : {};
}

/** XML 1.0에 넣을 수 없는 제어 문자(탭·줄바꿈 제외)는 빼고, & < >는 바꾼다 */
const stripControl = (s: string) => [...s].filter((ch) => { const c = ch.charCodeAt(0); return !(c < 9 || c === 11 || c === 12 || (c > 13 && c < 32)); }).join("");
const esc = (s: string) => stripControl(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const lastRPr = (xml: string) => xml.match(/<w:rPr>[\s\S]*?<\/w:rPr>/g)?.at(-1) ?? "";
const plain = (rPr: string) => rPr.replace(/<w:b(?:Cs)?(?:\s[^>]*)?\/>/g, "");
const bold = (rPr: string) => {
  if (!rPr) return "<w:rPr><w:b/><w:bCs/></w:rPr>";
  const head = /^<w:rPr>(?:<w:rStyle[^>]*\/>)?(?:<w:rFonts[^>]*\/>)?/.exec(rPr)![0];
  return `${rPr.slice(0, head.length)}<w:b/><w:bCs/>${rPr.slice(head.length)}`;
};
const run = (text: string, rPr: string) => `<w:r>${rPr}<w:t xml:space="preserve">${esc(text)}</w:t></w:r>`;

interface Edit { at: number; remove: number; insert: string }
/** 문단에 글자 말고도 들어 있는 것(그림·필드·체크박스·콘텐츠 컨트롤·책갈피 등)이 하나도 없는 진짜 빈 문단인가 — 빈 run·run 서식만 있는 것은 비어 있다고 본다 */
const isEmptyParagraph = (paraXml: string) => paraXml
  .replace(/^<w:p(?:\s[^>]*)?\/?>/, "").replace(/<\/w:p>$/, "")
  .replace(/<w:pPr>[\s\S]*?<\/w:pPr>|<w:pPr\/>/g, "")
  .replace(/<w:rPr>[\s\S]*?<\/w:rPr>|<w:rPr\/>/g, "")
  .replace(/<w:t(?:\s[^>]*)?\/>|<w:t(?:\s[^>]*)?><\/w:t>/g, "")
  .replace(/<w:r(?:\s[^>]*)?>\s*<\/w:r>|<w:r(?:\s[^>]*)?\/>/g, "")
  .trim() === "";
/** 칸의 마지막 문단과 같은 문단 서식(스타일·간격)·글자 서식(굵기 제외)으로 문단을 만든다. 칸의 마지막 문단이 진짜 빈 문단이면 그 자리에 넣고, 그림 등이 든 문단은 건드리지 않고 칸 끝에 덧붙인다 */
function cellEdit(xml: string, cell: Cell, paras: ParaSpec[]): Edit {
  const tmpl = cell.paragraphs.at(-1);
  const tmplXml = tmpl ? xml.slice(tmpl.start, tmpl.end) : "";
  const pPr = /<w:pPr>[\s\S]*?<\/w:pPr>/.exec(tmplXml)?.[0] ?? "";
  const rPr = plain(lastRPr(tmplXml));
  const insert = paras.map((p) => `<w:p>${pPr}${p.prefix ? run(p.prefix, bold(rPr)) : ""}${p.text ? run(p.text, rPr) : ""}</w:p>`).join("");
  return !cell.text && tmpl && isEmptyParagraph(tmplXml) ? { at: tmpl.start, remove: tmpl.end - tmpl.start, insert } : { at: cell.close, remove: 0, insert };
}

/** cells: 사용자가 단계마다 직접 고른 칸(DEC-064 보완) — 있으면 라벨 인식보다 우선한다 */
/** appendix: 8D 표 뒤에 별도 문단으로 붙는 선례 근거 부록(D4 타사 원인) — 칸에 들어가지 않는다 */
export interface ExportContent { subject: string; steps: Record<number, ParaSpec[]>; footer: string | null; cells?: Record<number, Place>; appendix?: ParaSpec[] }
/** missing: 칸을 못 찾은 단계, ambiguous: 라벨이 맞은 칸이 여럿인데 고르지 않아 넣지 않은 단계, conflict: 앞선 단계가 이미 쓰는 칸을 또 가리켜 넣지 않은 단계(두 편집이 같은 자리를 겹쳐 파일이 깨지지 않게) */
export interface PatchResult { xml: string; filled: number[]; missing: number[]; ambiguous: number[]; conflict: number[]; appendixPlaced: boolean | null }

/** 단계별 글을 칸에 덧붙인다. 글이 있는데 칸을 못 찾았거나(missing) 후보가 여럿인데 고르지 않은(ambiguous) 단계는 넣지 않는다 */
export function patchDocumentXml(xml: string, content: ExportContent): PatchResult {
  const found = recognize(xml);
  const edits: Edit[] = [];
  const filled: number[] = [];
  const missing: number[] = [];
  const ambiguous: number[] = [];
  const conflict: number[] = [];
  const used = new Set<Cell>();
  let tableEnd: number | undefined;
  for (const [key, paras] of Object.entries(content.steps)) {
    const step = Number(key);
    if (!paras.length) continue;
    const { target, ambiguous: many } = resolve(found, step, content.cells?.[step]);
    if (many) { ambiguous.push(step); continue; }
    if (!target) { missing.push(step); continue; }
    if (used.has(target.cell)) { conflict.push(step); continue; }
    used.add(target.cell);
    edits.push(cellEdit(xml, target.cell, paras));
    filled.push(step);
    tableEnd ??= target.tableEnd;
  }
  if (content.subject.trim() && found.subject && !found.subject.cell.text && !used.has(found.subject.cell)) edits.push(cellEdit(xml, found.subject.cell, [{ text: content.subject.trim() }]));
  // 선례 근거 부록(있으면) → 근거 데이터 줄. 자리는 "라벨로 인식했거나 사용자가 직접 고른 8D 단계 칸이 든 표 중 문서상 마지막" 표 뒤(중첩 표면 바깥 표 뒤) — D5~D8이 별도 표여도 그 뒤에 붙는다. 인식한 칸이 하나도 없으면 문서의 마지막 표 뒤.
  // 부록이 없으면 근거 데이터 줄은 처음 글이 들어간 단계의 표 뒤에만 붙는다(아무것도 못 넣은 파일에는 붙지 않는다)
  const outerEnd = (pos: number) => Math.max(...found.tables.filter((t) => t.start <= pos && t.end >= pos).map((t) => t.end));
  const recognized = [...found.matches.values()].flat();
  const chosen = Object.keys(content.cells ?? {}).flatMap((k) => { const t = resolve(found, Number(k), content.cells?.[Number(k)]).target; return t ? [t] : []; }); // 사용자가 직접 고른 칸은 어느 단계든 센다
  const stepCells = [...recognized, ...chosen].map((t) => t.cell.start);
  const appendixAt = stepCells.length ? Math.max(...stepCells.map(outerEnd)) : found.lastTableEnd;
  const anchor = (content.appendix?.length ? appendixAt : tableEnd);
  const appendixXml = (content.appendix ?? []).map((p) => `<w:p><w:r><w:rPr>${p.bold ? "<w:b/><w:bCs/>" : ""}<w:sz w:val="18"/></w:rPr><w:t xml:space="preserve">${esc(p.text)}</w:t></w:r></w:p>`).join("");
  const footerXml = content.footer ? `<w:p><w:r><w:rPr><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve">${esc(content.footer)}</w:t></w:r></w:p>` : "";
  const appendixPlaced = appendixXml ? anchor !== undefined : null;
  if (anchor !== undefined && (appendixXml || footerXml)) edits.push({ at: anchor, remove: 0, insert: appendixXml + footerXml });
  let out = xml;
  for (const e of edits.sort((a, b) => b.at - a.at)) out = out.slice(0, e.at) + e.insert + out.slice(e.at + e.remove);
  return { xml: out, filled: filled.sort((a, b) => a - b), missing: missing.sort((a, b) => a - b), ambiguous: ambiguous.sort((a, b) => a - b), conflict: conflict.sort((a, b) => a - b), appendixPlaced };
}

async function open(file: Blob) {
  let zip: JSZip;
  try { zip = await JSZip.loadAsync(await file.arrayBuffer()); } catch { throw new DocxError("올린 파일을 Word(.docx)로 읽지 못했습니다"); }
  const entry = zip.file("word/document.xml");
  if (!entry) throw new DocxError("Word(.docx) 파일이 아닙니다 — word/document.xml이 없습니다");
  return { zip, xml: await entry.async("string") };
}

/** 사용자가 고를 수 있는 칸 하나 — label은 그 칸 왼쪽 라벨 글, guess는 라벨이 가리키는 단계(없으면 null) */
export interface Candidate extends Place { label: string; guess: number | null }
export interface Inspection {
  /** 라벨이 있는 모든 칸(문서 순서) — 단계 칸을 직접 고를 때의 목록 */
  cells: Candidate[];
  /** 단계마다 라벨이 맞은 칸. 하나면 자동으로 넣고, 둘 이상이면 사용자가 고를 때까지 넣지 않는다 */
  matches: Record<number, Place[]>;
  subject: boolean;
}

/** 올린 파일에서 8D 단계별 칸 위치를 찾아 화면에 보여 줄 목록으로 */
export async function inspectDocx(file: Blob): Promise<Inspection> {
  const { xml } = await open(file);
  const found = recognize(xml);
  const at = ({ table, row, col }: Target): Place => ({ table, row, col });
  return {
    cells: found.cells.map((t) => ({ ...at(t), label: t.label, guess: t.guess })),
    matches: Object.fromEntries([...found.matches].map(([step, ts]) => [step, ts.map(at)])),
    subject: !!found.subject,
  };
}

/** 원본 파일은 그대로 두고 word/document.xml만 바꾼 새 .docx를 만든다 — 다른 파트(스타일·머리글·그림 등)는 손대지 않는다 */
export async function patchDocx(file: Blob, content: ExportContent): Promise<PatchResult & { blob: Blob }> {
  const { zip, xml } = await open(file);
  const result = patchDocumentXml(xml, content);
  zip.file("word/document.xml", result.xml, { createFolders: false }); // 원본에 없던 폴더 항목을 만들지 않는다
  return { ...result, blob: await zip.generateAsync({ type: "blob", mimeType: DOCX_MIME, compression: "DEFLATE" }) };
}

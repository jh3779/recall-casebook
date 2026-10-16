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
interface Target extends Place { cell: Cell; tableEnd: number }
interface Recognition { steps: Map<number, Target>; subject?: Target }

function recognize(xml: string): Recognition {
  const steps = new Map<number, Target>();
  let subject: Target | undefined;
  scan(xml).forEach((table, ti) => table.rows.forEach((cells, ri) => cells.forEach((label, ci) => {
    const cell = cells[ci + 1];
    if (!cell) return;
    const target: Target = { table: ti + 1, row: ri + 1, col: ci + 2, cell, tableEnd: table.end };
    if (/^subject\b/i.test(label.text)) subject ??= target;
    const step = stepOfLabel(label.text);
    if (step !== null && !steps.has(step)) steps.set(step, target);
  })));
  return { steps, subject };
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const lastRPr = (xml: string) => xml.match(/<w:rPr>[\s\S]*?<\/w:rPr>/g)?.at(-1) ?? "";
const plain = (rPr: string) => rPr.replace(/<w:b(?:Cs)?(?:\s[^>]*)?\/>/g, "");
const bold = (rPr: string) => {
  if (!rPr) return "<w:rPr><w:b/><w:bCs/></w:rPr>";
  const head = /^<w:rPr>(?:<w:rStyle[^>]*\/>)?(?:<w:rFonts[^>]*\/>)?/.exec(rPr)![0];
  return `${rPr.slice(0, head.length)}<w:b/><w:bCs/>${rPr.slice(head.length)}`;
};
const run = (text: string, rPr: string) => `<w:r>${rPr}<w:t xml:space="preserve">${esc(text)}</w:t></w:r>`;

interface Edit { at: number; remove: number; insert: string }
/** 칸의 마지막 문단과 같은 문단 서식(스타일·간격)·글자 서식(굵기 제외)으로 문단을 만든다. 칸이 비어 있으면 그 빈 문단 자리에 넣는다 */
function cellEdit(xml: string, cell: Cell, paras: ParaSpec[]): Edit {
  const tmpl = cell.paragraphs.at(-1);
  const tmplXml = tmpl ? xml.slice(tmpl.start, tmpl.end) : "";
  const pPr = /<w:pPr>[\s\S]*?<\/w:pPr>/.exec(tmplXml)?.[0] ?? "";
  const rPr = plain(lastRPr(tmplXml));
  const insert = paras.map((p) => `<w:p>${pPr}${p.prefix ? run(p.prefix, bold(rPr)) : ""}${p.text ? run(p.text, rPr) : ""}</w:p>`).join("");
  return !cell.text && tmpl ? { at: tmpl.start, remove: tmpl.end - tmpl.start, insert } : { at: cell.close, remove: 0, insert };
}

export interface ExportContent { subject: string; steps: Record<number, ParaSpec[]>; footer: string | null }
export interface PatchResult { xml: string; filled: number[]; missing: number[] }

/** 단계별 글을 인식한 칸에 덧붙인다. 글이 있는데 칸을 못 찾은 단계는 missing */
export function patchDocumentXml(xml: string, content: ExportContent): PatchResult {
  const found = recognize(xml);
  const edits: Edit[] = [];
  const filled: number[] = [];
  const missing: number[] = [];
  let tableEnd: number | undefined;
  for (const [key, paras] of Object.entries(content.steps)) {
    const step = Number(key);
    if (!paras.length) continue;
    const target = found.steps.get(step);
    if (!target) { missing.push(step); continue; }
    edits.push(cellEdit(xml, target.cell, paras));
    filled.push(step);
    tableEnd ??= target.tableEnd;
  }
  if (content.subject.trim() && found.subject && !found.subject.cell.text) edits.push(cellEdit(xml, found.subject.cell, [{ text: content.subject.trim() }]));
  if (content.footer && tableEnd !== undefined) edits.push({ at: tableEnd, remove: 0, insert: `<w:p><w:r><w:rPr><w:sz w:val="16"/></w:rPr><w:t xml:space="preserve">${esc(content.footer)}</w:t></w:r></w:p>` });
  let out = xml;
  for (const e of edits.sort((a, b) => b.at - a.at)) out = out.slice(0, e.at) + e.insert + out.slice(e.at + e.remove);
  return { xml: out, filled: filled.sort((a, b) => a - b), missing: missing.sort((a, b) => a - b) };
}

async function open(file: Blob) {
  let zip: JSZip;
  try { zip = await JSZip.loadAsync(await file.arrayBuffer()); } catch { throw new DocxError("올린 파일을 Word(.docx)로 읽지 못했습니다"); }
  const entry = zip.file("word/document.xml");
  if (!entry) throw new DocxError("Word(.docx) 파일이 아닙니다 — word/document.xml이 없습니다");
  return { zip, xml: await entry.async("string") };
}

/** 올린 파일에서 8D 단계별 칸 위치를 찾아 화면에 보여 줄 목록으로 */
export async function inspectDocx(file: Blob): Promise<{ steps: ({ step: number } & Place)[]; subject: boolean }> {
  const { xml } = await open(file);
  const found = recognize(xml);
  return { steps: [...found.steps].map(([step, t]) => ({ step, table: t.table, row: t.row, col: t.col })).sort((a, b) => a.step - b.step), subject: !!found.subject };
}

/** 원본 파일은 그대로 두고 word/document.xml만 바꾼 새 .docx를 만든다 — 다른 파트(스타일·머리글·그림 등)는 손대지 않는다 */
export async function patchDocx(file: Blob, content: ExportContent): Promise<PatchResult & { blob: Blob }> {
  const { zip, xml } = await open(file);
  const result = patchDocumentXml(xml, content);
  zip.file("word/document.xml", result.xml, { createFolders: false }); // 원본에 없던 폴더 항목을 만들지 않는다
  return { ...result, blob: await zip.generateAsync({ type: "blob", mimeType: DOCX_MIME, compression: "DEFLATE" }) };
}

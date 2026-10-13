import type { Flag } from "./types";

export interface HighlightPart { text: string; kind?: Flag["kind"]; label?: string }

/** Python 좌표는 코드포인트 단위다. 검증된 구간만 감싸고 원문은 바꾸지 않는다. */
export function highlight(text: string, flags: Flag[]): HighlightPart[] {
  const points = Array.from(text);
  const accepted: { start: number; end: number; kind: Flag["kind"]; label: string }[] = [];
  for (const flag of flags) {
    for (const span of flag.spans) {
      if (!Number.isInteger(span.start) || !Number.isInteger(span.end) || span.start < 0 || span.end > points.length || span.end <= span.start) continue;
      if (points.slice(span.start, span.end).join("") !== span.text) continue;
      if (accepted.some((other) => span.start < other.end && span.end > other.start)) continue;
      accepted.push({ ...span, kind: flag.kind, label: flag.label });
    }
  }
  accepted.sort((a, b) => a.start - b.start);
  const parts: HighlightPart[] = [];
  let cursor = 0;
  for (const span of accepted) {
    if (span.start > cursor) parts.push({ text: points.slice(cursor, span.start).join("") });
    parts.push({ text: points.slice(span.start, span.end).join(""), kind: span.kind, label: span.label });
    cursor = span.end;
  }
  if (cursor < points.length) parts.push({ text: points.slice(cursor).join("") });
  return parts.length && parts.map((part) => part.text).join("") === text ? parts : [{ text }];
}

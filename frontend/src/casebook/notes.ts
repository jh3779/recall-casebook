/**
 * 선례별 메모(DEC-067). 서버·LLM에는 보내지 않고 이 브라우저 안에만 둔다.
 * 저장 키는 "사건 이름 + 리콜 번호"다 — 사건 이름이 없으면 저장하지 않고 화면 메모리에만 둔다(다른 사건의 메모가 같은 선례에 나타나지 않게).
 */
export interface StorageLike { getItem(key: string): string | null; setItem(key: string, value: string): void; removeItem(key: string): void; key(index: number): string | null; readonly length: number }

const PREFIX = "casebook.note.v1|";
export const normalizeCaseName = (name: string) => name.trim().replace(/\s+/g, " ").slice(0, 80);
/** 사건 이름은 인코딩해서 넣는다 — 이름 안의 `|`가 다른 사건의 키 접두어와 겹치지 않게("A"와 "A|B") */
const head = (caseName: string) => `${PREFIX}${encodeURIComponent(caseName)}|`;
export const noteKey = (caseName: string, campno: string) => `${head(caseName)}${campno}`;

/** 저장소를 못 쓰는 환경(사생활 보호 창·차단)에서는 null — 호출하는 쪽이 메모리에만 두고 경고한다 */
export function browserStorage(): StorageLike | null {
  try {
    const probe = "casebook.probe";
    globalThis.localStorage.setItem(probe, "1");
    globalThis.localStorage.removeItem(probe);
    return globalThis.localStorage;
  } catch { return null; }
}

export function loadNotes(storage: StorageLike | null, caseName: string): Record<string, string> {
  const name = normalizeCaseName(caseName);
  if (!storage || !name) return {};
  const prefix = head(name);
  const out: Record<string, string> = {};
  try {
    for (let i = 0; i < storage.length; i++) {
      const key = storage.key(i);
      if (key?.startsWith(prefix)) { const value = storage.getItem(key); if (value) out[key.slice(prefix.length)] = value; }
    }
  } catch { return out; }
  return out;
}

/** 저장했으면 true. 글이 비면 지운다. 저장소가 막혔으면 false(화면 메모리 값은 그대로 둔다) */
export function saveNote(storage: StorageLike | null, caseName: string, campno: string, text: string): boolean {
  const name = normalizeCaseName(caseName);
  if (!storage || !name) return false;
  try {
    if (text) storage.setItem(noteKey(name, campno), text); else storage.removeItem(noteKey(name, campno));
    return true;
  } catch { return false; }
}

/** 지웠으면 true. 저장소가 막혔으면 false */
export function clearNotes(storage: StorageLike | null, caseName: string): boolean {
  const name = normalizeCaseName(caseName);
  if (!storage || !name) return false;
  try {
    const prefix = head(name);
    const keys: string[] = [];
    for (let i = 0; i < storage.length; i++) { const key = storage.key(i); if (key?.startsWith(prefix)) keys.push(key); }
    keys.forEach((key) => storage.removeItem(key));
    return true;
  } catch { return false; }
}

/** 전체 복사용 글 — 체크한 선례 순서대로, 메모가 있는 것만 */
export function notesText(cards: readonly { campno: string; maker: string }[], notes: Readonly<Record<string, string>>): string {
  return cards.filter((c) => notes[c.campno]?.trim()).map((c) => `[${c.campno} · ${c.maker}]\n${notes[c.campno].trim()}`).join("\n\n");
}

export const UNNAMED_MARK = "[Written before the case was named]";
/**
 * 사건 이름을 정했을 때: 저장돼 있던 그 사건의 메모를 불러오고, 이름 없이 화면에만 적어 둔 메모는 저장소에 옮긴다.
 * 같은 리콜에 서로 다른 글이 있으면 어느 쪽도 버리지 않고 저장된 글 뒤에 이름 없이 쓴 글을 이어 붙인다(`UNNAMED_MARK`).
 * `saved`가 false면 저장소에 쓰지 못한 것이 있다 — 화면 메모는 그대로 돌려주고 호출하는 쪽이 경고한다.
 */
export function adoptNotes(storage: StorageLike | null, caseName: string, memory: Readonly<Record<string, string>>): { notes: Record<string, string>; saved: boolean } {
  const stored = loadNotes(storage, caseName);
  const notes: Record<string, string> = { ...memory, ...stored };
  for (const [campno, text] of Object.entries(memory)) {
    const kept = stored[campno];
    if (kept && text.trim() && !kept.includes(text.trim())) notes[campno] = `${kept}\n\n${UNNAMED_MARK}\n${text}`;
  }
  let saved = !!storage && !!normalizeCaseName(caseName);
  for (const [campno, text] of Object.entries(notes)) if (stored[campno] !== text && !saveNote(storage, caseName, campno, text)) saved = false;
  return { notes, saved };
}

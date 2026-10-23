import { expect, it } from "vitest";
import { RequestGate } from "./requestGate";

// 화면(`CasebookView.run`)이 쓰는 순서 그대로: 시작 → 기다림 → 응답이 와도 인정될 때만 화면에 넣는다. 검색 Promise는 취소 신호를 무시하고 늦게 끝나도록 만든다.
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((r) => { resolve = r; });
  return { promise, resolve };
}
async function search(gate: RequestGate, late: Promise<string>, shown: string[]) {
  const request = gate.begin();
  const result = await late; // abort 신호를 보지 않는다
  if (gate.accepts(request)) shown.push(result);
  return request;
}

it("검색 A를 시작하고 새 질문(draft)이 와서 무효로 한 뒤 A가 끝나도 A의 결과는 화면에 들어오지 않는다", async () => {
  const gate = new RequestGate(), shown: string[] = [], a = deferred<string>();
  const running = search(gate, a.promise, shown);
  gate.invalidate(); // 쇼룸에서 새 질문
  a.resolve("airbag results");
  const request = await running;
  expect(shown).toEqual([]);
  expect(request.signal.aborted).toBe(true);
});
it("무효로 한 뒤 시작한 새 검색 B의 결과만 인정된다", async () => {
  const gate = new RequestGate(), shown: string[] = [], a = deferred<string>(), b = deferred<string>();
  const runA = search(gate, a.promise, shown);
  gate.invalidate();
  const runB = search(gate, b.promise, shown);
  b.resolve("steering results");
  a.resolve("airbag results"); // A가 B보다 늦게 끝난다
  await Promise.all([runA, runB]);
  expect(shown).toEqual(["steering results"]);
});
it("새 검색을 시작하면 진행 중이던 이전 검색은 취소되고 늦은 응답은 버려진다", async () => {
  const gate = new RequestGate(), shown: string[] = [], a = deferred<string>(), b = deferred<string>();
  const runA = search(gate, a.promise, shown);
  const runB = search(gate, b.promise, shown);
  a.resolve("old");
  b.resolve("new");
  const [requestA, requestB] = await Promise.all([runA, runB]);
  expect(shown).toEqual(["new"]);
  expect(requestA.signal.aborted).toBe(true);
  expect(requestB.signal.aborted).toBe(false);
});
it("무효로 한 뒤에는 이전 요청도, 이 관리자가 시작하지 않은 요청도 인정하지 않는다", () => {
  const gate = new RequestGate();
  const request = gate.begin();
  expect(gate.accepts(request)).toBe(true);
  gate.invalidate();
  expect(gate.accepts(request)).toBe(false);
  expect(gate.accepts(new AbortController())).toBe(false);
});

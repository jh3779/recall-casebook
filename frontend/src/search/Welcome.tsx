import { EXAMPLES } from "./examples";
import { Provenance } from "./Provenance";
import type { HealthState } from "./types";
export function Welcome({ health, onExample, onShowroom }: { health: HealthState; onExample: (question: string) => void; onShowroom: () => void }) {
  return <div className="welcome">
    <section className="example-section"><h2>예시 질문</h2><div className="examples">{EXAMPLES.map((q) => <button type="button" className="ex" lang="en" key={q} onClick={() => onExample(q)}>{q}</button>)}</div></section>
    <div className="does"><section className="box"><h2>이 도구가 하는 일</h2><ul>
      <li>영어 결함 한 줄로 같은 부품의 리콜 선례를 찾습니다</li><li>결함·결과·시정과 Part 573 원인 칸을 원문 그대로 보여 줍니다</li><li>원문마다 말한 주체와 출처(리콜 번호·573 파일·조사 번호)를 붙입니다</li>
    </ul></section><section className="box not"><h2>하지 않는 일</h2><ul><li>리콜 여부나 원인을 판정하지 않습니다</li><li>원문을 번역하거나 요약하지 않습니다</li><li>원문에 없는 원인·공급사를 짐작해 채우지 않습니다</li></ul></section></div>
    <section className="data-version"><h2>데이터 판본</h2>{typeof health === "string" ? <p className="note">{health === "loading" ? "서버 확인 중…" : "서버 판본을 받지 못했습니다"}</p> : <><p className="note">카드 {health.cards.toLocaleString("ko-KR")}장</p><Provenance data={health} /></>}</section>
    <section className="go-showroom"><span className="thumb" aria-hidden="true" /><div><h2>3D 쇼룸(데모)</h2><p className="note">Silverado·Ram 차종을 부품 분류로 둘러보는 데모 화면입니다. 데모 스냅샷이라 검색 결과와 다릅니다.</p></div><button className="btn ghost" onClick={onShowroom}>쇼룸 열기</button></section>
  </div>;
}

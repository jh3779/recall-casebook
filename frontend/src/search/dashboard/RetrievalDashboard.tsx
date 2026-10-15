import { useMemo, useState } from "react";
import { fmtDate } from "../../recalls";
import { hasCauseText, type SearchResponse } from "../types";
import { deriveDashboard } from "./deriveDashboard";

const maxCount = (rows: { count: number }[]) => Math.max(1, ...rows.map((row) => row.count));
const EvidenceState = ({ available }: { available: boolean }) => <span className={available ? "matrix-state on" : "matrix-state"}><i />{available ? "있음" : "없음"}</span>;

export function RetrievalDashboard({ response, question }: { response: SearchResponse; question: string }) {
  const data = useMemo(() => deriveDashboard(response), [response]);
  const [supplierName, setSupplierName] = useState(data.suppliers[0]?.name ?? "");
  const supplier = data.suppliers.find((item) => item.name === supplierName) ?? data.suppliers[0];
  const causeTotal = Math.max(1, data.total);
  const filledEnd = data.cause.filled / causeTotal * 100;
  const statedEnd = filledEnd + data.cause.stated / causeTotal * 100;
  const componentMax = maxCount(data.components);
  const yearMax = maxCount(data.years);
  const sourceNodes = [
    { name: "FLAT_RCL", value: data.total, note: "결함 · 결과 · 시정" },
    { name: "Part 573", value: data.part573Cards, note: "원인 · 생산 기간 · 공급사" },
    { name: "NHTSA 조사", value: data.investigationActions, note: "고유 ACTION" },
  ];
  return <section className="retrieval-dashboard" aria-labelledby="dashboard-heading">
    <header className="dash-hero">
      <div>
        <p className="dash-eyebrow">검색 응답 지도 · RETRIEVAL ATLAS</p>
        <h2 id="dashboard-heading">현재 검색 결과의 근거 지형</h2>
        <p className="dash-lede">순위나 위험도를 다시 계산하지 않고, 화면에 반환된 선례의 원문·출처·연결 구조를 펼쳐 봅니다.</p>
      </div>
      <div className="dash-query"><span>이번 검색어</span><strong lang="en">{question}</strong><small>검색 버튼을 누른 시점의 질문</small></div>
    </header>

    <div className="dash-stat-grid" aria-label="검색 결과 요약">
      <article className="dash-stat primary"><span>표시된 선례</span><strong>{data.total}</strong><small>고객사 {data.customerCount} · 다른 회사 {data.otherCount}</small></article>
      <article className="dash-stat"><span>원인 글이 있는 카드</span><strong>{data.cause.filled + data.cause.stated}</strong><small>원인 글 {data.cause.filled} · 미보고·조사 중 표현 {data.cause.stated}</small></article>
      <article className="dash-stat"><span>조사 연결</span><strong>{data.investigationActions}</strong><small>{data.investigationCards}개 카드 · 고유 ACTION 기준</small></article>
      <article className="dash-stat"><span>고유 본문 묶음</span><strong>{data.duplicateGroups}</strong><small>dup_group 기준 · 전체 {data.total}개 카드</small></article>
    </div>

    <div className="dash-grid">
      <article className="dash-card evidence-flow wide">
        <div className="dash-card-head"><div><span>01 · 근거 연결</span><h3>질문에서 원본까지</h3></div><small>현재 응답의 연결 수</small></div>
        <div className="flow-map" role="img" aria-label={`질문에서 선례 ${data.total}건을 거쳐 세 원본 계층으로 연결되는 흐름`}>
          <div className="flow-node query-node"><span>이번 검색어</span><strong lang="en">{question}</strong></div>
          <div className="flow-line"><i /></div>
          <div className="flow-node result-node"><span>검색 결과</span><strong>{data.total}건</strong><small>고객사와 다른 회사 선례</small></div>
          <div className="flow-line branch"><i /></div>
          <div className="source-stack">{sourceNodes.map((node) => <div className="flow-node source-node" key={node.name}><span>{node.name}</span><strong>{node.value}</strong><small>{node.note}</small></div>)}</div>
        </div>
        <p className="dash-footnote">검색 결과 밖 리콜을 보태지 않습니다. 숫자는 전체 NHTSA 통계가 아니라 이번 응답에서 관측된 값입니다.</p>
      </article>

      <article className="dash-card cause-orbit">
        <div className="dash-card-head"><div><span>02 · 원인 원문</span><h3>원인 글의 가용 상태</h3></div><small>{data.total}개 카드</small></div>
        <div className="cause-viz">
          <div className="cause-ring" style={{ background: `conic-gradient(var(--accent) 0 ${filledEnd}%, #8190a8 ${filledEnd}% ${statedEnd}%, #d9dee7 ${statedEnd}% 100%)` }}><div><strong>{data.cause.filled + data.cause.stated}</strong><span>원인 글 있음</span></div></div>
          <dl className="legend-list">
            <div><dt><i className="filled" />원인 글</dt><dd>{data.cause.filled}</dd></div>
            <div><dt><i className="stated" />미보고·조사 중 표현</dt><dd>{data.cause.stated}</dd></div>
            <div><dt><i className="missing" />원인 원문 없음</dt><dd>{data.cause.missing}</dd></div>
          </dl>
        </div>
        <p className="dash-footnote">상태는 글의 존재 방식만 구분하며 현재 결함의 원인을 말하지 않습니다.</p>
      </article>

      <article className="dash-card component-map">
        <div className="dash-card-head"><div><span>03 · 부품 분류</span><h3>어떤 부품 선례가 보이는가</h3></div><small>고유 CAMPNO 기준</small></div>
        <div className="bar-list">{data.components.map((row) => <div className="bar-row" key={row.label} title={row.label}><span>{row.label}</span><div><i style={{ width: `${row.count / componentMax * 100}%` }} /></div><strong>{row.count}</strong></div>)}</div>
      </article>

      <article className="dash-card timeline-card wide">
        <div className="dash-card-head"><div><span>04 · 접수 연도</span><h3>리콜 접수 연대기</h3></div><small>접수 연도 · 고유 CAMPNO</small></div>
        <div className="year-chart" aria-label="접수 연도별 카드 수">{data.years.map((row) => <div className="year-column" key={row.label}><strong>{row.count}</strong><div><i style={{ height: `${Math.max(12, row.count / yearMax * 100)}%` }} /></div><span>{row.label}</span></div>)}</div>
      </article>

      <article className="dash-card supplier-card wide">
        <div className="dash-card-head"><div><span>05 · 공급사 관측</span><h3>보고서에 적힌 공급사명</h3></div><small>현재 표시 결과 한정</small></div>
        {data.suppliers.length ? <div className="supplier-layout">
          <div className="supplier-index" role="list">{data.suppliers.map((item) => <button role="listitem" className={item.name === supplier?.name ? "on" : ""} key={item.name} onClick={() => setSupplierName(item.name)}><span>{item.name}</span><strong>{item.campnos.length}</strong></button>)}</div>
          {supplier && <div className="supplier-profile">
            <p className="profile-kicker">573 공급사명 · 원문 그대로</p>
            <h4 lang="en">{supplier.name}</h4>
            <div className="profile-metrics"><div><strong>{supplier.campnos.length}</strong><span>고유 CAMPNO</span></div><div><strong>{supplier.components.length}</strong><span>부품 분류</span></div></div>
            <div className="profile-section"><span>등장 캠페인</span><div className="token-cloud">{supplier.campnos.map((campno) => <code key={campno}>{campno}</code>)}</div></div>
            <div className="profile-section"><span>함께 기록된 부품</span><div className="token-cloud">{supplier.components.map((component) => <em key={component}>{component}</em>)}</div></div>
          </div>}
        </div> : <div className="supplier-empty"><strong>현재 표시 결과에는 공급사 원문이 없습니다.</strong><p>공급사 칸이 비어 있는 보고서도 있으므로, 표기가 없다는 사실만으로 관여 여부를 해석하지 않습니다.</p></div>}
        <p className="dash-footnote">동일 회사의 철자·법인명 대응 전 원문 표기입니다. 이 건수는 공급 물량·불량률·책임 또는 품질 수준을 뜻하지 않습니다. 전체 이력 프로필은 공급사별 573 파일 출처와 이름 대응표를 보강한 뒤 제공합니다.</p>
      </article>

      <article className="dash-card matrix-card wide">
        <div className="dash-card-head"><div><span>06 · 근거 매트릭스</span><h3>선례마다 확인 가능한 원문</h3></div><small>있음·없음만 표시</small></div>
        <div className="matrix-wrap"><table><thead><tr><th>CAMPNO</th><th>제조사</th><th>접수일</th><th>원인 글</th><th>조사</th><th>생산 기간</th><th>공급사 표기</th></tr></thead><tbody>{data.cards.map((card) => {
          const production = card.checklist.some((item) => item.item === "production_period");
          const supplierMention = card.checklist.some((item) => item.item === "supplier");
          return <tr key={card.campno}><td><code>{card.campno}</code></td><td>{card.maker}</td><td>{fmtDate(card.received_date)}</td><td><EvidenceState available={hasCauseText(card.cause)} /></td><td><EvidenceState available={card.investigations.length > 0} /></td><td><EvidenceState available={production} /></td><td><EvidenceState available={supplierMention} /></td></tr>;
        })}</tbody></table></div>
      </article>
    </div>

    <footer className="dash-provenance"><div><span>데이터 스냅샷</span><strong>{response.snapshot_date}</strong></div><div><span>검색 BUILD</span><strong>{response.build_id}</strong></div><div><span>임베딩 모델</span><strong>{response.model}</strong></div><div><span>생산 기간 근거</span><strong>{data.productionCards}개 카드</strong></div></footer>
  </section>;
}

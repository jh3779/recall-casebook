import type { RefObject } from "react";

export function SearchInput({ question, onChange, onSearch, loading, inputRef }: {
  question: string; onChange: (question: string) => void; onSearch: (question: string) => void;
  loading: boolean; inputRef: RefObject<HTMLInputElement | null>;
}) {
  const noEnglish = !!question.trim() && !/[A-Za-z]/.test(question);
  return <form className="search-form" onSubmit={(e) => { e.preventDefault(); if (!noEnglish && !loading && question.trim()) onSearch(question); }}>
    <div className="searchbar"><label className="field" htmlFor="question"><span className="lang" aria-hidden="true">EN</span>
      <input id="question" ref={inputRef} lang="en" value={question} maxLength={4000} onChange={(e) => onChange(e.target.value)}
        aria-label="영어 결함 서술" aria-describedby="search-help" aria-invalid={noEnglish}
        placeholder="결함 서술을 영어로 — 예: brake fluid leaking from front caliper"
        onKeyDown={(e) => { if (e.key === "Enter" && (e.nativeEvent.isComposing || e.keyCode === 229)) e.preventDefault(); }} />
    </label><button className="btn" disabled={loading || !question.trim()} type="submit">{loading ? "찾는 중…" : "선례 찾기"}</button></div>
    <div className="help-line" id="search-help"><span className={noEnglish ? "warn" : ""} aria-live="polite">{noEnglish ? "영어 단어가 없습니다" : "영어 질문만 받습니다"}</span><span>고객사(현대·기아) 최대 5건 + 다른 회사 상위 10건</span><span className={question.length === 4000 ? "warn count" : "count"}>{question.length} / 4000자</span></div>
  </form>;
}

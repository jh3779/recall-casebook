export interface LoaderState {
  text: string;
  active: boolean;
  failed?: boolean;
}

export function Loader({ text, active, failed }: LoaderState) {
  if (!active) return null;
  return (
    <div className="loader" role={failed ? "alert" : "status"}>
      {!failed && <div className="loader-ring" />}
      <div className="loader-text">{text}</div>
      {failed && <button className="search-category" onClick={() => { location.hash = "search"; }}>검색 화면으로</button>}
    </div>
  );
}

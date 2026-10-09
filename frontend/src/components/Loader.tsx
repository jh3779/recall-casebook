export interface LoaderState {
  text: string;
  active: boolean;
  failed?: boolean;
}

export function Loader({ text, active, failed }: LoaderState) {
  return (
    <div className={"loader" + (active ? "" : " done")}>
      {!failed && <div className="loader-ring" />}
      <div className="loader-text">{text}</div>
    </div>
  );
}

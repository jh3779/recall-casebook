import { useEffect, useRef, useState } from "react";

// 배경 영상·포스터는 출처·라이선스를 확인하지 못해 저장소에 올리지 않는다(gitignore, DEC-074) — 파일이 없으면 검은 바탕으로 둔다.
const FILM = "landing/roadster.mp4";
const POSTER = "landing/roadster.jpg";
const reducedMotion = () => typeof matchMedia === "function" && matchMedia("(prefers-reduced-motion: reduce)").matches;

/** focusEnter: 앱에서 돌아왔을 때만 버튼에 초점을 준다 — 첫 로드에서는 초점 테두리가 화면에 찍히지 않게 한다 */
export default function Landing({ onEnter, focusEnter = false }: { onEnter: () => void; focusEnter?: boolean }) {
  const [film, setFilm] = useState(true);
  const [reduce] = useState(reducedMotion);
  const video = useRef<HTMLVideoElement>(null);
  const enter = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (focusEnter) enter.current?.focus();
    if (!reduce) video.current?.play().catch(() => {});
  }, [reduce, focusEnter]);
  return <div className="landing" id="landing" lang="en">
    <header className="ld-bar ld-in">
      <span className="ld-cap ld-eye">NHTSA records</span>
      <h1 className="ld-mark">Recall Casebook</h1>
    </header>
    <section className="ld-hero">
      {film && <video ref={video} className="ld-film" src={FILM} poster={POSTER} muted loop playsInline preload={reduce ? "none" : "auto"} aria-hidden="true" onError={() => setFilm(false)} />}
      <div className="ld-hero-in ld-in">
        <p className="ld-cap ld-eye">For quality and product safety engineers</p>
        <p className="ld-lede">Find recalls that may involve the same part at other makers, with the cause text each one filed, quoted word for word from NHTSA records.</p>
        <button ref={enter} type="button" className="ld-btn ld-cap" onClick={onEnter}>Open casebook</button>
      </div>
    </section>
  </div>;
}

import { useEffect, useRef, useState } from "react";
import { Dock } from "../components/Dock";
import { Hero } from "../components/Hero";
import { Hotspots } from "../components/Hotspots";
import { Loader, type LoaderState } from "../components/Loader";
import { Panel } from "../components/Panel";
import { TopBar } from "../components/TopBar";
import { CATEGORY_KEYS, MODELS, PAINTS } from "../config";
import { otherModel, recallsFor } from "../recalls";
import { DemoDataError, loadFailed, startFailure } from "./loadFailure";
import { Showroom } from "./Showroom";
import type { CategoryKey, Mode, ModelKey, RecallsByModel } from "../types";

const FIRST: ModelKey = "sonata";

const loadingText = (key: ModelKey) => `${MODELS[key].label} 3D 모델 불러오는 중…`;

interface Ready {
  showroom: Showroom;
  recalls: RecallsByModel;
  snapshotDate: string;
  firstCats: ReadonlySet<CategoryKey>;
}

export default function ShowroomView({ onSearch }: { onSearch: (question: string) => void }) {
  const stageRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState<Ready | null>(null);
  const [loader, setLoader] = useState<LoaderState>({ text: loadingText(FIRST), active: true });

  // 3D 무대를 만들고 첫 차종을 띄운다. 언마운트 때 정리한다(StrictMode 이중 실행에도 안전)
  useEffect(() => {
    let showroom: Showroom | undefined;
    let alive = true;
    const controller = new AbortController();
    Promise.resolve().then(async () => {
      if (!alive) return;
      const scene = new Showroom(stageRef.current!);
      showroom = scene;
      const getJson = <T,>(path: string) => fetch(path, { signal: controller.signal }).then((r) => {
        if (!r.ok) throw new Error(`${path} ${r.status}`);
        return r.json() as Promise<T>;
      }).catch((e) => { throw new DemoDataError(String(e)); }); // 못 받았거나(네트워크·404) 읽지 못했거나 모두 데이터 오류
      const model = scene.load(FIRST);
      model.catch(() => {}); // 아래에서 기다리기 전에 먼저 실패해도 처리 안 된 거부로 남지 않게
      // 데이터와 모델이 함께 실패하면(네트워크 끊김) 먼저 끝난 쪽이 아니라 데이터 오류를 우선 알린다 — 모델 안내는 데이터를 받은 뒤에만
      const [recalls, manifest] = await Promise.all([
        getJson<RecallsByModel>("data/hyundai-kia-recalls.json"),
        getJson<{ snapshot_date: string }>("data/hyundai-kia-manifest.json"),
      ]);
      const firstCats = await model;
      if (!alive) return;
      scene.show(FIRST);
      scene.focus(null);
      setReady({ showroom: scene, recalls, snapshotDate: manifest.snapshot_date, firstCats });
      setLoader((l) => ({ ...l, active: false }));
      scene.load(otherModel(FIRST)).catch(() => {});
    }).catch((e) => {
      if (alive) setLoader(startFailure(e, !!showroom, FIRST));
    });
    return () => {
      alive = false;
      controller.abort();
      showroom?.dispose();
      document.body.classList.remove("xray");
    };
  }, []);

  return (
    <div className="view-showroom">
      <div className="stage" ref={stageRef} />
      {ready && <Explorer {...ready} setLoader={setLoader} onSearch={onSearch} />}
      <Loader {...loader} />
    </div>
  );
}

function Explorer({ showroom, recalls, snapshotDate, firstCats, setLoader, onSearch }: Ready & { setLoader: (s: LoaderState) => void; onSearch: (question: string) => void }) {
  const [model, setModel] = useState(FIRST);
  /** 지금 차종에서 3D 위치가 있는 부품 분류 */
  const [cats3d, setCats3d] = useState(firstCats);
  const [mode, setMode] = useState<Mode>("exterior");
  const [category, setCategory] = useState<CategoryKey | null>(null);
  const [paint, setPaint] = useState(PAINTS[0].color);

  function selectCategory(cat: CategoryKey | null) {
    setCategory(cat);
    if (cat) setMode(cats3d.has(cat) ? "xray" : "exterior");
    showroom.focus(cat && cats3d.has(cat) ? cat : null);
  }

  const aliveRef = useRef(true);
  const switchRef = useRef(0);
  useEffect(() => { aliveRef.current = true; return () => { aliveRef.current = false; }; }, []);

  async function switchModel(key: ModelKey, cat: CategoryKey | null) {
    const turn = ++switchRef.current;
    const wasLoaded = showroom.isLoaded(key);
    if (!wasLoaded) setLoader({ text: loadingText(key), active: true });
    let cats: ReadonlySet<CategoryKey>;
    try {
      cats = await showroom.load(key);
    } catch (e) {
      if (!aliveRef.current || turn !== switchRef.current) return;
      console.error(e);
      setLoader(loadFailed(key));
      return;
    }
    if (!aliveRef.current || turn !== switchRef.current) return;
    showroom.show(key);
    setModel(key);
    setCats3d(cats);
    setLoader({ text: loadingText(key), active: false });
    const keep = cat && recallsFor(recalls, key, cat).length > 0 ? cat : null;
    setCategory(keep);
    setMode(keep && cats.has(keep) ? "xray" : "exterior");
    showroom.focus(keep && cats.has(keep) ? keep : null);
  }

  function changeMode(m: Mode) {
    setMode(m);
    if (m === "exterior" && category) {
      setCategory(null);
      showroom.setAutoRotate(true);
    }
  }

  useEffect(() => {
    document.body.classList.toggle("xray", mode === "xray");
    return () => document.body.classList.remove("xray");
  }, [mode]);

  useEffect(() => {
    const active = new Set(CATEGORY_KEYS.filter((k) => recallsFor(recalls, model, k).length > 0));
    showroom.setLook(mode, category, active);
  }, [showroom, recalls, model, mode, category]);

  useEffect(() => {
    showroom.setPaint(paint);
  }, [showroom, paint]);

  const hotspots = CATEGORY_KEYS.filter((k) => cats3d.has(k))
    .map((key) => ({ key, count: recallsFor(recalls, model, key).length }))
    .filter((h) => h.count > 0);

  return (
    <>
      <Hotspots
        items={hotspots}
        category={category}
        onSelect={selectCategory}
        bind={(cat, el) => showroom.bindHotspot(cat, el)}
      />
      <TopBar model={model} onSelect={(k) => switchModel(k, category)} />
      <Hero model={model} recalls={recalls[model]} />
      <Panel
        recalls={recalls}
        model={model}
        category={category}
        cats3d={cats3d}
        onSelect={selectCategory}
        onCross={switchModel}
        onSearch={onSearch}
      />
      <Dock mode={mode} onMode={changeMode} paint={paint} onPaint={setPaint} onReset={() => selectCategory(null)} />
      <div className="model-legend">{mode === "xray" ? "● " : "+ "}부품 형상·위치는 설명용 추정 · 리콜은 실제 기록</div>
      <div className="credit">
        3D: <a href={MODELS[model].source} target="_blank" rel="noreferrer">{MODELS[model].credit}</a> · <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noreferrer">CC BY 4.0</a> · 크기·재질 조정{model === "sorento" ? " · 바퀴 복제" : " · 미사용 UV 제거"} · 추정 도형 추가<br />
        리콜: NHTSA · {snapshotDate} 스냅샷 {recalls.sonata.length + recalls.sorento.length}건 (검색 결과 아님)
      </div>
    </>
  );
}

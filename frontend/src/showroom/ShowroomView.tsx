import { useEffect, useRef, useState } from "react";
import { Dock } from "../components/Dock";
import { Hero } from "../components/Hero";
import { Hotspots } from "../components/Hotspots";
import { Loader, type LoaderState } from "../components/Loader";
import { Panel } from "../components/Panel";
import { TopBar } from "../components/TopBar";
import { CATEGORY_KEYS, MODELS, PAINTS } from "../config";
import { otherModel, recallsFor } from "../recalls";
import { Showroom } from "./Showroom";
import type { CategoryKey, Mode, ModelKey, RecallsByModel } from "../types";

const FIRST: ModelKey = "silverado";

const loadingText = (key: ModelKey) => `${MODELS[key].label} 3D 모델 불러오는 중…`;

// 모델 파일은 커밋하지 않으므로(용량) 받아 두지 않았으면 여기서 멈추고 안내한다
const loadFailed = (key: ModelKey): LoaderState => ({
  text: `3D 모델을 불러오지 못했습니다 (public/${MODELS[key].glb}). frontend/README.md의 "3D 모델 파일"을 보세요.`,
  active: true,
  failed: true,
});

interface Ready {
  showroom: Showroom;
  recalls: RecallsByModel;
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
      const [firstCats, recalls] = await Promise.all([
        scene.load(FIRST),
        fetch("data/recalls.json", { signal: controller.signal }).then((r) => {
          if (!r.ok) throw new Error("데모 데이터를 받지 못했습니다");
          return r.json() as Promise<RecallsByModel>;
        }),
      ]);
      if (!alive) return;
      scene.show(FIRST);
      scene.focus(null);
      setReady({ showroom: scene, recalls, firstCats });
      setLoader((l) => ({ ...l, active: false }));
      scene.load(otherModel(FIRST)).catch(() => {});
    }).catch(() => {
      if (alive) setLoader(showroom ? loadFailed(FIRST) : { text: "3D 화면을 시작하지 못했습니다. 이 브라우저에서 WebGL을 사용할 수 없습니다.", active: true, failed: true });
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

function Explorer({ showroom, recalls, firstCats, setLoader, onSearch }: Ready & { setLoader: (s: LoaderState) => void; onSearch: (question: string) => void }) {
  const [model, setModel] = useState(FIRST);
  /** 지금 차종에서 3D 위치가 있는 부품 분류 */
  const [cats3d, setCats3d] = useState(firstCats);
  const [mode, setMode] = useState<Mode>("exterior");
  const [category, setCategory] = useState<CategoryKey | null>(null);
  const [paint, setPaint] = useState(PAINTS[0].color);

  function selectCategory(cat: CategoryKey | null) {
    setCategory(cat);
    if (cat) setMode("xray");
    showroom.focus(cat);
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
    const keep = cat && cats.has(cat) && recallsFor(recalls, key, cat).length > 0;
    selectCategory(keep ? cat : null);
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
      <div className="credit">
        3D: CCSA, George Mason University · FHWA/NHTSA 유한요소 모델(실차 역설계, 단순화) · 리콜: NHTSA 공개 데이터 · 데모 스냅샷 {recalls.silverado.length + recalls.ram.length}건 (검색 결과 아님)
      </div>
    </>
  );
}

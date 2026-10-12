import { useEffect, useRef, useState } from "react";
import { Dock } from "./components/Dock";
import { Hero } from "./components/Hero";
import { Hotspots } from "./components/Hotspots";
import { Loader, type LoaderState } from "./components/Loader";
import { Panel } from "./components/Panel";
import { TopBar } from "./components/TopBar";
import { CATEGORY_KEYS, MODELS, PAINTS } from "./config";
import { otherModel, recallsFor } from "./recalls";
import { Showroom } from "./showroom/Showroom";
import type { CategoryKey, Mode, ModelKey, RecallsByModel } from "./types";

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

export default function App() {
  const stageRef = useRef<HTMLDivElement>(null);
  const [ready, setReady] = useState<Ready | null>(null);
  const [loader, setLoader] = useState<LoaderState>({ text: loadingText(FIRST), active: true });

  // 3D 무대를 만들고 첫 차종을 띄운다. 언마운트 때 정리한다(StrictMode 이중 실행에도 안전)
  useEffect(() => {
    const showroom = new Showroom(stageRef.current!);
    let alive = true;
    const recallsP = fetch("data/recalls.json").then((r) => r.json() as Promise<RecallsByModel>);
    showroom.load(FIRST).then(
      async (firstCats) => {
        const recalls = await recallsP;
        if (!alive) return;
        showroom.show(FIRST);
        showroom.focus(null);
        setReady({ showroom, recalls, firstCats });
        setLoader((l) => ({ ...l, active: false }));
        // 다른 차종은 미리 받아 둔다. 실패하면 그 차종을 고를 때 다시 시도해 안내한다
        showroom.load(otherModel(FIRST)).catch(() => {});
      },
      (e) => {
        if (!alive) return;
        console.error(e);
        setLoader(loadFailed(FIRST));
      },
    );
    return () => {
      alive = false;
      showroom.dispose();
    };
  }, []);

  return (
    <>
      <div className="stage" ref={stageRef} />
      {ready && <Explorer {...ready} setLoader={setLoader} />}
      <Loader {...loader} />
    </>
  );
}

function Explorer({ showroom, recalls, firstCats, setLoader }: Ready & { setLoader: (s: LoaderState) => void }) {
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

  async function switchModel(key: ModelKey, cat: CategoryKey | null) {
    const wasLoaded = showroom.isLoaded(key);
    if (!wasLoaded) setLoader({ text: loadingText(key), active: true });
    let cats: ReadonlySet<CategoryKey>;
    try {
      cats = await showroom.load(key);
    } catch (e) {
      console.error(e);
      setLoader(loadFailed(key));
      return;
    }
    showroom.show(key);
    setModel(key);
    setCats3d(cats);
    if (!wasLoaded) setLoader({ text: loadingText(key), active: false });
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
      />
      <Dock mode={mode} onMode={changeMode} paint={paint} onPaint={setPaint} onReset={() => selectCategory(null)} />
      <div className="credit">
        3D: CCSA, George Mason University · FHWA/NHTSA 유한요소 모델(실차 역설계, 단순화) · 리콜: NHTSA 공개 데이터 · 데모용
      </div>
    </>
  );
}

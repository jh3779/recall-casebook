import { Box3, BoxGeometry, Mesh, PerspectiveCamera, Vector3 } from "three";
import type { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Showroom } from "./Showroom";

// GPU와 DOM만 대체하고 Showroom 생성자·애니메이션·OrbitControls는 실제 구현을 쓴다.
vi.mock("three", async (importOriginal) => {
  const three = await importOriginal<typeof import("three")>();
  return {
    ...three,
    WebGLRenderer: class {
      domElement = Object.assign(new EventTarget(), {
        style: {}, ownerDocument: new EventTarget(), clientWidth: 1200, clientHeight: 800,
        getRootNode() { return this.ownerDocument; }, remove() {},
      });
      shadowMap = {};
      setPixelRatio() {}
      setSize() {}
      render() {}
      dispose() {}
      forceContextLoss() {}
    },
    PMREMGenerator: class { fromScene() { return { texture: new three.Texture() }; } },
  };
});

const center = new Vector3(0, 0.8, 0);
const scenes: Showroom[] = [];

function fixture(reducedMotion = true) {
  let frame: FrameRequestCallback;
  vi.stubGlobal("innerWidth", 1200);
  vi.stubGlobal("innerHeight", 800);
  vi.stubGlobal("devicePixelRatio", 1);
  vi.stubGlobal("matchMedia", () => ({ matches: reducedMotion }));
  vi.stubGlobal("addEventListener", vi.fn());
  vi.stubGlobal("removeEventListener", vi.fn());
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  vi.stubGlobal("requestAnimationFrame", (next: FrameRequestCallback) => { frame = next; return 1; });
  vi.spyOn(performance, "now").mockReturnValue(1000);
  const showroom = new Showroom({ clientWidth: 1200, clientHeight: 800, appendChild() {} } as unknown as HTMLElement);
  scenes.push(showroom);
  Object.assign(showroom, {
    current: { hotspots: { steering: { point: new Vector3(1.8, 0.4, -0.7), box: new Box3(new Vector3(1, 0, -1), new Vector3(2, 0.6, 0)) } } },
  });
  const { camera, controls } = showroom as unknown as { camera: PerspectiveCamera; controls: OrbitControls };
  return { showroom, camera, controls, tick: (now: number) => frame(now) };
}

afterEach(() => {
  scenes.splice(0).forEach((scene) => scene.dispose());
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("차량 중앙 회전축", () => {
  it("추정 부품은 외관에서 숨기고 실제 리콜이 있는 선택 분류에서만 보여 준다", () => {
    const { showroom } = fixture();
    const estimated = new Mesh(new BoxGeometry());
    estimated.userData = { estimated: true, part: { defect: "engine" }, base: estimated.material };
    Object.assign(showroom, { current: { meshes: [estimated] } });
    showroom.setLook("exterior", null, new Set(["engine"]));
    expect(estimated.visible).toBe(false);
    showroom.setLook("xray", "engine", new Set(["engine"]));
    expect(estimated.visible).toBe(true);
    showroom.setLook("xray", "fuel", new Set(["engine", "fuel"]));
    expect(estimated.visible).toBe(false);
    showroom.setLook("xray", null, new Set());
    expect(estimated.visible).toBe(false);
  });

  it("부품 표시 규칙(meshLook)을 재질·그림자·그리는 순서로 옮긴다 — 외관+강조는 주황·그림자 있음, 투시는 그림자 없음(DEC-078)", () => {
    const { showroom } = fixture();
    const mk = (defect: string, estimated = false) => {
      const m = new Mesh(new BoxGeometry());
      m.userData = { estimated, part: { defect }, base: m.material };
      return m;
    };
    const seat = mk("seat"), engineEst = mk("engine", true), body = mk("other");
    Object.assign(showroom, { current: { meshes: [seat, engineEst, body] } });
    const { mat } = showroom as unknown as { mat: Record<string, unknown> };
    showroom.setLook("exterior", "seat", new Set(["seat"]));
    expect(seat.material).toBe(seat.userData.base);
    expect(seat.castShadow).toBe(true);
    showroom.setLook("exterior", "seat", new Set(["seat"]), true);
    expect(seat.material).toBe(mat.hot);
    expect(seat.castShadow).toBe(true);
    expect(body.material).toBe(body.userData.base); // 차체는 불투명 원래 재질 그대로
    expect(engineEst.visible).toBe(false); // 다른 분류의 설명용 도형은 숨김
    showroom.setLook("xray", "seat", new Set(["seat"]));
    expect(seat.material).toBe(mat.hot);
    expect(seat.castShadow).toBe(false);
    expect(body.material).toBe(mat.ghost);
    expect(body.renderOrder).toBe(1);
    expect(seat.renderOrder).toBe(0);
  });

  it("부품을 선택해도 회전 중심은 차량 중앙에 머문다", () => {
    const { showroom, controls, camera } = fixture();
    const before = camera.position.clone();
    showroom.focus("steering");
    expect(controls.target.toArray()).toEqual(center.toArray());
    expect(camera.position.equals(before)).toBe(false);
    expect(controls.autoRotate).toBe(false);
  });

  it("부품으로 이동하는 애니메이션 도중에도 중심은 움직이지 않는다", () => {
    const { showroom, controls, tick } = fixture(false);
    showroom.focus("steering");
    tick(1550);
    expect(controls.target.toArray()).toEqual(center.toArray());
    tick(2100);
    expect(controls.target.toArray()).toEqual(center.toArray());
  });

  it("처음 시점 복귀와 자동 회전 재개도 같은 중심을 쓴다", () => {
    const { showroom, controls } = fixture();
    showroom.focus("steering");
    showroom.focus(null);
    showroom.setAutoRotate(true);
    expect(controls.target.toArray()).toEqual(center.toArray());
    expect(controls.autoRotate).toBe(false); // 모션 줄이기 설정 유지
  });

  it("상하 회전과 팬을 막고 확대·수평 회전은 유지한다", () => {
    const { controls, camera, showroom, tick } = fixture(false);
    const angle = controls.getPolarAngle();
    expect(controls.enablePan).toBe(false);
    expect(controls.enableZoom).toBe(true);
    expect(controls.enableRotate).toBe(true);
    showroom.focus("steering");
    tick(2100);
    expect(controls.getPolarAngle()).toBeCloseTo(angle);
    expect(camera.up.toArray()).toEqual([0, 1, 0]);
    const position = camera.position.clone();
    showroom.setAutoRotate(true);
    tick(2200);
    expect(camera.position.equals(position)).toBe(false);
    expect(controls.target.toArray()).toEqual(center.toArray());
    expect(controls.getPolarAngle()).toBeCloseTo(angle);
  });
});

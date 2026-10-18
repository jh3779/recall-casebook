import { Box3, Object3D, PerspectiveCamera, Quaternion, Vector3 } from "three";
import type { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { afterEach, describe, expect, it, vi } from "vitest";
import { peelFraming, peelShift } from "./peel";
import { Showroom } from "./Showroom";

// rotation.test.ts와 같은 방식: GPU와 DOM만 대체하고 Showroom 생성자·tick·OrbitControls는 실제 구현을 쓴다.
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

const HOME_POS = new Vector3(6.8, 2.6, -7.6);
const HOME_TARGET = new Vector3(0, 0.8, 0);
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
  // 걷어낼 뼈대: 부모는 단위 변환이고 rest는 (0,1,0)
  const bones = ["seats_09", "bodyshell_030", "door_dside_f_056"].map((name) => {
    const bone = new Object3D();
    bone.position.set(0, 1, 0);
    return { name, bone, rest: bone.position.clone(), toLocal: new Quaternion(), scale: 1 };
  });
  const hotspot = { point: new Vector3(0.5, 1.1, -0.4), box: new Box3(new Vector3(0, 0.8, -0.8), new Vector3(1, 1.4, 0)), bone: "steeringwheel_053" };
  Object.assign(showroom, { current: { meshes: [], hotspots: { steering: hotspot }, rig: bones } });
  const { camera, controls } = showroom as unknown as { camera: PerspectiveCamera; controls: OrbitControls };
  return { showroom, camera, controls, bones, hotspot, tick: (now: number) => frame(now) };
}

afterEach(() => {
  scenes.splice(0).forEach((scene) => scene.dispose());
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

const offset = (camera: PerspectiveCamera, controls: OrbitControls) => camera.position.clone().sub(controls.target);

describe("걷어내기: 뼈대 적용", () => {
  it("모션 감소 설정이면 setPeel이 뼈대 위치를 rest + 이동량으로 바로 바꾸고, 0으로 돌리면 rest로 돌아온다", () => {
    const { showroom, bones } = fixture();
    showroom.setPeel(2);
    for (const { name, bone, rest } of bones) expect(bone.position.toArray(), name).toEqual(rest.clone().add(new Vector3(...peelShift(name, 2))).toArray());
    expect(bones[1].bone.position.y).toBe(1); // 차체 껍데기는 4층에서야 움직인다
    showroom.setPeel(0);
    for (const { bone, rest } of bones) expect(bone.position.toArray()).toEqual(rest.toArray());
  });
  it("부모 뼈대가 회전·확대돼 있으면 차량 좌표의 이동량을 부모 좌표로 바꿔 적용한다", () => {
    const { showroom, bones } = fixture();
    const quarter = new Quaternion().setFromAxisAngle(new Vector3(0, 0, 1), Math.PI / 2); // 부모의 로컬 x → 차량의 y
    Object.assign(bones[0], { toLocal: quarter.clone().invert(), scale: 2 });
    showroom.setPeel(3);
    const shift = new Vector3(...peelShift("seats_09", 3)).applyQuaternion(quarter.clone().invert()).divideScalar(2);
    expect(bones[0].bone.position.toArray()).toEqual(bones[0].rest.clone().add(shift).toArray());
  });
  it("애니메이션 도중에 다시 호출하면 지금 값에서 새로 시작한다", () => {
    const { showroom, tick } = fixture(false);
    showroom.setPeel(4);
    tick(1350); // 700ms 중 절반 — smootherstep(0.5) = 0.5
    const mid = (showroom as unknown as { peelNow: number }).peelNow;
    expect(mid).toBeCloseTo(2, 6);
    showroom.setPeel(0);
    expect((showroom as unknown as { peelAnim: { from: number } }).peelAnim.from).toBeCloseTo(mid, 6);
    tick(2200);
    expect((showroom as unknown as { peelNow: number }).peelNow).toBe(0);
  });
  it("범위 밖·잘못된 값은 0~4로 고정한다", () => {
    const { showroom } = fixture();
    showroom.setPeel(9);
    expect((showroom as unknown as { peelNow: number }).peelNow).toBe(4);
    showroom.setPeel(Number.NaN);
    expect((showroom as unknown as { peelNow: number }).peelNow).toBe(0);
  });
});

describe("걷어내기: 카메라", () => {
  it("0층에서는 기존 시점 그대로다(처음 시점 복귀)", () => {
    const { showroom, camera, controls } = fixture();
    showroom.focus(null);
    expect(camera.position.distanceTo(HOME_POS)).toBeLessThan(1e-9);
    expect(controls.target.toArray()).toEqual(HOME_TARGET.toArray());
  });
  it("분류를 고르지 않은 상태에서 층을 바꾸면 카메라가 뒤로 빠지고 시선이 올라가며 보던 방향은 유지한다", () => {
    const { showroom, camera, controls } = fixture();
    camera.position.set(-4, 2.2, 6); // 사용자가 직접 돌려 둔 시점
    const before = offset(camera, controls);
    showroom.setPeel(4);
    const { scale, lift } = peelFraming(4);
    expect(controls.target.y).toBeCloseTo(HOME_TARGET.y + lift, 9);
    const after = offset(camera, controls);
    expect(after.length()).toBeCloseTo(before.length() * scale, 6);
    expect(after.clone().normalize().distanceTo(before.clone().normalize())).toBeLessThan(1e-9);
  });
  it("분류를 고른 상태(기본 상태)에서도 층을 바꾸면 카메라 거리가 늘고, 직접 돌려 둔 방향은 유지된다", () => {
    const { showroom, camera, controls } = fixture();
    showroom.focus("steering");
    camera.position.applyAxisAngle(new Vector3(0, 1, 0), 0.7); // 분류 선택 뒤 직접 회전
    const before = offset(camera, controls);
    showroom.setPeel(4);
    const { scale } = peelFraming(4);
    const after = offset(camera, controls);
    expect(after.length()).toBeCloseTo(before.length() * scale, 6);
    expect(after.clone().normalize().distanceTo(before.clone().normalize())).toBeLessThan(1e-9);
    showroom.setPeel(0); // 되돌리면 원래 거리
    expect(offset(camera, controls).length()).toBeCloseTo(before.length(), 6);
  });
  it("걷어낸 상태에서 분류를 고르면 부품(이동한 위치) 쪽으로 가되 거리에 확대 배율이 들어가고, 회전 중심은 걷어낸 만큼 올라간 중앙 축이다", () => {
    const { showroom, camera, controls, hotspot } = fixture();
    showroom.setPeel(3);
    showroom.focus("steering");
    const { scale, lift } = peelFraming(3);
    expect(controls.target.toArray()).toEqual([0, HOME_TARGET.y + lift, 0]);
    const point = hotspot.point.clone().add(new Vector3(...peelShift("steeringwheel_053", 3)));
    const size = hotspot.box.getSize(new Vector3()).length();
    expect(camera.position.distanceTo(point)).toBeCloseTo(Math.max(6.8, size * 2.2) * scale, 6);
  });
  it("층을 이동이 끝나기 전에 연달아 바꿔도 최종 카메라 거리는 원래 거리 × 최종 배율이고, 되돌리면 원래 거리다", () => {
    const { showroom, camera, controls, tick } = fixture(false);
    const base = offset(camera, controls).length();
    for (const level of [1, 2, 3, 4]) showroom.setPeel(level); // 카메라가 움직이기 전에 연속 호출(슬라이더를 쭉 끄는 경우)
    tick(1000 + 1200);
    expect(offset(camera, controls).length()).toBeCloseTo(base * peelFraming(4).scale, 6);
    for (const level of [3, 2, 1, 0]) showroom.setPeel(level);
    tick(1000 + 1200);
    expect(offset(camera, controls).length()).toBeCloseTo(base, 6);
  });
  it("이동 도중 사용자가 직접 돌려 이동이 취소돼도, 다음 층 변경의 거리는 지금 카메라에 실제로 적용된 배율을 기준으로 한다", () => {
    const { showroom, camera, controls, tick } = fixture(false);
    const base = offset(camera, controls).length();
    showroom.setPeel(4);
    tick(1000 + 550); // 이동의 절반 — 지금 거리에는 걷어내기 배율이 일부만 들어 있다
    expect(offset(camera, controls).length()).toBeGreaterThan(base);
    expect(offset(camera, controls).length()).toBeLessThan(base * peelFraming(4).scale);
    controls.dispatchEvent({ type: "start" } as never); // 사용자가 드래그를 시작해 이동이 취소된다
    showroom.setPeel(0);
    tick(1000 + 550 + 1200);
    expect(offset(camera, controls).length()).toBeCloseTo(base, 6);
  });
  it("걷어낸 상태에서 분류를 고른 뒤 되돌려도 거리가 어긋나지 않는다(분류 경로의 배율 기록)", () => {
    const { showroom, camera, controls } = fixture();
    showroom.setPeel(3);
    showroom.focus("steering");
    const focused = offset(camera, controls).length();
    showroom.setPeel(0);
    expect(offset(camera, controls).length()).toBeCloseTo(focused / peelFraming(3).scale, 6);
  });
  it("분류 없이 처음 시점으로 돌아갈 때도 걷어낸 정도의 거리·높이를 쓴다", () => {
    const { showroom, camera, controls } = fixture();
    showroom.setPeel(2);
    showroom.focus(null);
    const { scale, lift } = peelFraming(2);
    expect(controls.target.y).toBeCloseTo(HOME_TARGET.y + lift, 9);
    expect(offset(camera, controls).length()).toBeCloseTo(HOME_POS.distanceTo(HOME_TARGET) * scale, 6);
  });
});

describe("걷어내기: 핫스팟 표시", () => {
  it("핫스팟 요소(핀)는 걷어낸 부품의 이동량을 따라 움직인다", () => {
    const { showroom, camera, controls, tick } = fixture();
    const el = { style: { top: "", left: "" }, toggleAttribute() {} } as unknown as HTMLElement;
    showroom.bindHotspot("steering", el);
    tick(1100);
    const top0 = parseFloat(el.style.top);
    const pose = { position: camera.position.clone(), target: controls.target.clone() };
    showroom.setPeel(3); // 핸들은 3층에서 위로 올라간다
    camera.position.copy(pose.position); // 카메라 이동은 빼고 핀의 이동량만 비교한다
    controls.target.copy(pose.target);
    tick(1200);
    expect(parseFloat(el.style.top)).toBeLessThan(top0);
  });
});

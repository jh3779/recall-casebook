import { Box3, Group, Matrix4, Mesh, Object3D, Vector3 } from "three";
import type { Material } from "three";
import type { Look, ModelKey, PartsMap } from "../types";

/** 원본에 있는 바퀴와 배치 지점을 사용한다. 차체나 내부 부품을 새로 만들지 않는다. */
function completeSorentoWheels(source: Object3D) {
  const wheel = source.getObjectByName("wheel_lfchild");
  if (!wheel) return;
  source.updateMatrixWorld(true);
  const pivot = wheel.getWorldPosition(new Vector3());
  const local = new Matrix4().copy(source.matrixWorld).invert();
  for (const name of ["wheel_lr_027", "wheel_rr_028", "wheel_rf_029"]) {
    const anchor = source.getObjectByName(name);
    if (!anchor) continue;
    const point = anchor.getWorldPosition(new Vector3());
    const transform = new Matrix4().makeTranslation(point.x, point.y, point.z)
      .multiply(new Matrix4().makeScale(name.startsWith("wheel_r") ? -1 : 1, 1, 1))
      .multiply(new Matrix4().makeTranslation(-pivot.x, -pivot.y, -pivot.z))
      .multiply(wheel.matrixWorld).premultiply(local);
    const copy = wheel.clone(true);
    copy.name = `${name}_restored`;
    transform.decompose(copy.position, copy.quaternion, copy.scale);
    source.add(copy);
  }
}

/** 외관용 GLB: 원본 법선·텍스처·스킨을 유지하고, 표시 방향·크기·부품 대응만 맞춘다. */
export function prepareVehicle(source: Object3D, key: ModelKey, parts: PartsMap, materials: Record<Look, Material>) {
  if (key === "sorento") completeSorentoWheels(source);
  const root = new Group();
  root.add(source);
  const size = new Box3().setFromObject(source, true).getSize(new Vector3());
  root.scale.setScalar(5.2 / size.z);
  root.rotation.y = key === "sonata" ? Math.PI / 2 : -Math.PI / 2;
  root.updateMatrixWorld(true);
  const box = new Box3().setFromObject(root, true);
  const center = box.getCenter(new Vector3());
  root.position.set(-center.x, -box.min.y, -center.z);
  root.updateMatrixWorld(true);

  const meshes: Mesh[] = [];
  root.traverse((o) => {
    if (!(o instanceof Mesh)) return;
    const part = parts[o.name] ?? { title: o.name, defect: null, look: null };
    o.userData.part = part;
    if (part.look) o.material = materials[part.look];
    o.userData.base = o.material;
    o.castShadow = true;
    meshes.push(o);
  });
  return { root, meshes };
}

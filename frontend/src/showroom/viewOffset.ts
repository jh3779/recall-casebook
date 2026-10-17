/**
 * 3D 무대의 가로 보정(px) — 기존 쇼룸은 오른쪽 380px 패널이 무대 위에 겹치므로 넓은 화면(900px 초과)에서 차를 왼쪽으로 옮긴다.
 * 패널이 무대와 다른 열에 놓이는 화면(케이스북 3D 창)은 `shift`를 0으로 줘서 차가 한쪽으로 치우치지 않게 한다.
 */
export const DEFAULT_PANEL_SHIFT = 200;
export const panelOffset = (stageWidth: number, shift: number = DEFAULT_PANEL_SHIFT): number => (stageWidth > 900 ? shift : 0);

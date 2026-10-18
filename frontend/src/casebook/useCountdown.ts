import { useEffect, useState } from "react";

/** 마감(ms)까지 남은 올림 초. 마감이 없거나 지났으면 0 */
export const secondsLeft = (deadline: number | null, now: number) => (deadline === null ? 0 : Math.max(0, Math.ceil((deadline - now) / 1000)));

/** 어느 마감을 기준으로 언제 읽은 시각인지 */
export interface Stamp { deadline: number | null; at: number }

/**
 * 남은 초. 시각을 읽은 적이 없거나 다른 마감 때 읽은 시각이면(마감이 바뀌었는데 옛 시각으로 새 마감을 세지 않게) 막힌 것으로 두어 1이고,
 * 마감이 없으면 0이다.
 */
export const countdownLeft = (deadline: number | null, stamp: Stamp | null) =>
  deadline === null ? 0 : stamp !== null && stamp.deadline === deadline ? secondsLeft(deadline, stamp.at) : 1;

/**
 * 호출 상한(429) 뒤 다시 보낼 수 있을 때까지 남은 초를 1초마다 센다(DEC-057 ⑤ — 선례 검색 화면의 `RateLimited`를 옮겼다). 다 기다리면 타이머를 멈춘다.
 * 케이스북은 계속 떠 있으므로 시각을 마운트 때 한 번만 읽으면 오래된 시각으로 센다 — 마감이 정해질 때마다 시각을 새로 읽는다.
 * 현재 시각은 타이머 콜백에서만 읽는다(렌더 중에는 읽지 않는다). 마감이 막 정해진 첫 그림에서는 시각을 모르므로 막힌 것으로 둔다.
 */
export function useCountdown(deadline: number | null): number {
  const [now, setNow] = useState<Stamp | null>(null);
  const left = countdownLeft(deadline, now);
  const waiting = left > 0;
  useEffect(() => {
    if (!waiting) return; // 다 기다렸으면 타이머를 멈춘다
    const tick = () => setNow({ deadline, at: Date.now() });
    const first = setTimeout(tick, 0);
    const timer = setInterval(tick, 1000);
    return () => { clearTimeout(first); clearInterval(timer); };
  }, [waiting, deadline]);
  return left;
}

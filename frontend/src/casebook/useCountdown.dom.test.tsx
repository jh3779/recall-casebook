// @vitest-environment jsdom
import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { useCountdown } from "./useCountdown";

const START = 1_000_000;
beforeEach(() => { vi.useFakeTimers(); vi.setSystemTime(START); });
afterEach(() => { cleanup(); vi.useRealTimers(); });
const advance = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });

it("마감이 정해지면 막힌 채(1)로 시작해 곧 남은 초를 세고, 1초마다 줄어 0이 되면 타이머를 멈춘다", () => {
  const { result } = renderHook(({ deadline }) => useCountdown(deadline), { initialProps: { deadline: START + 3000 as number | null } });
  advance(0); // 첫 시각 읽기
  expect(result.current).toBe(3);
  advance(1000);
  expect(result.current).toBe(2);
  advance(1000);
  expect(result.current).toBe(1);
  advance(1000);
  expect(result.current).toBe(0);
  expect(vi.getTimerCount()).toBe(0); // 다 기다렸으면 1초 타이머도 멈춘다
  advance(5000);
  expect(result.current).toBe(0);
});

it("마감이 새로 정해지면 옛 시각으로 세지 않고 새 마감을 처음부터 센다", () => {
  const { result, rerender } = renderHook(({ deadline }) => useCountdown(deadline), { initialProps: { deadline: START + 2000 as number | null } });
  advance(2000);
  expect(result.current).toBe(0);
  vi.setSystemTime(START + 60_000); // 탭을 오래 열어 둔 뒤 새 429
  rerender({ deadline: START + 60_000 + 10_000 });
  expect(result.current).toBe(1); // 시각을 읽기 전의 첫 그림은 막힌 것으로 둔다
  advance(0);
  expect(result.current).toBe(10);
});

it("마감을 기다리다 화면이 사라지면 타이머를 모두 거둔다", () => {
  const { unmount } = renderHook(() => useCountdown(START + 5000));
  advance(0);
  expect(vi.getTimerCount()).toBeGreaterThan(0);
  unmount();
  expect(vi.getTimerCount()).toBe(0);
});

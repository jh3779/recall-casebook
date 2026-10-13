import { causeStatus } from "./causeStatus";
import type { Cause } from "./types";
export function CauseBadge({ cause }: { cause: Cause }) {
  const { level, label } = causeStatus(cause);
  return <span className={`cstate ${level}`}>{label}</span>;
}

import { useEffect, useRef, useState } from "react";
import { request } from "./client";
import { isTerminal, type RunDetail, type RunSummary } from "./models";
// The summary API has no amounts. Fetch actual detail records; never infer totals.
export function useRunDetails(runs: RunSummary[]) {
  const [records, setRecords] = useState<Record<string, RunDetail>>({});
  const cache = useRef<Record<string, RunDetail>>({});
  const signature = runs
    .map((r) => r.id + ":" + r.status + ":" + r.attempt + ":" + r.outcome)
    .join("|");
  useEffect(() => {
    const controller = new AbortController();
    const missing = runs.filter(
      (r) =>
        !cache.current[r.id] ||
        (!isTerminal(cache.current[r.id]) && isTerminal(r)),
    );
    async function load() {
      for (let index = 0; index < missing.length; index += 4) {
        if (controller.signal.aborted) return;
        const batch = await Promise.allSettled(
          missing.slice(index, index + 4).map((r) =>
            request<RunDetail>("/runs/" + r.id, {
              signal: controller.signal,
            }),
          ),
        );
        if (controller.signal.aborted) return;
        for (const result of batch)
          if (result.status === "fulfilled")
            cache.current[result.value.id] = result.value;
        setRecords({ ...cache.current });
      }
    }
    void load();
    return () => controller.abort();
    // Signature is the complete dependency for this bounded detail cache.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);
  return records;
}

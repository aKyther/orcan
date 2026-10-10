/** Opt-in, in-memory counters. Never store project paths or probe contents. */
export function createRenderMetrics(enabled: boolean, now = () => performance.now()) {
  const counters = new Map<string, { count: number; totalMs: number; maxMs: number }>();
  const samples: Array<{ name: string; durationMs: number }> = [];
  function run<T>(name: string, operation: () => T): T {
    if (!enabled) return operation();
    const started = now();
    try { return operation(); }
    finally {
      const durationMs = Math.max(0, now() - started);
      const counter = counters.get(name) ?? { count: 0, totalMs: 0, maxMs: 0 };
      counter.count++;
      counter.totalMs += durationMs;
      counter.maxMs = Math.max(counter.maxMs, durationMs);
      counters.set(name, counter);
      samples.push({ name, durationMs });
      if (samples.length > 64) samples.shift();
    }
  }
  return { run, snapshot: () => ({ counters: Object.fromEntries([...counters].map(([name, counter]) => [name, { ...counter }])), samples: samples.map(sample => ({ ...sample })) }) };
}

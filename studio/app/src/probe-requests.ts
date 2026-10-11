/** Share only in-flight reads; every explicit selection expires older activations. */
export function probeRequests<T>(read: (key: string) => Promise<T>) {
  let generation = 0;
  const pending = new Map<string, Promise<T>>();
  return {
    invalidate() { generation++; },
    begin() { const request = ++generation; return () => request === generation; },
    read(key: string): Promise<T> {
      const existing = pending.get(key);
      if (existing) return existing;
      const request = Promise.resolve().then(() => read(key)).finally(() => pending.delete(key));
      pending.set(key, request);
      return request;
    },
  };
}

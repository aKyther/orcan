/** A report and its connection are one approval target, never global mutable state. */
export function contextScope<C, R>(connection: C, report: R, current: () => [C | undefined, R | undefined]) {
  return {
    connection, report,
    active() { const [now, snapshot] = current(); return now === connection && snapshot === report; },
  };
}

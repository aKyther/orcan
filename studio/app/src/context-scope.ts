/** A report and its connection are one approval target, never global mutable state. */
export function contextScope<C, R>(connection: C, report: R, current: () => [C | undefined, R | undefined]) {
  const active = () => { const [now, snapshot] = current(); return now === connection && snapshot === report; };
  return {
    connection, report,
    active,
    async approve(confirm: () => Promise<boolean>, apply: () => Promise<unknown>): Promise<boolean> {
      if (!active() || !await confirm() || !active()) return false;
      await apply();
      return true;
    },
  };
}

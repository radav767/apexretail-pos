type AuthStorage = Pick<Storage, "getItem">;

let epoch = 0;
export function advanceAuthenticationEpoch() { epoch += 1; }

export function captureAuthentication(storage: AuthStorage = localStorage) {
  return {
    epoch,
    owner: storage.getItem("token"),
    employee: storage.getItem("employee_token"),
    employeeId: storage.getItem("employee_id"),
    company: storage.getItem("company_id"),
  };
}

export type AuthenticationSnapshot = ReturnType<typeof captureAuthentication>;

export function sameAuthentication(a: AuthenticationSnapshot, b = captureAuthentication()) {
  return a.epoch === b.epoch && a.owner === b.owner && a.employee === b.employee
    && a.employeeId === b.employeeId && a.company === b.company;
}

export function authorizationFor(snapshot: AuthenticationSnapshot) {
  const token = snapshot.employee || (!snapshot.employeeId ? snapshot.owner : null);
  return token ? `Bearer ${token}` : undefined;
}

export function shouldInvalidateAuthentication(
  status: number | undefined,
  url: string | undefined,
  sent: AuthenticationSnapshot | undefined,
  current = captureAuthentication(),
) {
  const path = url?.split("?")[0];
  return status === 401 && sent !== undefined && Boolean(authorizationFor(sent))
    && !["/auth/login", "/auth/register", "/employees/pin-login", "/employees/session/logout"].includes(path || "")
    && sameAuthentication(sent, current);
}

export function createBootstrapScope(storage: AuthStorage = localStorage) {
  const snapshot = captureAuthentication(storage);
  let cancelled = false;
  return {
    isCurrent: () => !cancelled && sameAuthentication(snapshot, captureAuthentication(storage)),
    cancel: () => { cancelled = true; },
  };
}

export function isCurrentAuthenticationFailure(error: unknown): boolean {
  return Boolean(error && typeof error === "object" &&
    (error as { apexInvalidatedAuthentication?: boolean }).apexInvalidatedAuthentication);
}

export async function runBootstrapSteps(isCurrent: () => boolean, steps: Array<() => Promise<unknown>>) {
  for (const step of steps) {
    if (!isCurrent()) return false;
    try { await step(); }
    catch (error) {
      if (!isCurrent() && !isCurrentAuthenticationFailure(error)) return false;
      throw error;
    }
  }
  return isCurrent();
}

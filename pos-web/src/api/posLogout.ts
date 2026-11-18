// One revocation-only request, using the interceptor's current credential.
// A cached owner is never installed as a request bearer or domain fallback.
export function requestPosLogout(
  client: { post: (path: string, body?: unknown) => Promise<unknown> },
  includeCachedOwner: boolean,
  storage: Pick<Storage, "getItem"> = localStorage,
) {
  const owner = includeCachedOwner ? storage.getItem("token") : null;
  return client.post("/employees/session/logout", owner ? { cached_user_token: owner } : {});
}

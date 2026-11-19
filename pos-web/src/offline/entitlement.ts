const STORAGE_KEY = "apexpos_entitlement_snapshot_v1";
const ENTITLEMENT_ISSUER = "apexpos";
const ENTITLEMENT_AUDIENCE = "apexpos-pos-entitlement";
const ACCEPTED_STATUSES = new Set(["trial", "active", "grace_period"]);

const PUBLIC_KEYRING_JSON =
  (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
    ?.VITE_ENTITLEMENT_PUBLIC_KEYRING || "";

export type CachedEntitlementSnapshot = {
  company_id: string;
  status: string;
  plan?: string | null;
  writes_allowed: boolean;
  effective_until?: string | null;
  offline_grace_expires_at: string;
  snapshot_expires_at: string;
  snapshot_token: string;
  message?: string | null;
  updated_at: string;
};

export type EntitlementClaims = {
  sub: string;
  company_id: string;
  status: string;
  plan?: string | null;
  features?: Record<string,boolean>;
  limits?: Record<string,number|null>;
  offline_grace_expires_at: string;
  token_type: string;
  lease_nonce?: string;
  offline_actor?: {
    actor_type: string; actor_id: string; session_version: number;
    branch_id: string | null; device_id: string | null; assignment_revision: number | null;
    actions: Record<string, boolean>;
  };
  iat?: number;
  exp: number;
  iss?: string;
  aud?: string;
};

export type EntitlementFailureCategory =
  | "missing_snapshot" | "keyring_not_configured" | "malformed_token"
  | "algorithm_mismatch" | "type_mismatch" | "invalid_key_id"
  | "unknown_key_id" | "key_retired" | "legacy_not_configured"
  | "legacy_key_retired" | "invalid_signature" | "invalid_claims"
  | "invalid_token_type" | "company_mismatch" | "subscription_not_writable"
  | "snapshot_expired" | "offline_grace_expired" | "issued_in_future"
  | "token_lifetime_exceeded" | "offline_grace_exceeded"
  | "issuer_mismatch" | "audience_mismatch"
  | "offline_reconnect_required" | "offline_lease_expired" | "offline_clock_changed"
  | "offline_challenge_mismatch" | "offline_refresh_stale" | "offline_permission_required";

export type EntitlementKeyring = {
  version: 1;
  max_token_lifetime_seconds: number;
  max_offline_grace_seconds: number;
  keys: Array<{
    kid: string;
    public_key_pem: string;
    accept_until?: string | null;
  }>;
  legacy_no_kid?: { kid: string; accept_until: string } | null;
};

export type EntitlementVerificationResult =
  | { ok: true; claims: EntitlementClaims; kid: string; legacy: boolean }
  | { ok: false; category: EntitlementFailureCategory; kid?: string };

export type EntitlementRefreshFailure = {
  category: "authorization_rejected" | "temporary_unavailable" | "request_rejected";
  status?: number;
};

type EntitlementKeyringInput = EntitlementKeyring | string;
const KID_PATTERN = /^[A-Za-z0-9._-]{1,64}$/;

function decodeBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function decodeJsonPart(value: string): Record<string, unknown> | null {
  try {
    const parsed = JSON.parse(
      new TextDecoder().decode(decodeBase64Url(value)),
    ) as unknown;
    return parsed && typeof parsed === "object"
      ? (parsed as Record<string, unknown>) : null;
  } catch {
    return null;
  }
}

function normalizePublicKeyPem(pem: string): string {
  return pem.replace(/\\n/g, "\n").trim();
}

function pemToArrayBuffer(pem: string): ArrayBuffer {
  const base64 = normalizePublicKeyPem(pem)
    .replace(/-----BEGIN PUBLIC KEY-----/g, "")
    .replace(/-----END PUBLIC KEY-----/g, "")
    .replace(/\s+/g, "");
  const bytes = decodeBase64Url(base64.replace(/\+/g, "-").replace(/\//g, "_"));
  return bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
}

async function importVerificationKey(publicKeyPem: string) {
  const normalizedPem = normalizePublicKeyPem(publicKeyPem);
  if (!normalizedPem.includes("-----BEGIN PUBLIC KEY-----") ||
      normalizedPem.includes("PRIVATE KEY") || !globalThis.crypto?.subtle) {
    return null;
  }
  return globalThis.crypto.subtle.importKey(
    "spki", pemToArrayBuffer(normalizedPem),
    { name: "RSASSA-PKCS1-v1_5", hash: "SHA-256" }, false, ["verify"],
  );
}

function parseKeyring(input: EntitlementKeyringInput): EntitlementKeyring | null {
  try {
    const parsed = (
      typeof input === "string" ? JSON.parse(input) : input
    ) as EntitlementKeyring;
    if (!parsed || parsed.version !== 1 || !Array.isArray(parsed.keys) ||
        parsed.keys.length === 0 ||
        !Number.isInteger(parsed.max_token_lifetime_seconds) ||
        parsed.max_token_lifetime_seconds <= 0 ||
        !Number.isInteger(parsed.max_offline_grace_seconds) ||
        parsed.max_offline_grace_seconds <= 0) return null;
    const seen = new Set<string>();
    for (const key of parsed.keys) {
      const pem = normalizePublicKeyPem(key.public_key_pem);
      if (!KID_PATTERN.test(key.kid) || seen.has(key.kid) ||
          !pem.includes("-----BEGIN PUBLIC KEY-----") || pem.includes("PRIVATE KEY") ||
          (key.accept_until != null && !Number.isFinite(Date.parse(key.accept_until)))) {
        return null;
      }
      seen.add(key.kid);
    }
    if (parsed.legacy_no_kid) {
      const legacyKey = parsed.keys.find(
        (key) => key.kid === parsed.legacy_no_kid?.kid,
      );
      const legacyDeadline = Date.parse(parsed.legacy_no_kid.accept_until);
      if (!legacyKey || !Number.isFinite(legacyDeadline) ||
          (legacyKey.accept_until != null &&
           legacyDeadline > Date.parse(legacyKey.accept_until))) return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function failure(category: EntitlementFailureCategory, kid?: unknown): EntitlementVerificationResult {
  const safeKid = typeof kid === "string" && KID_PATTERN.test(kid) ? kid : undefined;
  console.warn("[entitlement] verification failed", {
    category, kid: safeKid || "none",
  });
  return { ok: false, category, ...(safeKid ? { kid: safeKid } : {}) };
}

function finiteTimestamp(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function entitlementReconnectMessage(category: EntitlementFailureCategory): string {
  if (category === "offline_permission_required") {
    return "Reconnect and sign in with an authorized device-bound employee PIN. Saved cashier permissions alone cannot authorize offline actions. Queued records are retained.";
  }
  if (category.startsWith("offline_")) {
    return "Reconnect to renew POS access. Offline access lasts at most four hours in this open window, ends on sign-out, and cannot be restored after reload. Queued sales are retained.";
  }

  if (["unknown_key_id", "key_retired", "legacy_key_retired"].includes(category)) {
    return "This POS authorization key has changed or retired. Reconnect and reload the POS to renew access.";
  }
  if (category === "legacy_not_configured") {
    return "This saved POS authorization is no longer supported. Reconnect and reload the POS.";
  }
  if (category === "snapshot_expired" || category === "offline_grace_expired") {
    return "Offline authorization has expired. Reconnect and reload the POS to renew the subscription snapshot.";
  }
  return "The saved POS authorization could not be verified. Reconnect and reload the POS.";
}

export function classifyEntitlementRefreshFailure(
  error: unknown,
): EntitlementRefreshFailure {
  const candidate = error && typeof error === "object"
    ? error as {
        code?: unknown;
        message?: unknown;
        response?: { status?: unknown };
      }
    : null;
  const rawStatus = candidate?.response?.status;
  const status = typeof rawStatus === "number" && Number.isInteger(rawStatus)
    ? rawStatus
    : undefined;

  if (status === 401 || status === 403) {
    return { category: "authorization_rejected", status };
  }
  if (
    status === 408 || status === 425 || status === 429 ||
    (status != null && status >= 500) ||
    (status == null && ["ERR_NETWORK", "ECONNABORTED", "ETIMEDOUT"]
      .includes(String(candidate?.code || ""))) ||
    (status == null && String(candidate?.message || "") === "Network Error")
  ) {
    return { category: "temporary_unavailable", ...(status == null ? {} : { status }) };
  }
  return { category: "request_rejected", ...(status == null ? {} : { status }) };
}

export function entitlementRefreshFailureMessage(
  failure: EntitlementRefreshFailure,
  hasVerifiedSnapshot: boolean,
): string {
  if (failure.category === "authorization_rejected") {
    return `Online authorization was rejected (HTTP ${failure.status}). Sign in again before continuing online.`;
  }
  if (failure.category === "temporary_unavailable" && hasVerifiedSnapshot) {
    return "Connection temporarily unavailable. The saved POS authorization is verified and remains subject to its four-hour open-window lease and signed expiry.";
  }
  if (failure.category === "temporary_unavailable") {
    return "Connection temporarily unavailable and no valid saved POS authorization is available.";
  }
  const statusSuffix = failure.status == null ? "" : ` (HTTP ${failure.status})`;
  return `POS authorization refresh was rejected${statusSuffix}. Reconnect or sign in again.`;
}

export async function verifyEntitlementSnapshotDetailed(
  snapshot: CachedEntitlementSnapshot | null,
  keyringInput: EntitlementKeyringInput = PUBLIC_KEYRING_JSON,
  now = Date.now(),
): Promise<EntitlementVerificationResult> {
  if (!snapshot) return failure("missing_snapshot");
  const keyring = parseKeyring(keyringInput);
  if (!keyring) return failure("keyring_not_configured");
  const parts = snapshot.snapshot_token.split(".");
  if (parts.length !== 3) return failure("malformed_token");
  const [encodedHeader, encodedPayload, encodedSignature] = parts;
  const header = decodeJsonPart(encodedHeader);
  if (!header) return failure("malformed_token");
  if (header.alg !== "RS256") return failure("algorithm_mismatch", header.kid);
  if (header.typ !== "JWT") return failure("type_mismatch", header.kid);

  const legacy = header.kid == null || header.kid === "";
  let kid: string;
  let legacyDeadline: number | null = null;
  if (legacy) {
    if (!keyring.legacy_no_kid) return failure("legacy_not_configured");
    kid = keyring.legacy_no_kid.kid;
    legacyDeadline = Date.parse(keyring.legacy_no_kid.accept_until);
    if (now > legacyDeadline) return failure("legacy_key_retired", kid);
  } else {
    if (typeof header.kid !== "string" || !KID_PATTERN.test(header.kid)) {
      return failure("invalid_key_id");
    }
    kid = header.kid;
  }
  const selectedKey = keyring.keys.find((key) => key.kid === kid);
  if (!selectedKey) return failure("unknown_key_id", kid);
  if (selectedKey.accept_until && now > Date.parse(selectedKey.accept_until)) {
    return failure("key_retired", kid);
  }

  let cryptoKey: CryptoKey | null;
  try { cryptoKey = await importVerificationKey(selectedKey.public_key_pem); }
  catch { cryptoKey = null; }
  if (!cryptoKey) return failure("keyring_not_configured", kid);
  let signatureValid = false;
  try {
    signatureValid = await globalThis.crypto.subtle.verify(
      "RSASSA-PKCS1-v1_5", cryptoKey, decodeBase64Url(encodedSignature),
      new TextEncoder().encode(`${encodedHeader}.${encodedPayload}`),
    );
  } catch { signatureValid = false; }
  if (!signatureValid) return failure("invalid_signature", kid);

  const rawClaims = decodeJsonPart(encodedPayload);
  if (!rawClaims) return failure("invalid_claims", kid);
  const claims = rawClaims as unknown as EntitlementClaims;
  if (claims.token_type !== "entitlement") return failure("invalid_token_type", kid);
  if (!claims.company_id || claims.company_id !== snapshot.company_id ||
      claims.sub !== claims.company_id) return failure("company_mismatch", kid);
  if (!ACCEPTED_STATUSES.has(claims.status)) {
    return failure("subscription_not_writable", kid);
  }
  const expirySeconds = finiteTimestamp(claims.exp);
  const graceMilliseconds = Date.parse(claims.offline_grace_expires_at);
  if (expirySeconds == null || !Number.isFinite(graceMilliseconds)) {
    return failure("invalid_claims", kid);
  }
  if (now > expirySeconds * 1000) return failure("snapshot_expired", kid);
  if (now > graceMilliseconds) return failure("offline_grace_expired", kid);

  if (!legacy) {
    const issuedSeconds = finiteTimestamp(claims.iat);
    if (issuedSeconds == null) return failure("invalid_claims", kid);
    if (issuedSeconds * 1000 > now + 60_000) return failure("issued_in_future", kid);
    if (expirySeconds <= issuedSeconds ||
        expirySeconds - issuedSeconds > keyring.max_token_lifetime_seconds) {
      return failure("token_lifetime_exceeded", kid);
    }
    if (graceMilliseconds <= issuedSeconds * 1000 ||
        graceMilliseconds - issuedSeconds * 1000 >
          keyring.max_offline_grace_seconds * 1000) {
      return failure("offline_grace_exceeded", kid);
    }
    if (claims.iss !== ENTITLEMENT_ISSUER) return failure("issuer_mismatch", kid);
    if (claims.aud !== ENTITLEMENT_AUDIENCE) return failure("audience_mismatch", kid);
  } else if (legacyDeadline == null || now > legacyDeadline) {
    return failure("legacy_key_retired", kid);
  }
  return { ok: true, claims, kid, legacy };
}

export function saveEntitlementSnapshot(snapshot: CachedEntitlementSnapshot) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
}

export function loadEntitlementSnapshot(companyId: string): CachedEntitlementSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as CachedEntitlementSnapshot;
    if (!parsed?.company_id || parsed.company_id !== companyId || !parsed.snapshot_token) {
      return null;
    }
    return parsed;
  } catch { return null; }
}

export async function verifyEntitlementSnapshot(
  snapshot: CachedEntitlementSnapshot | null,
  keyringInput: EntitlementKeyringInput = PUBLIC_KEYRING_JSON,
  now = Date.now(),
): Promise<EntitlementClaims | null> {
  const result = await verifyEntitlementSnapshotDetailed(snapshot, keyringInput, now);
  return result.ok ? result.claims : null;
}

export async function isEntitlementSnapshotUsable(
  snapshot: CachedEntitlementSnapshot | null,
  keyringInput: EntitlementKeyringInput = PUBLIC_KEYRING_JSON,
  now = Date.now(),
): Promise<boolean> {
  return (await verifyEntitlementSnapshotDetailed(snapshot, keyringInput, now)).ok;
}

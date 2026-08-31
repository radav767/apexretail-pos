const STORAGE_KEY = "apexpos_entitlement_snapshot_v1";

const PUBLIC_KEY_PEM =
  (import.meta as ImportMeta & {
    env?: Record<string, string | undefined>;
  }).env?.VITE_ENTITLEMENT_PUBLIC_KEY || "";

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

type EntitlementClaims = {
  company_id: string;
  status: string;
  plan?: string | null;
  offline_grace_expires_at: string;
  token_type: string;
  exp: number;
};

function decodeBase64Url(value: string): Uint8Array<ArrayBuffer> {
  const normalized = value.replace(/-/g, "+").replace(/_/g, "/");
  const padded =
    normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  const binary = atob(padded);
  const bytes = new Uint8Array(new ArrayBuffer(binary.length));
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function normalizePublicKeyPem(pem: string): string {
  return pem.replace(/\\n/g, "\n").trim();
}

function pemToArrayBuffer(pem: string): ArrayBuffer {
  const base64 = normalizePublicKeyPem(pem)
    .replace(/-----BEGIN PUBLIC KEY-----/g, "")
    .replace(/-----END PUBLIC KEY-----/g, "")
    .replace(/\s+/g, "");
  const bytes = decodeBase64Url(
    base64.replace(/\+/g, "-").replace(/\//g, "_"),
  );
  return bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  );
}

async function importVerificationKey(publicKeyPem: string) {
  const normalizedPem = normalizePublicKeyPem(publicKeyPem);
  if (!normalizedPem || !globalThis.crypto?.subtle) {
    return null;
  }
  return globalThis.crypto.subtle.importKey(
    "spki",
    pemToArrayBuffer(normalizedPem),
    {
      name: "RSASSA-PKCS1-v1_5",
      hash: "SHA-256",
    },
    false,
    ["verify"],
  );
}

async function verifyJwt(
  token: string,
  publicKeyPem: string,
): Promise<EntitlementClaims | null> {
  const parts = token.split(".");
  if (parts.length !== 3) {
    return null;
  }
  const [header, payload, signature] = parts;
  let key: CryptoKey | null;
  try {
    key = await importVerificationKey(publicKeyPem);
  } catch {
    return null;
  }
  if (!key) {
    return null;
  }
  const valid = await globalThis.crypto.subtle.verify(
    "RSASSA-PKCS1-v1_5",
    key,
    decodeBase64Url(signature),
    new TextEncoder().encode(`${header}.${payload}`),
  );
  if (!valid) {
    return null;
  }
  try {
    const claims = JSON.parse(
      new TextDecoder().decode(decodeBase64Url(payload)),
    ) as EntitlementClaims;
    if (claims.token_type !== "entitlement") {
      return null;
    }
    return claims;
  } catch {
    return null;
  }
}

export function saveEntitlementSnapshot(
  snapshot: CachedEntitlementSnapshot,
) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(snapshot));
}

export function loadEntitlementSnapshot(
  companyId: string,
): CachedEntitlementSnapshot | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as CachedEntitlementSnapshot;
    if (!parsed?.company_id || parsed.company_id !== companyId) {
      return null;
    }
    if (!parsed.snapshot_token) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export async function verifyEntitlementSnapshot(
  snapshot: CachedEntitlementSnapshot | null,
  publicKeyPem = PUBLIC_KEY_PEM,
): Promise<EntitlementClaims | null> {
  if (!snapshot) {
    return null;
  }
  const claims = await verifyJwt(
    snapshot.snapshot_token,
    publicKeyPem,
  );
  if (!claims) {
    return null;
  }
  if (claims.company_id !== snapshot.company_id) {
    return null;
  }
  return claims;
}

export async function isEntitlementSnapshotUsable(
  snapshot: CachedEntitlementSnapshot | null,
  publicKeyPem = PUBLIC_KEY_PEM,
  now = Date.now(),
): Promise<boolean> {
  if (!snapshot) {
    return false;
  }
  const claims = await verifyEntitlementSnapshot(
    snapshot,
    publicKeyPem,
  );
  if (!claims) {
    return false;
  }
  if (!["trial", "active", "grace_period"].includes(claims.status)) {
    return false;
  }
  return (
    now <= claims.exp * 1000 &&
    now <= new Date(claims.offline_grace_expires_at).getTime()
  );
}

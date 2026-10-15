import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import test from "node:test";

import {
  classifyEntitlementRefreshFailure,
  entitlementReconnectMessage,
  entitlementRefreshFailureMessage,
  type CachedEntitlementSnapshot,
  type EntitlementKeyring,
  isEntitlementSnapshotUsable,
  verifyEntitlementSnapshotDetailed,
} from "../src/offline/entitlement.ts";

function keypair() {
  return generateKeyPairSync("rsa", {
    modulusLength: 2048,
    publicKeyEncoding: { type: "spki", format: "pem" },
    privateKeyEncoding: { type: "pkcs8", format: "pem" },
  });
}

const oldKeys = keypair();
const newKeys = keypair();
const companyId = "3c76516a-09f6-4735-8ac2-e9974f22395e";
const otherCompanyId = "3f7a7a91-9f77-43ed-abfb-ec5382cff475";
const now = Date.UTC(2026, 7, 31, 12, 0, 0);
const nowSeconds = now / 1000;

const keyring: EntitlementKeyring = {
  version: 1,
  max_token_lifetime_seconds: 43_200,
  max_offline_grace_seconds: 259_200,
  keys: [
    {
      kid: "legacy-2026",
      public_key_pem: oldKeys.publicKey,
      accept_until: "2026-09-01T12:00:00.000Z",
    },
    { kid: "active-2026", public_key_pem: newKeys.publicKey },
  ],
  legacy_no_kid: {
    kid: "legacy-2026",
    accept_until: "2026-08-31T18:00:00.000Z",
  },
};

function base64Url(value: string | Buffer): string {
  return Buffer.from(value).toString("base64url");
}

function claims(overrides: Record<string, unknown> = {}) {
  return {
    sub: companyId,
    company_id: companyId,
    status: "active",
    plan: "monthly",
    offline_grace_expires_at: "2026-09-02T12:00:00.000Z",
    token_type: "entitlement",
    iat: nowSeconds,
    exp: nowSeconds + 3600,
    iss: "apexpos",
    aud: "apexpos-pos-entitlement",
    ...overrides,
  };
}

function createToken({
  privateKey = newKeys.privateKey,
  kid = "active-2026",
  algorithm = "RS256",
  payload = claims(),
}: {
  privateKey?: string;
  kid?: string | null;
  algorithm?: string;
  payload?: Record<string, unknown>;
} = {}): string {
  const header = base64Url(JSON.stringify({
    alg: algorithm,
    typ: "JWT",
    ...(kid == null ? {} : { kid }),
  }));
  const encodedPayload = base64Url(JSON.stringify(payload));
  const signingInput = `${header}.${encodedPayload}`;
  const signature = sign("RSA-SHA256", Buffer.from(signingInput), privateKey);
  return `${signingInput}.${base64Url(signature)}`;
}

function snapshot(token: string, company = companyId): CachedEntitlementSnapshot {
  return {
    company_id: company,
    status: "active",
    plan: "monthly",
    writes_allowed: true,
    offline_grace_expires_at: "2026-09-02T12:00:00.000Z",
    snapshot_expires_at: "2026-08-31T13:00:00.000Z",
    snapshot_token: token,
    updated_at: "2026-08-31T12:00:00.000Z",
  };
}

async function category(value: CachedEntitlementSnapshot, at = now) {
  const result = await verifyEntitlementSnapshotDetailed(value, keyring, at);
  assert.equal(result.ok, false);
  return result.ok ? "" : result.category;
}

test("accepts valid active and old kid signatures", async () => {
  assert.equal(await isEntitlementSnapshotUsable(snapshot(createToken()), keyring, now), true);
  const old = createToken({ privateKey: oldKeys.privateKey, kid: "legacy-2026" });
  const result = await verifyEntitlementSnapshotDetailed(snapshot(old), keyring, now);
  assert.equal(result.ok, true);
  if (result.ok) assert.equal(result.kid, "legacy-2026");
});

test("legacy no-kid snapshots use only the designated key and deadline", async () => {
  const legacyClaims: Record<string, unknown> = claims();
  delete legacyClaims.iat;
  delete legacyClaims.iss;
  delete legacyClaims.aud;
  const token = createToken({
    privateKey: oldKeys.privateKey, kid: null, payload: legacyClaims,
  });
  const valid = await verifyEntitlementSnapshotDetailed(snapshot(token), keyring, now);
  assert.equal(valid.ok, true);
  if (valid.ok) assert.equal(valid.legacy, true);
  assert.equal(await category(snapshot(token), Date.UTC(2026, 7, 31, 18, 0, 1)),
    "legacy_key_retired");
});

test("unknown kid, algorithm confusion and tampering fail closed", async () => {
  assert.equal(await category(snapshot(createToken({ kid: "unknown-2026" }))),
    "unknown_key_id");
  assert.equal(await category(snapshot(createToken({ algorithm: "HS256" }))),
    "algorithm_mismatch");
  const parts = createToken().split(".");
  parts[2] = `${parts[2][0] === "A" ? "B" : "A"}${parts[2].slice(1)}`;
  assert.equal(await category(snapshot(parts.join("."))), "invalid_signature");
});

test("expiry, offline grace, long-lived claims and company mismatch fail", async () => {
  assert.equal(await category(snapshot(createToken({
    payload: claims({ exp: nowSeconds - 1 }),
  }))), "snapshot_expired");
  assert.equal(await category(snapshot(createToken({
    payload: claims({ exp: nowSeconds + 86_400 }),
  }))), "token_lifetime_exceeded");
  assert.equal(await category(snapshot(createToken({
    payload: claims({ offline_grace_expires_at: "2026-10-01T12:00:00.000Z" }),
  }))), "offline_grace_exceeded");
  assert.equal(await category(snapshot(createToken({
    payload: claims({ offline_grace_expires_at: "2026-08-31T11:59:59.000Z" }),
  }))), "offline_grace_expired");
  assert.equal(await category(snapshot(createToken(), otherCompanyId)), "company_mismatch");
});

test("fractional grace beyond the signed maximum fails closed", async () => {
  const fractionallyOversizedGrace = new Date(
    now + keyring.max_offline_grace_seconds * 1000 + 123,
  ).toISOString();
  assert.equal(await category(snapshot(createToken({
    payload: claims({ offline_grace_expires_at: fractionallyOversizedGrace }),
  }))), "offline_grace_exceeded");
});

test("retired key and refresh/reconnect guidance are explicit", async () => {
  const retiredRing: EntitlementKeyring = {
    ...keyring,
    keys: keyring.keys.map((key) => key.kid === "active-2026"
      ? { ...key, accept_until: "2026-08-31T11:59:59.000Z" } : key),
  };
  const result = await verifyEntitlementSnapshotDetailed(
    snapshot(createToken()), retiredRing, now,
  );
  assert.equal(result.ok, false);
  if (!result.ok) {
    assert.equal(result.category, "key_retired");
    assert.match(entitlementReconnectMessage(result.category), /Reconnect and reload/i);
  }
});

test("refresh failures distinguish rejected credentials from temporary outages", () => {
  const expired = classifyEntitlementRefreshFailure({ response: { status: 401 } });
  const revoked = classifyEntitlementRefreshFailure({ response: { status: 403 } });
  const offline = classifyEntitlementRefreshFailure({ code: "ERR_NETWORK" });
  const timeout = classifyEntitlementRefreshFailure({ code: "ECONNABORTED" });
  const unavailable = classifyEntitlementRefreshFailure({ response: { status: 503 } });

  assert.deepEqual(expired, { category: "authorization_rejected", status: 401 });
  assert.deepEqual(revoked, { category: "authorization_rejected", status: 403 });
  assert.deepEqual(offline, { category: "temporary_unavailable" });
  assert.deepEqual(timeout, { category: "temporary_unavailable" });
  assert.deepEqual(unavailable, { category: "temporary_unavailable", status: 503 });
  assert.match(entitlementRefreshFailureMessage(expired, false), /HTTP 401/);
  assert.match(entitlementRefreshFailureMessage(offline, true), /saved POS authorization is verified/i);
  assert.match(entitlementRefreshFailureMessage(offline, false), /no valid saved/i);
});

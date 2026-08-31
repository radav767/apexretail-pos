import assert from "node:assert/strict";
import { generateKeyPairSync, sign } from "node:crypto";
import test from "node:test";

import {
  type CachedEntitlementSnapshot,
  isEntitlementSnapshotUsable,
  verifyEntitlementSnapshot,
} from "../src/offline/entitlement.ts";

const { publicKey, privateKey } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
  publicKeyEncoding: { type: "spki", format: "pem" },
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
});

const companyId = "3c76516a-09f6-4735-8ac2-e9974f22395e";
const now = Date.UTC(2026, 7, 31, 12, 0, 0);

function base64Url(value: string | Buffer): string {
  return Buffer.from(value).toString("base64url");
}

function createToken(exp: number): string {
  const header = base64Url(
    JSON.stringify({ alg: "RS256", typ: "JWT" }),
  );
  const payload = base64Url(
    JSON.stringify({
      company_id: companyId,
      status: "active",
      plan: "monthly",
      offline_grace_expires_at: "2026-09-02T12:00:00.000Z",
      token_type: "entitlement",
      exp,
    }),
  );
  const signingInput = `${header}.${payload}`;
  const signature = sign("RSA-SHA256", Buffer.from(signingInput), privateKey);
  return `${signingInput}.${base64Url(signature)}`;
}

function createSnapshot(token: string): CachedEntitlementSnapshot {
  return {
    company_id: companyId,
    status: "active",
    plan: "monthly",
    writes_allowed: true,
    offline_grace_expires_at: "2026-09-02T12:00:00.000Z",
    snapshot_expires_at: "2026-09-02T12:00:00.000Z",
    snapshot_token: token,
    updated_at: "2026-08-31T12:00:00.000Z",
  };
}

test("accepts a valid signed entitlement with multiline PEM", async () => {
  const snapshot = createSnapshot(createToken(now / 1000 + 3600));
  const escapedMultilinePublicKey = publicKey.replace(/\n/g, "\\n");

  const claims = await verifyEntitlementSnapshot(
    snapshot,
    escapedMultilinePublicKey,
  );

  assert.equal(claims?.company_id, companyId);
  assert.equal(
    await isEntitlementSnapshotUsable(snapshot, publicKey, now),
    true,
  );
});

test("rejects an expired entitlement for offline use", async () => {
  const snapshot = createSnapshot(createToken(now / 1000 - 1));

  assert.equal(
    await isEntitlementSnapshotUsable(snapshot, publicKey, now),
    false,
  );
});

test("rejects an invalid entitlement signature", async () => {
  const snapshot = createSnapshot(createToken(now / 1000 + 3600));
  const tokenParts = snapshot.snapshot_token.split(".");
  tokenParts[2] = `${tokenParts[2][0] === "A" ? "B" : "A"}${tokenParts[2].slice(1)}`;
  snapshot.snapshot_token = tokenParts.join(".");

  assert.equal(
    await verifyEntitlementSnapshot(snapshot, publicKey),
    null,
  );
});

test("rejects verification when the public key is missing", async () => {
  const snapshot = createSnapshot(createToken(now / 1000 + 3600));

  assert.equal(await verifyEntitlementSnapshot(snapshot, ""), null);
});

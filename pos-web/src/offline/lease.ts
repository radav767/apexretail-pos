import {
  entitlementReconnectMessage,
  loadEntitlementSnapshot,
  verifyEntitlementSnapshotDetailed,
  type CachedEntitlementSnapshot,
  type EntitlementFailureCategory,
  type EntitlementKeyring,
  type EntitlementVerificationResult,
} from "./entitlement.ts";

export const MAX_DISCONNECTED_MS = 4 * 60 * 60 * 1000;
const MAX_RESPONSE_MS = 60_000;
const CLOCK_TOLERANCE_MS = 60_000;
type Clock = () => { monotonic: number; wall: number };
type Challenge = { companyId: string; nonce: string; monotonic: number; wall: number; identity: string };
type Anchor = Challenge & { token: string; serverTime: number };
const browserClock: Clock = () => ({ monotonic: performance.now(), wall: Date.now() });
const authKeys = ["company_id", "token", "employee_id", "employee_token", "device_id", "device_key", "branch_id"];
const browserIdentity = () => JSON.stringify(authKeys.map(key => localStorage.getItem(key)));
const denied = (category: EntitlementFailureCategory): EntitlementVerificationResult => ({ ok: false, category });

// Memory only. Restoring localStorage, a cached JWT or an old Challenge cannot
// re-create an anchor after reload. This is a bounded browser policy, not a
// claim of tamper-resistant hardware or immediate disconnected revocation.
export class OfflineLease {
  private anchor: Anchor | null = null;
  private pending: Challenge | null = null;
  private clock: Clock;
  private keyring?: EntitlementKeyring | string;
  private identity: () => string;
  constructor(clock: Clock = browserClock, keyring?: EntitlementKeyring | string,
              identity: () => string = browserIdentity) {
    this.clock = clock; this.keyring = keyring; this.identity = identity;
  }

  beginRefresh(companyId: string): Challenge {
    const challenge = { companyId, nonce: crypto.randomUUID(), identity: this.identity(), ...this.clock() };
    this.pending = challenge;
    return challenge;
  }

  invalidate() { this.anchor = null; this.pending = null; }

  private elapsed(anchor: Challenge): number | null {
    if (anchor.identity !== this.identity()) return null;
    const clock = this.clock();
    const monotonic = clock.monotonic - anchor.monotonic;
    const wall = clock.wall - anchor.wall;
    if (![clock.monotonic, clock.wall, monotonic, wall].every(Number.isFinite) ||
        monotonic < 0 || wall < -CLOCK_TOLERANCE_MS ||
        Math.abs(wall - monotonic) > CLOCK_TOLERANCE_MS) return null;
    // Wall time covers platforms that pause performance.now() during sleep;
    // monotonic time prevents wall rollback from extending the lease.
    return Math.max(monotonic, wall, 0);
  }

  async acceptOnline(snapshot: CachedEntitlementSnapshot, challenge: Challenge): Promise<EntitlementVerificationResult> {
    if (this.pending !== challenge) return denied("offline_refresh_stale");
    const elapsed = this.elapsed(challenge);
    if (elapsed === null || elapsed > MAX_RESPONSE_MS) {
      this.invalidate(); return denied("offline_clock_changed");
    }
    // Use the claimed server instant ONLY for signature/claim verification.
    // It becomes trusted only after RSA verification and a match to the fresh
    // unpredictable challenge still pending in this document.
    let issued: unknown;
    try {
      const encoded = snapshot.snapshot_token.split(".")[1];
      issued = JSON.parse(atob(encoded.replace(/-/g, "+").replace(/_/g, "/"))).iat;
    } catch { this.invalidate(); return denied("malformed_token"); }
    if (typeof issued !== "number" || !Number.isFinite(issued)) {
      this.invalidate(); return denied("invalid_claims");
    }
    const verified = await verifyEntitlementSnapshotDetailed(snapshot, this.keyring, issued * 1000 + elapsed);
    if (this.pending !== challenge) return denied("offline_refresh_stale");
    if (!verified.ok) { this.invalidate(); return verified; }
    if (verified.legacy || verified.claims.lease_nonce !== challenge.nonce || snapshot.company_id !== challenge.companyId) {
      this.invalidate(); return denied("offline_challenge_mismatch");
    }
    const finalElapsed = this.elapsed(challenge);
    if (finalElapsed === null || finalElapsed > MAX_RESPONSE_MS) {
      this.invalidate(); return denied("offline_clock_changed");
    }
    this.anchor = { ...challenge, token: snapshot.snapshot_token, serverTime: issued * 1000 };
    this.pending = null;
    return verified;
  }

  async verify(snapshot: CachedEntitlementSnapshot | null): Promise<EntitlementVerificationResult> {
    const anchor = this.anchor;
    if (!anchor || !snapshot || anchor.companyId !== snapshot.company_id || anchor.token !== snapshot.snapshot_token) {
      return denied("offline_reconnect_required");
    }
    const elapsed = this.elapsed(anchor);
    if (elapsed === null) { this.invalidate(); return denied("offline_clock_changed"); }
    if (elapsed >= MAX_DISCONNECTED_MS) { this.invalidate(); return denied("offline_lease_expired"); }
    const verified = await verifyEntitlementSnapshotDetailed(snapshot, this.keyring, anchor.serverTime + elapsed);
    if (this.anchor !== anchor) return denied("offline_reconnect_required");
    // Recheck elapsed after async cryptography; no crossing the lease boundary.
    const after = this.elapsed(anchor);
    if (after === null) { this.invalidate(); return denied("offline_clock_changed"); }
    if (after >= MAX_DISCONNECTED_MS) { this.invalidate(); return denied("offline_lease_expired"); }
    if (verified.ok && anchor.serverTime + after >= verified.claims.exp * 1000) {
      this.invalidate(); return denied("snapshot_expired");
    }
    if (verified.ok && anchor.serverTime + after >= Date.parse(verified.claims.offline_grace_expires_at)) {
      this.invalidate(); return denied("offline_grace_expired");
    }
    if (!verified.ok) this.invalidate();
    return verified;
  }
}

export const offlineLease = new OfflineLease();
const channel = typeof window !== "undefined" && typeof BroadcastChannel !== "undefined"
  ? new BroadcastChannel("apexpos-offline-lease") : null;
if (channel) channel.onmessage = () => offlineLease.invalidate();
if (typeof window !== "undefined") window.addEventListener("storage", event => {
  if (event.key === null || authKeys.includes(event.key)) offlineLease.invalidate();
});
export function invalidateOfflineLease() {
  offlineLease.invalidate();
  channel?.postMessage({ type: "invalidate" });
}

export async function requireOfflineAccess(companyId: string, features: string[] = []) {
  const result = await offlineLease.verify(loadEntitlementSnapshot(companyId));
  if (!result.ok) throw new Error(entitlementReconnectMessage(result.category));
  if (result.claims.features !== undefined && features.some(feature => result.claims.features?.[feature] !== true)) {
    throw new Error("Your subscription does not include this offline operation. Original queued records are retained.");
  }
  return result.claims;
}

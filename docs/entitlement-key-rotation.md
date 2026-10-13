# Entitlement signing-key rotation

Entitlement snapshots use RS256. Newly issued snapshots carry a `kid` header and
are accepted only when that exact ID exists in the public verification keyring.
The backend and POS use the same public-only JSON keyring.

## Keyring format

```json
{
  "version": 1,
  "max_token_lifetime_seconds": 43200,
  "max_offline_grace_seconds": 259200,
  "keys": [
    {
      "kid": "legacy-date",
      "public_key_pem": "PUBLIC PEM CONTENT",
      "accept_until": "UTC ISO-8601 DEADLINE"
    },
    {
      "kid": "active-date",
      "public_key_pem": "PUBLIC PEM CONTENT"
    }
  ],
  "legacy_no_kid": {
    "kid": "legacy-date",
    "accept_until": "UTC ISO-8601 DEADLINE"
  }
}
```

The legacy policy is optional. If present, its deadline is mandatory and may
not exceed the designated key's deadline. A token with an unknown `kid`, or a
no-`kid` token after the legacy deadline, fails closed. New tokens are also
bounded by trusted maximum token and offline-grace lifetimes; their claims
cannot extend those limits.

## Runtime configuration

- `ENTITLEMENT_ACTIVE_KEY_ID`: key used for new snapshots.
- `ENTITLEMENT_PUBLIC_KEYRING_FILE`: protected configuration path containing
  only public keys.
- `ENTITLEMENT_SIGNING_KEY_FILE`: mode-600 private-key file outside source and
  web roots.
- `ENTITLEMENT_SIGNING_KEY_CREDENTIAL`: preferred systemd credential filename.
  When set, it is loaded only beneath `$CREDENTIALS_DIRECTORY`.

The old inline `ENTITLEMENT_PRIVATE_KEY` remains a deprecated compatibility
input, but must not be used for the final rotation. Never place a private key in
the keyring, a Vite variable, source control, a build directory, logs, or an
operator transcript.

## POS browser and offline compatibility

Deploy the public-only old/new keyring in the POS browser bundle before the
backend begins signing with the replacement key. Existing browser tabs may
continue running a cached bundle that knows only the old public key, so terminals
must reconnect and reload during the controlled compatibility window. The POS
must never download a private key or accept a key supplied by a JWT header.

Previously cached no-`kid` snapshots remain usable only with the explicitly
designated legacy public key and only until the configured legacy deadline.
Offline terminals that do not reload before that deadline fail closed: financial
writes remain unavailable until the terminal reconnects and receives both the
current browser assets and a newly signed snapshot. Queued sales already created
under a valid snapshot retain their existing synchronization behavior; rotation
does not rewrite or re-sign queued payloads.

## Staged deployment and rotation

Because the previous signing key is considered compromised, the compatibility
period is an exposure window, not a normal long-lived migration. Keep it as
short as operationally feasible (recommended hours, never days):

1. Generate synthetic keys for rehearsal. Validate old/new/no-`kid` behavior in
   disposable environments.
2. During a controlled maintenance window, generate the replacement production
   key in the secret manager or protected credential location. Do not display
   or export it.
3. Build the POS with a public-only keyring containing old and new public keys,
   an explicit short legacy deadline, and the same old-key retirement deadline.
4. Deploy backend compatibility code and the POS verifier together. Initially,
   if unavoidable, the backend may still sign with the old key for only the time
   needed for clients to load the compatible POS. This step remains risky: an
   attacker with the compromised key can forge snapshots until the deadline.
5. As soon as compatibility assets are live, switch
   `ENTITLEMENT_ACTIVE_KEY_ID` and the protected signing credential to the new
   key, then restart only the backend. Confirm all newly issued JWT headers use
   the new `kid`; do not sign another token with the old key.
6. After the shortest feasible reconnect window, remove `legacy_no_kid`, remove
   the old public key, rebuild/redeploy the POS, and retain non-sensitive counts
   of verification failure categories. Offline devices that missed the window
   must reconnect and reload.
7. Revoke access to the old private key in the secret store and follow the
   incident-response retention policy. Do not delete audit evidence.

Recovery after signing-key rotation is forward-only. Rollback must never restore
the compromised signer or extend an expired legacy deadline. If the new signer
fails, fix its protected credential/keyring match or issue another new key. A
frontend rollback is safe only to a build that trusts the new key and preserves
the same or stricter retirement deadline.

## Validation and telemetry

Telemetry contains only a validated key ID, whether the legacy path was used,
and a fixed failure category. JWTs, claims, public-key bodies, private keys, and
secret paths are never logged. Acceptance tests cover algorithm confusion,
signature tampering, company mismatch, expiry, offline grace, forged long-lived
claims, and key retirement.

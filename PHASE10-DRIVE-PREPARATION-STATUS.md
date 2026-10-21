# Google Drive encrypted backup readiness — 21 October 2026

PREPARATION ONLY. Existing ApexRetail application/VPS; no activation authorized.

## Confirmed current state

- rclone Ubuntu package1.53.3-4ubuntu1.22.04.5, reports v1.53.3-DEV.
- Owner reports Google project ApexRetail POS Backups, Drive API enabled,
  Desktop OAuth client created, scope drive.file. Those console settings have
  not been independently inspected; no credentials requested or used here.
- Intended private config /etc/apexretail/drive/rclone.conf is ABSENT.
  Intended remote apexretail_drive is not configured there. Google connection,
  account identity, token refresh and folder access are NOT verified.
- Protected production encryption, destination and activation configs are absent:
  /etc/apexretail/backup.json, backup-offserver.json, backup-activation.json.
- Existing backup timer remains daily02:00UTC (04:00 Zimbabwe). Existing script
  targets apexretail_pos but still makes plaintext SQL; stale app-copy paths and
  failure masking mean timer success alone is insufficient backup verification.
- Backup script/service/timer hashes unchanged. No history deleted/modified.
- API healthy; POS/Backoffice200; API/Nginx/watchdog/backup timer active.

## Existing implementation reused, not rebuilt

backup_proposal.py: read-only custom PostgreSQL dump streamed into GPG before
network transfer; approved public-key-only keyring, recipient verification,
private files, both child exit statuses, ciphertext SHA256 and atomic publication.
backup_drive.py: pinned dedicated folder and drive.file scope; credential file
outside Git, no inherited token overrides, no child credential output, TLS
validation, fresh copy-only upload destinations, manifest last, full encrypted
archive and metadata download/readback comparison. No delete/sync/purge calls.
backup_schedule.py: rejects missing/changed authorization, recipient or actual
off-server/full-restore approval BEFORE dumping; not installed/activated.
backup_safety.py:30day retention planning available, protects recent verified
points, skips unknown/legacy/failed/corrupt files. Planner performs NO deletion.

Recorded18 focused tests passed in Step2, including real disposable GPG roundtrip,
missing-private-key and corruption rejection, simulated Drive full readback and
authorization/retention gates. Runtime unchanged; not rerun for this documentation/
Git-exclusion-only preparation. Previous real-dump disposable-key PostgreSQL
restore preserved34tables/890rows and original hashes/financial controls/ACLs.
None of this is a real Google upload or real owner-key recovery acceptance.

## Private owner authentication — next blocking action

Since the Google OAuth project/client already exists, do NOT create another one.
Use the existing own Desktop client and drive.file scope. Enter client details
only in a private terminal, never Codex tools/chat, screenshots, shell arguments
or recorded sessions. Do not use config show/dump or post a token/config file.

From a NEW LOCAL Termux session on Android (not an existing VPS shell):

```sh
ssh -o ExitOnForwardFailure=yes -L 127.0.0.1:53682:127.0.0.1:53682 root@187.77.179.100
```

Inside that PRIVATE SSH session:

```sh
umask 077
install -d -o root -g root -m 700 /etc/apexretail/drive
rclone config --config /etc/apexretail/drive/rclone.conf
```

Select New remote apexretail_drive, storage drive, own Desktop client details,
scope drive.file, blank service-account and initial root-folder settings, and
YES to auto config. Open its displayed localhost link privately in Chrome on
the SAME phone; approve expected permissions for prophetdavie@gmail.com. This
is an SSH-forwarded loopback flow, not a public authentication endpoint. Cancel
if unexpected scopes/account or a rejected legacy flow appears. No unattended
authorization or copying tokens into chat. After confirmation, quit the wizard,
chmod600 the dedicated config, and close the tunnel. If the file/remote already
exists when you perform this, STOP rather than overwrite it.

Report ONLY OAuth completed or a sanitized non-secret error. Existing installed
options support this method; actual Google interoperability is pending. Review
consent grant lifetime; do not enable jobs on an unaccepted7day Testing grant.

## Remaining gates / exact owner decisions

1. Complete the private consent above. Then approve credential-based read-only
   checks of intended account, granted scope, folder/quota and token refresh.
   Create/authorize the exact ApexRetail-POS-Secure-Backups folder with this client
   and pin its ID. A pre-existing browser-created folder may not be visible to
   drive.file; do not widen scope or create duplicates silently.
2. Nominate encryption/recovery custodian and independently held private-key
   escrow. Provide verified PUBLIC key/fingerprint through a protected channel.
   Private key/passphrase must be independently recoverable if VPS/phone is lost,
   not in scheduler, source tree, chat or same Drive backup folder. Keep old keys
   for retained historical archives. Real production key provisioning pending.
3. Approve one consistent read-only production dump → encryption → Google upload
   → independent retrieval → custodian-key full restore into an approved isolated
   target. Never production. Verify trusted hashes, native-currency financial
   controls/stock/shift/owner/ACL baselines and measure recovery time. No such
   production read/upload/restore is executed by this preparation.
4. Approve daily02:00UTC,30days for NEW verified encrypted archives; preserve all
   existing history. Cleanup execution is not implemented/approved by this plan.
   Fail-safe holds may retain files longer; do not use recursive age-only deletion.
5. Select monitored alert channel/contact: immediate failed-job notification,
   stale off-server success warning26hours/critical48hours, disk/quota/grant/key
   monitoring. No alert delivery is configured or claimed working yet.
6. Name monthly recovery operator and reminder contact. Proposed first Tuesday
   monthly10:00UTC/12:00 Zimbabwe, plus schema/key/storage changes: independent
   retrieval, private key on recovery environment only, full isolated restore,
   recorded original-data comparisons. No monthly service/timer installed.
7. Only AFTER real recovery/monitoring acceptance, approve the exact existing
   service replacement and protected activation receipt. Existing timer stays
   unchanged; no duplicate schedule. Separate approval for any cleanup execution.

## Security/production boundary

Production backup credentials belong under /etc/apexretail, outside Git/web roots.
Added explicit Git exclusions for common real OAuth/rclone/private-key files and
runtime backup JSON, while credential-free example files remain tracked. Ignore
rules are a guardrail, not a substitute for protected storage/review (git add -f
could bypass them). No actual secret is added by this work; never force-add it.

No production database records/schema, existing configurations, job schedules,
application releases, APKs, Nginx, Super Admin login or services were changed.
No Google calls, live credentials, uploads, private-key provisioning or new
recovery database. Stopped at owner-interactive authorization boundary.

Readiness: local software mechanism verified; OAuth, production encryption,
off-server recovery, monitoring and activation PENDING. Current production
routine backups are NOT encrypted or replicated by this prepared adapter.

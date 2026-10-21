# Google Drive encrypted backups — owner authorization and acceptance

21 October2026. Existing ApexRetail project, one Hostinger VPS. PREPARED ONLY.
Owner approved account: prophetdavie@gmail.com.
Approved folder: ApexRetail-POS-Secure-Backups. Database: apexretail_pos.
No paid service, extra VPS, production database write, scheduler change, upload,
OAuth grant, production key generation or Phase7–10 deployment occurred.

## Implementation / findings

rclone is now installed from Ubuntu: package1.53.3-4ubuntu1.22.04.5,
reports v1.53.3-DEV. Its installed help confirms drive.file, root_folder_id,
copyto/immutable and connection/retry flags. OAuth and live adapter acceptance
remain pending. Existing GPG is available. Initial preparation predated installation.
Current backup script correctly targets apexretail_pos, remains plaintext and
uses the existing daily02:00UTC timer. Preserve all existing backups/schedules.

Uninstalled `ops/phase10/backup_drive.py` extends the existing encrypted backup
coordinator, not another backup system. It validates a private single-remote
rclone config, `drive.file` scope, owner-approved pinned folder ID, protected
binary/config paths and stable OAuth authorization binding. It captures/suppresses
child output, clears inherited rclone/environment overrides, leaves TLS validation
enabled and uses copy-only immutable destinations. Ciphertext uploaded first,
minimal completion manifest last; both are fully downloaded and hash-compared
before a receipt is issued. No sync, purge, deletion, public-link or sharing call.
Renamed plaintext is rejected by encrypted GPG packet inspection and recipient
checks before network activity. Existing GPG public-key-only validation applies.

The email in the local config is OWNER ATTESTATION, not an API-verified identity.
Owner must confirm the selected Google account at consent and folder ownership.
Changing refresh credential, client ID or folder invalidates old recovery approval.
Access-token renewal does not. No token or token-derived binding is printed.

`drive.file` limits access to app-created/explicitly authorized files, not a
cryptographic folder-only permission. `root_folder_id` is a client routing fence,
NOT a Google-enforced folder-only OAuth scope. A dedicated owner-controlled OAuth
client narrows the app's accessible set. Cloud folder contents remain deletable
by an authorized owner/compromised upload credential; this is not immutable storage.
Keep an independent offline recovery copy; do not imply Drive is WORM storage.

## Private Android/Chrome OAuth steps

Perform authorization ONLY in a private Termux/SSH terminal, not through Codex
tools, chat, session recording, `script`, `tee`, shell tracing or shared screen.
Do not paste OAuth links/callbacks, client secrets, config summaries or tokens
into this conversation. Google password is entered only on accounts.google.com.

1. After approval for the utility installation, install the Ubuntu rclone package
   through the trusted package manager, review its version, and test supported
   flags. Do not use an unreviewed curl-to-shell installer. No VPS restart needed.
2. In the owner's Google Cloud console, use an owner-controlled OAuth client
   specifically for backups. Enable Google Drive API; configure the consent app
   for personal use and only `drive.file`; create a Desktop OAuth client. Do not
   activate billing or select paid services. Review current Google consent rules;
   do not leave a weekly-expiring Testing grant as unattended production access.
   Publishing an OAuth consent app is not deploying ApexRetail or bypassing any
   verification Google requires. Client ID/secret stay in private configuration.
3. Operator prepares `/etc/apexretail/drive` root0700 and dedicated rclone.conf0600.
   Do not overwrite any existing remote/config. Secret-bearing configuration must
   remain outside Git and web roots, with independent protected recovery custody.
4. From a LOCAL Termux shell on the Android phone (not already inside VPS SSH):

   ```sh
   ssh -o ExitOnForwardFailure=yes -L 127.0.0.1:53682:127.0.0.1:53682 root@187.77.179.100
   ```

   Keep this SSH session open. It exposes no public listener. In this private VPS
   session, run:

   ```sh
   umask 077
   rclone config --config /etc/apexretail/drive/rclone.conf
   ```

5. Create only remote `apexretail_drive`, type `drive`, own client ID/secret,
   scope `drive.file` (select by NAME, not a version-dependent menu number).
   Leave root folder blank ONLY for initial folder creation; no service account
   or Shared Drive. Choose web-browser authentication **Y** through the SSH tunnel.
   Open rclone's displayed localhost authorization link in Android Chrome. Verify
   Google account prophetdavie@gmail.com and requested narrow permissions; approve
   privately. Stop if permissions are broader than expected. Callback returns
   through the tunnel; do not copy tokens through chat. Close the tunnel after
   configuration. Never use rclone authorize output as a chat attachment.
6. Create the folder with THIS OAuth client so drive.file can access it:

   ```sh
   rclone mkdir apexretail_drive:ApexRetail-POS-Secure-Backups --config /etc/apexretail/drive/rclone.conf
   ```

   Confirm ownership/private sharing in Drive. If an existing same-named folder
   was created outside this client, STOP and review app authorization; do not
   create duplicates silently or widen to full Drive scope just to see it.
7. Copy its non-secret folder ID from the Drive URL. Privately edit the remote
   using rclone config advanced options to set root_folder_id to that exact ID;
   preserve type/client/scope/token. Pin the same ID in a protected copy of
   `ops/phase10/google-drive.json.example` at
   `/etc/apexretail/backup-offserver.json`. Token config is a separate0600 file.
   The adapter refuses blank IDs, wrong scopes, extra remotes and unexpected
   options. Verify exact local file modes and granted scope without dumping config.
8. Check quota, account MFA, private folder permissions and grant lifetime. Review
   that revocation blocks access and that reauthorization requires new acceptance.
   rclone must be allowed to persist normal refreshed tokens to its protected
   config; do not make it world-readable or put its tokens in command arguments.

No authorization has been initiated by Codex. A person must complete Google
consent; this document does not claim the folder/account has been verified.

## Real encryption-key custody and recovery acceptance

- Owner nominates custodian/recovery contact. Prefer generation on an independent
  owner-controlled recovery device using a passphrase and trusted cryptographic
  tooling. Import ONLY independently verified public recipient key on the VPS.
- Keep encrypted private-key escrow and passphrase separate; not on this VPS,
  in the same Drive folder, chat, Git or the scheduler. Keep an independently
  accessible second recovery copy, including necessary historical keys. Losing
  both key and escrow makes backups unrecoverable. Do not copy disposable test keys.
- If the owner only has this phone, agree an independently recoverable offline
  escrow arrangement before activation; a sole phone or VPS copy is insufficient.
- Approve a one-off encrypted production backup using the existing read-only
  streaming GPG implementation. Retrieve ciphertext independently from Drive;
  verify trusted hash, fail without private key, unlock custodian key privately,
  stream into an allowlisted isolated PostgreSQL target (never production), compare
  revision, original record hashes/financial/stock totals/owners/ACLs and measure
  recovery time. Existing disposable-key evidence is not real-key acceptance.
- Protect/archive actual evidence and manifest; only after this passes may the
  operator create a root-private, time-limited activation receipt binding the
  real recipient/config/OAuth/folder/archive/full-restore evidence. Never promote
  synthetic test receipts to production proof.

  After explicit one-off acceptance approval, the prepared manual entry point is
  `python3 ops/phase10/backup_drive.py publish-approved PRIVATE_ENCRYPTED_PACKAGE
  --config /etc/apexretail/backup-offserver.json` from the reviewed checkout.
  It never activates scheduling or creates a full-restore success receipt.

## Schedule, monitoring and retention — uninstalled proposals

- Reuse existing timer: DAILY02:00UTC =04:00 Zimbabwe time. No second job. After
  final approval, existing service ExecStart may use the reviewed backup_schedule
  coordinator; never activate local-only encryption as off-server success.
-30day rolling retention applies to NEW completed encrypted backups. Current
  planner only reports eligibility, protects two recent verified recovery points,
  preserves unknown/failed/legacy files and deletes nothing. Existing backups
  remain untouched. Cleanup implementation/activation needs a separate reviewed
  exact-file procedure; no `rclone sync/purge/delete` or age-only recursive cleanup.
- Proposed failure monitoring: nonzero job exit and sanitized journal event for
  failed dump/encryption/upload/readback; immediate owner notification, warning
  after26hours without verified off-server success, critical48hours; disk20%/10%
  and Drive quota/grant/key-expiry alerts. Owner must select an alert destination
  and delivery method. Delivery/independent stale-success monitoring is PENDING;
  no email credentials/channel or new monitoring job has been invented/activated.
- Monthly owner-supervised recovery task/reminder: independently retrieve one
  encrypted archive, privately decrypt, full isolated restore and baseline check.
  Do not place the private key on the unattended scheduler to automate decryption.
  Actual monthly scheduling/notification requires owner contact and approval.
- Logical daily dumps are not PITR. Proposed RPO approximately24hours plus delays;
  agreed RTO must be measured, not promised. Preserve config/media/role/entitlement/
  MFA/TLS recovery material separately; database files alone are not full recovery.

## Tests and remaining approvals

18 focused tests pass: existing SFTP/retention/activation gates plus Drive scope,
private configs, stable refresh binding, plaintext refusal, full simulated readback,
transfer/corruption failures, duplicate evidence refusal and real disposable GPG
encryption/decryption/missing-private-key/corruption checks. Existing real-dump
full PostgreSQL restore evidence retained (34tables/890rows, hashes/controls/ACLs
match); not rerun here. Drive transfer calls are simulated; rclone is now installed
but OAuth is not provisioned. No actual Google upload, account identity, granted scope,
quota, revocation or recovery test is reported as passed.

An initial sandbox GPG-agent failure and a nonexistent-keyring packet-inspection
failure were resolved by privileged TEMPORARY test execution and inspection with
the approved public-only keyring; final18 tests pass, not skipped.

Still needed: owner private OAuth consent/folder verification;
real recipient/custodian/escrow; alert contact/channel; approved one-off upload and
real-key isolated recovery; installed-version/API acceptance. THEN request explicit
approval before changing the existing backup schedule/service. No production
activation, deletion, migrations, customer-data modification or APK build.

Official references checked21October2026:
- https://rclone.org/drive/ (drive.file/root_folder_id/custom client)
- https://rclone.org/remote_setup/ (SSH tunnel authorization)
- https://rclone.org/commands/rclone_copyto/ (copy-only transfer)
- https://developers.google.com/workspace/drive/api/guides/api-specific-auth

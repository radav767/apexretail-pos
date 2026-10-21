# Step 2 — private Android OAuth preparation (not connected)

Owner: prophetdavie@gmail.com. Remote: apexretail_drive.
Folder: ApexRetail-POS-Secure-Backups. Database: apexretail_pos.

## Verified

Ubuntu package1.53.3-4ubuntu1.22.04.5; `rclone version` reports v1.53.3-DEV.
Installed help confirms drive.file, root_folder_id, own-client settings,
copyto/immutable and retry/timeout flags. These establish local option support,
NOT successful current Google OAuth/token refresh/API interoperability. Google
must accept the actual owner-controlled OAuth client before it is connected.
No credential files were found in the inspected default rclone directory; the
dedicated /etc/apexretail/drive directory/config has not been provisioned. No
listener was present on port53682. No authorization, public listener or upload
was started.18 isolated backup tests pass after requested remote-name alignment.

The uninstalled adapter/example and disposable tests now use apexretail_drive,
not the earlier apexretail-backups proposal. No existing authorized remote was
renamed or overwritten. `ops/phase10/rclone-google-drive.conf.example` is only
a credential-free template; it cannot connect or pass scheduling validation.

## Required owner action — in private Termux, not the Codex conversation

Do not run authorization with Codex tools. No recording/tee/shell tracing or
shared screen. Never send config output, OAuth links/callbacks, codes, tokens,
client secrets or Google passwords here. A Google password is entered only on
Google's own secure sign-in page. Do not run `rclone config show/dump`.

1. In Chrome, sign into your owner-controlled Google Cloud console. Select an
   appropriate existing project (or a dedicated OAuth credential project if
   necessary; not another POS application/server). Enable Google Drive API.
   Configure consent for personal use with only Drive `drive.file`; create a
   **Desktop app** OAuth client. Keep its details privately. Do not activate
   billing/paid services. If Google requires additional approval, stop and report
   only the non-secret error. Do not accept a broad Drive grant or ignore warnings
   for an unknown client. Do not use rclone's old shared client by leaving its
   client ID blank; current rclone documentation warns of its2026 retirement.
   Check consent publishing/lifetime before unattended use: a Testing grant can
   expire after7days. Do not activate jobs on an unaccepted short-lived grant.
2. Open a NEW LOCAL Termux session on your phone, not a shell already inside the
   VPS. Use your existing verified SSH host identity; do not disable host checks:

   ```sh
   ssh -o ExitOnForwardFailure=yes -L 127.0.0.1:53682:127.0.0.1:53682 root@187.77.179.100
   ```

   Keep the session open. This binds the PHONE loopback only; it does not open
   a VPS firewall port or require Nginx/DNS/TLS changes. If port forwarding is
   rejected, stop; do not enable public authentication or change SSH/firewall.
3. Inside that private SSH session, prepare the private location and start ONLY
   the interactive wizard (no unattended `config create`):

   ```sh
   umask 077
   install -d -o root -g root -m 700 /etc/apexretail/drive
   rclone config --config /etc/apexretail/drive/rclone.conf
   ```

   If a config/remote already exists, stop and inspect privately rather than
   overwrite it. Do not install the credential-free template as live credentials.
4. Wizard choices (labels may differ in1.53.3; do not assume menu numbers):

   - New remote: `n`; name: `apexretail_drive`.
   - Storage: `drive` (Google Drive).
   - Own Desktop OAuth client ID/secret: enter privately, not command arguments.
   - Scope: `drive.file`, NOT `drive`.
   - Root folder ID: initially blank, pending app-created folder verification.
   - Service account: blank. Advanced config: no unless required to set these.
   - **Use auto config? `y`** — the tunnel supplies the browser connection.

   Open the localhost authorization link that rclone prints in Chrome ON THIS
   PHONE. It is a private one-time link; do not post it here. Approve only the
   expected narrow consent for prophetdavie@gmail.com. Google redirects through
   phone localhost → SSH tunnel → VPS loopback. No token copy/paste is needed.
   No Shared Drive/Team Drive. Confirm privately and quit the wizard.
5. Protect and inspect only metadata locally:

   ```sh
   chmod 600 /etc/apexretail/drive/rclone.conf
   rclone listremotes --config /etc/apexretail/drive/rclone.conf
   ```

   The expected non-secret name is `apexretail_drive:`. Its presence proves a
   saved remote exists, not that token refresh, upload or recovery has passed.
   Close the SSH session/tunnel after authorization; never leave public listeners.

STOP here and report only: "OAuth completed" or the sanitized non-secret error.
Do not upload a database or enable any job. If an older wizard presents a
manual/out-of-band authorization-code route, cancel it rather than paste codes
through chat; use the loopback tunnel and review Google compatibility if blocked.

## Remaining steps, NOT authorized by completing this wizard

- Confirm actual account identity, narrow granted scope and token renewal with
  installed rclone; no live compatibility claim until those checks pass.
- Create/verify the exact private backup folder THROUGH this client so drive.file
  can access it, then pin its ID in remote and protected adapter JSON. If an
  inaccessible same-named folder already exists, review app access; do not silently
  duplicate it or widen scope. No database upload until encryption is configured.
- `drive.file` restricts app-created/authorized files. root_folder_id is a client
  routing restriction, not a server-enforced folder-only OAuth scope. Personal
  Drive does not supply immutable backup retention by itself.
- Real public encryption key, independently held private-key escrow and actual
  uploaded/retrieved real-key full recovery acceptance still required.
- Alert delivery, monthly recovery ownership and explicit schedule activation
  approval remain pending. Existing02:00UTC jobs and historical backups unchanged.

Official references:
https://rclone.org/remote_setup/ (SSH forwarding)
https://rclone.org/drive/ (scope/client/folder)
https://developers.google.com/identity/protocols/oauth2/native-app (Desktop OAuth)

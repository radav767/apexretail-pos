"""Encrypted restore rehearsal, NOT production encryption-key provisioning.

Uses an ephemeral test-only key and an existing verified private dump. No live
database connection, real key, plaintext recovery file or installed job change.
"""
import hashlib,importlib.util,json,os,subprocess,tempfile
from datetime import datetime,timezone
from pathlib import Path
from psycopg2 import sql
import verify_backup_target_correction as checks
from prepare_phase10_release import snapshot

SOURCE=Path('/tmp/apexretail-backup-target-before-custom-l21v8qmy')
EXPECTED='390e5673e8ec4a0e81706aa9a0bd8874e37d0f4d8e405f15981de39028469965'

def main():
    if os.geteuid()!=__import__('pwd').getpwnam('postgres').pw_uid:raise RuntimeError('Run as postgres')
    os.umask(0o077)
    dump=SOURCE/'apexretail_pos.dump'
    if hashlib.sha256(dump.read_bytes()).hexdigest()!=EXPECTED:raise RuntimeError('Verified source dump mismatch')
    baseline=json.loads((SOURCE/'baseline.json').read_text())
    out=Path(tempfile.mkdtemp(prefix='apexretail-encrypted-restore-evidence-'))
    print('Private evidence directory: '+str(out),flush=True)
    proposal=Path(__file__).resolve().parents[2]/'ops/phase10/backup_proposal.py'
    spec=importlib.util.spec_from_file_location('backup_proposal',proposal);backup=importlib.util.module_from_spec(spec);spec.loader.exec_module(backup)
    target='apexretail_backup_encrypted_'+datetime.now(timezone.utc).strftime('%Y%m%dt%H%M%S%f')
    checks.TARGET=target
    with tempfile.TemporaryDirectory(prefix='apexretail-backup-test-key-') as folder:
        home=Path(folder);home.chmod(0o700);base=['/usr/bin/gpg','--homedir',folder,'--batch','--no-tty']
        public_home=home/'public-only';public_home.mkdir(mode=0o700)
        try:
            subprocess.run(base+['--pinentry-mode','loopback','--passphrase','','--quick-generate-key',
                'ApexRetail EPHEMERAL RESTORE TEST ONLY','rsa2048','encrypt','1d'],capture_output=True,check=True)
            listing=subprocess.run(base+['--with-colons','--list-keys'],capture_output=True,text=True,check=True).stdout
            recipient=next(line.split(':')[9] for line in listing.splitlines() if line.startswith('fpr:'))
            try:backup.verify_public_keyring(home,recipient)
            except RuntimeError:pass
            else:raise RuntimeError('Scheduler accepted a private recovery key')
            exported=subprocess.run(base+['--export',recipient],capture_output=True,check=True).stdout
            public_base=['/usr/bin/gpg','--homedir',str(public_home),'--batch','--no-tty']
            subprocess.run(public_base+['--import'],input=exported,capture_output=True,check=True)
            subprocess.run(public_base+['--import-ownertrust'],input=(recipient+':6:\n').encode(),capture_output=True,check=True)
            backup.verify_public_keyring(public_home,recipient)
            ciphertext=home/'test-only.dump.gpg'
            with dump.open('rb') as source:
                subprocess.run(backup.encrypt_command(public_home,recipient,ciphertext),stdin=source,capture_output=True,check=True)
            # Authentication-integrity failure must be detected, not silently accepted.
            damaged=bytearray(ciphertext.read_bytes());damaged[-25]^=1
            broken=home/'damaged-test-only.gpg';broken.write_bytes(damaged)
            invalid=subprocess.run(base+['--decrypt',str(broken)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
            if invalid.returncode==0:raise RuntimeError('Corrupt ciphertext was accepted')
            conn=checks.connect('postgres',autocommit=True)
            try:
                with conn.cursor() as cur:
                    cur.execute('SELECT 1 FROM pg_database WHERE datname=%s',(target,))
                    if cur.fetchone():raise RuntimeError('Existing database will not be overwritten')
                    cur.execute(sql.SQL('CREATE DATABASE {} TEMPLATE template0').format(sql.Identifier(target)))
                    cur.execute(sql.SQL('REVOKE CONNECT,TEMPORARY ON DATABASE {} FROM PUBLIC,apex_user').format(sql.Identifier(target)))
            finally:conn.close()
            checks.assert_isolated()
            with (out/'decrypt-stderr.log').open('xb') as decerr,(out/'restore-stderr.log').open('xb') as reserr:
                decrypt=subprocess.Popen(base+['--decrypt',str(ciphertext)],stdout=subprocess.PIPE,stderr=decerr)
                try:
                    restore=subprocess.Popen(['pg_restore','--exit-on-error','--single-transaction','-d',target],
                        stdin=decrypt.stdout,stdout=subprocess.DEVNULL,stderr=reserr)
                    decrypt.stdout.close();restore_code=restore.wait();decrypt_code=decrypt.wait()
                except BaseException:
                    decrypt.stdout.close();decrypt.terminate();decrypt.wait(timeout=10);raise
                if restore_code or decrypt_code:raise RuntimeError('Encrypted restore failed')
            checks.assert_isolated()
            with checks.connect(target,readonly=True) as conn:restored=snapshot(conn,baseline['columns'])
            checks.compare(baseline,restored)
            summary={'source_backup_sha256':EXPECTED,'ephemeral_test_key_only':True,'real_recipient_provisioned':False,
                'encrypted_restore_passed':True,'corrupt_ciphertext_rejected':True,'plaintext_recovery_file_created':False,
                'clone':target,'clone_application_access':False,'tables':len(restored['tables']),
                'rows':sum(t['count'] for t in restored['tables'].values()),'historical_hashes_controls_acl_preserved':True,
                'revision':restored['revision'],'production_connected_or_modified':False,
                'public_only_encryption_keyring_passed':True,'scheduler_private_key_refused':True,
                'routine_encrypted_backup_acceptance':'PENDING owner recipient, escrow, off-host storage and real-key restore'}
            (out/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary,indent=2))
        finally:
            for key_home in (folder,str(public_home)):
                subprocess.run(['gpgconf','--homedir',key_home,'--kill','gpg-agent'],capture_output=True)

if __name__=='__main__':main()

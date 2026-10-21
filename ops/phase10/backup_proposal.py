#!/usr/bin/python3
"""UNINSTALLED scheduled-job proposal. Never deletes backup history.

Public encryption key must be independently verified/provisioned. No key is
invented, private decryption key loaded, or plaintext database dump stored here.
"""
import hashlib,json,os,re,stat,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path

DATABASE='apexretail_pos'
CONFIG=Path('/etc/apexretail/backup.json')
DEST=Path('/root/apexretail-pos/backups/scheduled-production')

def private(path,directory=False):
    s=path.lstat()
    if stat.S_ISLNK(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode&0o077 or (directory and not stat.S_ISDIR(s.st_mode)):
        raise RuntimeError('Private owned non-symlink path required')

def dump_command():
    return ['/usr/sbin/runuser','-u','postgres','--','/usr/bin/env','-i','PATH=/usr/bin:/bin',
        'PGOPTIONS=-c default_transaction_read_only=on -c lock_timeout=5000',
        '/usr/bin/pg_dump','--host=/var/run/postgresql','--username=postgres',
        '--dbname='+DATABASE,'--format=custom','--lock-wait-timeout=5s']

def load_config(path):
    private(path.parent,True);private(path);data=json.loads(path.read_text())
    if set(data)!={'recipient','gnupg_home'} or not isinstance(data['recipient'],str) or not re.fullmatch('(?:[A-F0-9]{40}|[A-F0-9]{64})',data['recipient']):
        raise RuntimeError('An approved full encryption-key fingerprint is required')
    home=Path(data['gnupg_home']);private(home,True)
    if not home.is_absolute():raise RuntimeError('Absolute private GPG home required')
    return data

def encrypt_command(home,recipient,output):
    return ['/usr/bin/gpg','--homedir',str(home),'--batch','--no-tty','--compress-algo','none',
        '--recipient',recipient,'--encrypt','--output',str(output)]

def run():
    if os.geteuid()!=0:raise RuntimeError('Authorized root execution required')
    os.umask(0o077);cfg=load_config(CONFIG);private(DEST,True)
    # Missing/untrusted recipient fails before reading production. No always-trust
    # flag: owner must validate the recipient and establish its trust beforehand.
    key=subprocess.run(['/usr/bin/gpg','--homedir',cfg['gnupg_home'],'--batch','--with-colons','--list-keys',cfg['recipient']],capture_output=True,check=True,text=True)
    if 'fpr:::::::::'+cfg['recipient']+':' not in key.stdout:raise RuntimeError('Recipient fingerprint mismatch')
    name=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    folder=DEST/name;folder.mkdir(mode=0o700);part=folder/'apexretail_pos.dump.gpg.part'
    with (folder/'dump-error.log').open('xb') as err:
        dump=subprocess.Popen(dump_command(),stdout=subprocess.PIPE,stderr=err)
        try:
            with (folder/'encryption-error.log').open('xb') as enc_err:
                enc=subprocess.Popen(encrypt_command(cfg['gnupg_home'],cfg['recipient'],part),stdin=dump.stdout,stdout=subprocess.DEVNULL,stderr=enc_err)
                dump.stdout.close();enc_status=enc.wait()
        except BaseException:
            dump.stdout.close();dump.terminate();dump.wait(timeout=10);raise
        dump_status=dump.wait()
    if dump_status or enc_status:raise RuntimeError('Backup failed; private partial evidence retained, no success published')
    final=folder/'apexretail_pos.dump.gpg';part.rename(final)
    digest=hashlib.sha256(final.read_bytes()).hexdigest()
    (folder/'SHA256SUMS').write_text(digest+'  '+final.name+'\n')
    (folder/'manifest.json').write_text(json.dumps({'database':DATABASE,'encrypted':True,'recipient':cfg['recipient'],
        'ciphertext_sha256':digest,'restore_verified':False,'retention':'no automatic deletion; owner-approved policy pending'},indent=2))
    print('Encrypted ApexRetail backup completed; restore verification must be performed separately.')

if __name__=='__main__':
    if sys.argv[1:]!=['--run-approved']:raise SystemExit('Requires --run-approved after installation approval')
    try:run()
    except Exception as e:print('BACKUP FAILED: '+str(e),file=sys.stderr);raise SystemExit(1)

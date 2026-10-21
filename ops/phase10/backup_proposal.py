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
    if stat.S_ISLNK(s.st_mode) or s.st_uid!=os.geteuid() or s.st_mode&0o077 or not (stat.S_ISDIR(s.st_mode) if directory else stat.S_ISREG(s.st_mode)):
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

def digest_file(path):
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for chunk in iter(lambda:file.read(1024*1024),b''):digest.update(chunk)
    return digest.hexdigest()

def verify_public_keyring(home,recipient):
    # The scheduler must never hold a private recovery key. Capture metadata only;
    # neither key listings nor subprocess output are printed/logged here.
    base=['/usr/bin/gpg','--homedir',str(home),'--batch','--with-colons']
    secret=subprocess.run(base+['--list-secret-keys'],capture_output=True,check=True,text=True)
    if any(line.startswith(('sec:','ssb:')) for line in secret.stdout.splitlines()):
        raise RuntimeError('Backup scheduler requires a public-key-only keyring')
    public=subprocess.run(base+['--list-keys',recipient],capture_output=True,check=True,text=True)
    lines=[line.split(':') for line in public.stdout.splitlines()]
    primary=next((line for line in lines if line[0]=='pub'),None)
    fingerprints=[line[9] for line in lines if line[0]=='fpr' and len(line)>9]
    if not primary or len(primary)<12 or not fingerprints or fingerprints[0]!=recipient or primary[1] in ('r','e','d') or 'E' not in primary[11]:
        raise RuntimeError('Approved active encryption recipient required')

def encrypt_command(home,recipient,output):
    return ['/usr/bin/gpg','--homedir',str(home),'--batch','--no-tty','--compress-algo','none',
        '--recipient',recipient,'--encrypt','--output',str(output)]

def run(announce=True):
    if os.geteuid()!=0:raise RuntimeError('Authorized root execution required')
    os.umask(0o077);cfg=load_config(CONFIG);private(DEST,True)
    # Missing/untrusted recipient fails before reading production. No always-trust
    # flag: owner must validate the recipient and establish its trust beforehand.
    verify_public_keyring(cfg['gnupg_home'],cfg['recipient'])
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
    with part.open('rb') as file:os.fsync(file.fileno())
    final=folder/'apexretail_pos.dump.gpg';part.rename(final)
    digest=digest_file(final)
    (folder/'SHA256SUMS').write_text(digest+'  '+final.name+'\n')
    (folder/'manifest.json').write_text(json.dumps({'database':DATABASE,'encrypted':True,'recipient':cfg['recipient'],
        'ciphertext_sha256':digest,'created_at':datetime.now(timezone.utc).isoformat(),
        'restore_verified':False,'retention':'no automatic deletion; owner-approved policy pending'},indent=2))
    for path in (folder/'SHA256SUMS',folder/'manifest.json'):
        with path.open('rb') as file:os.fsync(file.fileno())
    for directory in (folder,DEST):
        fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(fd)
        finally:os.close(fd)
    if announce:print('Encrypted ApexRetail backup completed; restore verification must be performed separately.')
    return folder

if __name__=='__main__':
    if sys.argv[1:]!=['--run-approved']:raise SystemExit('Requires --run-approved after installation approval')
    try:run()
    except Exception as e:print('BACKUP FAILED: '+str(e),file=sys.stderr);raise SystemExit(1)

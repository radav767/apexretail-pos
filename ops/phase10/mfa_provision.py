#!/usr/bin/python3
"""UNINSTALLED local provisioning proposal. Never overwrite/print a key."""
import os,stat,sys
from pathlib import Path
from cryptography.fernet import Fernet

TARGET=Path('/etc/apexretail/platform-mfa.env')

def protect_parent(path):
    parent=path.parent.lstat()
    if not stat.S_ISDIR(parent.st_mode) or parent.st_uid!=os.geteuid() or parent.st_mode&0o077:
        raise RuntimeError('Private owned 0700 parent directory required')

def provision(path):
    protect_parent(path)
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'wb') as file:file.write(b'PLATFORM_MFA_KEY='+Fernet.generate_key()+b'\n');file.flush();os.fsync(file.fileno())

def check(path):
    protect_parent(path);s=path.lstat()
    if not stat.S_ISREG(s.st_mode) or s.st_uid!=os.geteuid() or stat.S_IMODE(s.st_mode)!=0o600:raise RuntimeError('Owned regular 0600 key file required')
    with path.open('rb') as f:content=f.read()
    prefix=b'PLATFORM_MFA_KEY='
    if not content.startswith(prefix) or content.count(b'\n')!=1:raise RuntimeError('Invalid protected environment file')
    Fernet(content[len(prefix):].strip())

if __name__=='__main__':
    if os.geteuid()!=0 or sys.argv[1:] not in (['--provision-approved'],['--check']):raise SystemExit('Authorized root --provision-approved or --check required')
    if sys.argv[1]=='--provision-approved':provision(TARGET)
    check(TARGET);print('Protected MFA key validated; value not displayed.')

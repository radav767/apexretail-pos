"""Create a NEW separate staging instance only. Never reset an existing one."""
import grp
import json
import os
from pathlib import Path
import pwd
import secrets
import subprocess
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path("/tmp/apexretail-phase7f-runtime")
SOURCE = Path(__file__).resolve().parents[1]
ACCOUNT = "apexstage7f"
PG = "/usr/lib/postgresql/14/bin/"
PYTHON = "/tmp/apexretail-phase7b-venv/bin/python"
if os.geteuid() != 0: raise SystemExit("Preparation requires approved root execution")
if str(SOURCE) != "/tmp/apexpos-phase7f": raise SystemExit("Unexpected staging source")
if ROOT.exists():
    if sys.argv[1:] != ["--resume-migrations"]:
        raise SystemExit("Staging runtime already exists; inspect it, never overwrite or reset")
    data=json.loads((ROOT/"runtime.json").read_text())
    if data["environment"]!="phase7f-staging" or data["database"]!="apexretail_phase7f_acceptance":raise SystemExit("Unexpected runtime")
    if ROOT.stat().st_uid!=pwd.getpwnam(ACCOUNT).pw_uid:raise SystemExit("Unexpected runtime owner")
    owner_env=dict(data["api_environment"],DATABASE_URL=f"postgresql+asyncpg://{ACCOUNT}@/apexretail_phase7f_acceptance?host={ROOT}/socket&port=55437")
    subprocess.run(["/usr/sbin/runuser","-u",ACCOUNT,"--",PYTHON,"-m","alembic","upgrade","p7j_variant_batches"],cwd=SOURCE/"backend",env=owner_env,check=True)
    subprocess.run(["/usr/sbin/runuser","-u",ACCOUNT,"--",PG+"psql","-X","-v","ON_ERROR_STOP=1","-h",str(ROOT/"socket"),"-p","55437","-d",data["database"],"-f",str(SOURCE/"staging/grant_stage_runtime.sql")],cwd=SOURCE,check=True)
    print("Resumed migrations on the existing isolated staging database; no reset")
    raise SystemExit(0)
try: pwd.getpwnam(ACCOUNT)
except KeyError:
    subprocess.run(["useradd", "--system", "--user-group", "--no-create-home", "--home-dir", str(ROOT), "--shell", "/usr/sbin/nologin", ACCOUNT], check=True)
user = pwd.getpwnam(ACCOUNT)
ROOT.mkdir(mode=0o700); os.chown(ROOT, user.pw_uid, user.pw_gid)
for folder in ("socket", "keys", "images", "web", "logs"):
    path = ROOT / folder; path.mkdir(mode=0o700); os.chown(path, user.pw_uid, user.pw_gid)


def save(name, contents, mode=0o600):
    path = ROOT / name
    path.write_bytes(contents if isinstance(contents, bytes) else contents.encode())
    path.chmod(mode); os.chown(path, user.pw_uid, user.pw_gid)


def run(command, **kwargs):
    subprocess.run(["/usr/sbin/runuser", "-u", ACCOUNT, "--", *command], cwd=ROOT, check=True, **kwargs)


run([PG + "initdb", "-D", str(ROOT / "postgres"), "--auth-local=peer", "--auth-host=reject", "--no-instructions"], stdout=subprocess.DEVNULL)
save("postgres/pg_hba.conf", f"local all {ACCOUNT} peer\nlocal apexretail_phase7f_acceptance apex_user scram-sha-256\nlocal all all reject\n")
run([PG + "pg_ctl", "-D", str(ROOT / "postgres"), "-l", str(ROOT / "logs/postgres.log"), "-o",
     f"-p 55437 -c listen_addresses='' -c unix_socket_directories='{ROOT}/socket'", "start"])
password = secrets.token_urlsafe(36)
sql = f"CREATE ROLE apex_user LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE PASSWORD '{password}';\nCREATE DATABASE apexretail_phase7f_acceptance OWNER {ACCOUNT};\n"
run([PG + "psql", "-X", "-v", "ON_ERROR_STOP=1", "-h", str(ROOT / "socket"), "-p", "55437", "-d", "postgres"], input=sql, text=True, stdout=subprocess.DEVNULL)

# Dedicated staging TLS and entitlement keys: never the Android signing identity.
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtendedKeyUsageOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import ipaddress
now = datetime.now(timezone.utc)
key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "ApexRetail Phase 7F local acceptance CA")])
ca = x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=30)).add_extension(x509.BasicConstraints(ca=True,path_length=0),critical=True).sign(key,hashes.SHA256())
leaf_key = rsa.generate_private_key(public_exponent=65537,key_size=3072)
leaf = x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,"localhost")])).issuer_name(name).public_key(leaf_key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5)).not_valid_after(now+timedelta(days=30)).add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),critical=False).add_extension(x509.BasicConstraints(ca=False,path_length=None),critical=True).add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=False).sign(key,hashes.SHA256())
private = lambda k:k.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())
save("keys/local-ca.pem",ca.public_bytes(serialization.Encoding.PEM));save("keys/tls.pem",leaf.public_bytes(serialization.Encoding.PEM));save("keys/tls-key.pem",private(leaf_key))
entitlement = rsa.generate_private_key(public_exponent=65537,key_size=3072)
save("keys/entitlement.pem",private(entitlement))
save("keys/public-keyring.json",json.dumps({"version":1,"keys":[{"kid":"phase7f-staging-only","public_key_pem":entitlement.public_key().public_bytes(serialization.Encoding.PEM,serialization.PublicFormat.SubjectPublicKeyInfo).decode()}]}))
commit = subprocess.check_output(["git","rev-parse","HEAD"],cwd=SOURCE,text=True).strip()
environment={"PATH":"/usr/bin:/bin","APP_ENV":"staging","JWT_SECRET":secrets.token_urlsafe(48),"PRODUCT_IMAGE_ROOT":str(ROOT/"images"),"ENTITLEMENT_SIGNING_KEY_FILE":str(ROOT/"keys/entitlement.pem"),"ENTITLEMENT_PUBLIC_KEYRING_FILE":str(ROOT/"keys/public-keyring.json"),"ENTITLEMENT_ACTIVE_KEY_ID":"phase7f-staging-only"}
data={"environment":"phase7f-staging","source":str(SOURCE),"source_commit":commit,"database":"apexretail_phase7f_acceptance","database_url":f"postgresql+asyncpg://apex_user:{password}@/apexretail_phase7f_acceptance?host={ROOT}/socket&port=55437","api_environment":environment}
save("runtime.json",json.dumps(data,indent=2))
owner_env=dict(environment,DATABASE_URL=f"postgresql+asyncpg://{ACCOUNT}@/apexretail_phase7f_acceptance?host={ROOT}/socket&port=55437")
subprocess.run(["/usr/sbin/runuser","-u",ACCOUNT,"--",PYTHON,"-m","alembic","upgrade","p7j_variant_batches"],cwd=SOURCE/"backend",env=owner_env,check=True)
run([PG+"psql","-X","-v","ON_ERROR_STOP=1","-h",str(ROOT/"socket"),"-p","55437","-d",data["database"],"-f",str(SOURCE/"staging/grant_stage_runtime.sql")])
print(json.dumps({"runtime":str(ROOT),"separatePostgresCluster":True,"tcpDatabaseListener":False,"productionModified":False,"source_commit":commit}))

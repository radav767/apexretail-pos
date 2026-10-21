"""Test proposed vhosts in a private temporary Nginx process, never live Nginx.

Only loopback listeners and synthetic upstream/files. Temporary self-signed test
certificate is trusted explicitly by this test; it is never installed/published.
"""
import http.client,json,os,signal,socket,ssl,subprocess,tempfile,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]

class Upstream(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        self.send_response(401);self.send_header('Content-Type','application/json');self.end_headers()
        self.wfile.write(json.dumps({'path':self.path,'authorized':False,'authorization_forwarded':self.headers.get('Authorization')=='Bearer synthetic-only'}).encode())
    do_POST=do_GET

def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]

class DomainConfiguration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='apex-admin-domain-test-');cls.addClassCleanup(cls.temp.cleanup)
        cls.base=Path(cls.temp.name);cls.base.chmod(0o755)
        cls.static=cls.base/'static';cls.static.mkdir();(cls.static/'index.html').write_text('SYNTHETIC CONSOLE INDEX')
        (cls.static/'assets').mkdir();(cls.static/'assets/example.js').write_text('// synthetic asset')
        (cls.static/'downloads/token').mkdir(parents=True)
        (cls.static/'downloads/token/preview.png').write_text('SYNTHETIC PRIVATE PREVIEW')
        cls.acme=cls.base/'acme/.well-known/acme-challenge';cls.acme.mkdir(parents=True);(cls.acme/'synthetic').write_text('SYNTHETIC ACME')
        cls.upstream=ThreadingHTTPServer(('127.0.0.1',0),Upstream)
        cls.addClassCleanup(cls.upstream.server_close);cls.addClassCleanup(cls.upstream.shutdown)
        threading.Thread(target=cls.upstream.serve_forever,daemon=True).start()
        cls.http=port();cls.https=port()
        cert=cls.base/'test-cert.pem';key=cls.base/'test-key.pem'
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-days','1','-subj','/CN=admin.apexpos.cloud',
            '-addext','subjectAltName=DNS:admin.apexpos.cloud,IP:127.0.0.1','-keyout',str(key),'-out',str(cert)],check=True,capture_output=True)
        key.chmod(0o600)
        template=(ROOT/'ops/nginx/admin.apexpos.cloud.conf.example').read_text()
        template=template.replace('listen 80;',f'listen 127.0.0.1:{cls.http};').replace('listen 443 ssl;',f'listen 127.0.0.1:{cls.https} ssl;')
        template=template.replace('/etc/letsencrypt/live/admin.apexpos.cloud/fullchain.pem',str(cert)).replace('/etc/letsencrypt/live/admin.apexpos.cloud/privkey.pem',str(key))
        template=template.replace('/var/www/apexpos-backoffice',str(cls.static)).replace('/var/www/apexretail-acme',str(cls.base/'acme'))
        template=template.replace('http://127.0.0.1:8000',f'http://127.0.0.1:{cls.upstream.server_port}').replace('/var/log/nginx/apexretail-admin-error.log',str(cls.base/'error.log'))
        cls.conf=cls.base/'nginx.conf'
        prefix=f'worker_processes 1; pid {cls.base}/nginx.pid; error_log {cls.base}/master-error.log; events {{worker_connections 32;}} http {{ access_log off; include /etc/nginx/mime.types; client_body_temp_path {cls.base}/body; proxy_temp_path {cls.base}/proxy; '
        cls.conf.write_text(prefix+template+'}')
        result=subprocess.run(['nginx','-t','-p',str(cls.base),'-c',str(cls.conf)],check=True,capture_output=True,text=True)
        print(result.stderr.strip())
        cls.proc=subprocess.Popen(['nginx','-p',str(cls.base),'-c',str(cls.conf),'-g','daemon off;'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        cls.addClassCleanup(cls.stop)
        cls.context=ssl.create_default_context(cafile=str(cert))
        bootstrap=(ROOT/'ops/nginx/admin.apexpos.cloud-acme.conf.example').read_text().replace('listen 80;',f'listen 127.0.0.1:{cls.http};').replace('/var/www/apexretail-acme',str(cls.base/'acme'))
        bootstrap_conf=cls.base/'bootstrap.conf';bootstrap_conf.write_text(prefix+bootstrap+'}')
        subprocess.run(['nginx','-t','-p',str(cls.base),'-c',str(bootstrap_conf)],check=True,capture_output=True)
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',cls.https),timeout=.2):break
            except OSError:time.sleep(.05)
        else:raise RuntimeError('Private test Nginx did not start')

    @classmethod
    def stop(cls):
        if cls.proc.poll() is None:cls.proc.send_signal(signal.SIGQUIT)
        cls.proc.wait(timeout=10)

    def request(self,path,secure=True,method='GET',headers=None):
        c=http.client.HTTPSConnection('127.0.0.1',self.https,context=self.context,timeout=5) if secure else http.client.HTTPConnection('127.0.0.1',self.http,timeout=5)
        try:
            c.request(method,path,headers={'Host':'admin.apexpos.cloud',**(headers or {})});r=c.getresponse()
            return r.status,dict(r.getheaders()),r.read().decode()
        finally:c.close()

    def test_http_redirect_and_acme(self):
        status,headers,_=self.request('/?console=platform',False)
        self.assertEqual(status,301);self.assertEqual(headers['Location'],'https://admin.apexpos.cloud/?console=platform')
        self.assertEqual(self.request('/.well-known/acme-challenge/synthetic',False)[::2],(200,'SYNTHETIC ACME'))

    def test_https_root_and_spa(self):
        for path in ('/','/devices','/?console=business'):
            with self.subTest(path=path):
                status,headers,body=self.request(path);self.assertEqual(status,200);self.assertIn('SYNTHETIC CONSOLE INDEX',body)
                self.assertEqual(headers['Cache-Control'],'no-store');self.assertEqual(headers['X-Frame-Options'],'DENY')

    def test_only_platform_proxy_and_authorization_forwarding(self):
        status,_,body=self.request('/api/platform/dashboard?offset=0',headers={'Authorization':'Bearer synthetic-only'})
        self.assertEqual(status,401);data=json.loads(body)
        self.assertEqual(data['path'],'/api/platform/dashboard?offset=0');self.assertTrue(data['authorization_forwarded']);self.assertFalse(data['authorized'])
        self.assertEqual(self.request('/api/platform/login',method='POST')[0],401)

    def test_tenant_api_and_sensitive_files_are_not_exposed(self):
        for path in ('/api','/api/sales','/api/products/test','/.env','/.git/config','/secrets/key.pem','/backup.dump','/download.apk','/downloads','/downloads/token/preview.png','/assets/missing.js'):
            with self.subTest(path=path):self.assertEqual(self.request(path)[0],404)
        self.assertEqual(self.request('/assets/example.js')[0],200)

if __name__=='__main__':unittest.main(verbosity=2)

// Actual loopback HTTP redirects; synthetic credentials only, no external calls.
import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'node:http';
import {createRequire} from 'node:module';
import {resolve} from 'node:path';
import {runInNewContext} from 'node:vm';
const require = createRequire(resolve(process.cwd(), 'package.json'));
const {http} = require('follow-redirects');

async function check(headers, sensitiveHeaders, rejected) {
  const target = createServer((request, response) => response.end(JSON.stringify(request.headers)));
  const redirect = createServer((_request, response) => {
    response.writeHead(302, {Location: `http://127.0.0.1:${target.address().port}/target`});
    response.end();
  });
  const listen = server => new Promise((resolve, reject) => {
    server.once('error', reject); server.listen(0, '127.0.0.1', resolve);
  });
  const close = server => new Promise(resolve => { server.close(resolve); server.closeAllConnections(); });
  try {
    await listen(target); await listen(redirect);
    const received = await new Promise((resolve, reject) => {
      const request = http.get({hostname: '127.0.0.1', port: redirect.address().port,
        path: '/', headers, sensitiveHeaders, maxRedirects: 2}, response => {
        let body = ''; response.setEncoding('utf8');
        response.on('data', chunk => {body += chunk;});
        response.on('end', () => {try {resolve(JSON.parse(body));} catch (error) {reject(error);}});
        response.on('error', reject);
      });
      request.setTimeout(3000, () => request.destroy(new Error('Loopback redirect timed out')));
      request.on('error', reject);
    });
    for (const header of rejected) assert.equal(received[header], undefined, `${header} must not cross origins`);
    assert.equal(received['x-public'], 'synthetic-public');
  } finally {await close(redirect); await close(target);}
}

test('array-form credential headers are stripped across origins', async () => {
  await check(['Authorization', 'SYNTHETIC', 'Cookie', 'synthetic=1', 'Proxy-Authorization', 'SYNTHETIC',
    'X-Public', 'synthetic-public'], [], ['authorization', 'cookie', 'proxy-authorization']);
});
test('metacharacters in custom credential header names are escaped', async () => {
  await check({'X^Key': 'SYNTHETIC', 'X|Key': 'SYNTHETIC', 'X-Public': 'synthetic-public'},
    ['X^Key', 'X|Key'], ['x^key', 'x|key']);
});

test('cross-realm custom sensitive-header arrays strip credentials on redirect', async () => {
  const sensitive = runInNewContext("['X-Synthetic-Key']");
  assert.equal(Array.isArray(sensitive), true);
  assert.equal(sensitive instanceof Array, false);
  await check({'X-Synthetic-Key': 'SYNTHETIC', 'X-Public': 'synthetic-public'},
    sensitive, ['x-synthetic-key']);
});

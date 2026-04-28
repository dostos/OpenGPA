// Minimal smoke test — uses Node 18+ built-in test runner.
// Exercises the extracted client's POST behavior against an in-process stub.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import OpenGPAThreePlugin from './index.js';

test('capture() POSTs metadata to /api/v1/frames/{n}/metadata', async () => {
  const received = [];
  const server = http.createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => { body += chunk; });
    req.on('end', () => {
      received.push({ url: req.url, body: JSON.parse(body) });
      res.end('{"status":"ok"}');
    });
  });
  await new Promise((r) => server.listen(0, r));
  const port = server.address().port;

  const fakeScene = { traverse: (cb) => cb({ name: 'root', type: 'Scene', isMesh: false }) };
  const fakeCamera = {};
  const plugin = new OpenGPAThreePlugin(null, `http://127.0.0.1:${port}`);
  plugin.capture(fakeScene, fakeCamera);

  // Wait one tick for the fetch to complete.
  await new Promise((r) => setTimeout(r, 50));
  server.close();

  assert.equal(received.length, 1);
  assert.match(received[0].url, /\/api\/v1\/frames\/0\/metadata$/);
  assert.equal(received[0].body.framework, 'threejs');
  assert.ok(Array.isArray(received[0].body.objects));
});

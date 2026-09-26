import test from 'node:test';
import assert from 'node:assert/strict';
import { uploadKey } from '../assets/js/api.js';

function withCrypto(value, run) {
  const original = Object.getOwnPropertyDescriptor(globalThis, 'crypto');
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value });
  try { run(); }
  finally {
    if (original) Object.defineProperty(globalThis, 'crypto', original);
    else delete globalThis.crypto;
  }
}

test('upload keys work when randomUUID is unavailable', () => {
  let next = 0;
  withCrypto({ getRandomValues(bytes) { bytes.fill(next++); return bytes; } }, () => {
    const first = uploadKey();
    const second = uploadKey();
    assert.match(first, /^[0-9a-f]{32}$/);
    assert.match(second, /^[0-9a-f]{32}$/);
    assert.notEqual(first, second);
  });
});

test('upload keys work when Web Crypto is unavailable', () => {
  withCrypto(undefined, () => assert.match(uploadKey(), /^[0-9a-f]{32}$/));
});

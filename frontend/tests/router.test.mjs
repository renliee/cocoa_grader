import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveRoute, setNavigationGuard, startRouter } from '../assets/js/router.js';

function setup(path = '/') {
  setNavigationGuard(null);
  const events = {};
  const rendered = [];
  const navigations = [];
  let focusCount = 0;
  globalThis.location = new URL(path, 'http://localhost:8080');
  globalThis.history = { pushState(_state, _title, url) {
    navigations.push(String(url));
    globalThis.location = new URL(url);
  } };
  globalThis.document = {
    addEventListener(name, callback) { events[name] = callback; },
    getElementById() { return { focus() { focusCount++; } }; },
  };
  globalThis.window = {
    addEventListener(name, callback) { events[name] = callback; },
    scrollTo() {},
  };
  startRouter(route => rendered.push(route));
  return {
    rendered, navigations, events,
    get focusCount() { return focusCount; },
    click(path, options = {}) {
      const link = { href: new URL(path, location.origin).href, target: '', hasAttribute: () => false };
      let prevented = false;
      events.click({ target: { closest: () => link }, button: 0, preventDefault() { prevented = true; }, ...options });
      return prevented;
    },
  };
}

test('lot, sample, result, finalized detail, and guide routes resolve directly', () => {
  const id = 'a'.repeat(32);
  for (const step of ['lot', 'sample', 'result']) {
    assert.equal(resolveRoute(`/analysis/${id}/${step}`).draftId, id);
    assert.equal(resolveRoute(`/analysis/${id}/${step}`).step, step);
  }
  assert.equal(resolveRoute(`/lots/${id}`).lotId, id);
  assert.equal(resolveRoute(`/lots/${id}/revisions/${id}`).revisionId, id);
  assert.equal(resolveRoute(`/suppliers/${id}/performance`).supplierId, id);
  assert.equal(resolveRoute('/report/' + 'a'.repeat(43)).reportToken, 'a'.repeat(43));
  assert.equal(resolveRoute('/report/' + 'a'.repeat(43) + '/label').labelMode, true);
  assert.equal(resolveRoute('/settings/guide').label, 'KakaoLens guide');
  assert.equal(resolveRoute('/lots/invalid').label, 'Page not found');
});

test('all four navigation destinations render and retain query parameters', () => {
  const app = setup();
  for (const path of ['/history?tab=draft', '/suppliers', `/suppliers/${'a'.repeat(32)}/performance`, '/settings', '/?period=7d&preview=empty']) {
    assert.equal(app.click(path), true);
    assert.equal(location.pathname + location.search, path);
    assert.equal(app.rendered.at(-1).path, location.pathname);
  }
  assert.equal(app.focusCount, 5);
});

test('direct route loads and Back/Forward notifications select the right page', () => {
  const app = setup('/suppliers/');
  assert.equal(app.rendered[0].label, 'Suppliers');
  globalThis.location = new URL('/history', location.origin);
  app.events.popstate();
  assert.equal(app.rendered.at(-1).label, 'History');
});

test('external links, MVP, anchors, and modified clicks retain native behavior', () => {
  const app = setup();
  assert.equal(app.click('https://example.com/'), false);
  assert.equal(app.click('/mvp.html'), false);
  assert.equal(app.click('/#main'), false);
  assert.equal(app.click('/history', { ctrlKey: true }), false);
  assert.equal(app.click('/history', { button: 1 }), false);
  assert.equal(app.navigations.length, 0);
});

test('reselecting the current route does not add history; unknown routes are explicit', () => {
  const app = setup('/settings');
  assert.equal(app.click('/settings'), true);
  assert.equal(app.navigations.length, 0);
  globalThis.location = new URL('/missing', location.origin);
  app.events.popstate();
  assert.equal(app.rendered.at(-1).label, 'Page not found');
});

test('a draft can block navigation until its save succeeds', async () => {
  const app = setup('/analysis/new');
  setNavigationGuard(async () => false);
  assert.equal(app.click('/history'), true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(location.pathname, '/analysis/new');
  setNavigationGuard(async () => true);
  assert.equal(app.click('/history'), true);
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(location.pathname, '/history');
});

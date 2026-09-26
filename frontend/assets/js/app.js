import { api, setCsrf } from './api.js';
import { canNavigate, routes, startRouter } from './router.js';
import { icon } from './components/icons.js';
import { renderAuth } from './views/auth.js';
import { renderHome } from './views/home.js';
import { renderNewAnalysis, renderLotDraft } from './views/new-analysis.js';
import { renderSample } from './views/sample.js';
import { renderResult, renderLotDetail } from './views/result.js';
import { renderHistory } from './views/history.js';
import { renderSuppliers } from './views/suppliers.js';
import { renderSupplierPerformance } from './views/supplier-performance.js';
import { renderSettings } from './views/settings.js';
import { renderGuide } from './views/guide.js';
import { renderPublicReport } from './views/report.js';

const main = document.getElementById('main');
const nav = document.querySelector('.bottom-nav');
const logoutButton = document.getElementById('logout-button');
const accountAvatar = document.getElementById('account-avatar');
let user = null;
let pendingPath = null;
const homeUrl = '/?period=7d';

function navigate(path, replace = false) {
  const finish = () => {
    history[replace ? 'replaceState' : 'pushState']({}, '', path);
    window.dispatchEvent(new PopStateEvent('popstate'));
    window.scrollTo(0, 0);
    main.focus({ preventScroll: true });
  };
  const allowed = canNavigate(path);
  if (allowed === true) finish();
  else Promise.resolve(allowed).then(ok => { if (ok) finish(); });
}

function render(route) {
  if (!user && route.path !== '/login' && route.path !== '/signup' && !route.reportToken) {
    pendingPath = location.pathname + location.search;
    navigate('/login', true);
    return;
  }
  if (user && (route.path === '/login' || route.path === '/signup')) {
    navigate('/', true);
    return;
  }
  document.title = `${route.label} · KakaoLens`;
  main.setAttribute('aria-label', route.label);
  const authenticated = Boolean(user);
  nav.hidden = !authenticated;
  logoutButton.hidden = !authenticated;
  accountAvatar.hidden = !authenticated;
  document.querySelector('.workspace-label').hidden = !authenticated;
  if (authenticated) {
    accountAvatar.textContent = initials(user.display_name || user.login);
    accountAvatar.setAttribute('aria-label', `Open account settings for ${user.display_name || user.login}`);
    const activePath = route.path.startsWith('/analysis/') ? '/' : route.lotId ? '/history' : route.supplierId ? '/suppliers' : route.path.startsWith('/settings/') ? '/settings' : route.path;
    nav.innerHTML = routes.map(item => `<a href="${item.path === '/' ? homeUrl : item.path}" ${item.path === activePath ? 'aria-current="page"' : ''}><span class="nav-icon">${icon(item.icon)}</span><span>${item.label}</span></a>`).join('');
  }
  if (route.reportToken) {
    renderPublicReport(main, route.reportToken, route.labelMode);
  } else if (route.path === '/login' || route.path === '/signup') {
    renderAuth(main, route.path.slice(1), authenticatedUser => {
      user = authenticatedUser;
      const destination = pendingPath || '/';
      pendingPath = null;
      navigate(destination, true);
    });
  } else if (route.path === '/') {
    renderHome(main);
  } else if (route.path === '/history') {
    renderHistory(main, navigate);
  } else if (route.path === '/analysis/new') {
    renderNewAnalysis(main, navigate);
  } else if (route.draftId && route.step === 'lot') {
    renderLotDraft(main, route.draftId, navigate);
  } else if (route.draftId && route.step === 'sample') {
    renderSample(main, route.draftId, navigate);
  } else if (route.draftId && route.step === 'result') {
    renderResult(main, route.draftId, navigate);
  } else if (route.lotId) {
    renderLotDetail(main, route.lotId, navigate, route.revisionId);
  } else if (route.path === '/suppliers') {
    renderSuppliers(main);
  } else if (route.supplierId) {
    renderSupplierPerformance(main, route.supplierId);
  } else if (route.path === '/settings') {
    renderSettings(main, user, updated => { user = updated; accountAvatar.textContent = initials(user.display_name || user.login); });
  } else if (route.path === '/settings/guide') {
    renderGuide(main);
  } else {
    main.className = 'not-found';
    main.innerHTML = '<h1>Page not found</h1><a class="text-link" href="/">Back to Home</a>';
  }
}

function initials(value = '') {
  const parts = String(value).trim().split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts.at(-1)[0] : (parts[0] || 'K').slice(0, 2)).toLocaleUpperCase('en-GB');
}

accountAvatar.addEventListener('click', () => navigate('/settings'));

logoutButton.addEventListener('click', async () => {
  logoutButton.disabled = true;
  logoutButton.textContent = 'Sign out…';
  try {
    await api('/auth/logout', { method: 'POST' });
    setCsrf('');
    user = null;
    navigate('/login', true);
  } catch {
    logoutButton.textContent = 'Sign-out failed · Retry';
  } finally {
    logoutButton.disabled = false;
    if (user === null) logoutButton.textContent = 'Sign out';
  }
});

async function bootstrap() {
  main.innerHTML = '<p class="loading-state" role="status">Membuka KakaoLens…</p>';
  if (location.pathname.startsWith('/report/')) { startRouter(render); return; }
  try {
    const session = await api('/auth/me');
    user = session.user;
    setCsrf(session.csrf_token);
  } catch {
    user = null;
    setCsrf('');
  }
  startRouter(render);
}
bootstrap();

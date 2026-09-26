export const routes = [
  { path: '/', label: 'Home', icon: 'home' },
  { path: '/history', label: 'History', icon: 'history' },
  { path: '/suppliers', label: 'Suppliers', icon: 'suppliers' },
  { path: '/settings', label: 'Settings', icon: 'settings' },
];

let navigationGuard = null;
export function setNavigationGuard(guard) { navigationGuard = guard; }
export function canNavigate(target) {
  const guard = navigationGuard;
  if (!guard) return true;
  return Promise.resolve(guard(target)).then(allowed => {
    if (allowed && navigationGuard === guard) navigationGuard = null;
    return allowed;
  }).catch(() => false);
}

export function resolveRoute(path) {
  const normalized = path.replace(/\/$/, '') || '/';
  const staticRoute = routes.find(item => item.path === normalized);
  if (staticRoute) return staticRoute;
  if (normalized === '/login') return { path: normalized, label: 'Sign in' };
  if (normalized === '/signup') return { path: normalized, label: 'Sign up' };
  if (normalized === '/settings/guide') return { path: normalized, label: 'KakaoLens guide' };
  const report = normalized.match(/^\/report\/([A-Za-z0-9_-]{40,64})(\/label)?$/);
  if (report) return { path: normalized, label: report[2] ? 'Lot label' : 'KakaoLens report',
                       reportToken: report[1], labelMode: Boolean(report[2]) };
  if (normalized === '/analysis/new') return { path: normalized, label: 'New lot analysis' };
  const supplierPerformance = normalized.match(/^\/suppliers\/([a-f0-9]{32})\/performance$/);
  if (supplierPerformance) return { path: normalized, label: 'Supplier performance', supplierId: supplierPerformance[1] };
  const draft = normalized.match(/^\/analysis\/([a-f0-9]{32})\/(lot|sample|result)$/);
  if (draft) return { path: normalized, label: 'Lot analysis', draftId: draft[1], step: draft[2] };
  const lot = normalized.match(/^\/lots\/([a-f0-9]{32})$/);
  if (lot) return { path: normalized, label: 'Lot details', lotId: lot[1] };
  const revision = normalized.match(/^\/lots\/([a-f0-9]{32})\/revisions\/([a-f0-9]{32})$/);
  if (revision) return { path: normalized, label: 'Lot revision', lotId: revision[1], revisionId: revision[2] };
  return { path: normalized, label: 'Page not found' };
}
export function startRouter(render) {
  let currentUrl = location.pathname + location.search;
  function update() {
    currentUrl = location.pathname + location.search;
    render(resolveRoute(location.pathname));
  }
  document.addEventListener('click', event => {
    const link = event.target.closest('a[href]');
    if (!link || event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || link.target || link.hasAttribute('download')) return;
    const url = new URL(link.href);
    if (url.origin !== location.origin || resolveRoute(url.pathname).label === 'Page not found' || url.hash) return;
    event.preventDefault();
    if (url.href === location.href) return;
    const finish = () => {
      history.pushState({}, '', url);
      update();
      window.scrollTo(0, 0);
      document.getElementById('main').focus({ preventScroll: true });
    };
    const allowed = canNavigate(url.pathname + url.search);
    if (allowed === true) finish();
    else Promise.resolve(allowed).then(ok => { if (ok) finish(); });
  });
  window.addEventListener('popstate', () => {
    const destination = location.pathname + location.search;
    if (destination === currentUrl) { update(); return; }
    const finish = allowed => {
      if (allowed) update();
      else history.pushState({}, '', currentUrl);
    };
    const allowed = canNavigate(destination);
    if (allowed === true) finish(true);
    else Promise.resolve(allowed).then(finish);
  });
  update();
}

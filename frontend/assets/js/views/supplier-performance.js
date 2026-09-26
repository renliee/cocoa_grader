import { api, escapeHtml, formatNumber, shortDate } from '../api.js';
import { icon } from '../components/icons.js';

const percent = value => value === null ? '—' : `${formatNumber(value)}%`;

export async function renderSupplierPerformance(container, supplierId) {
  const path = `/suppliers/${supplierId}/performance`;
  container.className = 'supplier-performance-page';
  container.innerHTML = '<p class="loading-state" role="status">Loading supplier performance…</p>';
  let data;
  try { data = await api(`/suppliers/${supplierId}/performance`); }
  catch (error) {
    if (location.pathname !== path) return;
    container.innerHTML = `<div class="load-error" role="alert"><h2>Unable to load performance</h2><p>${escapeHtml(error.message)}</p><button class="secondary-button" id="retry-performance">Retry</button><a class="text-link" href="/suppliers">Back to Suppliers</a></div>`;
    container.querySelector('#retry-performance').addEventListener('click', () => renderSupplierPerformance(container, supplierId));
    return;
  }
  if (location.pathname !== path) return;
  const supplier = data.supplier;
  const trend = data.trend.map(item => `<a class="supplier-trend-row" href="/lots/${item.lot_id}" aria-label="${escapeHtml(item.human_id)}, ${percent(item.percent)} well fermented, ${item.usable_count} beans">
    <span class="supplier-trend-meta"><strong>${escapeHtml(item.human_id)}</strong><small>${shortDate(item.first_finalized_at)} · ${item.usable_count} beans</small></span>
    <span class="supplier-trend-bar" aria-hidden="true"><span style="width:${item.percent}%"></span></span><strong>${percent(item.percent)}</strong>
  </a>`).join('');
  const inspectionHistory = data.history.slice(0, 5).map(item => `<a class="supplier-inspection-row" href="/lots/${item.lot_id}">
    <span><strong>${escapeHtml(item.human_id)}</strong><small>${shortDate(item.first_finalized_at)} · Revision ${item.revision_number} · ${item.usable_count} beans${item.archived_at ? ' · Archived' : ''}</small></span>
    <span class="supplier-inspection-result"><strong>${percent(item.percent)}</strong><small>${item.eligible ? 'Included in statistics' : item.usable_count < 50 ? 'Sample <50' : 'Excluded from statistics'}</small></span>
  </a>`).join('');
  container.innerHTML = `<a class="back-link" href="/suppliers">${icon('arrow')}Suppliers</a>
    <header class="supplier-performance-header"><div><p class="eyebrow">SUPPLIER PERFORMANCE</p><h1>${escapeHtml(supplier.name)}</h1><p>Code ${escapeHtml(supplier.code)}${supplier.archived_at ? ' · Archived' : ''}</p></div><span class="supplier-avatar" aria-hidden="true">${escapeHtml(supplier.code.slice(0, 2))}</span></header>
    <p class="supplier-performance-intro">An overview of incoming lot inspections. Each lot is counted once using its current finalized revision.</p>
    <section class="supplier-performance-metrics" aria-label="Performance overview">
      <article><span>Finalized lots</span><strong>${data.total_lots}</strong><small>All supplier history</small></article>
      <article class="accent"><span>Average well-fermented beans</span><strong>${percent(data.mean_fermented)}</strong><small>${data.eligible_lots} eligible lots · average per lot</small></article>
      <article><span>Eligible for statistics</span><strong>${data.eligible_lots} / ${data.total_lots}</strong><small>Current revision · at least 50 beans · not manually excluded</small></article>
      <article><span>Samples ≥300 beans</span><strong>${data.sample_300_count} / ${data.total_lots}</strong><small>Cut-test sample-size reference</small></article>
    </section>
    <section class="workflow-card supplier-performance-section"><h2>Fermentation trends across lots</h2><p>Eligible finalized lots, from oldest to newest. Bars show the percentage of well-fermented beans.</p>
      ${trend ? `<div class="supplier-trend-list">${trend}</div>` : '<div class="supplier-performance-empty">No eligible lots yet. Finalized results remain available in inspection history.</div>'}</section>
    <section class="workflow-card supplier-performance-section"><h2>Result consistency</h2><p>Range and standard deviation are calculated from the percentages of eligible lots.</p>
      ${data.eligible_lots >= 2 ? `<div class="supplier-consistency-grid"><div><span>Well-fermented range</span><strong>${percent(data.min_fermented)}–${percent(data.max_fermented)}</strong></div><div><span>Standard deviation</span><strong>${formatNumber(data.stddev_points)} percentage points</strong></div></div><p class="supplier-section-note">Based on ${data.eligible_lots} lots. This describes variation in results; it is not a supplier quality rating.</p>`
        : `<div class="supplier-performance-empty">At least two eligible lots are needed to show variation. Currently available: ${data.eligible_lots} lot.</div>`}</section>
    <section class="workflow-card supplier-performance-section"><div class="supplier-section-heading"><div><h2>Inspection history</h2><p>The five latest finalized lots, including results with limited samples.</p></div>${data.history.length ? `<a class="text-link" href="/history?supplier=${supplierId}">View all ${icon('arrow')}</a>` : ''}</div>
      ${inspectionHistory ? `<div class="supplier-inspection-list">${inspectionHistory}</div>` : '<div class="supplier-performance-empty">No finalized inspections for this supplier yet.</div>'}</section>`;
}

import { icon } from '../components/icons.js';
import { api, escapeHtml, formatNumber as number, shortDate } from '../api.js';

const periods = [
  { id: '7d', label: '7 days' }, { id: '30d', label: '30 days' },
  { id: '3m', label: '3 months' }, { id: 'all', label: 'All time' },
];

function fromDatabase(raw, period) {
  const asLot = item => ({
    id: item.human_id, lotId: item.lot_id, supplier: { name: item.supplier_name || 'Supplier not recorded', code: item.supplier_code || '' },
    date: new Date(`${item.first_finalized_date}T12:00:00`), usable: item.usable_count,
    fermented: item.fermented_count, weight: item.weight_kg,
    excluded: item.excluded_count, percent: item.percent, revision: item.revision_number,
  });
  const defs = [
    ['Very limited', '<50 beans', 'limited', 'under50'],
    ['Small sample', '50–99 beans', 'small', '50to99'],
    ['Indicative', '100–299 beans', 'indicative', '100to299'],
    ['Meets reference', '≥300 beans', 'sufficient', '300plus'],
  ];
  return {
    period, today: new Date(), lotCount: raw.lot_count,
    eligible: raw.trend.map(asLot), recent: raw.recent.map(asLot),
    bands: defs.map(([label, range, color, id]) => ({ label, range, color, count: raw.sample_bands[id] })),
    mean: raw.mean_fermented, weight: raw.weight_kg, weightCount: raw.weight_count,
    sufficient: raw.sample_bands['300plus'], lowSample: raw.attention.low_sample,
    highExclusion: raw.attention.high_exclusion, drafts: raw.attention.drafts,
    activeSuppliers: raw.active_supplier_count,
    range: `${period.label} · based on each lot’s first finalization date`,
  };
}

function metric(name, label, value, unit, detail, accent = '') {
  return `<article class="metric ${accent}"><div class="metric-heading"><span>${label}</span>${icon(name)}</div><p class="metric-value">${value}<span>${unit}</span></p><p class="metric-detail">${detail}</p></article>`;
}

function trend(data) {
  if (!data.eligible.length) return `<div class="empty-chart">${icon('trend')}<h3>Trends start with your first lot</h3><p>Finalized results with at least 50 beans appear here.</p></div>`;
  const lots = data.eligible;
  const width = Math.max(440, lots.length * 58);
  const points = lots.map((lot, i) => ({ lot, x: 44 + i * (width - 70) / Math.max(1, lots.length - 1), y: 18 + (100 - lot.percent) * 1.6 }));
  const grid = [0, 25, 50, 75, 100].map(value => {
    const y = 18 + (100 - value) * 1.6;
    return `<line x1="35" x2="${width - 12}" y1="${y}" y2="${y}"/><text x="27" y="${y + 4}" text-anchor="end">${value}</text>`;
  }).join('');
  const labels = points.filter((_, i) => i === 0 || i === points.length - 1 || i % 3 === 0).map(point => `<text x="${point.x}" y="205" text-anchor="middle">${shortDate(point.lot.date)}</text>`).join('');
  return `<div class="chart-key"><span class="legend-dot sufficient"></span>Well fermented <span class="chart-unit">Percentage (%)</span></div>
    <div class="chart-scroll" tabindex="0" aria-label="Lots in chronological order. Scroll to view all lots.">
      <div class="chart-canvas" style="min-width:${width}px">
        <svg viewBox="0 0 ${width} 220" class="trend-chart" aria-hidden="true">
          <g class="chart-grid">${grid}</g><g class="chart-labels">${labels}</g>
          <polyline class="chart-line" points="${points.map(point => `${point.x},${point.y}`).join(' ')}"/>
        </svg>
        ${points.map(({ lot, x, y }) => `<button class="chart-point" style="left:${x / width * 100}%;top:${y / 220 * 100}%" data-lot="${escapeHtml(lot.id)}" aria-label="${escapeHtml(lot.id)}, ${escapeHtml(lot.supplier.name)}, ${shortDate(lot.date)}, ${number(lot.percent)} percent well fermented" aria-pressed="false"><span></span></button>`).join('')}
      </div>
    </div>
    <div class="chart-selection" id="chart-selection" aria-live="polite">${icon('info')}<span>Tap a point for lot details. Scroll to see more lots.</span></div>`;
}

function sampleQuality(data) {
  return `<div class="sample-summary"><strong>${data.sufficient}<span> / ${data.lotCount} lot</span></strong><p>meet the 300-bean reference</p></div>
    <div class="sample-stack" role="img" aria-label="${data.bands.map(band => `${band.range}: ${band.count} lot`).join(', ')}">${data.bands.map(band => `<span class="${band.color}" style="flex:${band.count}" ${band.count ? '' : 'hidden'}></span>`).join('')}</div>
    <div class="sample-legend">${[...data.bands].reverse().map(band => `<div><span class="legend-dot ${band.color}"></span><span>${band.range}<small>${band.label}</small></span><strong>${band.count}<small> lot</small></strong></div>`).join('')}</div>
    <p class="panel-footnote">Sample size alone does not ensure a representative lot sample.</p>`;
}

function attention(data) {
  const items = [];
  if (data.drafts) items.push({ icon: 'clock', className: 'draft', title: `${data.drafts} analyses are still drafts`, text: 'Resume unfinished inspections.', action: 'Continue', href: '/history?tab=draft' });
  if (data.lowSample) items.push({ icon: 'warning', className: 'limited', title: `${data.lowSample} lots have fewer than 50 beans`, text: 'Excluded from fermentation statistics.', action: 'View', href: '/history?sample=under50' });
  if (data.highExclusion) items.push({ icon: 'sample', className: 'small', title: `${data.highExclusion} lots have a high proportion of excluded objects`, text: 'More than 25% of detected objects were excluded.', action: 'Review', href: '/history?attention=exclusions' });
  return items.length ? `<div class="attention-list">${items.map(item => `<a class="attention-row" href="${item.href}"><span class="attention-icon ${item.className}">${icon(item.icon)}</span><span class="attention-copy"><strong>${item.title}</strong><small>${item.text}</small></span><span class="attention-action">${item.action}${icon('chevron')}</span></a>`).join('')}</div>` : `<div class="empty-attention">${icon('check')}<div><strong>No follow-up needed</strong><p>Inspection reminders appear here.</p></div></div>`;
}

function recent(data) {
  if (!data.recent.length) return `<div class="empty-recent">${icon('box')}<h3>No saved analyses yet</h3><p>Start an analysis to record your first lot inspection.</p><a class="text-link" href="/analysis/new">Start analysis ${icon('arrow')}</a></div>`;
  return `<div class="recent-list">${data.recent.map(lot => `<a class="lot-card" href="/lots/${lot.lotId}">
    <div class="lot-top"><span class="lot-avatar">${icon('box')}</span><div><strong>${escapeHtml(lot.supplier.name)}</strong><span class="lot-id">${escapeHtml(lot.id)}</span></div>${icon('chevron')}</div>
    <div class="lot-result"><strong>${Math.round(lot.percent)}<span>%</span></strong><span>Well<br>fermented</span><span class="lot-date">${shortDate(lot.date)}<small>${lot.weight === null ? 'Weight not recorded' : `${number(lot.weight)} kg`}</small></span></div>
    <div class="composition" role="img" aria-label="${Math.round(lot.percent)}% well fermented, ${100 - Math.round(lot.percent)}% poorly fermented"><span style="width:${lot.percent}%"></span></div>
    <div class="lot-bottom"><span class="sample-badge ${lot.usable < 50 ? 'limited' : 'sufficient'}">${lot.usable < 50 ? icon('warning') : icon('check')}${lot.usable} beans</span><span>${lot.usable < 50 ? 'Excluded from statistics' : `Revision ${lot.revision}`}</span></div>
  </a>`).join('')}</div>`;
}

export async function renderHome(container, onUrlChange = () => {}, retainContent = false) {
  const params = new URLSearchParams(location.search);
  const period = periods.find(item => item.id === params.get('period')) || periods[0];
  container.className = 'home-page';
  if (retainContent && container.querySelector('.period-control')) {
    container.setAttribute('aria-busy', 'true');
    const control = container.querySelector('.period-control');
    control.dataset.active = String(periods.findIndex(item => item.id === period.id));
    control.querySelectorAll('[data-period]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.period === period.id)));
  } else {
    container.innerHTML = '<p class="loading-state" role="status">Loading overview…</p>';
  }
  let data;
  try {
    data = fromDatabase(await api(`/dashboard?period=${period.id}`), period);
  } catch (exc) {
    const requested = periods.find(item => item.id === new URLSearchParams(location.search).get('period')) || periods[0];
    if (location.pathname !== '/' || requested.id !== period.id) return;
    container.removeAttribute('aria-busy');
    container.innerHTML = `<div class="load-error" role="alert"><h2>Unable to load overview</h2><p>${escapeHtml(exc.message)}</p><button class="secondary-button" id="retry-home">Retry</button></div>`;
    container.querySelector('#retry-home').addEventListener('click', () => renderHome(container, onUrlChange));
    return;
  }
  const activePeriod = periods.find(item => item.id === new URLSearchParams(location.search).get('period')) || periods[0];
  if (location.pathname !== '/' || activePeriod.id !== period.id) return;
  container.className = 'home-page';
  container.innerHTML = `
    <div class="preview-strip"><span><span class="preview-dot"></span>Your account data · refreshed when this page opens</span></div>
    <section class="welcome" aria-labelledby="home-title"><div><p class="eyebrow">YOUR COCOA QUALITY OVERVIEW</p><h1 id="home-title">Clearer insight into every lot.</h1><p>Track inspections and understand fermentation across your lots.</p></div><span class="welcome-date">${new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'long', year: 'numeric' }).format(data.today)}</span></section>
    <section class="new-analysis"><div class="hero-icon">${icon(data.activeSuppliers ? 'sample' : 'suppliers')}</div><div class="hero-copy"><h2>${data.activeSuppliers ? 'Inspect an incoming lot.' : 'Add a supplier first.'}</h2><p>${data.activeSuppliers ? 'Select a supplier, enter lot details, and photograph the cut-test sample.' : 'Each inspection is linked to a supplier. Add your first supplier to get started.'}</p></div><a class="hero-button" href="/analysis/new">${icon('plus')}${data.activeSuppliers ? 'New lot analysis' : 'Add supplier'}${icon('arrow')}</a></section>
    <section aria-labelledby="overview-title"><div class="section-heading overview-heading"><div><h2 id="overview-title">Inspection overview</h2><p id="period-range">${data.range}</p></div><div class="period-control" role="group" aria-label="Overview period" data-active="${periods.findIndex(item => item.id === data.period.id)}">${periods.map(period => `<button data-period="${period.id}" aria-pressed="${period.id === data.period.id}">${period.label}</button>`).join('')}</div></div>
      <div class="metrics">
        ${metric('box', 'Lots analyzed', data.lotCount, 'lot', 'Finalized results · current revisions')}
        ${metric('trend', 'Average well-fermented beans', data.mean === null ? '—' : number(data.mean), data.mean === null ? '' : '%', data.mean === null ? 'No eligible data yet' : `Average per lot · ${data.eligible.length} eligible lots`, 'metric-green')}
        ${metric('weight', 'Recorded lot weight', number(data.weight), 'kg', `${data.weightCount} of ${data.lotCount} lots have a recorded weight`)}
        ${metric('sample', 'Samples ≥300 beans', data.sufficient, `/ ${data.lotCount} lot`, 'Meets sample-size reference')}
      </div>
    </section>
    <div class="chart-layout"><section class="panel trend-panel" aria-labelledby="trend-title"><div class="panel-heading"><div><h2 id="trend-title">Fermentation trends</h2><p>Each point represents one eligible lot.</p></div>${icon('trend')}</div>${trend(data)}</section>
      <section class="panel sample-panel" aria-labelledby="sample-title"><div class="panel-heading"><div><h2 id="sample-title">Sample sufficiency</h2><p>Bean counts across lots.</p></div></div>${sampleQuality(data)}</section></div>
    <section class="attention-section" aria-labelledby="attention-title"><div class="section-heading"><div class="title-with-count"><h2 id="attention-title">Needs attention</h2>${data.drafts || data.lowSample || data.highExclusion ? '<span class="attention-indicator" aria-label="Follow-up needed"></span>' : ''}</div><span class="section-note">Drafts shown across all periods</span></div>${attention(data)}</section>
    <section aria-labelledby="recent-title"><div class="section-heading"><h2 id="recent-title">Recent analyses</h2><a class="text-link" href="/history">View all${icon('arrow')}</a></div>${recent(data)}</section>
    <footer class="home-footer">${icon('leaf')}<p>Supporting cocoa quality control.<br><span>Visual fermentation analysis does not replace comprehensive quality testing or SNI testing.</span></p></footer>`;
  container.removeAttribute('aria-busy');

  function updateQuery(key, value, focusSelector) {
    const url = new URL(location.href);
    url.searchParams.set(key, value);
    history.replaceState({}, '', url);
    onUrlChange(url.pathname + url.search);
    renderHome(container, onUrlChange, true).then(() => {
      if (location.pathname === '/' && new URLSearchParams(location.search).get(key) === value) {
        container.querySelector(focusSelector)?.focus({ preventScroll: true });
      }
    });
  }
  container.querySelectorAll('[data-period]').forEach(button => button.addEventListener('click', () => {
    updateQuery('period', button.dataset.period, `[data-period="${button.dataset.period}"]`);
  }));
  container.querySelectorAll('[data-lot]').forEach(button => button.addEventListener('click', () => {
    const lot = data.eligible.find(item => item.id === button.dataset.lot);
    container.querySelectorAll('[data-lot]').forEach(point => point.setAttribute('aria-pressed', String(point === button)));
    container.querySelector('#chart-selection').innerHTML = `${icon('box')}<span><strong>${escapeHtml(lot.supplier.name)} · ${number(lot.percent)}%</strong><small>${escapeHtml(lot.id)} · ${shortDate(lot.date)}</small></span><a class="text-link" href="/history?lot=${escapeHtml(lot.id)}" aria-label="View lot ${escapeHtml(lot.id)}">${icon('arrow')}</a>`;
  }));
}

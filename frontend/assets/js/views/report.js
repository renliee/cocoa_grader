import { api, escapeHtml } from '../api.js';

const reasons = {
  edge_cut: 'Cut off at edge',
  unresolved_cluster: 'Unresolved cluster',
  fragment: 'Fragment',
  suspicious_geometry: 'Irregular geometry',
};

export async function renderPublicReport(container, token, label = false) {
  const route = `/report/${token}${label ? '/label' : ''}`;
  container.className = 'public-report-page';
  container.innerHTML = '<p class="loading-state" role="status">Loading report…</p>';
  let data;
  try { data = await api(`/reports/${token}`); }
  catch (exc) {
    if (location.pathname !== route) return;
    container.innerHTML = `<div class="load-error" role="alert"><h1>Unable to open report</h1><p>${escapeHtml(exc.message)}</p></div>`;
    return;
  }
  if (location.pathname !== route) return;
  const item = data.report;
  const warning = item.usable_count < 50
    ? 'Very limited sample. This result is excluded from summary statistics.'
    : item.usable_count < 300
      ? 'Below the 300-bean reference. Treat this result as indicative.'
      : 'The 300-bean reference is met; sample representativeness still matters.';
  if (label) {
    container.innerHTML = `<section class="print-label"><img class="print-label-logo" src="/assets/report-logo.png" alt="KakaoLens"><p class="eyebrow">LOT LABEL</p><h1>${escapeHtml(item.human_id)}</h1><p>${escapeHtml(item.supplier_name)}</p><p>${item.weight_kg ? `${escapeHtml(item.weight_kg)} kg · ` : ''}${item.usable_count} beans analyzed</p><strong>${item.percent_rounded.fermented}% / ${item.percent_rounded.poorly_fermented}%</strong>
      ${data.lan_ready ? `<img src="/api/reports/${token}/qr" alt="QR code for the public report">` : '<p>Open KakaoLens using this computer’s LAN address, then reopen the label to display its QR code.</p>'}
      <p>Revision ${item.revision_number}</p><button class="secondary-button no-print" id="print-label">Print label</button></section>`;
    container.querySelector('#print-label').addEventListener('click', () => window.print());
    return;
  }
  container.innerHTML = `<header class="report-header"><img class="report-brand-logo" src="/assets/report-logo.png" alt="KakaoLens"><p>Fermentation analysis report</p></header>
    <div class="public-report-content"><p class="eyebrow">LOT INSPECTION EVIDENCE</p><h1>${escapeHtml(item.human_id)}</h1>
    <section class="workflow-card report-identity"><h2>Lot details</h2><dl><div><dt>Supplier</dt><dd>${escapeHtml(item.supplier_name)}</dd></div><div><dt>Analysis date</dt><dd>${escapeHtml(new Date(item.analysis_date).toLocaleString('en-GB'))}</dd></div><div><dt>Finalized revision</dt><dd>${item.revision_number}</dd></div><div><dt>Recorded weight</dt><dd>${item.weight_kg ? `${escapeHtml(item.weight_kg)} kg` : 'Not recorded'}</dd></div></dl></section>
    <section class="report-metric"><span>Well fermented</span><strong>${item.percent_rounded.fermented}%</strong><p>${item.counts.fermented} of ${item.usable_count} analyzed beans</p></section>
    <div class="report-two-stats"><article><span>Poorly fermented</span><strong>${item.percent_rounded.poorly_fermented}%</strong><p>${item.counts.poorly_fermented} beans</p></article><article><span>Excluded objects</span><strong>${item.excluded_count}</strong><p>excluded from classification</p></article></div>
    <section class="workflow-card report-quality"><h2>Sample sufficiency</h2><strong>${escapeHtml(item.sample_band.label)}</strong><p>${item.usable_count} beans analyzed from ${item.detected_count} detected candidates.</p><p class="report-warning">${warning}</p></section>
    <details class="workflow-card report-exclusions"><summary>Excluded object breakdown</summary>${Object.entries(item.exclusion_reasons).length ? `<ul>${Object.entries(item.exclusion_reasons).map(([key,count]) => `<li>${escapeHtml(reasons[key] || key)}: ${count}</li>`).join('')}</ul>` : '<p>No objects excluded.</p>'}</details>
    <section class="report-evidence"><h2>Annotated photos</h2><p>All photos used in this revision are shown.</p>${item.photos.map((photo,index) => `<article class="workflow-card"><div class="report-photo-heading"><strong>Photo ${index+1} / ${item.photos.length}</strong><span>${photo.usable_count} beans analyzed</span></div><img loading="lazy" src="${photo.image_url}" alt="Annotated result for photo ${index+1}"><p>${photo.fermented_count} well fermented · ${photo.poorly_count} poorly fermented · ${photo.excluded_count} excluded</p></article>`).join('')}</section>
    <section class="workflow-card report-limit"><h2>Analysis scope</h2><p>KakaoLens assesses visual fermentation characteristics. This report is not a comprehensive quality assessment or an official SNI test.</p></section>
    <div class="report-download" id="report-download"></div></div>`;
  const download = container.querySelector('#report-download');
  function drawDownload() {
    download.innerHTML = data.pdf_status === 'complete'
      ? `<a class="primary-button" href="/api/reports/${token}/pdf">Download PDF Report</a>`
      : data.pdf_status === 'failed'
        ? `<p role="alert">PDF export failed: ${escapeHtml(data.pdf_error || 'The lot owner needs to review the evidence.')}</p>`
        : '<p role="status">Preparing PDF… The digital report and photos remain available.</p>';
  }
  drawDownload();
  async function pollPdf() {
    if (location.pathname !== route || data.pdf_status === 'complete' || data.pdf_status === 'failed') return;
    try { data = await api(`/reports/${token}`); drawDownload(); }
    catch { download.innerHTML = '<p role="alert">Unable to refresh PDF status. Reload to retry.</p>'; return; }
    if (data.pdf_status === 'queued' || data.pdf_status === 'running') setTimeout(pollPdf, 1300);
  }
  if (data.pdf_status === 'queued' || data.pdf_status === 'running') setTimeout(pollPdf, 1300);
}

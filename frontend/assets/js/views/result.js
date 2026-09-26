import { api, escapeHtml, formatNumber } from '../api.js';
import { icon } from '../components/icons.js';
import { createReportDialog } from './report-share.js';

const activePolls = new Map();

function resultPercent(result) {
  return new Intl.NumberFormat('en-GB', { maximumFractionDigits: 1 }).format(result.percent_exact);
}

export async function renderLotDetail(container, lotId, navigate, revisionId = null) {
  return renderResult(container, lotId, navigate, true, revisionId);
}

export async function renderResult(container, draftId, navigate, finalized = false, revisionId = null) {
  const routePath = finalized ? revisionId ? `/lots/${draftId}/revisions/${revisionId}` : `/lots/${draftId}` : `/analysis/${draftId}/result`;
  if (location.pathname !== routePath) return;
  container.className = 'workflow-page result-page';
  container.innerHTML = '<p class="loading-state" role="status">Loading analysis results…</p>';
  let draft, result, revisions;
  try {
    if (finalized) {
      const [detail, history] = await Promise.all([
        api(revisionId ? `/lots/${draftId}/revisions/${revisionId}` : `/lots/${draftId}`),
        api(`/lots/${draftId}/revisions`),
      ]);
      draft = detail.lot; result = detail.analysis;
      revisions = history;
    } else {
      [draft, result] = await Promise.all([api(`/drafts/${draftId}`), api(`/drafts/${draftId}/result`)]);
    }
  } catch (exc) {
    if (location.pathname !== routePath) return;
    container.innerHTML = `<div class="load-error" role="alert"><h2>Unable to load results</h2><p>${escapeHtml(exc.message)}</p><a class="secondary-button" href="/history${finalized ? '' : '?tab=draft'}">Back ke ${finalized ? 'History' : 'Draft'}</a></div>`;
    return;
  }
  if (location.pathname !== routePath) return;
  if (!finalized && !draft.supplier_id) { navigate(`/analysis/${draftId}/lot`, true); return; }
  if (result.status === 'queued' || result.status === 'processing') {
    container.innerHTML = `<div class="analysis-running"><span class="loading-spinner" aria-hidden="true"></span><p class="eyebrow">ANALYSIS IN PROGRESS</p><h1>Analyzing fermentation composition.</h1><p>${result.usable_count} beans of ${result.photo_count} photos are being analyzed. Your draft and sample are saved.</p><a class="text-link" href="/history?tab=draft">Resume later from Drafts</a></div>`;
    const previous = activePolls.get(draftId);
    if (previous) clearTimeout(previous);
    activePolls.set(draftId, setTimeout(() => renderResult(container, draftId, navigate), 1000));
    return;
  }
  activePolls.delete(draftId);
  if (result.status === 'failed') {
    container.innerHTML = `<div class="workflow-top"><a class="back-link" href="/analysis/${draftId}/sample">${icon('arrow')}Back to sample</a><p class="eyebrow">ANALYSIS INCOMPLETE</p><h1>Your draft and precheck results are saved.</h1><p>${escapeHtml(result.error_text || 'Analysis failed. Check the connection and model availability, then retry.')}</p><button class="primary-button" id="retry-analysis">Retry</button></div>`;
    container.querySelector('#retry-analysis').addEventListener('click', async event => {
      event.currentTarget.disabled = true;
      try {
        await api(`/drafts/${draftId}/analyze`, { method: 'POST', body: {
          expected_input_version: draft.input_version, confirm_small_sample: true,
        } });
        renderResult(container, draftId, navigate);
      } catch (exc) {
        event.currentTarget.disabled = false;
        const msg = document.createElement('p');
        msg.className = 'form-error'; msg.setAttribute('role', 'alert'); msg.textContent = exc.message;
        event.currentTarget.after(msg);
      }
    });
    return;
  }
  if (!result.result) {
    container.innerHTML = `<div class="load-error"><h2>No results yet</h2><p>Select a ready sample and run the analysis.</p><a class="primary-button" href="/analysis/${draftId}/sample">Review sample ${icon('arrow')}</a></div>`;
    return;
  }
  const data = result.result;
  const isCurrent = finalized && draft.id === (draft.current_revision_id || revisions.current_revision_id);
  let selected = 0;
  container.innerHTML = `<div class="workflow-top"><a class="back-link" href="${finalized ? '/history' : `/analysis/${draftId}/sample`}">${icon('arrow')}${finalized ? 'History' : 'Review sample'}</a><p class="eyebrow">ANALYSIS RESULTS</p><h1>Sample fermentation composition.</h1><p>Results show the composition of the analyzed beans. They support quality control and do not determine whether a lot should be accepted or rejected.</p></div>
    <ol class="wizard-steps" aria-label="Analysis steps"><li><span>1</span>Lot</li><li><span>2</span>Sample</li><li aria-current="step"><span>3</span>Results</li></ol>
    <section class="lot-identity"><span>${finalized ? `Final · Revision ${draft.revision_number}${isCurrent ? ' · Current' : ' · Historical revision'}` : `Draft${draft.base_revision_id ? ` · Revision ${draft.next_revision_number}` : ''} · not finalized`}</span><strong>${escapeHtml(draft.human_id)}</strong><p>${escapeHtml(draft.supplier_name || 'Supplier not recorded')}${draft.weight_kg ? ` · ${formatNumber(draft.weight_kg)} kg` : ''}</p>${draft.notes ? `<p>${escapeHtml(draft.notes)}</p>` : ''}</section>
    ${finalized ? '<p class="finalized-notice" role="status">This analysis is finalized and saved in History.</p>' : ''}
    <section class="result-highlight"><span>Well fermented</span><strong>${resultPercent(data)}<small>%</small></strong><p>${data.counts.fermented} of ${data.usable_count} beans</p></section>
    <div class="composition result-composition" role="img" aria-label="${data.percent_rounded.fermented}% well fermented, ${data.percent_rounded.poorly_fermented}% poorly fermented"><span style="width:${data.percent_rounded.fermented}%"></span></div>
    <section class="result-counts"><article><span>Poorly fermented</span><strong>${data.percent_rounded.poorly_fermented}%</strong><p>${data.counts.poorly_fermented} beans</p></article><article><span>Beans analyzed</span><strong>${data.usable_count}</strong><p>from ${data.photos.length} photos</p></article><article><span>Excluded candidates</span><strong>${data.excluded_count}</strong><p>excluded from fermentation percentages</p></article></section>
    <section class="sample-overview result-sufficiency"><div><span class="eyebrow">SAMPLE SUFFICIENCY</span><strong>${escapeHtml(data.sample_band.label)}</strong><p>${data.usable_count} / 300-bean reference. ${escapeHtml(data.sample_band.description)}</p></div></section>
    <section class="workflow-card result-visual"><div class="sample-heading"><div><h2>Annotated photos</h2><p>Green marks well-fermented beans; red marks poorly fermented beans.</p></div><span class="sample-position" id="result-position"></span></div><div id="result-image-slot"></div></section>
    ${(data.notes || []).length ? `<section class="result-notes"><h2>Notes</h2><ul>${data.notes.map(note => `<li>${escapeHtml(note)}</li>`).join('')}</ul></section>` : ''}
    <p class="result-disclaimer">${escapeHtml(data.disclaimer)}</p>
    <p class="form-error" id="finalize-error" role="alert" hidden></p>
    <div class="result-actions result-decision-actions">${finalized
      ? `<button class="primary-button" id="share-report">Share / Export Report</button>${isCurrent ? '<button class="secondary-button" id="revise-result">Revise analysis</button>' : '<button class="secondary-button" id="activate-result">Set as current revision</button>'}<a class="secondary-button" href="/history">Back to History</a>`
      : `<button class="primary-button" id="finalize-result">${draft.base_revision_id ? `Save as revision ${draft.next_revision_number}` : 'Finalize analysis'}</button><a class="secondary-button" href="/analysis/${draftId}/sample">Edit photos / sample</a><a class="secondary-button" href="/analysis/${draftId}/lot">Edit lot details</a><button class="finish-without-save" id="finish-unsaved">Discard draft</button>`}</div>
    ${finalized ? `<section class="revision-history workflow-card"><h2>Revision history</h2><p>Statistics use one current revision. Reports for previous revisions remain available.</p><div>${revisions.items.map(item => `<a href="/lots/${draftId}/revisions/${item.id}" ${item.id === draft.id ? 'aria-current="page"' : ''}><strong>Revision ${item.revision_number}${item.current ? ' · Current' : ''}</strong><span>${escapeHtml(new Date(item.finalized_at).toLocaleString('en-GB'))} · ${item.usable_count} beans</span></a>`).join('')}</div></section>` : ''}
    <dialog class="mobile-dialog" id="revision-action-dialog"><h2 id="revision-action-title"></h2><p id="revision-action-copy"></p><p class="form-error" id="revision-action-error" role="alert" hidden></p><div class="dialog-actions"><button class="secondary-button" id="revision-action-cancel">Cancel</button><button class="primary-button" id="revision-action-confirm">Next</button></div></dialog>
    <dialog class="mobile-dialog" id="finish-dialog"><form method="dialog"><h2>Discard this draft?</h2><p>Draft ${escapeHtml(draft.human_id)} and its photos will be permanently deleted. Results have not been finalized.</p><p class="form-error" id="finish-error" hidden></p><div class="dialog-actions"><button class="secondary-button" value="cancel">Back</button><button class="danger-button" value="discard">Discard results</button></div></form></dialog>`;
  const slot = container.querySelector('#result-image-slot');
  const dialog = container.querySelector('#finish-dialog');
  function drawImage() {
    const photo = data.photos[selected];
    container.querySelector('#result-position').textContent = `${selected + 1} / ${data.photos.length}`;
    slot.innerHTML = `<div class="photo-toolbar result-photo-toolbar"><button class="photo-arrow" id="result-prev" ${selected === 0 ? 'disabled' : ''} aria-label="Previous photo">‹</button><div class="result-photo-title"><strong>Photo ${selected + 1}</strong><span>${photo.usable_count} beans analyzed</span></div><button class="photo-arrow" id="result-next" ${selected >= data.photos.length - 1 ? 'disabled' : ''} aria-label="Next photo">›</button></div><img class="result-annotated" src="/api/runs/${result.id}/photos/${photo.photo_id}/image" alt="Fermentation classification for photo ${selected + 1}"><div class="photo-counts"><span><strong>${photo.fermented_count}</strong> well fermented</span><span><strong>${photo.poorly_count}</strong> poorly fermented</span><span><strong>${photo.excluded_count}</strong> excluded</span></div>`;
    slot.querySelector('#result-prev').addEventListener('click', () => { selected--; drawImage(); });
    slot.querySelector('#result-next').addEventListener('click', () => { selected++; drawImage(); });
  }
  drawImage();
  container.querySelector('#finalize-result')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    const error = container.querySelector('#finalize-error');
    button.disabled = true; button.textContent = 'Finalizing…'; error.hidden = true;
    try {
      const saved = await api(`/drafts/${draftId}/finalize`, { method: 'POST', body: { expected_version: draft.draft_version } });
      navigate(`/lots/${saved.lot_id}`, true);
    } catch (exc) {
      error.textContent = exc.message; error.hidden = false;
      button.disabled = false; button.textContent = draft.base_revision_id ? `Save as revision ${draft.next_revision_number}` : 'Finalize analysis';
    }
  });
  container.querySelector('#finish-unsaved')?.addEventListener('click', () => {
    dialog.returnValue = 'cancel'; dialog.showModal();
  });
  dialog.addEventListener('close', async () => {
    if (dialog.returnValue !== 'discard') return;
    try {
      await api(`/drafts/${draftId}`, { method: 'DELETE' });
      navigate('/');
    } catch (exc) {
      container.querySelector('#finish-error').textContent = exc.message;
      container.querySelector('#finish-error').hidden = false;
      dialog.returnValue = 'cancel'; dialog.showModal();
    }
  });
  if (finalized) {
    const actionDialog = container.querySelector('#revision-action-dialog');
    const actionButton = container.querySelector('#revision-action-confirm');
    const actionError = container.querySelector('#revision-action-error');
    let action = null;
    function confirmAction(kind) {
      action = kind;
      actionError.hidden = true;
      container.querySelector('#revision-action-title').textContent = kind === 'revise' ? 'Revise analysis?' : 'Set this revision as current?';
      container.querySelector('#revision-action-copy').textContent = kind === 'revise'
        ? 'Previous results remain available. The revision draft opens at step 2, Sample.'
        : 'Statistics and the lot overview will use this revision. Newer revisions remain available.';
      actionButton.textContent = kind === 'revise' ? 'Continue to Sample' : 'Set as current';
      actionDialog.showModal();
    }
    container.querySelector('#revise-result')?.addEventListener('click', () => confirmAction('revise'));
    container.querySelector('#activate-result')?.addEventListener('click', () => confirmAction('activate'));
    container.querySelector('#revision-action-cancel').addEventListener('click', () => actionDialog.close());
    actionButton.addEventListener('click', async () => {
      actionButton.disabled = true; actionError.hidden = true;
      try {
        if (action === 'revise') {
          const working = await api(`/lots/${draftId}/revisions`, { method: 'POST', body: {
            expected_lot_version: revisions.lot_version,
          } });
          actionDialog.close(); navigate(`/analysis/${working.id}/sample`);
        } else {
          await api(`/lots/${draftId}/revisions/${draft.id}/activate`, { method: 'POST', body: {
            expected_lot_version: revisions.lot_version,
          } });
          actionDialog.close(); navigate(`/lots/${draftId}`, true);
        }
      } catch (exc) { actionError.textContent = exc.message; actionError.hidden = false; }
      finally { actionButton.disabled = false; }
    });
    const report = createReportDialog(container, {
      lotId: draftId, revisionId: draft.id, revisionNumber: draft.revision_number,
    });
    container.querySelector('#share-report').addEventListener('click', report.open);
    if (new URLSearchParams(location.search).get('report') === '1') report.open();
  }
}

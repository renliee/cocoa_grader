import { api, escapeHtml, formatNumber, shortDate } from '../api.js';
import { icon } from '../components/icons.js';
import { createReportDialog } from './report-share.js';

export async function renderHistory(container, navigate) {
  container.className = 'history-page';
  container.innerHTML = '<p class="loading-state" role="status">Loading history…</p>';
  let drafts, completed;
  try {
    [drafts, completed] = await Promise.all([api('/drafts'), api('/lots')]);
  } catch (exc) {
    if (location.pathname !== '/history') return;
    container.innerHTML = `<div class="load-error" role="alert"><h2>Unable to load history</h2><p>${escapeHtml(exc.message)}</p><button class="secondary-button" id="retry-history">Retry</button></div>`;
    container.querySelector('#retry-history').addEventListener('click', () => renderHistory(container, navigate));
    return;
  }
  if (location.pathname !== '/history') return;
  const requestedTab = new URLSearchParams(location.search).get('tab');
  const supplierFilter = new URLSearchParams(location.search).get('supplier');
  const supplierName = [...completed.items, ...drafts.items].find(item => item.supplier_id === supplierFilter)?.supplier_name;
  let tab = requestedTab === 'draft' ? 'draft' : 'completed';
  container.innerHTML = `<div class="history-heading"><div><p class="eyebrow">INSPECTION RECORDS</p><h1>Analysis history</h1><p>Review saved results and resume unfinished analyses.</p></div><button class="primary-button" id="choose-revision" ${completed.items.length ? '' : 'disabled'}>Revise lot</button></div>
    <div class="history-controls"><div class="history-tabs" role="group" aria-label="Record type"><button data-tab="completed">Finalized <span>${completed.items.length}</span></button><button data-tab="draft">Draft <span>${drafts.items.length}</span></button></div><label class="search-field"><span class="sr-only">Search lot ID, supplier, or notes</span><input id="history-search" type="search" placeholder="Search lot ID or supplier" value="${escapeHtml(new URLSearchParams(location.search).get('lot') || '')}"></label></div>
    ${supplierFilter ? `<div class="history-filter-note">Supplier: <strong>${escapeHtml(supplierName || 'Previous selection')}</strong><a href="/history">Clear filter</a></div>` : ''}
    <p class="history-count" id="history-count"></p><div id="history-list" class="history-list"></div>
    <dialog class="mobile-dialog" id="delete-draft-dialog"><form method="dialog"><h2>Delete this draft?</h2><p><strong id="delete-draft-name"></strong><br>The unfinished analysis and its saved photos will be permanently deleted.</p><p class="form-error" id="delete-draft-error" hidden></p><div class="dialog-actions"><button class="secondary-button" value="cancel">Cancel</button><button class="danger-button" value="delete">Delete draft</button></div></form></dialog>
    <dialog class="mobile-dialog revision-choice" id="revision-choice"><h2>Select a lot to revise</h2><p>Previous results remain available. The revision draft opens at step 2, Sample.</p><div id="revision-choices"></div><button class="secondary-button" id="close-revision-choice">Cancel</button></dialog>
    <dialog class="mobile-dialog" id="revision-confirm"><h2>Revise lot <span id="revision-name"></span>?</h2><p>Previous results remain available. Saving your changes creates a new revision.</p><p class="form-error" id="revision-error" role="alert" hidden></p><div class="dialog-actions"><button class="secondary-button" id="cancel-revision">Cancel</button><button class="primary-button" id="start-revision">Continue to Sample</button></div></dialog>`;
  const tabs = container.querySelectorAll('[data-tab]');
  const search = container.querySelector('#history-search');
  const list = container.querySelector('#history-list');
  const count = container.querySelector('#history-count');
  const deleteDialog = container.querySelector('#delete-draft-dialog');
  const choiceDialog = container.querySelector('#revision-choice');
  const confirmDialog = container.querySelector('#revision-confirm');
  let selectedDraft = null;
  let selectedLot = null;
  function draw() {
    tabs.forEach(button => button.setAttribute('aria-pressed', String(button.dataset.tab === tab)));
    const term = search.value.trim().toLocaleLowerCase('en-GB');
    const all = tab === 'draft' ? drafts.items : completed.items;
    const items = all.filter(item => !supplierFilter || item.supplier_id === supplierFilter)
      .filter(item => [item.human_id, item.supplier_name, item.supplier_code, item.notes]
      .some(value => String(value ?? '').toLocaleLowerCase('en-GB').includes(term)));
    count.textContent = `${items.length} ${tab === 'draft' ? 'draft' : 'finalized lots'}${term ? ' found' : ''}`;
    if (!items.length) {
      list.innerHTML = `<div class="history-empty">${icon(tab === 'draft' ? 'clock' : 'box')}<h2>${term ? 'No matching results' : tab === 'draft' ? 'No drafts' : 'No finalized analyses yet'}</h2><p>${term ? 'Try a different search.' : tab === 'draft' ? 'Unfinished analyses are saved here.' : 'Finalize your first lot before creating a revision. Start a new lot from Home.'}</p></div>`;
      return;
    }
    list.innerHTML = items.map(item => tab === 'draft'
      ? `<article class="history-card"><div class="history-card-main"><span class="history-kind">Draft · ${item.selected_run_id ? 'results ready for review' : item.wizard_step === 'lot' ? 'no photos yet' : 'review sample'}</span><h2>${escapeHtml(item.human_id)}</h2><p>${escapeHtml(item.supplier_name || 'Select a supplier to continue')} · ${shortDate(item.created_at)}</p></div><div class="history-card-side"><a class="text-link" href="${!item.supplier_id || item.wizard_step === 'lot' ? `/analysis/${item.id}/lot` : item.selected_run_id ? `/analysis/${item.id}/result` : `/analysis/${item.id}/sample`}">Continue ${icon('arrow')}</a><button class="draft-delete" data-delete-draft="${item.id}">Delete draft</button></div></article>`
      : `<article class="history-card"><div><span class="history-kind">Final · Revision ${item.revision_number}</span><h2>${escapeHtml(item.human_id)}</h2><p>${escapeHtml(item.supplier_name || 'Supplier not recorded')} · ${shortDate(item.first_finalized_at)}</p><span class="history-meta">${item.usable_count} beans${item.weight_kg ? ` · ${formatNumber(item.weight_kg)} kg` : ''}${item.eligible ? '' : ' · Excluded from statistics'}</span></div><div class="history-card-side"><strong>${formatNumber(item.percent)}%</strong><span>Well fermented</span><a class="history-action history-action-primary" href="/lots/${item.lot_id}">View results →</a><button class="secondary-button" data-revise-lot="${item.lot_id}">Revise lot</button><button class="history-action history-action-report" data-export-lot="${item.lot_id}">Export report</button></div></article>`).join('');
  }
  list.addEventListener('click', event => {
    const exportButton = event.target.closest('[data-export-lot]');
    if (exportButton) {
      const item = completed.items.find(entry => entry.lot_id === exportButton.dataset.exportLot);
      if (!item) return;
      const report = createReportDialog(container, {
        lotId: item.lot_id, revisionId: item.revision_id, revisionNumber: item.revision_number,
      });
      report.dialog.addEventListener('close', () => report.dialog.remove(), { once: true });
      report.open();
      return;
    }
    const revise = event.target.closest('[data-revise-lot]');
    if (revise) { openRevision(revise.dataset.reviseLot); return; }
    const button = event.target.closest('[data-delete-draft]');
    if (!button) return;
    selectedDraft = drafts.items.find(item => item.id === button.dataset.deleteDraft);
    if (!selectedDraft) return;
    container.querySelector('#delete-draft-name').textContent = selectedDraft.human_id;
    container.querySelector('#delete-draft-error').hidden = true;
    deleteDialog.returnValue = 'cancel';
    deleteDialog.showModal();
  });
  function openRevision(lotId) {
    selectedLot = completed.items.find(item => item.lot_id === lotId);
    if (!selectedLot) return;
    if (choiceDialog.open) choiceDialog.close();
    container.querySelector('#revision-name').textContent = selectedLot.human_id;
    container.querySelector('#revision-error').hidden = true;
    confirmDialog.showModal();
  }
  container.querySelector('#choose-revision').addEventListener('click', () => {
    if (completed.items.length === 1) { openRevision(completed.items[0].lot_id); return; }
    container.querySelector('#revision-choices').innerHTML = completed.items.map(item =>
      `<button class="revision-choice-item" data-choose-lot="${item.lot_id}"><strong>${escapeHtml(item.human_id)}</strong><span>${escapeHtml(item.supplier_name)} · Revision ${item.revision_number}</span></button>`).join('');
    choiceDialog.showModal();
  });
  container.querySelector('#revision-choices').addEventListener('click', event => {
    const button = event.target.closest('[data-choose-lot]');
    if (button) openRevision(button.dataset.chooseLot);
  });
  container.querySelector('#close-revision-choice').addEventListener('click', () => choiceDialog.close());
  container.querySelector('#cancel-revision').addEventListener('click', () => confirmDialog.close());
  container.querySelector('#start-revision').addEventListener('click', async event => {
    if (!selectedLot) return;
    const button = event.currentTarget;
    const error = container.querySelector('#revision-error');
    button.disabled = true; button.textContent = 'Preparing draft…'; error.hidden = true;
    try {
      const detail = await api(`/lots/${selectedLot.lot_id}`);
      const draft = await api(`/lots/${selectedLot.lot_id}/revisions`, { method: 'POST', body: {
        expected_lot_version: detail.lot.lot_version,
      } });
      confirmDialog.close();
      navigate(`/analysis/${draft.id}/sample`);
    } catch (exc) { error.textContent = exc.message; error.hidden = false; }
    finally { button.disabled = false; button.textContent = 'Continue to Sample'; }
  });
  deleteDialog.addEventListener('close', async () => {
    if (deleteDialog.returnValue !== 'delete' || !selectedDraft) return;
    try {
      await api(`/drafts/${selectedDraft.id}`, { method: 'DELETE' });
      drafts.items = drafts.items.filter(item => item.id !== selectedDraft.id);
      container.querySelector('[data-tab="draft"] span').textContent = drafts.items.length;
      selectedDraft = null;
      draw();
    } catch (exc) {
      container.querySelector('#delete-draft-error').textContent = exc.message;
      container.querySelector('#delete-draft-error').hidden = false;
      deleteDialog.returnValue = 'cancel';
      deleteDialog.showModal();
    }
  });
  tabs.forEach(button => button.addEventListener('click', () => {
    tab = button.dataset.tab;
    const url = new URL(location.href);
    url.searchParams.set('tab', tab);
    history.replaceState({}, '', url);
    draw();
    button.focus({ preventScroll: true });
  }));
  search.addEventListener('input', draw);
  draw();
}

import { api, escapeHtml } from '../api.js';
import { icon } from '../components/icons.js';
import { setNavigationGuard } from '../router.js';

function suggestedCode(name) {
  const words = name.normalize('NFKD').replace(/[^a-zA-Z0-9 ]/g, '').trim().split(/\s+/);
  const meaningful = words.filter(word => !/^(pak|bu|bapak|ibu)$/i.test(word));
  return (meaningful[0] || words[0] || '').toUpperCase().slice(0, 4);
}

function supplierOptions(suppliers, selected) {
  return `<option value="" disabled ${selected ? '' : 'selected'}>Select supplier</option>${suppliers.map(item =>
    `<option value="${item.id}" ${item.id === selected ? 'selected' : ''}>${escapeHtml(item.name)} · ${escapeHtml(item.code)}</option>`).join('')}`;
}

function supplierForm(container, onCreated) {
  container.innerHTML = `<div class="inline-supplier"><div class="inline-heading"><h3>Add supplier</h3><p>This supplier will be available for future lots.</p></div>
    <form id="supplier-form">
      <label for="supplier-name">Supplier name</label><input id="supplier-name" name="name" required minlength="2" maxlength="80" placeholder="Example: Pak Ahmad">
      <label for="supplier-code">Supplier code</label><input id="supplier-code" name="code" required minlength="2" maxlength="8" pattern="[A-Za-z0-9]{2,8}" placeholder="AHMD" autocapitalize="characters"><small>The code appears in lot IDs and cannot be changed after the first lot is created.</small>
      <p class="form-error" id="supplier-error" role="alert" hidden></p><div class="inline-actions"><button class="secondary-button" type="button" id="cancel-supplier">Cancel</button><button class="primary-button" type="submit">Save supplier</button></div>
    </form></div>`;
  const form = container.querySelector('#supplier-form');
  const nameInput = form.querySelector('#supplier-name');
  const codeInput = form.querySelector('#supplier-code');
  let codeEdited = false;
  codeInput.addEventListener('input', () => { codeEdited = true; codeInput.value = codeInput.value.toUpperCase(); });
  nameInput.addEventListener('input', () => { if (!codeEdited) codeInput.value = suggestedCode(nameInput.value); });
  form.querySelector('#cancel-supplier').addEventListener('click', () => { container.innerHTML = ''; });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type=submit]');
    const error = form.querySelector('#supplier-error');
    error.hidden = true;
    button.disabled = true;
    button.textContent = 'Saving…';
    try {
      const supplier = await api('/suppliers', { method: 'POST', body: {
        name: nameInput.value, code: codeInput.value,
      } });
      container.innerHTML = '';
      onCreated(supplier);
    } catch (exc) {
      error.textContent = exc.message;
      error.hidden = false;
      button.disabled = false;
      button.textContent = 'Save supplier';
    }
  });
  nameInput.focus();
}

const steps = '<ol class="wizard-steps" aria-label="Analysis steps"><li aria-current="step"><span>1</span>Lot</li><li><span>2</span>Sample</li><li><span>3</span>Results</li></ol>';

export async function renderNewAnalysis(container, navigate) {
  container.className = 'workflow-page';
  container.innerHTML = '<p class="loading-state" role="status">Loading suppliers…</p>';
  let suppliers;
  try { suppliers = (await api('/suppliers')).items; }
  catch (exc) {
    if (location.pathname !== '/analysis/new') return;
    container.innerHTML = `<div class="load-error" role="alert"><h2>Unable to load suppliers</h2><p>${escapeHtml(exc.message)}</p><button class="secondary-button" id="retry-new">Retry</button></div>`;
    container.querySelector('#retry-new').addEventListener('click', () => renderNewAnalysis(container, navigate));
    return;
  }
  if (location.pathname !== '/analysis/new') return;
  container.innerHTML = `<div class="workflow-top"><a class="back-link" href="/">${icon('arrow')}Home</a><p class="eyebrow">LOT · STEP 1 OF 3</p><h1>Start with a supplier.</h1><p>Select a supplier to create the lot, then add sample photos.</p></div>${steps}
    <section class="workflow-card"><h2>Lot supplier</h2><p class="muted">Save a supplier once and select them for future inspections.</p>
      ${suppliers.length ? `<label for="new-supplier">Supplier <span class="optional">Required</span></label><select id="new-supplier">${supplierOptions(suppliers, '')}</select>` : '<div class="no-suppliers"><strong>Add a supplier first</strong><p>Each lot must be linked to a supplier so inspection results remain traceable.</p></div>'}
      <button class="secondary-button identity-add-supplier" id="add-supplier">${icon('plus')} Add new supplier</button><div id="inline-supplier"></div>
      <p class="autosave-status" id="create-status" role="status">The lot ID is generated when you select a supplier.</p><p class="form-error" id="create-error" role="alert" hidden></p><button class="secondary-button" id="retry-create" hidden>Retry lot creation</button>
    </section>`;
  let creating = false;
  let chosenSupplier = '';
  const error = container.querySelector('#create-error');
  const status = container.querySelector('#create-status');
  const retry = container.querySelector('#retry-create');
  async function begin(supplierId) {
    if (!supplierId || creating) return;
    chosenSupplier = supplierId;
    creating = true;
    error.hidden = true; retry.hidden = true;
    status.textContent = 'Creating lot…';
    container.querySelectorAll('button, select').forEach(el => { el.disabled = true; });
    setNavigationGuard(() => !creating);
    try {
      const draft = await api('/lots', { method: 'POST', body: { supplier_id: supplierId } });
      creating = false;
      setNavigationGuard(null);
      navigate(`/analysis/${draft.id}/lot`, true);
    } catch (exc) {
      error.textContent = exc.message; error.hidden = false;
      status.textContent = 'The lot could not be created.';
      retry.hidden = false;
    } finally {
      creating = false;
      container.querySelectorAll('button, select').forEach(el => { el.disabled = false; });
    }
  }
  const openSupplier = () => supplierForm(container.querySelector('#inline-supplier'), supplier => begin(supplier.id));
  container.querySelector('#new-supplier')?.addEventListener('change', event => begin(event.target.value));
  container.querySelector('#add-supplier').addEventListener('click', openSupplier);
  retry.addEventListener('click', () => begin(chosenSupplier));
  if (!suppliers.length) openSupplier();
}

export async function renderLotDraft(container, draftId, navigate) {
  const path = `/analysis/${draftId}/lot`;
  container.className = 'workflow-page';
  container.innerHTML = '<p class="loading-state" role="status">Loading lot details…</p>';
  try {
    let [draft, response] = await Promise.all([api(`/drafts/${draftId}`), api('/suppliers')]);
    if (location.pathname !== path) return;
    const suppliers = response.items;
    if (draft.supplier_id && !suppliers.some(item => item.id === draft.supplier_id)) {
      suppliers.push({ id: draft.supplier_id, name: `${draft.supplier_name} (archived)`, code: draft.supplier_code });
    }
    let chosenSupplier = draft.supplier_id || '';
    container.innerHTML = `<div class="workflow-top"><a class="back-link" href="/history?tab=draft">${icon('arrow')}Draft</a><p class="eyebrow">LOT · STEP 1 OF 3</p><h1>${draft.base_revision_id ? `Revision details ${draft.next_revision_number}` : 'Lot details'}</h1><p>${draft.base_revision_id ? `Based on revision ${draft.base_revision_number}. Supplier and lot ID are fixed; previous results remain available.` : 'Complete the incoming lot details before photographing the sample. Changes are saved automatically.'}</p></div>${steps}
      <section class="workflow-card"><div id="supplier-area"></div><div id="inline-supplier"></div>
        <div class="lot-identity identity-code"><span>Lot ID · generated automatically</span><strong id="human-id">${escapeHtml(draft.human_id)}</strong><small>Linked to the selected supplier.</small></div>
        <label for="draft-weight">Lot weight <span class="optional">Optional · kg</span></label><input id="draft-weight" inputmode="decimal" type="number" min="0.001" max="100000000" step="0.001" value="${escapeHtml(draft.weight_kg || '')}" placeholder="Example: 52">
        <small>Weight is recorded for reference. The sample-size reference remains 300 beans.</small>
        <label for="draft-notes">Lot notes <span class="optional">Optional</span></label><textarea id="draft-notes" rows="3" maxlength="1000" placeholder="Origin, condition on arrival, or other relevant details">${escapeHtml(draft.notes)}</textarea>
        <p class="autosave-status" id="save-status" role="status">Saved automatically</p><p class="form-error" id="draft-error" role="alert" hidden></p><button class="secondary-button" id="retry-save" hidden>Retry save</button>
        <div class="wizard-actions"><a class="secondary-button" href="/history?tab=draft">Resume later</a><button class="primary-button" id="continue-sample">Continue to Sample ${icon('arrow')}</button></div>
        ${draft.selected_run_id ? `<a class="text-link identity-result-link" href="/analysis/${draftId}/result">Back to results ${icon('arrow')}</a>` : ''}
      </section>`;
    const status = container.querySelector('#save-status');
    const error = container.querySelector('#draft-error');
    const retry = container.querySelector('#retry-save');
    const weight = container.querySelector('#draft-weight');
    const notes = container.querySelector('#draft-notes');
    let timer = null;
    let saving = Promise.resolve(true);
    const values = () => ({ supplier_id: chosenSupplier, weight_kg: weight.value || null, notes: notes.value });
    let lastSaved = JSON.stringify(values());
    async function persist(step = draft.wizard_step) {
      clearTimeout(timer); timer = null;
      const snapshot = values();
      const snapshotKey = JSON.stringify(snapshot);
      if (snapshotKey === lastSaved && step === draft.wizard_step) return true;
      if (!snapshot.supplier_id) {
        error.textContent = 'Select a supplier for this lot.'; error.hidden = false; return false;
      }
      status.textContent = 'Saving…'; error.hidden = true; retry.hidden = true;
      try {
        draft = await api(`/drafts/${draftId}`, { method: 'PATCH', body: {
          expected_version: draft.draft_version, ...snapshot, wizard_step: step,
        } });
        lastSaved = snapshotKey;
        container.querySelector('#human-id').textContent = draft.human_id;
        status.textContent = JSON.stringify(values()) === lastSaved ? 'Saved automatically' : 'Unsaved changes';
        return true;
      } catch (exc) {
        status.textContent = 'Not yet saved';
        error.textContent = `${exc.message} Your entries remain in the form.`;
        error.hidden = false; retry.hidden = false; return false;
      }
    }
    function enqueue(step) { saving = saving.then(() => persist(step)); return saving; }
    function schedule() {
      status.textContent = 'Unsaved changes';
      clearTimeout(timer);
      timer = setTimeout(() => enqueue(), 600);
    }
    function drawSupplier() {
      const area = container.querySelector('#supplier-area');
      area.innerHTML = draft.base_revision_id
        ? `<div class="revision-locked-supplier"><span>Lot supplier</span><strong>${escapeHtml(draft.supplier_name)}</strong><small>Revisions retain the original supplier.</small></div>`
        : `${suppliers.length ? `<label for="draft-supplier">Supplier <span class="optional">Required</span></label><select id="draft-supplier">${supplierOptions(suppliers, chosenSupplier)}</select>` : '<div class="no-suppliers"><strong>Select a supplier to continue this draft.</strong></div>'}
        <button class="secondary-button identity-add-supplier" id="add-supplier">${icon('plus')} Add new supplier</button>`;
      area.querySelector('#draft-supplier')?.addEventListener('change', event => { chosenSupplier = event.target.value; schedule(); });
      area.querySelector('#add-supplier')?.addEventListener('click', () => supplierForm(container.querySelector('#inline-supplier'), supplier => {
        suppliers.push(supplier); chosenSupplier = supplier.id; drawSupplier(); schedule();
      }));
    }
    drawSupplier();
    [weight, notes].forEach(field => {
      field.addEventListener('input', schedule);
      field.addEventListener('blur', () => { if (timer) { clearTimeout(timer); timer = null; enqueue(); } });
    });
    retry.addEventListener('click', () => enqueue());
    const beforeUnload = event => {
      if (JSON.stringify(values()) !== lastSaved || status.textContent === 'Saving…') {
        event.preventDefault(); event.returnValue = '';
      }
    };
    window.addEventListener('beforeunload', beforeUnload);
    setNavigationGuard(async destination => {
      clearTimeout(timer); timer = null;
      const toSample = destination.startsWith(`/analysis/${draftId}/sample`);
      if (toSample && !chosenSupplier) {
        error.textContent = 'Select a supplier before opening the sample.'; error.hidden = false; return false;
      }
      await saving;
      let saved;
      do { saved = await enqueue(toSample ? 'sample' : draft.wizard_step); }
      while (saved && JSON.stringify(values()) !== lastSaved);
      if (saved) window.removeEventListener('beforeunload', beforeUnload);
      return saved;
    });
    container.querySelector('#continue-sample').addEventListener('click', () => navigate(`/analysis/${draftId}/sample`));
  } catch (exc) {
    if (location.pathname !== path) return;
    container.innerHTML = `<div class="load-error" role="alert"><h2>Unable to open draft</h2><p>${escapeHtml(exc.message)}</p><button class="secondary-button" id="retry-lot">Retry</button><a class="text-link" href="/history?tab=draft">Back to History</a></div>`;
    container.querySelector('#retry-lot').addEventListener('click', () => renderLotDraft(container, draftId, navigate));
  }
}

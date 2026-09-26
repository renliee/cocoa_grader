import { api, escapeHtml } from '../api.js';
import { icon } from '../components/icons.js';

const codeFromName = name => name.normalize('NFKD').replace(/[^a-zA-Z0-9 ]/g, '').trim().split(/\s+/).filter(Boolean).filter(x => !/^(pak|bu|bapak|ibu)$/i.test(x))[0]?.slice(0, 4).toUpperCase() || 'SUPL';

export async function renderSuppliers(container) {
  container.className = 'supplier-page';
  container.innerHTML = '<p class="loading-state" role="status">Loading suppliers…</p>';
  try {
    let showArchived = false;
    let items = (await api('/suppliers?include_archived=true')).items;
    container.innerHTML = `<div class="history-heading supplier-heading"><div><p class="eyebrow">SUPPLIER DIRECTORY</p><h1>Suppliers</h1><p>Manage supplier contacts and keep inspection records organized.</p></div><button class="primary-button" id="create-supplier">${icon('plus')} Add supplier</button></div>
      <div class="supplier-tools"><label class="search-field"><span class="sr-only">Search suppliers</span><input id="supplier-search" type="search" placeholder="Search supplier name or code"></label><label class="archived-toggle"><input id="show-archived" type="checkbox"> Show archived suppliers</label></div>
      <p id="supplier-count" class="history-count"></p><div id="supplier-list" class="supplier-list"></div>
      <dialog class="mobile-dialog" id="supplier-form-dialog"><form id="supplier-form"><h2 id="supplier-form-title">Add supplier</h2><label for="supplier-name">Supplier name</label><input id="supplier-name" required minlength="2" maxlength="80" autocomplete="organization"><label for="supplier-code">Supplier code</label><input id="supplier-code" required minlength="2" maxlength="8" pattern="[A-Za-z0-9]{2,8}" autocapitalize="characters"><small>Lot IDs are generated from the supplier code.</small><label for="supplier-contact">Contact <span class="optional">Optional</span></label><input id="supplier-contact" maxlength="120" autocomplete="tel" placeholder="Phone number or contact name"><label for="supplier-notes">Notes <span class="optional">Optional</span></label><textarea id="supplier-notes" rows="3" maxlength="1000"></textarea><p class="form-error" id="supplier-form-error" role="alert" hidden></p><div class="dialog-actions"><button class="secondary-button" type="button" id="cancel-supplier-form">Cancel</button><button class="primary-button" type="submit" id="save-supplier">Save</button></div></form></dialog>
      <dialog class="mobile-dialog" id="supplier-action-dialog"><form method="dialog"><h2 id="supplier-action-title">Archive supplier?</h2><p id="supplier-action-copy"></p><p class="form-error" id="supplier-action-error" hidden></p><div class="dialog-actions"><button class="secondary-button" value="cancel">Cancel</button><button class="danger-button" value="confirm">Continue</button></div></form></dialog>`;
    const list = container.querySelector('#supplier-list');
    const search = container.querySelector('#supplier-search');
    const count = container.querySelector('#supplier-count');
    const formDialog = container.querySelector('#supplier-form-dialog');
    const form = container.querySelector('#supplier-form');
    const actionDialog = container.querySelector('#supplier-action-dialog');
    let editing = null;
    let pendingAction = null;
    function draw() {
      const term = search.value.trim().toLocaleLowerCase('en-GB');
      const visible = items.filter(item => showArchived ? Boolean(item.archived_at) : !item.archived_at)
        .filter(item => `${item.name} ${item.code} ${item.contact} ${item.notes}`.toLocaleLowerCase('en-GB').includes(term));
      count.textContent = `${visible.length} suppliers${term ? ' found' : ''}`;
      if (!visible.length) {
        list.innerHTML = `<section class="supplier-empty"><div class="scan-symbol">${icon('suppliers')}</div><h2>${term ? 'No matching suppliers' : showArchived ? 'No archived suppliers' : 'No suppliers yet'}</h2><p>${term ? 'Try a different name or code.' : showArchived ? 'Archived suppliers appear here.' : 'Add your first supplier to start inspecting lots.'}</p>${term || showArchived ? '' : '<button class="primary-button" id="empty-create">Add supplier</button>'}</section>`;
        list.querySelector('#empty-create')?.addEventListener('click', () => openForm());
        return;
      }
      list.innerHTML = visible.map(item => `<article class="supplier-card ${item.archived_at ? 'is-archived' : ''}"><div class="supplier-card-title"><span class="supplier-avatar">${escapeHtml(item.code.slice(0, 2))}</span><div><h2>${escapeHtml(item.name)}</h2><p>${escapeHtml(item.code)} · ${item.lot_count} lots recorded${item.archived_at ? ' · Archived' : ''}</p></div></div><div class="supplier-card-detail">${item.contact ? `<p><span>Contact</span>${escapeHtml(item.contact)}</p>` : ''}${item.notes ? `<p><span>Notes</span>${escapeHtml(item.notes)}</p>` : ''}</div><div class="supplier-card-actions"><a class="supplier-performance-link" href="/suppliers/${item.id}/performance">View performance</a>${item.archived_at ? `<button class="secondary-button" data-action="restore" data-id="${item.id}">Restore</button>` : `<button class="secondary-button" data-action="edit" data-id="${item.id}">Edit</button><button class="secondary-button" data-action="archive" data-id="${item.id}">Archive</button>`}${Number(item.lot_count) === 0 ? `<button class="danger-link" data-action="delete" data-id="${item.id}">Delete permanently</button>` : ''}</div></article>`).join('');
    }
    function openForm(item = null) {
      editing = item;
      container.querySelector('#supplier-form-title').textContent = item ? 'Edit supplier' : 'Add supplier';
      const name = form.querySelector('#supplier-name'); const code = form.querySelector('#supplier-code');
      name.value = item?.name || ''; code.value = item?.code || ''; code.readOnly = Boolean(item);
      delete code.dataset.edited;
      form.querySelector('#supplier-contact').value = item?.contact || '';
      form.querySelector('#supplier-notes').value = item?.notes || '';
      container.querySelector('#supplier-form-error').hidden = true;
      formDialog.showModal();
      name.focus();
    }
    container.querySelector('#create-supplier').addEventListener('click', () => openForm());
    container.querySelector('#cancel-supplier-form').addEventListener('click', () => formDialog.close());
    form.querySelector('#supplier-name').addEventListener('input', () => {
      const code = form.querySelector('#supplier-code'); if (!editing && !code.dataset.edited) code.value = codeFromName(form.querySelector('#supplier-name').value);
    });
    form.querySelector('#supplier-code').addEventListener('input', event => { event.currentTarget.value = event.currentTarget.value.toUpperCase(); event.currentTarget.dataset.edited = 'true'; });
    form.addEventListener('submit', async event => {
      event.preventDefault();
      const button = container.querySelector('#save-supplier'); const error = container.querySelector('#supplier-form-error');
      button.disabled = true; error.hidden = true;
      const body = { name: form.querySelector('#supplier-name').value, code: form.querySelector('#supplier-code').value,
        contact: form.querySelector('#supplier-contact').value, notes: form.querySelector('#supplier-notes').value };
      try {
        const saved = editing ? await api(`/suppliers/${editing.id}`, { method: 'PATCH', body: { name: body.name, contact: body.contact, notes: body.notes } })
          : await api('/suppliers', { method: 'POST', body });
        items = editing ? items.map(item => item.id === saved.id ? { ...item, ...saved } : item) : [{ ...saved, lot_count: 0 }, ...items];
        formDialog.close(); draw();
      } catch (exc) { error.textContent = exc.message; error.hidden = false; }
      finally { button.disabled = false; }
    });
    list.addEventListener('click', async event => {
      const button = event.target.closest('[data-action]'); if (!button) return;
      const item = items.find(row => row.id === button.dataset.id); if (!item) return;
      if (button.dataset.action === 'edit') { openForm(item); return; }
      pendingAction = { action: button.dataset.action, item };
      const remove = pendingAction.action === 'delete';
      container.querySelector('#supplier-action-title').textContent = remove ? 'Permanently delete supplier?' : pendingAction.action === 'archive' ? 'Archive supplier?' : 'Restore supplier?';
      container.querySelector('#supplier-action-copy').textContent = remove
        ? `“${item.name}” will be permanently deleted. This supplier has no linked lots.`
        : pendingAction.action === 'archive' ? `“${item.name}” will be hidden from supplier selection. Existing lots and results will remain available.`
          : `“${item.name}” will be available for new inspections again.`;
      const confirm = actionDialog.querySelector('[value="confirm"]'); confirm.className = remove ? 'danger-button' : 'primary-button'; confirm.textContent = remove ? 'Delete permanently' : pendingAction.action === 'archive' ? 'Archive' : 'Restore';
      container.querySelector('#supplier-action-error').hidden = true; actionDialog.returnValue = 'cancel'; actionDialog.showModal();
    });
    actionDialog.addEventListener('close', async () => {
      if (actionDialog.returnValue !== 'confirm' || !pendingAction) return;
      const { action, item } = pendingAction; pendingAction = null;
      try {
        if (action === 'archive') await api(`/suppliers/${item.id}/archive`, { method: 'POST' });
        if (action === 'restore') await api(`/suppliers/${item.id}/restore`, { method: 'POST' });
        if (action === 'delete') await api(`/suppliers/${item.id}`, { method: 'DELETE' });
        items = (await api('/suppliers?include_archived=true')).items; draw();
      } catch (exc) {
        container.querySelector('#supplier-action-error').textContent = exc.message;
        container.querySelector('#supplier-action-error').hidden = false;
        actionDialog.returnValue = 'cancel'; pendingAction = { action, item }; actionDialog.showModal();
      }
    });
    search.addEventListener('input', draw);
    container.querySelector('#show-archived').addEventListener('change', event => { showArchived = event.target.checked; draw(); });
    draw();
  } catch (exc) {
    if (location.pathname !== '/suppliers') return;
    container.innerHTML = `<div class="load-error" role="alert"><h2>Unable to load suppliers</h2><p>${escapeHtml(exc.message)}</p><button class="secondary-button" id="retry-suppliers">Retry</button></div>`;
    container.querySelector('#retry-suppliers').addEventListener('click', () => renderSuppliers(container));
  }
}

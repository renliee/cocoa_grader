import { api, escapeHtml } from '../api.js';

export function createReportDialog(container, { lotId, revisionId, revisionNumber }) {
  const dialog = document.createElement('dialog');
  dialog.className = 'mobile-dialog share-dialog';
  dialog.setAttribute('aria-labelledby', 'share-report-title');
  dialog.setAttribute('aria-describedby', 'share-report-description');
  dialog.innerHTML = `<h2 id="share-report-title">Share / Export Report</h2><p id="share-report-description">Share a permanent record of revision ${revisionNumber}, including its results and photo evidence.</p><div class="report-sheet" aria-busy="true">Preparing report…</div><button class="secondary-button close-report" type="button">Close</button>`;
  container.append(dialog);
  const sheet = dialog.querySelector('.report-sheet');
  dialog.querySelector('.close-report').addEventListener('click', () => dialog.close());
  let pollTimer;
  dialog.addEventListener('close', () => { clearTimeout(pollTimer); });

  async function open() {
    clearTimeout(pollTimer);
    if (!dialog.open) dialog.showModal();
    sheet.setAttribute('aria-busy', 'true');
    sheet.textContent = 'Preparing report…';
    try {
      let info = await api(`/lots/${lotId}/revisions/${revisionId}/report`, { method: 'POST' });
      if (!dialog.open || !dialog.isConnected) return;
      const token = new URL(info.url).pathname.split('/').at(-1);
      sheet.setAttribute('aria-busy', 'false');
      sheet.innerHTML = `<div class="report-link-group"><label for="report-url">Public report link</label><div class="report-url-row"><input id="report-url" readonly value="${escapeHtml(info.url)}"><button class="secondary-button" id="copy-report">Copy link</button></div><p id="copy-status" role="status"></p></div>
        <div class="report-export-actions"><div id="report-pdf-action" role="status"></div>
        <button class="secondary-button" id="show-report-qr" aria-controls="report-qr-slot" aria-expanded="false">Show QR code</button><div id="report-qr-slot" role="status"></div>
        ${info.lan_ready ? `<a class="secondary-button" href="/report/${token}/label" target="_blank" rel="noopener noreferrer">Open printable label</a>` : '<p class="report-lan-note">To scan from a phone, open KakaoLens using this computer’s LAN address, then reopen the report.</p>'}</div>`;
      sheet.querySelector('#copy-report').addEventListener('click', async () => {
        const field = sheet.querySelector('#report-url');
        try { await navigator.clipboard.writeText(info.url); sheet.querySelector('#copy-status').textContent = 'Link copied.'; }
        catch { field.focus(); field.select(); sheet.querySelector('#copy-status').textContent = 'Link selected. Use your device’s menu to copy it.'; }
      });
      sheet.querySelector('#show-report-qr').addEventListener('click', event => {
        const button = event.currentTarget;
        const qrSlot = sheet.querySelector('#report-qr-slot');
        const expanded = button.getAttribute('aria-expanded') === 'true';
        button.setAttribute('aria-expanded', String(!expanded));
        button.textContent = expanded ? 'Show QR code' : 'Hide QR code';
        qrSlot.innerHTML = expanded ? '' : `<img class="report-qr-logo" src="/assets/report-logo.png" alt="KakaoLens"><img class="report-qr-image" src="/api/reports/${token}/qr" alt="QR code for report revision ${revisionNumber}"><p>Scan with a phone on the same network.</p>`;
        qrSlot.querySelector('.report-qr-image')?.addEventListener('error', () => {
          qrSlot.textContent = 'Unable to load the QR code. Open KakaoLens using this computer’s LAN address and retry.';
          button.setAttribute('aria-expanded', 'false'); button.textContent = 'Retry QR code';
        });
      });
      function drawPdf() {
        const actionSlot = sheet.querySelector('#report-pdf-action');
        if (!actionSlot) return;
        actionSlot.innerHTML = info.pdf_status === 'complete'
          ? `<a class="primary-button" href="/api/reports/${token}/pdf">Download PDF Report</a>`
          : info.pdf_status === 'failed'
            ? `<button class="secondary-button" id="retry-report-pdf">Retry PDF export</button><p role="alert">${escapeHtml(info.pdf_error || 'PDF export failed.')}</p>`
            : '<p>Preparing PDF…</p>';
        actionSlot.querySelector('#retry-report-pdf')?.addEventListener('click', async () => {
          try { await api(`/lots/${lotId}/revisions/${revisionId}/report/pdf/retry`, { method: 'POST' });
            info = await api(`/reports/${token}`); drawPdf(); pollPdf(); }
          catch (exc) { actionSlot.insertAdjacentHTML('beforeend', `<p role="alert">${escapeHtml(exc.message)}</p>`); }
        });
      }
      async function pollPdf() {
        if (!dialog.open || !dialog.isConnected || !['queued', 'running'].includes(info.pdf_status)) return;
        try { info = await api(`/reports/${token}`); if (!dialog.open || !dialog.isConnected) return; drawPdf(); }
        catch { return; }
        if (['queued', 'running'].includes(info.pdf_status)) pollTimer = setTimeout(pollPdf, 1400);
      }
      drawPdf();
      if (['queued', 'running'].includes(info.pdf_status)) pollTimer = setTimeout(pollPdf, 1400);
    } catch (exc) {
      if (!dialog.open || !dialog.isConnected) return;
      sheet.setAttribute('aria-busy', 'false');
      sheet.innerHTML = `<p class="form-error" role="alert">${escapeHtml(exc.message)}</p><button class="secondary-button" id="retry-report">Retry</button>`;
      sheet.querySelector('#retry-report').addEventListener('click', open);
    }
  }
  return { open, dialog };
}

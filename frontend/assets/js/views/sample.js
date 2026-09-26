import { api, escapeHtml } from '../api.js';
import { icon } from '../components/icons.js';

const selectedByDraft = new Map();
const renderTokens = new WeakMap();
const reasonLabels = {
  edge_cut: 'Cut off at edge', unresolved_cluster: 'Unresolved cluster',
  fragment: 'Fragment', suspicious_geometry: 'Irregular geometry',
};

function stateFor(photo) {
  if (photo.status === 'queued' || photo.status === 'processing') return ['Detecting beans…', 'processing'];
  if (photo.status === 'failed') return ['Precheck failed', 'failed'];
  if (photo.status === 'invalid') return ['No usable beans', 'failed'];
  if (photo.excluded_severity === 'critical') return ['Most objects cannot be used', 'warning'];
  if (photo.excluded_severity === 'high') return ['Many objects are excluded', 'warning'];
  if (photo.status === 'warning') return ['Needs attention', 'warning'];
  return ['Ready to use', 'included'];
}

export async function renderSample(container, draftId, navigate) {
  if (location.pathname !== `/analysis/${draftId}/sample`) return;
  const token = {};
  renderTokens.set(container, token);
  const isCurrent = () => renderTokens.get(container) === token && location.pathname === `/analysis/${draftId}/sample` && container.isConnected;
  container.className = 'workflow-page sample-page';
  container.innerHTML = '<p class="loading-state" role="status">Checking sample photos…</p>';
  let draft, photos, summary;
  try {
    [draft, { items: photos, summary }] = await Promise.all([
      api(`/drafts/${draftId}`), api(`/drafts/${draftId}/photos`),
    ]);
    if (!isCurrent()) return;
    if (!draft.supplier_id) { navigate(`/analysis/${draftId}/lot`, true); return; }
    const oldPending = photos.some(photo => photo.review_state === 'pending' &&
      ['ready', 'warning', 'invalid'].includes(photo.status));
    if (oldPending) {
      await api(`/drafts/${draftId}/photos/use-all`, { method: 'POST', body: {
        expected_input_version: draft.input_version,
      } });
      return renderSample(container, draftId, navigate);
    }
  } catch (exc) {
    if (!isCurrent()) return;
    container.innerHTML = `<div class="load-error" role="alert"><h2>Unable to load sample</h2><p>${escapeHtml(exc.message)}</p><button class="secondary-button" id="retry-sample">Retry</button></div>`;
    container.querySelector('#retry-sample').addEventListener('click', () => renderSample(container, draftId, navigate));
    return;
  }
  if (!isCurrent()) return;
  let busy = false;
  const disabledBefore = new Map();
  function setBusy(value) {
    busy = value;
    if (value) {
      for (const control of container.querySelectorAll('button, input')) {
        disabledBefore.set(control, control.disabled);
        control.disabled = true;
      }
    } else {
      for (const [control, disabled] of disabledBefore) control.disabled = disabled;
      disabledBefore.clear();
    }
  }
  let selected = Math.min(selectedByDraft.get(draftId) || 0, Math.max(0, photos.length - 1));
  const finished = photos.filter(photo => !['queued', 'processing'].includes(photo.status)).length;
  const hasBlockingFailure = photos.some(photo => photo.review_state === 'included' && photo.status === 'failed');
  const analysisReady = photos.length > 0 && !summary.processing_count && !hasBlockingFailure && summary.usable_count > 0;
  container.innerHTML = `<div class="workflow-top compact-workflow-top"><a class="back-link" href="/analysis/${draftId}/lot">${icon('arrow')}Lot details</a><p class="eyebrow">SAMPLE · STEP 2 OF 3${draft.base_revision_id ? ` · REVISION ${draft.next_revision_number}` : ''}</p><h1>Review photos before analysis</h1><p>${escapeHtml(draft.human_id)} · ${escapeHtml(draft.supplier_name)}. ${draft.base_revision_id ? `Draft based on revision ${draft.base_revision_number}. Replacing a photo only changes this revision. ` : ''}Review through to the last photo to start analysis.</p></div>
    <ol class="wizard-steps" aria-label="Analysis steps"><li><span>1</span>Lot</li><li aria-current="step"><span>2</span>Sample</li><li><span>3</span>Results</li></ol>
    <section class="sample-total-card" aria-live="polite"><div><span class="eyebrow">${summary.usable_count ? 'DETECTED SAMPLE' : 'NO SAMPLE YET'}</span><strong>${summary.usable_count}<small> / 300</small></strong><p>usable beans from ${photos.length} photos</p></div><div class="sample-progress"><span>${finished}/${photos.length}</span><p>photos checked</p></div></section>
    <div class="sample-target-progress" data-band="${summary.sample_band.id}" role="progressbar" aria-label="Progress toward the 300-bean reference" aria-valuemin="0" aria-valuemax="300" aria-valuenow="${Math.min(summary.usable_count, 300)}" aria-valuetext="${summary.usable_count} of the 300-bean reference"><span style="width:${Math.min(summary.usable_count / 3, 100)}%"></span></div>
    <section class="sample-confidence" data-band="${summary.sample_band.id}"><strong>${escapeHtml(summary.sample_band.label)}</strong><span>${escapeHtml(summary.sample_band.description)}</span></section>
    <details class="sample-guidance"><summary>Photo guide</summary><p>Select beans randomly from several parts of the lot. Use white paper and even lighting, leave space between beans, and keep beans within the photo. Sample size alone does not ensure a representative lot sample.</p><a class="text-link" href="/settings/guide">View full guide</a></details>
    <section class="workflow-card sample-workspace"><div class="sample-heading"><div><h2>Sample photos</h2><p>Up to 50 photos · excluded objects do not affect other usable beans.</p></div><span class="sample-position" id="sample-position"></span></div>
      <div id="sample-photo"></div><p class="form-error" id="sample-error" role="alert" hidden></p>
      <div class="simple-upload" ${photos.length >= 50 ? 'hidden' : ''}><label class="primary-button" for="sample-gallery">${icon('plus')} Add photos</label><input class="sr-only" id="sample-gallery" type="file" accept="image/jpeg,image/png" multiple><label class="camera-link" for="sample-camera">Open camera</label><input class="sr-only" id="sample-camera" type="file" accept="image/*" capture="environment"><span>${photos.length}/50 photos</span></div>
      <p class="upload-status" id="sample-upload-status" role="status"></p>
      ${photos.length ? '<button class="danger-button clear-photos" id="clear-photos">Delete all photos</button>' : ''}
    </section>
    <p class="autosave-status">Photos and precheck results are saved automatically to your draft.</p>
    <div class="sample-exit-actions"><a class="text-link" href="/history?tab=draft">Resume later</a><button class="danger-link" id="discard-draft">Discard analysis</button></div>
    <dialog class="mobile-dialog" id="small-sample-dialog"><form method="dialog"><h2>${summary.usable_count < 50 ? 'Very limited sample' : 'Sample below 300 beans'}</h2><p>${summary.usable_count < 50 ? `Only ${summary.usable_count} beans are usable. Results can be calculated but will be excluded from KakaoLens summary statistics.` : `A sample of ${summary.usable_count} beans is below the 300-bean reference. Results are indicative and should be interpreted with caution.`}</p><div class="dialog-actions"><button class="secondary-button" value="cancel">Add photos</button><button class="primary-button" value="continue">Analyze anyway</button></div></form></dialog>
    <dialog class="mobile-dialog" id="clear-photos-dialog"><form method="dialog"><h2>Delete all photos?</h2><p>${photos.length} photos in draft ${escapeHtml(draft.human_id)} will be removed from the sample. The draft will need to be analyzed again. Lot details remain saved.</p><div class="dialog-actions"><button class="secondary-button" value="cancel">Cancel</button><button class="danger-button" value="delete">Delete all photos</button></div></form></dialog>
    <dialog class="mobile-dialog" id="delete-photo-dialog"><form method="dialog"><h2>Delete this photo?</h2><p>The photo and its precheck results will be removed from the sample.</p><div class="dialog-actions"><button class="secondary-button" value="cancel">Cancel</button><button class="danger-button" value="delete">Delete photo</button></div></form></dialog>
    <dialog class="mobile-dialog" id="discard-dialog"><form method="dialog"><h2>Discard this analysis?</h2><p>The draft and all saved photos will be permanently deleted.</p><p class="form-error" id="discard-error" hidden></p><div class="dialog-actions"><button class="secondary-button" value="cancel">Cancel</button><button class="danger-button" value="delete">Discard analysis</button></div></form></dialog>
    <dialog class="image-dialog" id="sample-image-dialog"><button class="image-close" id="close-sample-image" aria-label="Close image">×</button><img alt="Full-size precheck photo"></dialog>`;
  const photoSlot = container.querySelector('#sample-photo');
  const error = container.querySelector('#sample-error');
  const uploadStatus = container.querySelector('#sample-upload-status');
  const discardDialog = container.querySelector('#discard-dialog');
  const deleteDialog = container.querySelector('#delete-photo-dialog');
  const smallDialog = container.querySelector('#small-sample-dialog');
  const imageDialog = container.querySelector('#sample-image-dialog');
  const clearDialog = container.querySelector('#clear-photos-dialog');
  container.querySelector('#clear-photos')?.addEventListener('click', () => { clearDialog.returnValue = 'cancel'; clearDialog.showModal(); });
  clearDialog.addEventListener('close', async () => {
    if (clearDialog.returnValue !== 'delete') return;
    const button = container.querySelector('#clear-photos');
    setBusy(true);
    button.disabled = true;
    try {
      await api(`/drafts/${draftId}/photos`, { method: 'DELETE', body: { expected_input_version: draft.input_version } });
      selectedByDraft.delete(draftId);
      await renderSample(container, draftId, navigate);
    } catch (exc) { error.textContent = exc.message; error.hidden = false; button.disabled = false; }
    finally { setBusy(false); }
  });

  async function uploadFiles(files) {
    if (!files.length || busy) return;
    if (photos.length + files.length > 50) {
      error.textContent = `You can add ${50 - photos.length} more photos. Maximum: 50 photos per analysis.`;
      error.hidden = false; return;
    }
    error.hidden = true;
    setBusy(true);
    const failures = [];
    selectedByDraft.set(draftId, photos.length);
    for (const [index, file] of files.entries()) {
      uploadStatus.textContent = `Uploading photo ${index + 1} of ${files.length}…`;
      const body = new FormData(); body.append('file', file, file.name);
      try { await api(`/drafts/${draftId}/photos`, { method: 'POST', body, headers: { 'Idempotency-Key': crypto.randomUUID() } }); }
      catch (exc) { failures.push(`${file.name}: ${exc.message}`); }
    }
    setBusy(false);
    if (!isCurrent()) return;
    await renderSample(container, draftId, navigate);
    if (failures.length && location.pathname === `/analysis/${draftId}/sample`) {
      const fresh = container.querySelector('#sample-error'); fresh.textContent = failures.join(' '); fresh.hidden = false;
    }
  }

  async function runAnalysis(confirmSmall) {
    if (busy) return;
    setBusy(true);
    const button = container.querySelector('#run-analysis');
    button.disabled = true; button.textContent = 'Starting analysis…'; error.hidden = true;
    try {
      await api(`/drafts/${draftId}/analyze`, { method: 'POST', body: {
        expected_input_version: draft.input_version, confirm_small_sample: confirmSmall,
      } });
      navigate(`/analysis/${draftId}/result`);
    } catch (exc) {
      error.textContent = exc.message; error.hidden = false; button.disabled = false;
      button.innerHTML = `Analysis ${summary.usable_count} beans ${icon('arrow')}`;
    } finally { setBusy(false); }
  }

  function showPhoto() {
    const photo = photos[selected];
    selectedByDraft.set(draftId, selected);
    container.querySelector('#sample-position').textContent = photo ? `${selected + 1} / ${photos.length}` : '0 / 0';
    if (!photo) {
      photoSlot.innerHTML = `<div class="sample-empty">${icon('sample')}<h3>No sample yet</h3><p>Add a cut-test photo to start counting usable beans.</p></div>`;
      return;
    }
    const [state, stateClass] = stateFor(photo);
    const reasons = Object.entries(photo.excluded_reasons || {}).filter(([, count]) => count);
    const last = selected === photos.length - 1;
    photoSlot.innerHTML = `<div class="review-navigation"><button class="photo-arrow" id="prev-photo" aria-label="Previous photo" ${selected === 0 ? 'disabled' : ''}>‹</button><div><strong>Photo ${selected + 1}</strong><span>${escapeHtml(photo.filename)}</span></div><button class="photo-arrow" id="next-photo" aria-label="Next photo" ${last ? 'disabled' : ''}>›</button></div>
      ${!last && photos.length > 2 ? '<button class="skip-last" id="skip-last">Skip to last photo →</button>' : ''}
      <button class="photo-figure" id="open-photo" aria-label="Enlarge precheck image"><img src="${photo.image_url}" alt="Precheck visualization for photo ${selected + 1}"></button>
      <div class="photo-detail"><span class="photo-status ${stateClass}">${state}</span>
      ${photo.usable_count === null ? '<p class="detecting-copy">Detection boxes and bean counts appear automatically.</p>' : `<div class="photo-counts clean-counts"><span><strong>${photo.usable_count}</strong> usable beans</span><span><strong>${photo.excluded_count}</strong> excluded objects</span></div>`}
      ${reasons.length ? `<div class="excluded-note"><strong>Excluded from classification</strong><p>${reasons.map(([reason, count]) => `${reasonLabels[reason] || reason} ${count}`).join(' · ')}</p><small>Other usable beans in this photo will still be analyzed.</small></div>` : ''}
      ${(photo.warnings || []).map(warning => `<p class="photo-warning">${icon('warning')}${escapeHtml(warning)}</p>`).join('')}
      ${photo.error_text ? `<p class="photo-warning">${escapeHtml(photo.error_text)}</p>` : ''}</div>
      <div class="photo-manage"><label for="replace-photo-file">Choose replacement file</label><input class="sr-only" id="replace-photo-file" data-replace-photo type="file" accept="image/jpeg,image/png"><label for="replace-photo-camera">Retake with camera</label><input class="sr-only" id="replace-photo-camera" data-replace-photo type="file" accept="image/*" capture="environment"><button id="delete-photo">Delete photo</button>${photo.status === 'failed' ? '<button id="retry-photo">Retry processing</button>' : ''}</div>
      ${last ? `<div class="last-photo-submit"><p><strong>Last photo.</strong><br>${analysisReady ? `${summary.usable_count} usable beans from ${photos.length} photos are ready for classification.` : summary.processing_count ? 'Wait for all photos to finish precheck.' : hasBlockingFailure ? 'Replace, delete, or retry failed photos.' : 'No usable beans to analyze yet.'}</p><button class="primary-button" id="run-analysis" ${analysisReady ? '' : 'disabled'}>Analysis ${summary.usable_count} beans ${icon('arrow')}</button></div>` : ''}`;
    photoSlot.querySelector('#prev-photo').addEventListener('click', () => { selected--; showPhoto(); });
    photoSlot.querySelector('#next-photo').addEventListener('click', () => { selected++; showPhoto(); });
    photoSlot.querySelector('#skip-last')?.addEventListener('click', () => { selected = photos.length - 1; showPhoto(); });
    photoSlot.querySelector('#open-photo').addEventListener('click', () => { imageDialog.querySelector('img').src = photo.image_url; imageDialog.showModal(); });
    photoSlot.querySelector('#delete-photo').addEventListener('click', () => { deleteDialog.returnValue = 'cancel'; deleteDialog.showModal(); });
    photoSlot.querySelectorAll('[data-replace-photo]').forEach(input => input.addEventListener('change', async event => {
      const [file] = event.target.files; if (!file) return;
      setBusy(true);
      uploadStatus.textContent = `Replacing photo ${selected + 1}…`; error.hidden = true;
      const body = new FormData(); body.append('file', file, file.name);
      try { await api(`/drafts/${draftId}/photos/${photo.id}`, { method: 'PUT', body, headers: { 'Idempotency-Key': crypto.randomUUID() } }); await renderSample(container, draftId, navigate); }
      catch (exc) { error.textContent = exc.message; error.hidden = false; uploadStatus.textContent = ''; }
      finally { setBusy(false); }
    }));
    photoSlot.querySelector('#retry-photo')?.addEventListener('click', async () => {
      setBusy(true);
      try { await api(`/drafts/${draftId}/photos/${photo.id}/retry`, { method: 'POST' }); await renderSample(container, draftId, navigate); }
      catch (exc) { error.textContent = exc.message; error.hidden = false; }
      finally { setBusy(false); }
    });
    photoSlot.querySelector('#run-analysis')?.addEventListener('click', () => {
      if (summary.usable_count < 300) { smallDialog.returnValue = 'cancel'; smallDialog.showModal(); }
      else runAnalysis(false);
    });
    deleteDialog.onclose = async () => {
      if (deleteDialog.returnValue !== 'delete') return;
      setBusy(true);
      try {
        await api(`/drafts/${draftId}/photos/${photo.id}`, { method: 'DELETE' });
        selectedByDraft.set(draftId, Math.min(selected, photos.length - 2));
        await renderSample(container, draftId, navigate);
      } catch (exc) { error.textContent = exc.message; error.hidden = false; }
      finally { setBusy(false); }
    };
  }
  showPhoto();

  let touchX = null;
  photoSlot.addEventListener('touchstart', event => { touchX = event.changedTouches[0].clientX; }, { passive: true });
  photoSlot.addEventListener('touchend', event => {
    if (busy) return;
    if (touchX === null) return;
    const delta = event.changedTouches[0].clientX - touchX; touchX = null;
    if (Math.abs(delta) < 55) return;
    if (delta < 0 && selected < photos.length - 1) selected++;
    else if (delta > 0 && selected > 0) selected--;
    else return;
    showPhoto();
  }, { passive: true });
  container.querySelector('#close-sample-image').addEventListener('click', () => imageDialog.close());
  for (const input of container.querySelectorAll('#sample-camera, #sample-gallery')) {
    input.addEventListener('change', () => uploadFiles([...input.files]));
  }
  smallDialog.addEventListener('close', () => { if (smallDialog.returnValue === 'continue') runAnalysis(true); });
  container.querySelector('#discard-draft').addEventListener('click', () => { discardDialog.returnValue = 'cancel'; discardDialog.showModal(); });
  discardDialog.addEventListener('close', async () => {
    if (discardDialog.returnValue !== 'delete') return;
    setBusy(true);
    try { await api(`/drafts/${draftId}`, { method: 'DELETE' }); selectedByDraft.delete(draftId); navigate('/history?tab=draft'); }
    catch (exc) { container.querySelector('#discard-error').textContent = exc.message; container.querySelector('#discard-error').hidden = false; discardDialog.returnValue = 'cancel'; discardDialog.showModal(); }
    finally { setBusy(false); }
  });
  if (summary.processing_count) {
    const poll = async () => {
      if (!isCurrent()) return;
      if (busy || container.querySelector('dialog[open]')) { setTimeout(poll, 1100); return; }
      try { await renderSample(container, draftId, navigate); }
      catch { uploadStatus.textContent = 'Connection lost. Refresh to view precheck results.'; }
    };
    setTimeout(poll, 1100);
  }
}

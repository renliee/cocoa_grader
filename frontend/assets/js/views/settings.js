import { api, escapeHtml } from '../api.js';

export function renderSettings(container, user, onProfileChange = () => {}) {
  container.className = 'settings-page';
  const name = escapeHtml(user?.display_name || 'KakaoLens user');
  const login = escapeHtml(user?.login || '');
  container.innerHTML = `<header class="settings-heading"><p class="eyebrow">ACCOUNT AND PROFILE</p><h1>Settings</h1><p>Manage your profile for lot inspections.</p></header>
    <section class="settings-card" aria-labelledby="profile-title">
      <div class="settings-card-heading"><span class="settings-avatar" aria-hidden="true">${escapeHtml(initials(user?.display_name || user?.login))}</span><div><p class="eyebrow">USER PROFILE</p><h2 id="profile-title">${name}</h2><p>KakaoLens account</p></div></div>
      <dl class="settings-account-details"><div><dt>Username / email</dt><dd>${login}</dd></div><div><dt>Account time zone</dt><dd>${escapeHtml(user?.timezone || 'Asia/Jakarta')}</dd></div></dl>
      <form id="profile-form" class="settings-form">
        <div class="settings-form-intro"><h3>Update display name</h3><p>This name appears in the application. Updating it does not change finalized results.</p></div>
        <label for="profile-name">Full name or professional name</label>
        <input id="profile-name" name="display_name" type="text" value="${name}" minlength="2" maxlength="80" autocomplete="name" required>
        <p class="settings-help">Use a name your inspection team will recognize.</p>
        <p id="profile-message" class="settings-message" role="status" hidden></p>
        <div class="settings-form-actions"><button id="save-profile" class="primary-button" type="submit" disabled>Save changes</button></div>
      </form>
    </section>
    <section class="settings-card settings-guide"><h2>KakaoLens guide</h2><p>Learn the supplier workflow, cut-test photo preparation, the 300-bean reference, and how to interpret results.</p><a class="secondary-button" href="/settings/guide">Open guide</a></section>`;

  const form = container.querySelector('#profile-form');
  const field = container.querySelector('#profile-name');
  const save = container.querySelector('#save-profile');
  const message = container.querySelector('#profile-message');
  let savedName = user?.display_name || 'KakaoLens user';
  field.addEventListener('input', () => {
    save.disabled = field.value.trim() === savedName.trim();
    message.hidden = true;
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (field.value.trim() === savedName.trim()) return;
    message.hidden = true;
    save.disabled = true;
    save.textContent = 'Saving…';
    try {
      const updated = await api('/account/profile', { method: 'PATCH', body: { display_name: field.value } });
      field.value = updated.display_name;
      savedName = updated.display_name;
      container.querySelector('.settings-avatar').textContent = initials(updated.display_name);
      container.querySelector('#profile-title').textContent = updated.display_name;
      onProfileChange(updated);
      message.textContent = 'Display name saved.';
      message.className = 'settings-message is-success';
      message.hidden = false;
    } catch (error) {
      message.textContent = error.message;
      message.className = 'settings-message is-error';
      message.hidden = false;
    } finally {
      save.disabled = field.value.trim() === savedName.trim();
      save.textContent = 'Save changes';
    }
  });
}

function initials(value = '') {
  const parts = String(value).trim().split(/\s+/).filter(Boolean);
  return (parts.length > 1 ? parts[0][0] + parts.at(-1)[0] : (parts[0] || 'K').slice(0, 2)).toLocaleUpperCase('en-GB');
}

import { api, escapeHtml, setCsrf } from '../api.js';
import { icon } from '../components/icons.js';

export function renderAuth(container, mode, onAuthenticated) {
  const signup = mode === 'signup';
  container.className = 'auth-page';
  container.innerHTML = `<section class="auth-card">
    <p class="eyebrow">KAKAOLENS</p>
    <h1>${signup ? 'Create your account' : 'Sign in to KakaoLens'}</h1>
    <p class="auth-intro">Save cocoa lot inspections and resume your work at any time.</p>
    <form id="auth-form">
      ${signup ? '<label for="display-name">Display name</label><input id="display-name" name="display_name" autocomplete="name" required minlength="2" maxlength="80">' : ''}
      <label for="login-name">Email or username</label><input id="login-name" name="login" autocomplete="username" required minlength="3" maxlength="64">
      <label for="password">Password</label><input id="password" name="password" type="password" autocomplete="${signup ? 'new-password' : 'current-password'}" required minlength="${signup ? 10 : 1}">
      ${signup ? '<label for="confirmation">Confirm password</label><input id="confirmation" name="password_confirmation" type="password" autocomplete="new-password" required minlength="10">' : ''}
      <p class="form-error" id="auth-error" role="alert" hidden></p>
      <button class="primary-button" type="submit">${signup ? 'Create account' : 'Sign in'}${icon('arrow')}</button>
    </form>
    <p class="auth-switch">${signup ? 'Already have an account?' : 'Need an account?'} <a class="text-link" href="${signup ? '/login' : '/signup'}">${signup ? 'Sign in' : 'Sign up'}</a></p>
  </section>`;
  const form = container.querySelector('#auth-form');
  form.addEventListener('submit', async event => {
    event.preventDefault();
    const button = form.querySelector('button[type=submit]');
    const error = form.querySelector('#auth-error');
    error.hidden = true;
    const values = Object.fromEntries(new FormData(form));
    if (signup && values.password !== values.password_confirmation) {
      error.textContent = 'Passwords do not match.';
      error.hidden = false;
      return;
    }
    button.disabled = true;
    button.textContent = signup ? 'Creating account…' : 'Signing in…';
    try {
      const session = await api(signup ? '/auth/signup' : '/auth/login', { method: 'POST', body: values });
      setCsrf(session.csrf_token);
      onAuthenticated(session.user);
    } catch (exc) {
      error.textContent = exc.message;
      error.hidden = false;
      button.disabled = false;
      button.innerHTML = `${signup ? 'Create account' : 'Sign in'}${icon('arrow')}`;
    }
  });
}

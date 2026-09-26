// Small local icon set: no remote assets or runtime dependency.
const paths = {
  home: '<path d="m3 10 9-7 9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z"/>',
  history: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V2m6 2V2M9 10h6m-6 4h6m-6 4h3"/>',
  suppliers: '<circle cx="9" cy="8" r="3"/><path d="M3 21v-3a6 6 0 0 1 12 0v3m1-16a3 3 0 0 1 0 6m3 10v-3a6 6 0 0 0-2-4"/>',
  settings: '<path d="m9 3-.6 2-2 .9-2-.5-2 3.2L4 10v3l-1.6 1.4 2 3.2 2-.5 2 .9.6 2h4l.6-2 2-.9 2 .5 2-3.2L18 13v-3l1.6-1.4-2-3.2-2 .5-2-.9-.6-2Z"/><circle cx="11" cy="11.5" r="3"/>',
  plus: '<path d="M12 5v14M5 12h14"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  box: '<path d="m3 7 9-4 9 4v11l-9 4-9-4Zm0 0 9 4 9-4M12 11v11M7.5 5l9 4"/>',
  trend: '<path d="m3 17 6-6 4 4 8-10m-6 0h6v6"/>',
  weight: '<path d="M5 9h14l2 12H3Z"/><circle cx="12" cy="6" r="3"/>',
  sample: '<path d="M8 2H3a1 1 0 0 0-1 1v5m14-6h5a1 1 0 0 1 1 1v5M2 16v5a1 1 0 0 0 1 1h5m14-6v5a1 1 0 0 1-1 1h-5"/><path d="m8 12 3 3 5-6"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  warning: '<path d="m10.2 4-8 14a2 2 0 0 0 1.7 3h16.2a2 2 0 0 0 1.7-3l-8-14a2 2 0 0 0-3.6 0Z"/><path d="M12 9v4m0 4h.01"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6m0-10h.01"/>',
  close: '<path d="m6 6 12 12M18 6 6 18"/>',
  leaf: '<path d="M20 3C8 2 2 8 5 16c7 5 16-1 15-13ZM4 21 16 8"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
};
export function icon(name, className = '') {
  return `<svg class="icon ${className}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.info}</svg>`;
}

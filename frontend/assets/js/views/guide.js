import { icon } from '../components/icons.js';

const pages = [
  { title: 'One supplier, multiple lots.', label: 'Supplier', icon: 'suppliers', body: '<p>Add a supplier once and select them for future inspections. Each lot receives an ID based on the supplier code and date.</p><p>Weight and notes are optional. Lot details and photos are saved automatically as a draft until you finalize the results.</p>' },
  { title: 'Prepare a representative sample.', label: 'Sample', icon: 'sample', body: '<p>Select beans randomly from several parts of the lot. Avoid selecting beans based on appearance alone.</p><p>Cut the beans, place them on white paper, leave space between them, use even lighting, and keep every bean within the photo.</p><p>The sample-size reference is <strong>300 usable beans</strong>, regardless of lot weight. Bean count alone does not ensure a representative sample.</p><p>Photo precheck flags objects cut off at the edge, clusters, and fragments. These objects are excluded from classification. Other usable beans remain included. Review and replace photos as needed.</p>' },
  { title: 'Interpret results alongside sample size.', label: 'Analysis', icon: 'trend', body: '<p>Results show the proportions of <strong>Well fermented</strong> and <strong>Poorly fermented</strong> among beans accepted during precheck.</p><ul class="guide-bands"><li><strong>&lt;50 · Very limited</strong><span>Can be analyzed, but excluded from summary statistics.</span></li><li><strong>50–99 · Small sample</strong><span>Interpret results with caution.</span></li><li><strong>100–299 · Indicative</strong><span>Below the 300-bean reference.</span></li><li><strong>≥300 · Meets sample-size reference</strong><span>Meets the sample-size reference; representativeness still matters.</span></li></ul><p>Finalize the analysis to save results to History. KakaoLens assesses visual fermentation characteristics and does not replace comprehensive quality testing or SNI testing.</p>' },
];

export function renderGuide(container) {
  container.className = 'workflow-page guide-page';
  let step = 0;
  function draw() {
    const page = pages[step];
    container.innerHTML = `<div class="workflow-top"><a class="back-link" href="/settings">${icon('arrow')}Settings</a><p class="eyebrow">KAKAOLENS GUIDE · ${step + 1} / ${pages.length}</p><h1>${page.title}</h1></div>
      <ol class="wizard-steps" aria-label="Guide">${pages.map((item, i) => `<li ${i === step ? 'aria-current="step"' : ''}><span>${i + 1}</span>${item.label}</li>`).join('')}</ol>
      <section class="workflow-card guide-content"><div class="scan-symbol">${icon(page.icon)}</div>${page.body}</section>
      <div class="wizard-actions"><button class="secondary-button" id="guide-prev" ${step === 0 ? 'disabled' : ''}>Previous</button>${step === pages.length - 1 ? '<a class="primary-button guide-start" href="/analysis/new">Start</a>' : '<button class="primary-button" id="guide-next">Next</button>'}</div>`;
    container.querySelector('#guide-prev').addEventListener('click', () => { step--; draw(); container.focus(); window.scrollTo(0, 0); });
    container.querySelector('#guide-next')?.addEventListener('click', () => { step++; draw(); container.focus(); window.scrollTo(0, 0); });
  }
  draw();
}

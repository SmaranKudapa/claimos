export interface Presenter { name: string | null; title: string; license: string | null; }

export interface BriefingInput {
  caseId: string;
  address: string;
  county: string | null;
  parcel: string | null;
  use: string | null;
  sqft: number | null;
  yearBuilt: number | null;
  justValue: number;
  assessedValue: number | null;
  taxableValue: number | null;
  estimate: { defensibleValue: number | null; annualSavings: number | null; range: [number, number] | null; millage: number | null };
  neighbors: { address: string; sqft: number | null; justValue: number | null; perSqft: number | null }[];
  sales: { address: string; when: string | null; price: number | null; adjusted: number | null; sqft: number | null }[];
  ratios: { neighbor: number | null; neighborCount: number | null; sales: number | null; salesCount: number | null };
  qualify: { verdict: string | null; pWin: number | null; fee: number | null; savings: number | null; deadline: string | null } | null;
  evidence: {
    requested: number;
    comps: { address: string; date: string | null; price: number | null; adjusted: number | null; sqft: number | null; perSqft: number | null }[];
    equity: { peers: number | null; medianPerSqft: number | null; subjectPerSqft: number | null; indicated: number | null } | null;
  } | null;
  filing: { closes: string | null; status: string | null };
  warnings: string[];
  feePct: number;
}

export interface Bar { label: string; value: number; highlight: boolean; }
export interface Slide {
  kicker: string;
  title: string;
  lead: string | null;
  bullets: string[];
  table: { head: string[]; rows: string[][] } | null;
  bars: { unit: string; items: Bar[] } | null;
  notes: string;
}
export interface Deck {
  caseId: string;
  version: number;
  builtOn: string;
  address: string;
  county: string | null;
  presenter: Presenter;
  bookingUrl: string | null;
  hasEvidence: boolean;
  slides: Slide[];
  sources: string[];
}

const usd = (n: number | null | undefined) => n == null ? '—' : `$${Math.round(n).toLocaleString('en-US')}`;
const pct = (n: number) => `${Math.round(n * 100)}%`;
const median = (xs: number[]) => { const s = [...xs].sort((a, b) => a - b); const m = Math.floor(s.length / 2); return s.length ? (s.length % 2 ? s[m]! : (s[m - 1]! + s[m]!) / 2) : null; };
const title = (s: string) => s.replace(/\s+/g, ' ').trim();

export function presenterLine(p: Presenter) {
  const who = p.name ? `${p.name}, ` : 'your ';
  return p.license ? `${who}${p.title} (license ${p.license})` : `${who}${p.title}`;
}

export function buildDeck(input: BriefingInput, opts: { version: number; today: string; presenter: Presenter; bookingUrl: string | null }): Deck {
  const i = input;
  const slides: Slide[] = [];
  const perSqft = i.sqft ? i.justValue / i.sqft : null;
  const neighborPer = i.neighbors.map((n) => n.perSqft ?? (n.justValue && n.sqft ? n.justValue / n.sqft : null)).filter((x): x is number => x != null);
  const neighborMedian = i.evidence?.equity?.medianPerSqft ?? median(neighborPer);
  const subjectPer = i.evidence?.equity?.subjectPerSqft ?? perSqft;
  const target = i.evidence?.requested ?? i.estimate.defensibleValue;
  const cut = target != null ? Math.max(0, i.justValue - target) : null;

  slides.push({
    kicker: 'Property value review · 2026 tax roll',
    title: title(i.address),
    lead: `${i.county ? `${i.county} County, Florida` : 'Florida'}${i.parcel ? ` · parcel ${i.parcel}` : ''}`,
    bullets: [
      `Prepared for the owner of record on ${opts.today}`,
      `Presented by ${presenterLine(opts.presenter)}`,
      'Claim OS is a private company. It is not a government agency and not a law firm.',
    ],
    table: null, bars: null,
    notes: 'Introduce yourself and Claim OS. Say plainly that we are a private company, not the county and not a law firm, and that this review uses public county records. Ask what made them want to talk to someone before signing.',
  });

  slides.push({
    kicker: 'Your home on the county roll',
    title: `The county values your home at ${usd(i.justValue)}`,
    lead: perSqft ? `That is ${usd(perSqft)} per square foot.` : null,
    bullets: [],
    table: { head: ['', 'County record'], rows: [
      ['Just (market) value', usd(i.justValue)],
      ['Assessed value', usd(i.assessedValue)],
      ['Taxable value', usd(i.taxableValue)],
      ['Use', i.use ? i.use.replace(/_/g, ' ') : '—'],
      ['Living area', i.sqft ? `${i.sqft.toLocaleString('en-US')} sq ft` : '—'],
      ['Year built', i.yearBuilt ? String(i.yearBuilt) : '—'],
    ] },
    bars: null,
    notes: 'These figures come straight from the county property appraiser\'s 2026 roll. Ask the owner whether anything here looks wrong, for example the size, the year built or missing damage. A factual error on the record is often the easiest win.',
  });

  if (neighborMedian != null && subjectPer != null) {
    const items: Bar[] = [{ label: 'Your home', value: subjectPer, highlight: true }, { label: `Median of ${i.evidence?.equity?.medianPerSqft != null ? (i.evidence.equity.peers ?? 'the') : neighborPer.length} similar homes`, value: neighborMedian, highlight: false }];
    for (const n of i.neighbors.slice(0, 4)) { const v = n.perSqft ?? (n.justValue && n.sqft ? n.justValue / n.sqft : null); if (v != null) items.push({ label: title(n.address), value: v, highlight: false }); }
    slides.push({
      kicker: 'Compared with similar homes',
      title: `Your home is valued ${pct(subjectPer / neighborMedian - 1)} higher per square foot than similar homes nearby`,
      lead: i.evidence?.equity?.indicated ? `Valued like its neighbors, your home would be about ${usd(i.evidence.equity.indicated)}.` : null,
      bullets: [],
      table: null,
      bars: { unit: 'per sq ft', items },
      notes: 'This is the uniformity argument: Florida law asks the county to value similar homes alike. Point at the gap between their bar and the median. Similar means the same appraisal neighborhood and a comparable size and type.',
    });
  }

  const comps = i.evidence?.comps.length ? i.evidence.comps.map((c) => ({ address: c.address, when: c.date, price: c.price, adjusted: c.adjusted, sqft: c.sqft })) : i.sales;
  if (comps.length) {
    const rows = comps.slice(0, 6).map((c) => [title(c.address), c.when ?? '—', usd(c.price), usd(c.adjusted), c.sqft ? c.sqft.toLocaleString('en-US') : '—']);
    slides.push({
      kicker: 'What recent sales say',
      title: `${comps.length} comparable sale${comps.length === 1 ? '' : 's'} point to a lower value`,
      lead: i.ratios.sales ? `The county's value is ${pct(i.ratios.sales - 1)} above what these sales imply once adjusted to January 1.` : null,
      bullets: [],
      table: { head: ['Address', 'Sold', 'Price', 'Adjusted to Jan 1', 'Sq ft'], rows },
      bars: null,
      notes: `These are arm's-length sales from the county's own sales file${i.evidence ? ', as used in our evidence packet' : ''}. "Adjusted to Jan 1" moves each price to the valuation date. Invite questions about any sale the owner knows.`,
    });
  }

  if (target != null) {
    const range = i.estimate.range ? `${usd(i.estimate.range[0])}–${usd(i.estimate.range[1])} a year` : null;
    slides.push({
      kicker: 'What we would ask the county for',
      title: `Lower the value to about ${usd(target)}`,
      lead: cut ? `A reduction of ${usd(cut)} from the county's ${usd(i.justValue)}.` : null,
      bullets: [
        i.estimate.annualSavings != null ? `Estimated tax saving: about ${usd(i.qualify?.savings ?? i.estimate.annualSavings)} a year${range ? ` (range ${range})` : ''}.` : 'The tax saving depends on the corrected bill.',
        `This is an estimate${i.estimate.millage ? ` using an assumed tax rate of ${(i.estimate.millage * 100).toFixed(2)}%` : ''}. The real figure comes from your corrected tax bill.`,
        i.evidence ? 'The requested value comes from our evidence packet for your home.' : 'Our evidence packet for your home is in preparation; this figure will be refined.',
      ],
      table: null, bars: null,
      notes: 'Be clear that every saving figure is an estimate until the county issues a corrected bill. Never promise the number.',
    });
  }

  const closed = i.filing.status === 'closed' || (i.filing.closes != null && i.filing.closes < opts.today);
  slides.push({
    kicker: 'How the appeal works',
    title: 'Five steps, and you only sign once',
    lead: closed && i.filing.closes ? `The 2026 petition deadline was ${i.filing.closes}. A late petition needs good cause; otherwise we prepare for the 2027 roll.` : i.filing.closes ? `The petition deadline is ${i.filing.closes}.` : null,
    bullets: [
      'You sign our agreement and the county\'s authorization form (DR-486POA).',
      'We file a petition with the Value Adjustment Board (DR-486).',
      'We exchange evidence with the property appraiser.',
      'A special magistrate hears the case; we present the evidence.',
      'The board decides; if the value drops, the county issues a corrected bill.',
    ],
    table: null, bars: null,
    notes: closed ? 'Be upfront about the deadline. Explain the good-cause exception honestly and that next year\'s petition can use the same evidence.' : 'Walk through the steps and the deadline. Nothing is filed before they sign.',
  });

  const strength: string[] = [];
  if (i.qualify?.pWin != null) strength.push(`Our model estimates about a ${pct(i.qualify.pWin)} chance of some reduction. It is an estimate, not a promise.`);
  if (i.ratios.neighbor != null) strength.push(`Your value per square foot is ${i.ratios.neighbor.toFixed(2)}× that of ${i.ratios.neighborCount ?? 'similar'} neighbors.`);
  if (i.ratios.sales != null) strength.push(`Your value is ${i.ratios.sales.toFixed(2)}× what ${i.ratios.salesCount ?? 'recent'} comparable sales imply.`);
  slides.push({
    kicker: 'Our honest assessment',
    title: 'Why we think the case is worth bringing',
    lead: null,
    bullets: [...strength, ...i.warnings.slice(0, 2).map((w) => `To check together: ${w}`)],
    table: null, bars: null,
    notes: 'Give the strengths and the open questions with equal weight. If a warning applies (for example a recent sale or an ownership change), ask the owner about it now.',
  });

  slides.push({
    kicker: 'What it costs',
    title: 'Nothing unless your value goes down',
    lead: `Our fee is ${pct(i.feePct)} of the first year's tax saving, invoiced only after the corrected bill arrives.`,
    bullets: [
      i.qualify?.fee != null ? `At the estimated saving, that would be about ${usd(i.qualify.fee)}.` : 'The fee is worked out from the corrected bill, not from an estimate.',
      'No upfront cost and no fee if the value does not go down.',
      'The exact terms are in the agreement you sign.',
    ],
    table: null, bars: null,
    notes: 'State the fee once, clearly. Do not negotiate terms in the call; the agreement governs.',
  });

  slides.push({
    kicker: 'Next steps',
    title: 'Questions, then the agreement',
    lead: null,
    bullets: [
      opts.bookingUrl ? `Book a time to talk: ${opts.bookingUrl}` : 'Reply to our email with a few times that suit you.',
      'If you want to go ahead, we send the agreement and the DR-486POA to sign.',
      'Questions any time: claimos@agentmail.to',
      'Claim OS is a private company and is not affiliated with any government agency.',
    ],
    table: null, bars: null,
    notes: 'Close by asking whether they want the agreement. If not ready, agree on a follow-up date.',
  });

  return {
    caseId: i.caseId,
    version: opts.version,
    builtOn: opts.today,
    address: title(i.address),
    county: i.county,
    presenter: opts.presenter,
    bookingUrl: opts.bookingUrl,
    hasEvidence: !!i.evidence,
    slides,
    sources: ['Florida Department of Revenue county tax roll (NAL)', 'County sales file', ...(i.evidence ? ['Claim OS evidence packet'] : []), 'Claim OS Qualify assessment'],
  };
}

const esc = (s: string) => s.replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!);
const linkify = (s: string) => esc(s).replace(/(https:\/\/[^\s<]+)/g, '<a href="$1">$1</a>');

function slideHtml(s: Slide, n: number, total: number) {
  const max = s.bars ? Math.max(...s.bars.items.map((b) => b.value)) : 0;
  return `<section class="slide" data-n="${n}">
  <p class="kicker">${esc(s.kicker)}</p>
  <h2>${esc(s.title)}</h2>
  ${s.lead ? `<p class="lead">${esc(s.lead)}</p>` : ''}
  ${s.table ? `<table><thead><tr>${s.table.head.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${s.table.rows.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join('')}</tr>`).join('')}</tbody></table>` : ''}
  ${s.bars ? `<div class="bars">${s.bars.items.map((b) => `<div class="bar${b.highlight ? ' hl' : ''}"><span class="bl">${esc(b.label)}</span><span class="bt"><span style="width:${Math.max(2, (b.value / max) * 100).toFixed(1)}%"></span></span><span class="bv">$${Math.round(b.value)} ${esc(s.bars!.unit)}</span></div>`).join('')}</div>` : ''}
  ${s.bullets.length ? `<ul>${s.bullets.map((b) => `<li>${linkify(b)}</li>`).join('')}</ul>` : ''}
  <p class="foot">${n} / ${total}</p>
  <aside class="notes"><strong>Speaker notes</strong><p>${esc(s.notes)}</p></aside>
</section>`;
}

export function renderHtml(d: Deck, opts: { present: boolean; pdfUrl: string }) {
  return `<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>${esc(d.address)} · Claim OS briefing</title>
<style>
:root{--ink:#14213d;--muted:#5c6b80;--line:#d9e0ea;--bg:#f5f7fa;--card:#fff;--accent:#1f6feb;--hl:#d9480f}
@media (prefers-color-scheme:dark){:root{--ink:#e8edf5;--muted:#9aa8bb;--line:#2b3546;--bg:#0f141c;--card:#161d28;--accent:#5b9dff;--hl:#ff8a4c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
header{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--line)}
header a,header button{font:inherit;color:var(--accent);background:none;border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer;text-decoration:none}
main{max-width:1100px;margin:0 auto;padding:16px}
.slide{display:none;background:var(--card);border:1px solid var(--line);border-radius:14px;padding:clamp(20px,5vw,56px);min-height:min(70vh,620px);position:relative}
.slide.on{display:block}.kicker{color:var(--accent);font-weight:600;letter-spacing:.02em;margin:0 0 8px}
h2{font-size:clamp(24px,4vw,40px);line-height:1.15;margin:0 0 12px}.lead{font-size:clamp(17px,2.2vw,22px);color:var(--muted);margin:0 0 20px}
ul{padding-left:1.2em;font-size:clamp(16px,2vw,20px)}li{margin:8px 0}a{color:var(--accent)}
table{border-collapse:collapse;width:100%;font-size:clamp(14px,1.8vw,18px);margin:8px 0 16px;display:block;overflow-x:auto}th,td{text-align:left;padding:8px 12px;border-bottom:1px solid var(--line);white-space:nowrap}th{color:var(--muted);font-weight:600}
.bars{display:grid;gap:10px;margin:16px 0}.bar{display:grid;grid-template-columns:minmax(120px,30%) 1fr auto;gap:12px;align-items:center}.bl{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bt{background:var(--line);border-radius:6px;height:22px;overflow:hidden}.bt span{display:block;height:100%;background:var(--muted)}.bar.hl .bt span{background:var(--hl)}.bar.hl .bl,.bar.hl .bv{font-weight:700}
.foot{position:absolute;right:20px;bottom:12px;color:var(--muted);font-size:13px;margin:0}
.notes{display:none;margin-top:20px;border-top:1px dashed var(--line);padding-top:12px;color:var(--muted)}body.present .notes{display:block}
nav{display:flex;justify-content:center;gap:12px;margin:16px 0}
@media print{header,nav{display:none}.slide{display:block;page-break-after:always;border:0;min-height:auto}.notes{display:none!important}}
@media (max-width:600px){.bar{grid-template-columns:1fr;gap:4px}}
</style></head>
<body class="${opts.present ? 'present' : ''}">
<header><strong>Claim OS · ${esc(d.address)}</strong><span><a href="${esc(opts.pdfUrl)}">PDF</a> <button id="notes" type="button">${opts.present ? 'Hide notes' : 'Speaker notes'}</button></span></header>
<main>${d.slides.map((s, k) => slideHtml(s, k + 1, d.slides.length)).join('\n')}
<nav><button id="prev" type="button">← Back</button><button id="next" type="button">Next →</button></nav>
<p style="color:var(--muted);font-size:13px">Version ${d.version} · built ${esc(d.builtOn)} · sources: ${esc(d.sources.join('; '))}. Claim OS is a private company and is not affiliated with any government agency.</p></main>
<script>
const s=[...document.querySelectorAll('.slide')];let i=0;const show=()=>s.forEach((x,k)=>x.classList.toggle('on',k===i));
document.getElementById('prev').onclick=()=>{i=Math.max(0,i-1);show()};document.getElementById('next').onclick=()=>{i=Math.min(s.length-1,i+1);show()};
document.getElementById('notes').onclick=(e)=>{document.body.classList.toggle('present');e.target.textContent=document.body.classList.contains('present')?'Hide notes':'Speaker notes'};
addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key===' '){i=Math.min(s.length-1,i+1);show()}if(e.key==='ArrowLeft'){i=Math.max(0,i-1);show()}});show();
</script></body></html>`;
}

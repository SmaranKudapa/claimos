// The check flow. Needs on the page: <form class="bar" data-check> with inputs named address + zip and a
// <p class="bar-err" role="alert"> after it, plus an empty <section id="result" class="wrap" hidden>.
// Reads ?address=&zip= from the URL and runs on load when both are present.
(() => {
  const $ = (s, r = document) => r.querySelector(s);
  const money = (n) => '$' + Math.round(n).toLocaleString('en-US');
  const title = (s) => s.trim().replace(/\s+/g, ' ').toLowerCase().replace(/(^|\s)\S/g, (c) => c.toUpperCase());
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const TIERS = { strong: ['Strong case', 'green'], possible: ['Possible case', 'amber'], review: ['Needs review', 'gray'],
    cap_absorbs: ['Likely no savings this year', 'gray'], new_build: ['Likely no savings this year', 'gray'] };
  const STEPS = ['Locating the parcel on the county roll', 'Comparing recent nearby sales', "Checking similar homes' assessments", 'Estimating your savings'];
  const TICKS = [500, 1100, 1800];
  const CHECK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m5 12 5 5 9-10"/></svg>';

  const form = $('form[data-check]'), bar = $('.bar-err'), result = $('#result');
  if (!form || !result) return;

  // Not in our scan: realistic, deterministic numbers from the same key the API matches on (FNV-1a 32-bit).
  function illustrative(address, zip) {
    const key = address.trim().replace(/\s+/g, ' ').toUpperCase() + '|' + zip.trim();
    let h = 0x811c9dc5;
    for (let i = 0; i < key.length; i++) h = Math.imul(h ^ key.charCodeAt(i), 0x01000193) >>> 0;
    const value = 240000 + (h % 540001);
    const over = Math.round(value * (7 + ((h >>> 8) % 12)) / 100 / 1000) * 1000;
    return { value, over, savings: Math.round(over * 0.015 / 10) * 10 };
  }

  // Ease-out count from $0; the final string's width is reserved first so nothing shifts.
  function countUp(el, target, { duration = 1400, delay = 0 } = {}) {
    const final = money(target);
    el.textContent = final;
    el.style.minWidth = el.offsetWidth + 'px';
    if (reduced) return;
    el.textContent = '$0';
    setTimeout(() => {
      let start;
      const frame = (t) => {
        start ??= t;
        const p = Math.min(1, (t - start) / duration), e = 1 - Math.pow(1 - p, 3);
        el.textContent = p < 1 ? money(target * e) : final;
        if (p < 1) requestAnimationFrame(frame);
      };
      requestAnimationFrame(frame);
    }, delay);
  }

  const finding = (address, zip) => {
    const el = document.createElement('div');
    el.className = 'card finding rise'; el.setAttribute('aria-busy', 'true');
    el.innerHTML = '<span class="label">Finding your property</span><p class="finding-addr"></p><ol>' +
      STEPS.map((s, i) => `<li${i ? '' : ' class="is-current"'}><span class="tick">${CHECK}</span>${s}</li>`).join('') + '</ol>';
    $('.finding-addr', el).textContent = title(address) + ', ' + zip;
    return el;
  };
  const tick = (el, i) => {
    const rows = el.querySelectorAll('li');
    if (!rows[i] || rows[i].classList.contains('is-done')) return;
    rows[i].className = 'is-done';
    if (rows[i + 1]) rows[i + 1].className = 'is-current';
  };

  const verdictCard = (d) => {
    const el = document.createElement('div');
    el.className = 'rise';
    el.innerHTML = `
      <div class="result-head"><span class="label">${d.illustrative ? 'Illustrative estimate' : 'Your property'}</span><span></span></div>
      <div class="card stat dual">
        <div><span class="label">Over-assessed by</span><strong class="figure" id="r-over">$0</strong><span class="stat-sub"></span></div>
        <div><span class="label">You could save</span><strong class="figure"><span id="r-save">$0</span><small>/ yr</small></strong><span class="stat-sub">Estimated yearly tax saving</span></div>
        <div class="stat-foot full"><span class="badge" data-tone="${d.tone}">${d.badge}</span><span class="r-note"></span><span class="caption"></span></div>
      </div>`;
    $('.result-head span:last-child', el).textContent = d.address;
    $('.stat-sub', el).textContent = d.illustrative ? `Illustrative value ${money(d.value)}` : `County's value ${money(d.value)} · Our defensible value ${money(d.value - d.over)}`;
    $('.r-note', el).textContent = d.note;
    $('.caption', el).textContent = d.illustrative ? "Illustrative estimate — we'll confirm against the county roll." : `From county records, run ${d.run}.`;
    return el;
  };

  const signupCard = (d) => {
    const el = document.createElement('div');
    el.className = 'card form-card rise'; el.id = 'signup';
    el.innerHTML = `
      <h2>Start your review</h2>
      <p class="sub">No cost to start. We reply from claimos@agentmail.to.</p>
      <form class="form-grid" novalidate>
        <div class="field full"><label for="f-address">Street address</label><input id="f-address" name="address" type="text" autocomplete="street-address" required><small class="err" id="err-address" role="alert"></small></div>
        <div class="field" id="unit-field" hidden><label for="f-unit">Unit</label><input id="f-unit" name="unit" type="text" autocomplete="address-line2"></div>
        <div class="field"><label for="f-city">City</label><input id="f-city" name="city" type="text" autocomplete="address-level2"></div>
        <div class="field"><label for="f-zip">ZIP</label><input id="f-zip" name="zip" type="text" inputmode="numeric" pattern="[0-9]{5}" maxlength="5" autocomplete="postal-code" required><small class="err" id="err-zip" role="alert"></small></div>
        <div class="field"><label for="f-email">Email</label><input id="f-email" name="email" type="email" autocomplete="email" required><small class="err" id="err-email" role="alert"></small></div>
        <div class="field"><label for="f-phone">Phone (optional)</label><input id="f-phone" name="phone" type="tel" autocomplete="tel"></div>
        <label class="check full"><input id="f-call-ok" name="call_ok" type="checkbox" disabled><span>You may call me about this property</span></label>
        <label class="check full"><input name="pro_call" type="checkbox"><span>Request a call with a licensed tax professional</span></label>
        <div class="field full"><label class="check"><input name="consent" type="checkbox" required><span>I own this property or act for the owner, and agree that Claim OS may review its public records and email me about an appeal.</span></label><small class="err" id="err-consent" role="alert"></small></div>
        <div class="field full"><button class="btn" type="submit">Start my review</button><small class="err" id="err-form" role="alert"></small></div>
      </form>
      <div class="thanks" id="thanks" hidden>
        <h2 tabindex="-1">Thanks — we're on it.</h2>
        <ul>
          <li>We confirm your parcel against the county roll by hand.</li>
          <li>You'll hear from claimos@agentmail.to within a day or two — add it to your contacts so it isn't filtered.</li>
          <li>If the case holds, we send the agreement to sign. Nothing is filed before you sign.</li>
        </ul>
        <div class="pills"><a class="pill" href="/track">Track my claim</a><a class="pill" href="/check">Check another address</a></div>
      </div>`;
    const f = $('form', el);
    f.address.value = d.street; f.unit.value = d.unit || ''; f.city.value = d.city || ''; f.zip.value = d.zip;
    $('#unit-field', el).hidden = !d.needUnit;
    f.phone.addEventListener('input', () => { f.call_ok.disabled = !f.phone.value.trim(); if (f.call_ok.disabled) f.call_ok.checked = false; });
    f.addEventListener('submit', async (e) => {
      e.preventDefault();
      const btn = $('button', f);
      f.querySelectorAll('.err').forEach((x) => { x.textContent = ''; });
      const body = { address: f.address.value, unit: f.unit.value, city: f.city.value, zip: f.zip.value, email: f.email.value, phone: f.phone.value,
        call_ok: f.call_ok.checked, pro_call: f.pro_call.checked, consent: f.consent.checked };
      btn.disabled = true;
      try {
        const r = await fetch('/api/signup', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
        if (r.status === 201) {
          f.hidden = true; $('.sub', el).hidden = true; $('h2', el).hidden = true;
          const t = $('#thanks', el); t.hidden = false; $('h2', t).focus();
          return;
        }
        const errors = (await r.json().catch(() => ({}))).errors || { form: 'Something went wrong. Please try again.' };
        for (const k in errors) ($('#err-' + k, el) || $('#err-form', el)).textContent = errors[k];
      } catch { $('#err-form', el).textContent = 'We could not reach our server. Please try again.'; }
      btn.disabled = false;
    });
    return el;
  };

  function show(d) {
    const card = verdictCard(d);
    result.replaceChildren(card, signupCard(d));
    countUp($('#r-over', card), d.over);
    countUp($('#r-save', card), d.savings, { delay: 300 });
  }

  const fmtRun = (iso) => (iso ? new Date(iso + 'T00:00:00').toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : 'recently');

  async function run(address, zip, unit = '') {
    bar.textContent = '';
    result.hidden = false;
    const seq = finding(address, zip);
    result.replaceChildren(seq);
    if (result.getBoundingClientRect().top > innerHeight * .6) result.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
    const timers = reduced ? [] : TICKS.map((ms, i) => setTimeout(() => tick(seq, i), ms));
    let v;
    try {
      // The sequence takes ~2.5 s and never finishes before the records answer.
      [v] = await Promise.all([fetch('/api/verdict?' + new URLSearchParams({ address, zip, unit })).then((r) => r.json()), wait(reduced ? 0 : 2500)]);
    } catch {
      timers.forEach(clearTimeout);
      bar.textContent = 'We could not reach our records. Please try again.';
      result.replaceChildren(signupCard({ street: title(address), zip, unit }));
      return;
    }
    if (v.several && v.units && v.units.length) {
      timers.forEach(clearTimeout);
      const pick = document.createElement('div');
      pick.className = 'finding-unit';
      pick.innerHTML = '<p>Several units share this address. Which one is yours?</p><div class="row"><div class="field"><select aria-label="Your unit"></select></div><button class="btn" type="button">Continue</button></div>';
      const sel = $('select', pick);
      sel.replaceChildren(new Option('Choose your unit', '', true, true), ...v.units.map((u) => new Option('Unit ' + u, u)));
      $('button', pick).addEventListener('click', () => { if (sel.value) run(address, zip, sel.value); });
      seq.append(pick); seq.removeAttribute('aria-busy'); sel.focus();
      return;
    }
    STEPS.forEach((_, i) => tick(seq, i));
    seq.removeAttribute('aria-busy');
    await wait(reduced ? 0 : 450);
    seq.classList.add('is-leaving');
    await wait(reduced ? 0 : 300);
    if (v.found) {
      const [badge, tone] = TIERS[v.tier] || TIERS.review;
      show({ street: title(v.address), address: title(v.address) + (v.unit ? ' #' + v.unit : '') + ', ' + (v.zip || zip), unit: v.unit || unit, city: v.city ? title(v.city) : '', zip: v.zip || zip,
        value: v.just_value, over: v.just_value - v.defensible_value, savings: v.annual_savings, badge, tone,
        note: 'Estimate from public county records and recent sales; the county decides.', run: fmtRun(v.run_date) });
    } else {
      const n = illustrative(address, zip);
      show({ street: title(address), address: title(address) + ', ' + zip, unit, zip, illustrative: true, needUnit: Boolean(v.several), value: n.value, over: n.over, savings: n.savings, badge: 'Needs a manual check', tone: 'gray',
        note: v.several ? "Several units share this address and the county roll does not tell them apart. Leave your unit number below and we'll check by hand."
          : "We haven't scanned this address yet. Leave your email and we'll check it by hand." });
    }
  }

  form.addEventListener('submit', (e) => {
    e.preventDefault();
    const address = form.address.value.trim(), zip = form.zip.value.trim();
    if (!address || !/^\d{5}$/.test(zip)) { bar.textContent = 'Enter a street address and a 5-digit ZIP.'; return; }
    run(address, zip);
  });

  const q = new URLSearchParams(location.search);
  if (q.get('address') && /^\d{5}$/.test(q.get('zip') || '')) {
    form.address.value = q.get('address'); form.zip.value = q.get('zip');
    run(q.get('address').trim(), q.get('zip'));
  }
})();

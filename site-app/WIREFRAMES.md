# Claim OS site — information architecture and wireframes (2026-11-07)

Static pages in `public/`, one `site.css` (rename of `styles.css`; everything below reuses its classes), vanilla JS,
Inter, Mainstay visual language. `vercel.json` gets `"cleanUrls": true` so `check.html` serves at `/check`.
Decisions that trim the brief: `/thanks` is a state on `/check`, not a page; the home "sample verdict card" is the
hero card (same component as the `/check` result, static Example numbers); the home hero bar hands off to
`/check?address=&zip=` instead of running the flow twice; the mobile menu is a `<details>` (no JS).

## 1. Site map

| URL | File | Title (`<title>`) | In nav |
|---|---|---|---|
| `/` | index.html | Claim OS — Your property tax, appealed | wordmark |
| `/check` (+`?address=&zip=`) | check.html | Check my property — Claim OS | dark pill (right) |
| `/how-it-works` | how-it-works.html | How it works — Claim OS | 1 |
| `/pricing` | pricing.html | How we get paid — Claim OS | 2 (label "How we get paid") |
| `/faq` | faq.html | Questions owners ask — Claim OS | 3 |
| `/about` | about.html | About Claim OS | 4 |
| `/track` (+`?t=`) | track.html | Track my claim — Claim OS | ghost pill (right, before the dark pill) |
| `/privacy`, `/terms` | privacy.html, terms.html | Privacy — Claim OS / Terms — Claim OS | footer only |

APIs: `/api/verdict` (exists), `/api/signup` (exists), `/api/stats` (new, GET, `cache-control: public, max-age=3600`,
returns `{counties, homes, cases, run_date}` from `candidates`: distinct `county`, `count(*)`, `count(tier in
strong,possible)`, `max(imported_at)`), `/api/track-link` (new, POST `{email}` → HMAC token with `TRACK_SECRET`,
emailed via AgentMail from the server), `/api/track` (new, GET `?t=` → verifies, returns `cases` ⋈ `signups` on email).

Footer links, three columns: **Product** Check my property · Track my claim · How it works · How we get paid;
**Company** About · FAQ · claimos@agentmail.to; **Legal** Privacy · Terms. Below: the disclaimer paragraph
(private company, not a government agency, county property appraiser or VAB; not a law firm; estimates from public
records, the county decides, nothing here is a promise) and "© 2026 Claim OS".

## 2. Shared components (all in site.css; names are the current classes where they exist)

- **Nav** `.nav`: 72px (64 mobile); wordmark "Claim OS" left; centre links in the order above (15px); right: `.pill`
  "Track my claim" + `.btn` "Check my property" → `/check`. `aria-current="page"` on the active link (ink underline).
  ≤720px: links and the ghost pill fold into `<details class="menu"><summary>Menu</summary>…` listing all 5 links.
- **Footer** `footer`: 3 link columns (`.label` headings) over the disclaimer `<p>` (13px, muted, max 90ch).
- **Pill buttons**: `.btn` dark 44px pill (primary, one per section); `.pill` off-white 34px ghost pill with a 13px
  icon (secondary links); `.btn.btn-light` off-white 44px pill (secondary CTA beside a `.btn`). Dark bands invert.
- **Numeric card** `.card.num`: `.label` micro-label (11px upper) → figure 36px/500, `font-variant-numeric:
  tabular-nums`, `.num-sub` 12px muted line under it. Variants: `.num.dual` two cards side by side (grid 1fr 1fr,
  stacks ≤720); the hero/pricing "Example" version carries a `.label` "Example". Width reserved from the final
  formatted string before the count-up so nothing shifts.
- **Badge** `.badge[data-tone=green|amber|gray]`: Strong case / Possible case / Needs review / Likely no savings this
  year / Needs a manual check (gray) / Closed (gray).
- **Step tracker** `.tracker`: 8 `<li>` (Find, Qualify, Sign up, Evidence, File, Waiting on county, Appeal again, Won
  and paid); states `is-done` (ink dot + check), `is-current` (ring, label in ink), upcoming (muted). Horizontal
  with a connecting line ≥960px, vertical list below. `aria-current="step"` on the current one.
- **FAQ accordion** `.faq details > summary` (+ icon rotates 45° when open; 17px question; 16px muted answer,
  max 64ch). Groups get an `h2` above a `.grid`.
- **Form fields** `.field` (13px label, 44px input, 8px radius), `.check` (checkbox + 14px text), `.err[role=alert]`
  under each field (`:empty` hidden), `.form-grid` 2 columns → 1 at ≤720. Buttons disabled while submitting.
- **Address bar** `.bar`: icon + street input + ZIP input (`inputmode=numeric`, `pattern=[0-9]{5}`) + `.btn` inside;
  stacks to three rows ≤720. Used on `/`, `/check`, and every "final CTA" band.
- **Finding sequence** `.finding` (`aria-live=polite`, `aria-busy` while running): micro-label "FINDING YOUR
  PROPERTY" + the typed address (title-cased); 4 rows, each a 16px circle that fills with a check and a 14px line.
  Ticks at 500 / 1100 / 1800 / 2500 ms after submit; the 4th row never ticks before `/api/verdict` has answered
  (`Promise.all([fetch, timer(2500)])`). Rows: "Locating the parcel on the county roll" · "Comparing recent nearby
  sales" · "Checking similar homes' assessments" · "Estimating your savings". `prefers-reduced-motion`: all four
  shown ticked at once when the response lands.
- **Count-up** `countUp(el, target, {duration: 1400, delay: 0})`: ease-out cubic via `requestAnimationFrame`, renders
  `$` + `toLocaleString('en-US')` each frame, tabular numerals, final text set exactly; reduced motion → set at once.
- **Section header** pattern: `.label` eyebrow → `h2` 32px → one-line `.sub` (18px muted). Blocks are 96px tall
  padding (64 mobile); `.band` is the off-white #f4f3f0 section; `.band.dark` is #1b1d21 with white text.
- **Prose** `.prose` for /privacy, /terms, /about: 16px/1.6, max 64ch, `h2` 22px with 40px top margin.

## 3. Pages

### `/` Home
1. Nav.
2. Hero (grid background, 2 columns 1fr/340px): h1 "Your property tax, appealed. You pay only if it goes down."
   `.sub` "Claim OS checks public county records for over-assessed Florida homes, files the appeal, and keeps a
   share of the first year's savings — only if your value goes down. Terms in the agreement." Address bar → on
   submit `location = /check?address=…&zip=…` (client validation: both fields; error line "Enter a street address
   and a 5-digit ZIP."). Under it 3 ghost pills: How it works (`/how-it-works`), Why trust us (`#trust`), FAQ (`/faq`).
   Right: `.num.dual` Example card — "OVER-ASSESSED BY $60,000" (sub "County's value $420,000 · Our defensible
   value $360,000") | "YOU COULD SAVE $1,100 / yr"; badge "Strong case"; caption "Example figures. Check your own
   address." Static, no count-up.
3. Proof strip (`.band`, three `.num` tiles from `/api/stats`): "COUNTIES SCANNED" counties · "HOMES IN OUR LAST
   SCAN" homes · "STRONG OR POSSIBLE CASES" cases; caption "From public county rolls, run {run_date}". While
   loading show "—"; if the request fails hide the whole strip (never show zeros).
4. How it works: eyebrow "HOW IT WORKS", h2 "Four things happen. You do one of them." 4 `.step` cards (existing copy:
   We find / We check / We file / You save) + `.pill` "See all eight steps" → `/how-it-works`.
5. Why trust us `#trust`: h2 "Why trust us", 3 `.step` cards (existing copy: Paid only on a win / Every number from
   county records / A licensed professional on request, with the private-company line).
6. FAQ teaser: h2 "Questions owners ask", the 3 existing `<details>` (cost, how long, what we need) + `.pill` "All
   questions" → `/faq`.
7. Final CTA `.band.dark`: h2 "Check your address. It takes ten seconds." address bar (white) → `/check`; 13px line
   "Claim OS is a private company, not a government agency."
8. Footer.
Mobile: hero text → bar → pills → example card; strip tiles 3 rows; all grids 1 column.

### `/check` Check my property (the demo moment)
1. Nav.
2. Compact hero (grid bg): eyebrow "CHECK MY PROPERTY", h1 36px "Is your home over-assessed?", `.sub` "Enter the
   address as it appears on your tax bill. We look it up in the county roll we scanned last." Address bar prefilled
   from the query (autofocus when empty; auto-submit when both present). Error line: "Enter a street address and a
   5-digit ZIP." / "We could not reach our records. Please try again." (typed values kept; `.pill` "Try again").
3. `#result` (hidden until submit, `aria-live=polite`), states in order:
   a. **Finding sequence** card (above). Unit picker: when the response is `several:true`, rows 2–4 stop, and under
      row 1 appears "Several units share this address. Which one is yours?" + `<select>` (existing `.v-unit`) +
      `.btn` "Continue"; choosing re-runs the fetch with `unit` and rows 2–4 tick. `several` with no unit list →
      "…the county roll does not tell them apart. Leave your unit number below and we'll check by hand." and the
      flow falls through to the illustrative result (c, not-found branch).
   b. **Result** replaces the sequence with a 300ms fade: `.num.dual` — LEFT "OVER-ASSESSED BY" count-up of
      `just_value − defensible_value` (sub "County's value {just} · Our defensible value {def}"); RIGHT "YOU COULD
      SAVE" count-up of `annual_savings` with "/ yr" suffix (sub "Estimated yearly tax saving"), delay 250ms after
      the left. Under the pair: `.badge` from `tier` (map in index.html today) + one line "Estimate from public
      county records and recent sales; the county decides." + 12px "From county records, run {run_date}."
   c. **Not found** (`found:false`): same screen; eyebrow becomes "ILLUSTRATIVE ESTIMATE", badge "Needs a manual
      check" (gray), line "Illustrative estimate — we'll confirm against the county roll." Numbers are deterministic
      from `addrKey(address, zip)`: FNV-1a 32-bit `h`; value = 240,000 + h % 540,001; over% = 7 + (h >> 8) % 12;
      over-assessed = round(value × over% / 100, 1000); savings = round(over-assessed × 0.015, 10). Sub under the left
      card: "Illustrative value {value}". No web lookups.
   d. **Sign-up form** `.card.form-card` directly under the result: h2 "Start your review", sub "No cost to start.
      We reply from claimos@agentmail.to." Fields as today (address, unit hidden, city, ZIP, email, phone, "You may
      call me" enabled only with a phone, "Request a call with a licensed tax professional", consent) prefilled from
      the check; `.btn` "Start my review". Field errors from `/api/signup` land in their `.err`; network → `#err-form`.
   e. **Thank-you** replaces the form (`#thanks`, focus moves to its h2): h2 "Thanks — we're on it." Three lines:
      "We confirm your parcel against the county roll by hand." · "You'll hear from claimos@agentmail.to within a
      day or two — add it to your contacts so it isn't filtered." · "If the case holds, we send the agreement to
      sign. Nothing is filed before you sign." `.pill` "Track my claim" → `/track`; `.pill` "Check another address".
4. Footer.
Mobile: cards stack left-then-right (same timing); form 1 column; sequence rows unchanged.

### `/how-it-works`
1. Nav. 2. Compact hero: eyebrow "HOW IT WORKS", h1 "Eight steps. Most of them are ours.", `.sub` "The whole loop,
   what we do at each step, and the little we need from you."
3. Eight `.step` cards (2 per row, 1 on mobile), each: `.num`, h3, two 14px blocks labelled "CLAIM OS" and "YOU":
   1 Find — We scan the county roll for homes valued above similar recent sales. / Nothing.
   2 Qualify — We compare your assessment with neighbours' and with sales; weak cases are dropped and we say so. / Nothing.
   3 Sign up — You check your address and leave an email; we confirm the parcel by hand. / Ten seconds on the site,
     then one signed agreement and, where the county asks for it, a DR-486POA form.
   4 Evidence — We assemble comparable sales, assessment ratios and anything you send into one packet. / Answer an
     email or two if we have a question.
   5 File — We file the petition with the county's value adjustment board before its deadline and pay the filing
     fee. / Nothing.
   6 Waiting on the county — The VAB sets a hearing; a special magistrate hears both sides. / Nothing; we email the date.
   7 Appeal again — If the first decision is weak we judge whether a second round is worth it, and tell you. / Decide with us.
   8 Won and paid — Your value goes down and your bill follows. We invoice a share of the first year's savings; the
     terms are in the agreement. If nothing changes, you owe nothing. / Pay once the lower bill is real.
4. Timeline `.band`: h2 "The Florida calendar", 4 `.num`-style tiles (eyebrow month, 20px title, 14px line): AUGUST
   "TRIM notices" · ~25 DAYS LATER "Petition deadline" · FALL–WINTER "Hearings" · NOVEMBER "Tax bills". Caption
   "Each county sets its own dates. We work to the county's, never ours."
5. CTA `.band.dark` with address bar → `/check`. 6. Footer.

### `/pricing` — "How we get paid"
1. Nav. 2. Hero: eyebrow "HOW WE GET PAID", h1 "A share of the first year's savings. Only if the value goes down.",
   `.sub` "Nothing upfront, nothing if the county keeps the value where it is. The exact share is in the agreement
   you sign before we file." (No number anywhere on the page.)
3. Two cards: **Included** — the parcel check · the evidence packet · the petition and its filing fee ·
   representation at the hearing · email updates at every step · a licensed tax professional on request.
   **Not included** — legal advice (Claim OS is not a law firm) · your tax bill itself · tax years already closed ·
   anything you did not sign for.
4. "Who files" `.prose`: "Claim OS files as your agent, with a DR-486POA where the county requires one. The petition
   is in your name, and you can withdraw it before the hearing."
5. Example `.num.dual` card (eyebrow "EXAMPLE"): "COUNTY'S VALUE $420,000 → AGREED VALUE $360,000" | "FIRST-YEAR
   SAVING $1,100"; under it two lines "Our share: set in your agreement." · "You keep the rest, and every year after."
6. FAQ teaser: the three money questions from `/faq` + `.pill` "All questions". 7. CTA `.band.dark` → `/check`. 8. Footer.

### `/faq`
1. Nav. 2. Hero: eyebrow "FAQ", h1 "Questions owners ask us."
3. Accordions in five groups (h2 22px): **Money** What does it cost? · When do I pay? · Can my value go up because
   I appealed? **Timing** How long does it take? · I missed the petition deadline — now what? **What we need** What
   do you need from me? · What is a DR-486POA? · I have a homestead cap, does this still help? **Your home** I own a
   condo — does this work? · I live out of state. · How did you find my home? **Us** Are you the county? · Are you
   lawyers? · What do you store about me? Answers 2–4 sentences, honest: fee answer is the agreement line (no number);
   "can it go up" → "The board rules on the evidence; a value can in principle move either way, which is why we
   drop weak cases before filing."; homestead cap → "The cap limits how fast your assessed value rises; if the cap
   already holds your taxable value below our target, there may be no saving this year, and the check says so."
4. Row: "Still have a question?" + `.pill` "Email claimos@agentmail.to" (`mailto:`). 5. Footer.

### `/about`
1. Nav. 2. Hero: eyebrow "ABOUT", h1 "A small team, mostly software.", `.sub` "Claim OS was built at the Naïve
   Autonomous Company Hackathon (YC), November 2026. Agents do the scanning, drafting and follow-up; people approve
   every email that goes out and every filing."
3. Two cards: **Agents do** scan rolls, qualify cases, draft emails, assemble evidence, chase the county. **People do**
   approve outreach, sign filings, answer you when the question is hard.
4. "Rules we hold ourselves to" (6 `.step` cards): A private company, not affiliated with any government agency ·
   No fee outside the agreement you sign · No promised outcomes · No cold calls or texts · Public records plus what
   you typed, nothing more · The county's dates, never ours.
5. Contact: "claimos@agentmail.to — we reply by email, and only call when you asked us to." 6. Footer.

### `/track` Track my claim
1. Nav.
2. **State A** (no `t`): eyebrow "TRACK MY CLAIM", h1 "Where is my claim?", `.sub` "Enter the email you signed up
   with. We send a link that opens your cases." Form: email `.field` + `.btn` "Email me a link". Success (same text
   whether or not the email is known): "If we have cases for that email, a link is on its way from
   claimos@agentmail.to. It works for 24 hours." Error: "We could not send the link. Please try again."
3. **State B** (`?t=` valid): h1 "Your claims", `.sub` with the email. One `.card` per case: address + county;
   `.tracker` with `is-current` = `cases.stage`; `.num.dual` "COUNTY'S VALUE {county_value}" | "OUR REQUESTED VALUE
   {requested_value}" with sub "Est. saving {annual_savings} / yr"; row "Filing deadline {filing_deadline}"; callout
   "WHAT WE NEED FROM YOU" = `needs_from_owner` or "Nothing right now."; "History" list from `history` jsonb
   (date · line, newest first). `status = stopped` → badge "Closed", tracker greyed.
   Empty state (signups but no cases): "Nothing yet. We have your sign-up for {address} and are checking the parcel;
   this page fills in as we go." Invalid or expired token: "This link has expired. Request a new one." + State A form.
4. Footer. Mobile: tracker vertical; dual card stacks.

### `/privacy` and `/terms`
Same layout: Nav → eyebrow + h1 ("Privacy" / "Terms") + "Last updated 7 Nov 2026" → `.prose` → Footer.
Privacy h2s: What we store (what you typed on the site; public county roll data about the parcel; the emails we
exchange) · What we never do (sell or share your data; contact you beyond this claim) · Where (Florida; US hosting)
· Delete or ask (email claimos@agentmail.to). Terms h2s: Who we are (a private company; not a government agency; not
a law firm) · What we do · How we are paid (a share of the first year's savings, only if the value goes down; the
share is in the agreement) · No guarantee (the county decides) · Your choices (withdraw before the hearing) ·
Governing law (Florida) · Contact.

## 4. Content rules checked on every page
Private-company line in the footer and wherever we describe ourselves; no fee number or percentage anywhere;
no promised outcome ("could save", "estimate", "the county decides"); no urgency beyond the county's own dates;
"not a law firm"; 11px only for `.label`, reading text ≥12px; every page passes at 1280 and 375 with no horizontal
scroll, clean console, keyboard-reachable forms, real `<title>` and meta description.

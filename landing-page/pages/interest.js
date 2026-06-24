import Head from 'next/head';
import { useState, useCallback, useRef } from 'react';

/* ── helpers ── */
const fmt = (n, d = 0) => Number(n).toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtD = n => '$' + fmt(Math.round(n));
const fmtPct = n => Number(n).toFixed(2) + '%';
const fmtYr = mo => {
  const y = Math.floor(mo / 12), m = mo % 12;
  return y > 0 ? (m > 0 ? `${y} yr ${m} mo` : `${y} yr`) : `${m} mo`;
};

function amortize(principal, annRate, totalMo, extraMo = 0) {
  const r = annRate / 100 / 12;
  const pmt = r === 0
    ? principal / totalMo
    : principal * (r * Math.pow(1 + r, totalMo)) / (Math.pow(1 + r, totalMo) - 1);
  let bal = principal, totInt = 0, mo = 0, sched = [];
  while (bal > 0.005 && mo < totalMo * 2) {
    mo++;
    const ip = bal * r;
    let pp = pmt - ip + extraMo;
    if (pp > bal) pp = bal;
    totInt += ip;
    bal -= pp;
    if (bal < 0) bal = 0;
    sched.push({ mo, payment: ip + pp, principal: pp, interest: ip, balance: bal, cumInt: totInt });
  }
  return { pmt, totInt, months: mo, sched };
}

function irr(cfs, g = 0.005) {
  let r = g;
  for (let i = 0; i < 300; i++) {
    let f = 0, df = 0;
    for (let t = 0; t < cfs.length; t++) {
      const d = Math.pow(1 + r, t);
      f += cfs[t] / d;
      df -= t * cfs[t] / Math.pow(1 + r, t + 1);
    }
    if (Math.abs(df) < 1e-15) break;
    const nr = r - f / df;
    if (Math.abs(nr - r) < 1e-9) return nr;
    r = nr;
  }
  return r;
}

function effectiveRate(extra, baseRes, extraRes) {
  if (extra <= 0) return null;
  const saved = baseRes.totInt - extraRes.totInt;
  if (saved <= 0) return null;
  const n = extraRes.months;
  const cfs = Array(n).fill(-extra);
  cfs[n - 1] += saved;
  try {
    const mr = irr(cfs);
    if (!isFinite(mr) || isNaN(mr) || mr < 0) return null;
    return mr * 12 * 100;
  } catch { return null; }
}

function currentBalance(loanAmt, annRate, totalMo, paysMade) {
  if (paysMade <= 0) return loanAmt;
  const r = annRate / 100 / 12;
  if (r === 0) return loanAmt * (1 - paysMade / totalMo);
  const pmt = loanAmt * (r * Math.pow(1 + r, totalMo)) / (Math.pow(1 + r, totalMo) - 1);
  let bal = loanAmt;
  for (let i = 0; i < paysMade && bal > 0; i++) bal -= (pmt - bal * r);
  return Math.max(bal, 0);
}

function balAt(sched, mo) {
  if (!sched || mo <= 0) return 0;
  if (mo >= sched.length) return 0;
  return sched[mo - 1]?.balance ?? 0;
}

function buildAmortHTML(base, xtra, biwk) {
  const hasBi = !!biwk;
  let html = `<table class="amort"><thead><tr>
    <th>Mo.</th><th>Std payment</th><th>Std balance</th>
    <th style="color:#4db89c">+Extra pmt</th><th style="color:#4db89c">+Extra bal</th><th style="color:#4db89c">Int saved</th>`;
  if (hasBi) html += `<th style="color:#9ab8d4">Bi-wkly bal</th>`;
  html += `</tr></thead><tbody>`;
  const rows = Math.max(base.sched.length, xtra.sched.length);
  let marked = false;
  for (let i = 0; i < rows; i++) {
    const b = base.sched[i], x = xtra.sched[i], bw = hasBi ? biwk.sched[i] : null;
    const isPayoff = !marked && !x && b;
    if (isPayoff) marked = true;
    html += `<tr class="${isPayoff ? 'payoff-row' : ''}">
      <td>${b ? b.mo : (x ? x.mo : '')}</td>
      <td>${b ? fmtD(b.payment) : '—'}</td><td>${b ? fmtD(b.balance) : 'paid off'}</td>
      <td>${x ? fmtD(x.payment) : '—'}</td>
      <td>${x ? fmtD(x.balance) : (isPayoff ? '<span class="badge">✓ Paid off</span>' : 'paid off')}</td>
      <td>${x && b ? fmtD(Math.max(0, b.cumInt - x.cumInt)) : '—'}</td>`;
    if (hasBi) html += `<td>${bw ? fmtD(bw.balance) : 'paid off'}</td>`;
    html += `</tr>`;
  }
  html += `</tbody><tfoot><tr><td>Total</td><td></td><td></td>
    <td>${fmtD(xtra.sched.reduce((a, r) => a + r.payment, 0))}</td><td></td>
    <td>${fmtD(base.totInt - xtra.totInt)}</td>`;
  if (hasBi) html += `<td></td>`;
  html += `</tr></tfoot></table>`;
  return html;
}

const DEFAULTS = { loanAmt: '350000', rate: '6.75', termYrs: '30', paysMade: '0', extraAmt: '300', escrow: '450', doBiweekly: false };

export default function InterestPage() {
  const [form, setForm] = useState(DEFAULTS);
  const [result, setResult] = useState(null);
  const [amortOpen, setAmortOpen] = useState(false);

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  const calculate = useCallback(() => {
    const loanAmt = parseFloat(form.loanAmt) || 0;
    const rate = parseFloat(form.rate) || 0;
    const termYrs = parseInt(form.termYrs) || 30;
    const paysMade = parseInt(form.paysMade) || 0;
    const extra = parseFloat(form.extraAmt) || 0;
    const escrow = parseFloat(form.escrow) || 0;
    const doBi = form.doBiweekly;

    if (loanAmt < 1000 || rate <= 0) { alert('Please enter a valid loan amount and interest rate.'); return; }

    const totalMo = termYrs * 12;
    const remMo = Math.max(totalMo - paysMade, 1);
    const curBal = currentBalance(loanAmt, rate, totalMo, paysMade);

    const base = amortize(curBal, rate, remMo, 0);
    const xtra = amortize(curBal, rate, remMo, extra);
    const biwk = doBi ? amortize(curBal, rate, remMo, base.pmt / 2) : null;

    const effRate = effectiveRate(extra, base, xtra);
    const effRateBi = biwk ? effectiveRate(base.pmt / 2, base, biwk) : null;

    setResult({ loanAmt, rate, termYrs, paysMade, extra, escrow, doBi, curBal, remMo, base, xtra, biwk, effRate, effRateBi });
    setAmortOpen(false);
  }, [form]);

  const reset = () => { setForm(DEFAULTS); setResult(null); setAmortOpen(false); };

  const r = result;
  const biCol = r && r.doBi && r.biwk;
  const saved = r ? r.base.totInt - r.xtra.totInt : 0;
  const moElim = r ? r.base.months - r.xtra.months : 0;
  const eq5 = r ? r.curBal - balAt(r.xtra.sched, 60) : 0;
  const eq10 = r ? r.curBal - balAt(r.xtra.sched, 120) : 0;
  const eq5b = r ? r.curBal - balAt(r.base.sched, 60) : 0;
  const eq10b = r ? r.curBal - balAt(r.base.sched, 120) : 0;
  const maxMo = r ? r.base.months : 1;

  return (
    <>
      <Head>
        <title>Additional Payment Analysis — Perennia AI</title>
        <meta name="description" content="See how extra mortgage payments save interest and shorten your loan. Free tool from Perennia AI." />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet" />
        <style>{`
:root{--navy:#1e3a5f;--navy-mid:#2c527d;--teal:#00896a;--teal-light:#e6f4f0;--teal-mid:#4db89c;--gold:#c47d0e;--gold-light:#fdf3de;--text:#1a2a3a;--text-muted:#5a6a7a;--border:#d4dde8;--surface:#f4f7fb;--white:#ffffff;--radius:8px}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
html{font-size:15px}
body{font-family:'Inter',sans-serif;color:var(--text);background:var(--surface);line-height:1.5}
label{display:block;font-size:.72rem;color:var(--text-muted);font-weight:500;margin-bottom:4px}
input,select{width:100%;padding:7px 10px;border:1px solid var(--border);border-radius:6px;font-family:inherit;font-size:.85rem;color:var(--text);background:#fff;transition:border-color .15s}
input:focus,select:focus{outline:none;border-color:var(--teal);box-shadow:0 0 0 2px rgba(0,137,106,.1)}

/* topbar */
.topbar{background:var(--navy);height:52px;display:flex;align-items:center;justify-content:space-between;padding:0 28px;position:sticky;top:0;z-index:50}
.brand{display:flex;align-items:center;gap:10px;color:#fff;font-size:.9rem;font-weight:600}
.brand svg{width:20px;height:20px;color:var(--teal-mid)}
.tbr{display:flex;gap:8px}
.btn-g{background:rgba(255,255,255,.1);border:1px solid rgba(255,255,255,.2);color:#fff;padding:6px 14px;border-radius:6px;font-family:inherit;font-size:.78rem;font-weight:500;cursor:pointer;display:flex;align-items:center;gap:6px}
.btn-g:hover{background:rgba(255,255,255,.2)}
.btn-g svg,.btn-p svg{width:14px;height:14px}
.btn-p{background:var(--teal);border:none;color:#fff;padding:6px 16px;border-radius:6px;font-family:inherit;font-size:.78rem;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:6px}
.btn-p:hover{background:#007558}

/* layout */
.main{max-width:1140px;margin:0 auto;padding:24px 24px 48px}
.layout{display:grid;grid-template-columns:340px 1fr;gap:20px;align-items:start}
@media(max-width:860px){.layout{grid-template-columns:1fr}}

/* input panel */
.panel{background:var(--white);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;position:sticky;top:68px}
.phead{background:var(--navy);padding:13px 18px;font-size:.78rem;font-weight:600;color:#9ab8d4;text-transform:uppercase;letter-spacing:.07em;display:flex;align-items:center;gap:8px}
.phead svg{width:14px;height:14px;color:var(--teal-mid)}
.psec{padding:16px 18px;border-bottom:1px solid var(--border)}
.psec:last-child{border-bottom:none}
.psec-title{font-size:.7rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.07em;margin-bottom:12px}
.igrid{display:flex;flex-direction:column;gap:11px}
.fld{position:relative}
.pfx .sym{position:absolute;left:10px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:.85rem;pointer-events:none}
.pfx input{padding-left:22px}
.sfx .sym{position:absolute;right:10px;top:50%;transform:translateY(-50%);color:var(--text-muted);font-size:.85rem;pointer-events:none}
.sfx input{padding-right:26px}
.chk{display:flex;align-items:center;gap:8px;cursor:pointer}
.chk input[type=checkbox]{width:15px;height:15px;accent-color:var(--teal);cursor:pointer;flex-shrink:0}
.chk span{font-size:.82rem;color:var(--text)}
.run-btn{display:block;width:calc(100% - 36px);margin:14px 18px;background:var(--navy);color:#fff;border:none;padding:11px;border-radius:7px;font-family:inherit;font-size:.9rem;font-weight:600;cursor:pointer}
.run-btn:hover{background:var(--navy-mid)}

/* results */
.results{display:flex;flex-direction:column;gap:16px}
.sh{display:flex;align-items:baseline;gap:10px;margin-bottom:12px}
.sh h2{font-size:.95rem;font-weight:600;color:var(--navy);white-space:nowrap}
.shl{flex:1;border-top:1px solid var(--border);margin-top:2px}

/* effective rate banner */
.eff{background:var(--navy);border-radius:var(--radius);padding:18px 22px;display:grid;grid-template-columns:1fr auto;gap:12px;align-items:center}
.eff .el{font-size:.75rem;font-weight:600;color:#9ab8d4;text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.eff .et{font-size:1rem;font-weight:600;color:#fff;margin-bottom:3px}
.eff .ed{font-size:.78rem;color:#7fa3c0;line-height:1.5}
.ern{text-align:right}
.ern .ev{font-size:2.6rem;font-weight:700;color:var(--teal-mid);line-height:1}
.ern .eu{font-size:.78rem;color:#7fa3c0;margin-top:2px}
.ern .elnl{font-size:.7rem;color:#9ab8d4;text-transform:uppercase;letter-spacing:.05em;margin-bottom:4px}

/* bridge */
.bc{background:var(--white);border:1px solid var(--border);border-radius:var(--radius);padding:18px 20px}
.br{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.bl{font-size:.78rem;color:var(--text-muted);width:120px;flex-shrink:0;font-weight:500}
.bbw{flex:1;height:26px;background:var(--surface);border-radius:4px;overflow:hidden}
.bb{height:100%;border-radius:4px;transition:width .5s ease;display:flex;align-items:center;padding-left:10px}
.bb span{font-size:.72rem;font-weight:600;color:#fff;white-space:nowrap}
.br.std .bb{background:var(--navy)}
.br.extra .bb{background:var(--teal)}
.br.biwk .bb{background:var(--navy-mid)}
.bst{font-size:.75rem;color:var(--teal);font-weight:600;white-space:nowrap}

/* metrics */
.mg{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px}
.mc{border-radius:var(--radius);padding:13px 15px;border:1px solid transparent}
.mc.base{background:var(--surface);border-color:var(--border)}
.mc.pos{background:var(--teal-light);border-color:rgba(0,137,106,.18)}
.mc.gold{background:var(--gold-light);border-color:rgba(196,125,14,.2)}
.mc .ml{font-size:.68rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px}
.mc.pos .ml{color:#007558}
.mc.gold .ml{color:var(--gold)}
.mc .mv{font-size:1.3rem;font-weight:700;color:var(--navy)}
.mc.pos .mv{color:#007558}
.mc.gold .mv{color:var(--gold)}
.mc .ms{font-size:.7rem;color:var(--text-muted);margin-top:2px}

/* cmp table */
.ctw{background:var(--white);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden;overflow-x:auto}
table.cmp{width:100%;border-collapse:collapse;font-size:.82rem}
table.cmp thead th{background:var(--navy);color:#9ab8d4;font-weight:500;padding:9px 14px;text-align:right;white-space:nowrap}
table.cmp thead th:first-child{text-align:left}
table.cmp thead th.tc{color:var(--teal-mid)}
table.cmp thead th.gh{color:#f0b843}
table.cmp tbody td{padding:8px 14px;text-align:right;border-bottom:1px solid var(--border)}
table.cmp tbody td:first-child{text-align:left;color:var(--text-muted);font-size:.78rem}
table.cmp tbody tr:last-child td{border-bottom:none}
table.cmp tbody tr:nth-child(even) td{background:#fafbfd}
table.cmp tbody td.tv{color:var(--teal);font-weight:600}
table.cmp tbody td.gv{color:var(--gold);font-weight:600}
table.cmp tfoot td{padding:8px 14px;font-weight:600;color:var(--navy);border-top:2px solid var(--border);text-align:right;background:#f0f4f8}
table.cmp tfoot td:first-child{text-align:left;font-size:.78rem}

/* amort */
.at-btn{background:var(--white);border:1px solid var(--border);color:var(--text-muted);padding:8px 16px;border-radius:6px;font-family:inherit;font-size:.78rem;cursor:pointer;display:flex;align-items:center;gap:6px}
.at-btn:hover{background:var(--surface)}
.at-btn svg{width:13px;height:13px;transition:transform .2s}
.at-btn.open svg{transform:rotate(180deg)}
.aw{display:none;background:var(--white);border:1px solid var(--border);border-radius:var(--radius);overflow:auto;margin-top:10px;max-height:480px}
.aw.open{display:block}
table.amort{width:100%;border-collapse:collapse;font-size:.78rem}
table.amort thead th{background:var(--navy);color:#9ab8d4;font-weight:500;padding:7px 12px;text-align:right;white-space:nowrap;position:sticky;top:0}
table.amort thead th:first-child{text-align:left}
table.amort tbody td{padding:5px 12px;text-align:right;border-bottom:1px solid #edf1f6}
table.amort tbody td:first-child{text-align:left;color:var(--text-muted)}
table.amort tbody tr.payoff-row td{background:var(--teal-light);color:#007558;font-weight:600}
table.amort tfoot td{padding:7px 12px;text-align:right;font-weight:600;color:var(--navy);border-top:2px solid var(--border);background:#f0f4f8}
table.amort tfoot td:first-child{text-align:left}
.badge{display:inline-flex;align-items:center;gap:5px;background:var(--teal-light);border:1px solid rgba(0,137,106,.2);color:var(--teal);font-size:.73rem;font-weight:600;padding:3px 10px;border-radius:20px}

.empty{background:var(--white);border:1px dashed var(--border);border-radius:var(--radius);padding:48px 24px;text-align:center;color:var(--text-muted);font-size:.85rem}
.empty svg{width:36px;height:36px;margin:0 auto 12px;display:block;color:var(--border)}
.disc{font-size:.7rem;color:var(--text-muted);border-top:1px solid var(--border);padding-top:10px;line-height:1.5}

@media print{
  .topbar,.panel,.at-btn,.btn-p,.btn-g{display:none!important}
  body{background:#fff!important}
  .main{max-width:100%;padding:0;margin:0}
  .layout{display:block}
  .aw{display:block!important;max-height:none!important}
}
        `}</style>
      </Head>

      {/* TOP BAR */}
      <div className="topbar">
        <div className="brand">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          Additional Payment Analysis
        </div>
        <div className="tbr">
          <button className="btn-g" onClick={reset}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.5"/></svg>
            Reset
          </button>
          <button className="btn-p" onClick={() => typeof window !== 'undefined' && window.print()}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            Print / Save PDF
          </button>
        </div>
      </div>

      <div className="main">
        <div className="layout">

          {/* INPUT PANEL */}
          <div className="panel">
            <div className="phead">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="12" y2="14"/></svg>
              Loan details
            </div>

            <div className="psec">
              <div className="psec-title">Loan parameters</div>
              <div className="igrid">
                <div><label>Original loan amount</label>
                  <div className="fld pfx"><span className="sym">$</span>
                    <input type="number" value={form.loanAmt} min="1000" step="1000" onChange={e => set('loanAmt', e.target.value)} /></div></div>
                <div><label>Annual interest rate</label>
                  <div className="fld sfx"><input type="number" value={form.rate} min="0.1" max="30" step="0.125" onChange={e => set('rate', e.target.value)} /><span className="sym">%</span></div></div>
                <div><label>Original term</label>
                  <select value={form.termYrs} onChange={e => set('termYrs', e.target.value)}>
                    <option value="10">10 years</option>
                    <option value="15">15 years</option>
                    <option value="20">20 years</option>
                    <option value="25">25 years</option>
                    <option value="30">30 years</option>
                  </select></div>
                <div><label>Payments already made</label>
                  <input type="number" value={form.paysMade} min="0" step="1" onChange={e => set('paysMade', e.target.value)} /></div>
              </div>
            </div>

            <div className="psec">
              <div className="psec-title">Extra payment scenario</div>
              <div className="igrid">
                <div><label>Extra monthly amount</label>
                  <div className="fld pfx"><span className="sym">$</span>
                    <input type="number" value={form.extraAmt} min="0" step="25" onChange={e => set('extraAmt', e.target.value)} /></div></div>
                <div><label>Monthly escrow (taxes / ins / HOA)</label>
                  <div className="fld pfx"><span className="sym">$</span>
                    <input type="number" value={form.escrow} min="0" step="10" onChange={e => set('escrow', e.target.value)} /></div></div>
                <div style={{marginTop:4}}>
                  <label className="chk">
                    <input type="checkbox" checked={form.doBiweekly} onChange={e => set('doBiweekly', e.target.checked)} />
                    <span>Include bi-weekly scenario</span>
                  </label>
                </div>
              </div>
            </div>

            <button className="run-btn" onClick={calculate}>Run analysis →</button>
          </div>

          {/* RESULTS */}
          <div className="results">
            {!r && (
              <div className="empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                <p>Enter loan details and click <strong>Run analysis</strong> to generate the report.</p>
              </div>
            )}

            {r && <>
              {/* Effective rate banner */}
              <div className="eff">
                <div>
                  <div className="el">Key insight</div>
                  <div className="et">Equivalent interest rate earned by overpaying</div>
                  <div className="ed">Every extra dollar paid saves interest at this annualized rate — a guaranteed, risk-free return with no market exposure.</div>
                </div>
                <div className="ern">
                  <div className="elnl">Eff. rate</div>
                  <div className="ev">{r.effRate != null ? r.effRate.toFixed(2) : '—'}</div>
                  <div className="eu">% per year</div>
                </div>
              </div>

              {/* Bridge */}
              <div>
                <div className="sh"><h2>Payoff timeline comparison</h2><div className="shl" /></div>
                <div className="bc">
                  <div className="br std">
                    <div className="bl">Standard</div>
                    <div className="bbw"><div className="bb" style={{width:'100%'}}><span>{fmtYr(r.base.months)}</span></div></div>
                    <div className="bst" />
                  </div>
                  <div className="br extra" style={{marginTop:8}}>
                    <div className="bl">+ Extra payment</div>
                    <div className="bbw"><div className="bb" style={{width:Math.max(20,r.xtra.months/maxMo*100).toFixed(1)+'%'}}><span>{fmtYr(r.xtra.months)}</span></div></div>
                    <div className="bst">saves {fmtYr(r.base.months - r.xtra.months)}</div>
                  </div>
                  {biCol && (
                    <div className="br biwk" style={{marginTop:8}}>
                      <div className="bl">Bi-weekly</div>
                      <div className="bbw"><div className="bb" style={{width:Math.max(20,r.biwk.months/maxMo*100).toFixed(1)+'%'}}><span>{fmtYr(r.biwk.months)}</span></div></div>
                      <div className="bst">saves {fmtYr(r.base.months - r.biwk.months)}</div>
                    </div>
                  )}
                </div>
              </div>

              {/* Metrics */}
              <div>
                <div className="sh"><h2>Extra payment impact</h2><div className="shl" /></div>
                <div className="mg">
                  <div className="mc pos"><div className="ml">Interest saved</div><div className="mv">{fmtD(saved)}</div><div className="ms">vs. standard schedule</div></div>
                  <div className="mc pos"><div className="ml">Months eliminated</div><div className="mv">{fmt(moElim)}</div><div className="ms">{fmtYr(moElim)} off your loan</div></div>
                  <div className="mc gold"><div className="ml">Equiv. interest rate</div><div className="mv">{r.effRate != null ? r.effRate.toFixed(2)+'%' : '—'}</div><div className="ms">Guaranteed annual return</div></div>
                  <div className="mc base"><div className="ml">New payoff</div><div className="mv">{fmtYr(r.xtra.months)}</div><div className="ms">vs. {fmtYr(r.base.months)} standard</div></div>
                  <div className="mc base"><div className="ml">Equity after 5 yrs</div><div className="mv">{fmtD(eq5)}</div><div className="ms">vs. {fmtD(eq5b)} standard</div></div>
                  <div className="mc base"><div className="ml">Equity after 10 yrs</div><div className="mv">{fmtD(eq10)}</div><div className="ms">vs. {fmtD(eq10b)} standard</div></div>
                </div>
              </div>

              {/* Comparison table */}
              <div>
                <div className="sh"><h2>Side-by-side comparison</h2><div className="shl" /></div>
                <div className="ctw">
                  <table className="cmp">
                    <thead><tr>
                      <th></th>
                      <th>Standard</th>
                      <th className="tc">+ Extra ${fmt(r.extra)}/mo</th>
                      {biCol && <><th>Bi-weekly</th><th className="gh">Bi-wkly + Extra</th></>}
                    </tr></thead>
                    <tbody>
                      {[
                        ['Regular P&I payment', fmtD(r.base.pmt), fmtD(r.base.pmt+r.extra), biCol?fmtD(r.base.pmt/2)+' /2wk':null, null],
                        ['Total with escrow', fmtD(r.base.pmt+r.escrow), fmtD(r.base.pmt+r.extra+r.escrow), null, null],
                        ['Extra monthly amount', '—', fmtD(r.extra), biCol?fmtD(r.base.pmt/2)+' /2wk':null, null],
                        ['Months to pay off', fmt(r.base.months), fmt(r.xtra.months), biCol?fmt(r.biwk.months):null, null],
                        ['Years to pay off', (r.base.months/12).toFixed(1)+' yr', (r.xtra.months/12).toFixed(1)+' yr', biCol?(r.biwk.months/12).toFixed(1)+' yr':null, null],
                        ['Months saved', '—', fmt(r.base.months-r.xtra.months), biCol?fmt(r.base.months-r.biwk.months):null, null],
                        ['Total interest paid', fmtD(r.base.totInt), fmtD(r.xtra.totInt), biCol?fmtD(r.biwk.totInt):null, null],
                        ['Interest saved', '—', fmtD(r.base.totInt-r.xtra.totInt), biCol?fmtD(r.base.totInt-r.biwk.totInt):null, null],
                        ['Equity after 5 years', fmtD(eq5b), fmtD(eq5), biCol?fmtD(r.curBal-balAt(r.biwk.sched,60)):null, null],
                        ['Equity after 10 years', fmtD(eq10b), fmtD(eq10), biCol?fmtD(r.curBal-balAt(r.biwk.sched,120)):null, null],
                        ['Equivalent rate earned', '—', r.effRate!=null?fmtPct(r.effRate):'—', biCol?(r.effRateBi!=null?fmtPct(r.effRateBi):'—'):null, null],
                      ].map(([label, std, extra, bi, biX]) => (
                        <tr key={label}>
                          <td>{label}</td>
                          <td>{std??'—'}</td>
                          <td className="tv">{extra??'—'}</td>
                          {biCol && <><td>{bi??'—'}</td><td className="gv">{biX??'—'}</td></>}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Amortization */}
              <div>
                <div className="sh"><h2>Amortization schedule</h2><div className="shl" /></div>
                <button className={`at-btn${amortOpen?' open':''}`} onClick={() => setAmortOpen(o => !o)}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"/></svg>
                  {amortOpen ? 'Hide amortization schedule' : 'Show full amortization schedule'}
                </button>
                <div
                  className={`aw${amortOpen?' open':''}`}
                  dangerouslySetInnerHTML={{__html: buildAmortHTML(r.base, r.xtra, biCol ? r.biwk : null)}}
                />
              </div>

              <div className="disc">
                This analysis is for illustrative purposes only. Actual loan terms, payments, and savings may vary.
                Interest rate shown as equivalent annualized pre-tax return. Consult a licensed mortgage professional
                before making financial decisions. &copy; {new Date().getFullYear()} Perennia AI.
              </div>
            </>}
          </div>
        </div>
      </div>
    </>
  );
}

export async function getStaticProps() {
  return { props: {} };
}

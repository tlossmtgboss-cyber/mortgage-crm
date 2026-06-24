import React, { useState, useCallback, useRef } from 'react';
import './AdditionalPaymentAnalysis.css';

/* ── helpers ── */
const fmt = (n, d = 0) => n.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
const fmtD = n => '$' + fmt(Math.round(n));
const fmtPct = n => n.toFixed(2) + '%';
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

/* Effective interest rate: the annual rate at which a standard loan of `pv`
   over `termMo` months would produce the same total interest as `targetTotInt`.
   Always lower than the note rate when extra payments are made. */
function equivalentRate(pv, termMo, targetTotInt) {
  const targetPmt = (targetTotInt + pv) / termMo;
  const calcPmt = r => {
    const mr = r / 12;
    if (mr < 1e-9) return pv / termMo;
    return pv * mr * Math.pow(1 + mr, termMo) / (Math.pow(1 + mr, termMo) - 1);
  };
  let lo = 0.0001, hi = 0.9999;
  if (calcPmt(lo) >= targetPmt) return lo * 100;
  if (calcPmt(hi) <= targetPmt) return hi * 100;
  for (let i = 0; i < 100; i++) {
    const mid = (lo + hi) / 2;
    if (calcPmt(mid) > targetPmt) hi = mid;
    else lo = mid;
  }
  return ((lo + hi) / 2) * 100;
}

function currentBalance(loanAmt, annRate, totalMo, paysMade) {
  if (paysMade <= 0) return loanAmt;
  const r = annRate / 100 / 12;
  if (r === 0) return loanAmt * (1 - paysMade / totalMo);
  const pmt = loanAmt * (r * Math.pow(1 + r, totalMo)) / (Math.pow(1 + r, totalMo) - 1);
  let bal = loanAmt;
  for (let i = 0; i < paysMade && bal > 0; i++) { bal -= (pmt - bal * r); }
  return Math.max(bal, 0);
}

function balAt(sched, mo) {
  if (mo <= 0) return null;
  if (mo >= sched.length) return 0;
  return sched[mo - 1]?.balance ?? 0;
}

function buildAmortHTML(base, xtra, biwk) {
  const hasBi = !!biwk;
  let html = `<table class="apa-amort"><thead><tr>
    <th>Mo.</th>
    <th>Std payment</th><th>Std balance</th>
    <th style="color:#4db89c">+Extra payment</th><th style="color:#4db89c">+Extra balance</th><th style="color:#4db89c">Int saved (cum)</th>`;
  if (hasBi) html += `<th style="color:#9ab8d4">Bi-wkly bal</th>`;
  html += `</tr></thead><tbody>`;

  const rows = Math.max(base.sched.length, xtra.sched.length);
  let xtraPayoffMarked = false;
  for (let i = 0; i < rows; i++) {
    const b = base.sched[i], x = xtra.sched[i], bw = hasBi ? biwk.sched[i] : null;
    const isPayoff = !xtraPayoffMarked && !x && b;
    if (isPayoff) xtraPayoffMarked = true;
    const cls = isPayoff ? 'class="payoff-row"' : '';
    html += `<tr ${cls}>
      <td>${b ? b.mo : (x ? x.mo : '')}</td>
      <td>${b ? fmtD(b.payment) : '—'}</td><td>${b ? fmtD(b.balance) : 'paid off'}</td>
      <td>${x ? fmtD(x.payment) : '—'}</td><td>${x ? fmtD(x.balance) : (isPayoff ? '<span class="apa-payoff-badge">✓ Paid off</span>' : 'paid off')}</td>
      <td>${x ? fmtD(Math.max(0, b ? (b.cumInt - x.cumInt) : 0)) : '—'}</td>`;
    if (hasBi) html += `<td>${bw ? fmtD(bw.balance) : 'paid off'}</td>`;
    html += `</tr>`;
  }
  html += `</tbody><tfoot><tr>
    <td>Total</td><td></td><td></td>
    <td>${fmtD(xtra.sched.reduce((a, r) => a + r.payment, 0))}</td>
    <td></td>
    <td>${fmtD(base.totInt - xtra.totInt)}</td>`;
  if (hasBi) html += `<td></td>`;
  html += `</tr></tfoot></table>`;
  return html;
}

/* ── defaults ── */
const DEFAULTS = { loanAmt: '350000', rate: '6.75', termYrs: '30', paysMade: '0', extraAmt: '300', escrow: '450', doBiweekly: false };

export default function AdditionalPaymentAnalysis() {
  const [form, setForm] = useState(DEFAULTS);
  const [result, setResult] = useState(null);
  const [amortOpen, setAmortOpen] = useState(false);
  const amortRef = useRef(null);

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
    const biwk = doBi ? amortize(curBal, rate, remMo, base.pmt / 12) : null;
    const biwkXtra = doBi ? amortize(curBal, rate, remMo, base.pmt / 12 + extra) : null;

    const effRate = equivalentRate(curBal, remMo, xtra.totInt);
    const effRateBi = biwk ? equivalentRate(curBal, remMo, biwk.totInt) : null;
    const effRateBiXtra = biwkXtra ? equivalentRate(curBal, remMo, biwkXtra.totInt) : null;

    setResult({ loanAmt, rate, termYrs, paysMade, extra, escrow, doBi, curBal, remMo, base, xtra, biwk, biwkXtra, effRate, effRateBi, effRateBiXtra });
    setAmortOpen(false);
  }, [form]);

  const reset = () => { setForm(DEFAULTS); setResult(null); setAmortOpen(false); };

  const r = result;

  /* derived display values */
  let saved = 0, moElim = 0, eq5 = 0, eq10 = 0, eq5b = 0, eq10b = 0;
  if (r) {
    saved = r.base.totInt - r.xtra.totInt;
    moElim = r.base.months - r.xtra.months;
    eq5 = r.curBal - balAt(r.xtra.sched, 60);
    eq10 = r.curBal - balAt(r.xtra.sched, 120);
    eq5b = r.curBal - balAt(r.base.sched, 60);
    eq10b = r.curBal - balAt(r.base.sched, 120);
  }

  const maxMo = r ? r.base.months : 1;
  const biCol = r && r.doBi && r.biwk;

  return (
    <div className="apa-root">
      {/* TOP BAR */}
      <div className="apa-topbar">
        <div className="apa-topbar-brand">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
            <polyline points="9 22 9 12 15 12 15 22"/>
          </svg>
          Additional Payment Analysis
        </div>
        <div className="apa-topbar-actions">
          <button className="apa-btn-ghost" onClick={reset}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-3.5"/></svg>
            Reset
          </button>
          <button className="apa-btn-print" onClick={() => window.print()}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            Print / Save PDF
          </button>
        </div>
      </div>

      <div className="apa-main">
        <div className="apa-calc-layout">

          {/* INPUT PANEL */}
          <div className="apa-input-panel">
            <div className="apa-panel-head">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><rect x="4" y="2" width="16" height="20" rx="2"/><line x1="8" y1="6" x2="16" y2="6"/><line x1="8" y1="10" x2="16" y2="10"/><line x1="8" y1="14" x2="12" y2="14"/></svg>
              Loan details
            </div>

            <div className="apa-panel-section">
              <div className="apa-panel-section-title">Loan parameters</div>
              <div className="apa-input-grid">
                <div className="apa-fld">
                  <label>Original loan amount</label>
                  <div className="apa-pfx">
                    <span className="apa-sym">$</span>
                    <input type="number" value={form.loanAmt} min="1000" step="1000" onChange={e => set('loanAmt', e.target.value)} />
                  </div>
                </div>
                <div className="apa-fld">
                  <label>Annual interest rate</label>
                  <div className="apa-sfx">
                    <input type="number" value={form.rate} min="0.1" max="30" step="0.125" onChange={e => set('rate', e.target.value)} />
                    <span className="apa-sym">%</span>
                  </div>
                </div>
                <div className="apa-fld">
                  <label>Original term</label>
                  <select value={form.termYrs} onChange={e => set('termYrs', e.target.value)}>
                    <option value="10">10 years</option>
                    <option value="15">15 years</option>
                    <option value="20">20 years</option>
                    <option value="25">25 years</option>
                    <option value="30">30 years</option>
                  </select>
                </div>
                <div className="apa-fld">
                  <label>Payments already made</label>
                  <input type="number" value={form.paysMade} min="0" step="1" onChange={e => set('paysMade', e.target.value)} />
                </div>
              </div>
            </div>

            <div className="apa-panel-section">
              <div className="apa-panel-section-title">Extra payment scenario</div>
              <div className="apa-input-grid">
                <div className="apa-fld">
                  <label>Extra monthly amount</label>
                  <div className="apa-pfx">
                    <span className="apa-sym">$</span>
                    <input type="number" value={form.extraAmt} min="0" step="25" onChange={e => set('extraAmt', e.target.value)} />
                  </div>
                </div>
                <div className="apa-fld">
                  <label>Monthly escrow (taxes / ins / HOA)</label>
                  <div className="apa-pfx">
                    <span className="apa-sym">$</span>
                    <input type="number" value={form.escrow} min="0" step="10" onChange={e => set('escrow', e.target.value)} />
                  </div>
                </div>
                <div className="apa-fld" style={{ marginTop: 4 }}>
                  <label className="apa-chk-row">
                    <input type="checkbox" checked={form.doBiweekly} onChange={e => set('doBiweekly', e.target.checked)} />
                    <span>Include bi-weekly scenario</span>
                  </label>
                </div>
              </div>
            </div>

            <button className="apa-calc-action-btn" onClick={calculate}>Run analysis →</button>
          </div>

          {/* RESULTS */}
          <div className="apa-results-pane">
            {!r && (
              <div className="apa-empty-state">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/></svg>
                <p>Enter loan details and click <strong>Run analysis</strong> to generate the borrower report.</p>
              </div>
            )}

            {r && (
              <>
                {/* EFFECTIVE RATE BANNER */}
                <div className="apa-eff-banner">
                  <div>
                    <div className="eb-label">Key insight</div>
                    <div className="eb-title">Effective interest rate with extra payments</div>
                    <div className="eb-desc">Making extra payments lowers your effective interest rate. This is the rate a standard loan would need to match your total interest cost.</div>
                  </div>
                  <div className="apa-eff-rate-num">
                    <div className="ern-label">Eff. rate</div>
                    <div className="ern-value">{r.effRate != null ? r.effRate.toFixed(2) : '—'}</div>
                    <div className="ern-unit">% per year</div>
                  </div>
                </div>

                {/* BRIDGE */}
                <div>
                  <div className="apa-sec-head"><h2>Payoff timeline comparison</h2><div className="apa-sec-line" /></div>
                  <div className="apa-bridge-card">
                    <div className="apa-bridge-row std">
                      <div className="apa-bridge-label">Standard</div>
                      <div className="apa-bridge-bar-wrap">
                        <div className="apa-bridge-bar" style={{ width: '100%' }}>
                          <span>{fmtYr(r.base.months)}</span>
                        </div>
                      </div>
                      <div className="apa-bridge-savings-tag"></div>
                    </div>
                    <div className="apa-bridge-row extra" style={{ marginTop: 8 }}>
                      <div className="apa-bridge-label">+ Extra payment</div>
                      <div className="apa-bridge-bar-wrap">
                        <div className="apa-bridge-bar" style={{ width: Math.max(20, r.xtra.months / maxMo * 100).toFixed(1) + '%' }}>
                          <span>{fmtYr(r.xtra.months)}</span>
                        </div>
                      </div>
                      <div className="apa-bridge-savings-tag">saves {fmtYr(r.base.months - r.xtra.months)}</div>
                    </div>
                    {biCol && (
                      <div className="apa-bridge-row biwk" style={{ marginTop: 8 }}>
                        <div className="apa-bridge-label">Bi-weekly</div>
                        <div className="apa-bridge-bar-wrap">
                          <div className="apa-bridge-bar" style={{ width: Math.max(20, r.biwk.months / maxMo * 100).toFixed(1) + '%' }}>
                            <span>{fmtYr(r.biwk.months)}</span>
                          </div>
                        </div>
                        <div className="apa-bridge-savings-tag">saves {fmtYr(r.base.months - r.biwk.months)}</div>
                      </div>
                    )}
                  </div>
                </div>

                {/* METRICS */}
                <div>
                  <div className="apa-sec-head"><h2>Extra payment impact</h2><div className="apa-sec-line" /></div>
                  <div className="apa-metrics-grid">
                    <div className="apa-mc pos"><div className="mc-lbl">Interest saved</div><div className="mc-val">{fmtD(saved)}</div><div className="mc-sub">vs. standard schedule</div></div>
                    <div className="apa-mc pos"><div className="mc-lbl">Months eliminated</div><div className="mc-val">{fmt(moElim)}</div><div className="mc-sub">{fmtYr(moElim)} off your loan</div></div>
                    <div className="apa-mc gold"><div className="mc-lbl">Effective interest rate</div><div className="mc-val">{r.effRate != null ? r.effRate.toFixed(2) + '%' : '—'}</div><div className="mc-sub">vs. {r.rate}% note rate</div></div>
                    <div className="apa-mc base"><div className="mc-lbl">New payoff</div><div className="mc-val">{fmtYr(r.xtra.months)}</div><div className="mc-sub">vs. {fmtYr(r.base.months)} standard</div></div>
                    <div className="apa-mc base"><div className="mc-lbl">Equity after 5 yrs</div><div className="mc-val">{fmtD(eq5)}</div><div className="mc-sub">vs. {fmtD(eq5b)} standard</div></div>
                    <div className="apa-mc base"><div className="mc-lbl">Equity after 10 yrs</div><div className="mc-val">{fmtD(eq10)}</div><div className="mc-sub">vs. {fmtD(eq10b)} standard</div></div>
                  </div>
                </div>

                {/* COMPARISON TABLE */}
                <div>
                  <div className="apa-sec-head"><h2>Side-by-side comparison</h2><div className="apa-sec-line" /></div>
                  <div className="apa-cmp-table-wrap">
                    <table className="apa-cmp">
                      <thead>
                        <tr>
                          <th></th>
                          <th>Standard</th>
                          <th className="teal">+ Extra ${fmt(r.extra)}/mo</th>
                          {biCol && <><th>Bi-weekly</th><th className="gold-h">Bi-wkly + Extra</th></>}
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          ['Regular P&I payment', fmtD(r.base.pmt), fmtD(r.base.pmt + r.extra), biCol ? fmtD(r.base.pmt / 2) + ' /2wk' : null, biCol ? fmtD(r.base.pmt / 2) + ' /2wk' : null],
                          ['Total with escrow', fmtD(r.base.pmt + r.escrow), fmtD(r.base.pmt + r.extra + r.escrow), null, biCol ? fmtD(r.base.pmt / 2 + r.extra + r.escrow) + ' /2wk' : null],
                          ['Extra monthly amount', '—', fmtD(r.extra), fmtD(r.base.pmt / 12) + '/mo equiv', biCol ? fmtD(r.base.pmt / 12 + r.extra) : null],
                          ['Months to pay off', fmt(r.base.months), fmt(r.xtra.months), biCol ? fmt(r.biwk.months) : null, biCol ? fmt(r.biwkXtra.months) : null],
                          ['Years to pay off', (r.base.months / 12).toFixed(1) + ' yr', (r.xtra.months / 12).toFixed(1) + ' yr', biCol ? (r.biwk.months / 12).toFixed(1) + ' yr' : null, biCol ? (r.biwkXtra.months / 12).toFixed(1) + ' yr' : null],
                          ['Months saved', '—', fmt(r.base.months - r.xtra.months), biCol ? fmt(r.base.months - r.biwk.months) : null, biCol ? fmt(r.base.months - r.biwkXtra.months) : null],
                          ['Total interest paid', fmtD(r.base.totInt), fmtD(r.xtra.totInt), biCol ? fmtD(r.biwk.totInt) : null, biCol ? fmtD(r.biwkXtra.totInt) : null],
                          ['Interest saved', '—', fmtD(r.base.totInt - r.xtra.totInt), biCol ? fmtD(r.base.totInt - r.biwk.totInt) : null, biCol ? fmtD(r.base.totInt - r.biwkXtra.totInt) : null],
                          ['Equity after 5 years', fmtD(eq5b), fmtD(eq5), biCol ? fmtD(r.curBal - balAt(r.biwk.sched, 60)) : null, biCol ? fmtD(r.curBal - balAt(r.biwkXtra.sched, 60)) : null],
                          ['Equity after 10 years', fmtD(eq10b), fmtD(eq10), biCol ? fmtD(r.curBal - balAt(r.biwk.sched, 120)) : null, biCol ? fmtD(r.curBal - balAt(r.biwkXtra.sched, 120)) : null],
                          ['Effective rate of interest', fmtPct(r.rate), r.effRate != null ? fmtPct(r.effRate) : '—', biCol ? (r.effRateBi != null ? fmtPct(r.effRateBi) : '—') : null, biCol ? (r.effRateBiXtra != null ? fmtPct(r.effRateBiXtra) : '—') : null],
                        ].map(([label, std, extra, bi, biExtra]) => (
                          <tr key={label}>
                            <td>{label}</td>
                            <td>{std ?? '—'}</td>
                            <td className="teal-val">{extra ?? '—'}</td>
                            {biCol && <><td>{bi ?? '—'}</td><td className="gold-val">{biExtra ?? '—'}</td></>}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* AMORTIZATION */}
                <div>
                  <div className="apa-sec-head"><h2>Amortization schedule</h2><div className="apa-sec-line" /></div>
                  <button
                    className={`apa-amort-toggle${amortOpen ? ' open' : ''}`}
                    onClick={() => setAmortOpen(o => !o)}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><polyline points="6 9 12 15 18 9"/></svg>
                    {amortOpen ? 'Hide amortization schedule' : 'Show full amortization schedule'}
                  </button>
                  <div
                    ref={amortRef}
                    className={`apa-amort-wrap${amortOpen ? ' open' : ''}`}
                    dangerouslySetInnerHTML={{ __html: buildAmortHTML(r.base, r.xtra, biCol ? r.biwk : null) }}
                  />
                </div>

                <div className="apa-disclaimer">
                  This analysis is for illustrative purposes only. Actual loan terms, payments, and savings may vary. Interest rate shown as equivalent annualized pre-tax return. Consult a licensed mortgage professional before making financial decisions.
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

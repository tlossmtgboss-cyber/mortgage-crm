/**
 * MUMScenarios — borrower-facing "what are my options?" calculators.
 *
 * Portal consolidation Phase 1 harvest: the Scenarios tab from the deleted
 * PerenniaClientPortalUltimate, rebuilt against data the PURL MUM portal
 * already computes (property value, balance, rate). Self-contained — uses
 * inline styles so it carries no dependency on the deleted component's CSS.
 */
import React, { useState } from 'react';
import {
  calculateRefinance,
  calculateCashOut,
  calculateHeloc,
  calculateSell,
} from './scenarioCalcs';

const fmt = (amount, decimals = 0) =>
  (amount || 0).toLocaleString('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

const card = {
  background: '#fff',
  borderRadius: 12,
  padding: 20,
  boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  marginBottom: 16,
};
const cardTitle = { margin: '0 0 12px', fontSize: 16, fontWeight: 600, color: '#1a202c' };
const row = { display: 'flex', justifyContent: 'space-between', padding: '6px 0', fontSize: 14 };
const label = { color: '#64748b' };
const value = { fontWeight: 600, color: '#1a202c' };
const total = { ...row, borderTop: '1px solid #e2e8f0', marginTop: 8, paddingTop: 10, fontSize: 15 };
const inputStyle = {
  width: '100%',
  padding: '8px 10px',
  border: '1px solid #cbd5e1',
  borderRadius: 8,
  fontSize: 14,
  marginTop: 4,
};

export default function MUMScenarios({ propertyValue = 0, currentBalance = 0, currentRate = 6.5 }) {
  const currentEquity = Math.max(0, propertyValue - currentBalance);
  const [newRate, setNewRate] = useState(Math.max(0, Number((currentRate - 1).toFixed(3))) || 5.5);
  const [cashOutAmount, setCashOutAmount] = useState(50000);
  const targetLtv = 80;

  const refi = calculateRefinance({ currentBalance, currentRate, newRate });
  const cashOut = calculateCashOut({ currentValue: propertyValue, currentBalance, targetLtv, cashOutAmount });
  const heloc = calculateHeloc({ currentEquity });
  const sell = calculateSell({ currentValue: propertyValue, currentBalance });

  const savingsPositive = refi.monthlySavings >= 0;

  return (
    <div className="mum-scenarios">
      <p style={{ color: '#64748b', marginBottom: 16 }}>
        Estimates based on your property value and current loan. Contact your loan officer to explore any option.
      </p>

      {/* Refinance */}
      <div style={card}>
        <h3 style={cardTitle}>💵 Refinance</h3>
        <label style={label} htmlFor="scenario-new-rate">New interest rate (%)</label>
        <input
          id="scenario-new-rate"
          type="number"
          step="0.125"
          value={newRate}
          onChange={(e) => setNewRate(parseFloat(e.target.value) || 0)}
          style={inputStyle}
        />
        <div style={{ marginTop: 12 }}>
          <div style={row}><span style={label}>Current payment</span><span style={value}>{fmt(refi.currentPayment)}/mo</span></div>
          <div style={row}><span style={label}>New payment</span><span style={value}>{fmt(refi.newPayment)}/mo</span></div>
          <div style={total}>
            <span style={label}>{savingsPositive ? 'Monthly savings' : 'Monthly increase'}</span>
            <span style={{ ...value, color: savingsPositive ? '#16a34a' : '#dc2626' }}>
              {fmt(Math.abs(refi.monthlySavings))}/mo
            </span>
          </div>
        </div>
      </div>

      {/* Cash-out */}
      <div style={card}>
        <h3 style={cardTitle}>🏦 Cash-Out Refinance</h3>
        <div style={row}><span style={label}>Available equity</span><span style={value}>{fmt(currentEquity)}</span></div>
        <label style={label} htmlFor="scenario-cashout">Cash out amount</label>
        <input
          id="scenario-cashout"
          type="number"
          step="5000"
          value={cashOutAmount}
          onChange={(e) => setCashOutAmount(parseFloat(e.target.value) || 0)}
          style={inputStyle}
        />
        <div style={{ marginTop: 12 }}>
          <div style={row}><span style={label}>Max available (80% LTV)</span><span style={value}>{fmt(cashOut.availableCashOut)}</span></div>
          <div style={row}><span style={label}>New loan amount</span><span style={value}>{fmt(cashOut.newLoanAmount)}</span></div>
          <div style={total}><span style={label}>New LTV</span><span style={value}>{cashOut.newLtv.toFixed(1)}%</span></div>
        </div>
      </div>

      {/* HELOC */}
      <div style={card}>
        <h3 style={cardTitle}>🔑 HELOC</h3>
        <div style={total}><span style={label}>Estimated credit line</span><span style={value}>{fmt(heloc.estimatedCreditLine)}</span></div>
        <p style={{ ...label, marginTop: 8, fontSize: 13 }}>
          A home equity line of credit lets you borrow against your equity as needed.
        </p>
      </div>

      {/* Sell */}
      <div style={card}>
        <h3 style={cardTitle}>🏡 Sell Analysis</h3>
        <div style={row}><span style={label}>Estimated sale price</span><span style={value}>{fmt(sell.salePrice)}</span></div>
        <div style={row}><span style={label}>Loan payoff</span><span style={value}>- {fmt(sell.loanPayoff)}</span></div>
        <div style={row}><span style={label}>Estimated selling costs (~8%)</span><span style={value}>- {fmt(sell.sellingCosts)}</span></div>
        <div style={total}><span style={label}>Net proceeds</span><span style={{ ...value, color: '#16a34a' }}>{fmt(sell.netProceeds)}</span></div>
      </div>
    </div>
  );
}

import React, { useState, useEffect } from 'react';
import './GoalTracker.css';

function GoalTracker() {
  // User Input Fields (Yellow highlighted in Excel)
  const [inputs, setInputs] = useState({
    // Simplified Business Plan Inputs
    avgLoanAmount: 200000,
    annualClosingsDollarGoal: 40000000,
    pullThroughRate: 0.90,
    conversionToApp: 0.25,
    totalReferralPartners: 10,

    // High Trust Business Plan Inputs
    annualIncomeGoal: 300000,
    avgCommissionBasisPoints: 0.01,
    preQualToAppRate: 0.17,
  });

  const [calculated, setCalculated] = useState({});
  const [history, setHistory] = useState([]);
  const [showHistory, setShowHistory] = useState(false);
  const [lastSaved, setLastSaved] = useState(null);

  // Load saved data on mount
  useEffect(() => {
    loadSavedData();
  }, []);

  // Auto-save when inputs change
  useEffect(() => {
    calculateMetrics();
    saveData();
  }, [inputs]);

  const loadSavedData = () => {
    try {
      // Load current inputs
      const savedInputs = localStorage.getItem('goalTrackerInputs');
      if (savedInputs) {
        setInputs(JSON.parse(savedInputs));
      }

      // Load history
      const savedHistory = localStorage.getItem('goalTrackerHistory');
      if (savedHistory) {
        setHistory(JSON.parse(savedHistory));
      }

      // Load last saved timestamp
      const savedTimestamp = localStorage.getItem('goalTrackerLastSaved');
      if (savedTimestamp) {
        setLastSaved(new Date(savedTimestamp));
      }
    } catch (error) {
      console.error('Failed to load saved data:', error);
    }
  };

  const saveData = () => {
    try {
      localStorage.setItem('goalTrackerInputs', JSON.stringify(inputs));
      const now = new Date();
      localStorage.setItem('goalTrackerLastSaved', now.toISOString());
      setLastSaved(now);
    } catch (error) {
      console.error('Failed to save data:', error);
    }
  };

  const saveSnapshot = () => {
    const snapshot = {
      date: new Date().toISOString(),
      inputs: { ...inputs },
      calculated: { ...calculated },
    };

    const newHistory = [snapshot, ...history].slice(0, 50); // Keep last 50 snapshots
    setHistory(newHistory);
    localStorage.setItem('goalTrackerHistory', JSON.stringify(newHistory));
  };

  const loadSnapshot = (snapshot) => {
    setInputs(snapshot.inputs);
    setCalculated(snapshot.calculated);
  };

  const clearHistory = () => {
    if (window.confirm('Are you sure you want to clear all historical data?')) {
      setHistory([]);
      localStorage.removeItem('goalTrackerHistory');
    }
  };

  const exportToExcel = () => {
    // Create CSV format that can be opened in Excel
    const csvRows = [
      ['High Trust Business Plan - Export'],
      ['Generated:', new Date().toLocaleString()],
      [],
      ['INPUTS'],
      ['Average Loan Amount', inputs.avgLoanAmount],
      ['Annual Closings Dollar Goal', inputs.annualClosingsDollarGoal],
      ['Pull Through Rate', inputs.pullThroughRate],
      ['Conversion to App', inputs.conversionToApp],
      ['Total Referral Partners', inputs.totalReferralPartners],
      ['Annual Income Goal', inputs.annualIncomeGoal],
      ['Average Commission Basis Points', inputs.avgCommissionBasisPoints],
      ['Pre-Qual to App Rate', inputs.preQualToAppRate],
      [],
      ['CALCULATED METRICS'],
      ['Annual Closings Unit Goal', calculated.annualClosingsUnitGoal],
      ['Annual Origination Dollar Goal', calculated.annualOriginationDollarGoal],
      ['Annual Origination Unit Goal', calculated.annualOriginationUnitGoal],
      ['Monthly Units Goal', calculated.monthlyUnitsGoal],
      ['Weekly Units Goal', calculated.weeklyUnitsGoal],
      ['Daily Units Goal', calculated.dailyUnitsGoal],
      ['Daily Referred Pre-Quals Needed', calculated.dailyReferredPreQuals],
      ['Monthly Referred Pre-Quals Needed', calculated.monthlyReferredPreQuals],
      ['Min Pre-Qual Per Partner', calculated.minPreQualPerPartner],
    ];

    const csvContent = csvRows.map(row => row.join(',')).join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `business-plan-${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
    window.URL.revokeObjectURL(url);
  };

  const calculateMetrics = () => {
    // ===== SIMPLIFIED BUSINESS PLAN =====

    // Part 1: Volume Goals
    const annualClosingsUnitGoal = inputs.annualClosingsDollarGoal / inputs.avgLoanAmount;
    const annualOriginationDollarGoal = inputs.avgLoanAmount * Math.floor(annualClosingsUnitGoal / inputs.pullThroughRate);
    const annualOriginationUnitGoal = Math.floor(annualClosingsUnitGoal / inputs.pullThroughRate);

    // Part 2: Chunk Down - Building Consistency
    const annualUnitsGoal = annualOriginationUnitGoal;
    const monthlyUnitsGoal = annualUnitsGoal / 12;
    const weeklyUnitsGoal = Math.ceil(annualUnitsGoal / 52);
    const dailyUnitsGoal = Math.ceil(weeklyUnitsGoal / 5);

    // Part 3: Referred Pre-Qual Conversion
    const dailyLoans = dailyUnitsGoal;
    const dailyReferredPreQuals = Math.ceil(dailyLoans / inputs.conversionToApp);

    // Part 4: Referral Standards for Strategic Partners
    const monthlyReferredPreQuals = Math.ceil(dailyReferredPreQuals * 5 * 52 / 12);
    const minPreQualPerPartner = monthlyReferredPreQuals / inputs.totalReferralPartners;

    // ===== HIGH TRUST BUSINESS PLAN =====

    // Target Closings
    const targetClosings = inputs.annualIncomeGoal / inputs.avgCommissionBasisPoints;

    // Part 1: Volume Goals (High Trust)
    const annualFundedUnitGoal = targetClosings / inputs.avgLoanAmount;
    const annualSubmittedOrigination = targetClosings / inputs.pullThroughRate;
    const annualOriginationUnitNeeded = annualFundedUnitGoal / inputs.pullThroughRate;

    // Part 2: Chunk Down (High Trust)
    const ht_annualOriginationUnits = annualOriginationUnitNeeded;
    const ht_monthlyUnitsGoal = ht_annualOriginationUnits / 12;
    const ht_weeklyUnitsGoal = ht_annualOriginationUnits / 52;
    const ht_dailyUnitsGoal = ht_weeklyUnitsGoal / 5;

    // Part 3: Referred Pre-Qual Conversations (High Trust)
    const ht_dailyLoans = ht_dailyUnitsGoal;
    const ht_weeklyLoans = ht_weeklyUnitsGoal;
    const ht_dailyPreQualsNeeded = ht_dailyLoans / inputs.preQualToAppRate;
    const ht_weeklyPreQualsNeeded = ht_weeklyLoans / inputs.preQualToAppRate;

    // Part 4: Strategic Partner Referral Standards (High Trust)
    const ht_monthlyPreQualInquiries = Math.ceil(ht_dailyPreQualsNeeded * 5 * 52 / 12);
    const ht_totalPartnersNeeded = Math.ceil(ht_monthlyPreQualInquiries / minPreQualPerPartner);

    setCalculated({
      // Simplified Business Plan
      annualClosingsUnitGoal,
      annualOriginationDollarGoal,
      annualOriginationUnitGoal,
      annualUnitsGoal,
      monthlyUnitsGoal,
      weeklyUnitsGoal,
      dailyUnitsGoal,
      dailyLoans,
      dailyReferredPreQuals,
      monthlyReferredPreQuals,
      minPreQualPerPartner,

      // High Trust Business Plan
      targetClosings,
      annualFundedUnitGoal,
      annualSubmittedOrigination,
      annualOriginationUnitNeeded,
      ht_annualOriginationUnits,
      ht_monthlyUnitsGoal,
      ht_weeklyUnitsGoal,
      ht_dailyUnitsGoal,
      ht_dailyLoans,
      ht_weeklyLoans,
      ht_dailyPreQualsNeeded,
      ht_weeklyPreQualsNeeded,
      ht_monthlyPreQualInquiries,
      ht_totalPartnersNeeded,
    });
  };

  const handleInputChange = (field, value) => {
    setInputs(prev => ({
      ...prev,
      [field]: parseFloat(value) || 0
    }));
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const formatNumber = (value) => {
    return value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 2 });
  };

  const formatPercent = (value) => {
    return `${(value * 100).toFixed(0)}%`;
  };

  return (
    <div className="goal-tracker-page">
      <div className="page-header">
        <h1>📊 High Trust Business Plan</h1>
        <p className="plan-subtitle">Set your goals and see exactly what activities you need to hit them</p>

        {/* Action Buttons */}
        <div className="action-buttons">
          <button className="btn-primary" onClick={saveSnapshot}>
            💾 Save Snapshot
          </button>
          <button className="btn-secondary" onClick={() => setShowHistory(!showHistory)}>
            📈 {showHistory ? 'Hide' : 'View'} History ({history.length})
          </button>
          <button className="btn-secondary" onClick={exportToExcel}>
            📥 Export to Excel
          </button>
          {lastSaved && (
            <span className="last-saved">
              Last saved: {lastSaved.toLocaleTimeString()}
            </span>
          )}
        </div>

        {/* History Panel */}
        {showHistory && (
          <div className="history-panel">
            <div className="history-header">
              <h3>📊 Historical Snapshots</h3>
              {history.length > 0 && (
                <button className="btn-danger-sm" onClick={clearHistory}>
                  Clear All
                </button>
              )}
            </div>
            {history.length === 0 ? (
              <p className="no-history">No snapshots saved yet. Click "Save Snapshot" to track your progress over time.</p>
            ) : (
              <div className="history-list">
                {history.map((snapshot, index) => (
                  <div key={index} className="history-item">
                    <div className="history-date">
                      {new Date(snapshot.date).toLocaleString()}
                    </div>
                    <div className="history-metrics">
                      <span>Daily Goal: {formatNumber(snapshot.calculated.dailyUnitsGoal || 0)}</span>
                      <span>Monthly: {formatNumber(snapshot.calculated.monthlyUnitsGoal || 0)}</span>
                      <span>Annual: {formatCurrency(snapshot.inputs.annualClosingsDollarGoal || 0)}</span>
                    </div>
                    <button
                      className="btn-load"
                      onClick={() => loadSnapshot(snapshot)}
                    >
                      Load
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        <div className="plan-key">
          <span className="key-item"><span className="key-box user-input"></span> User Input Fields</span>
          <span className="key-item"><span className="key-box calculated"></span> Calculated Values</span>
        </div>
      </div>

      <div className="business-plans-container">
        {/* ========== SIMPLIFIED BUSINESS PLAN ========== */}
        <div className="business-plan-section">
          <h2 className="plan-title">📈 Simplified Business Plan</h2>

          {/* Part 1: Volume Goals */}
          <div className="goal-section">
            <h3>Part 1: Volume Goals</h3>
            <div className="spreadsheet-table">
              <table>
                <tbody>
                  <tr>
                    <td className="label-cell">Average Loan Amount</td>
                    <td className="input-cell user-input">
                      {formatCurrency(inputs.avgLoanAmount)}
                      <input
                        type="number"
                        value={inputs.avgLoanAmount}
                        onChange={(e) => handleInputChange('avgLoanAmount', e.target.value)}
                      />
                    </td>
                  </tr>
                  <tr>
                    <td className="label-cell">Annual Closings Dollar Goal</td>
                    <td className="input-cell user-input">
                      {formatCurrency(inputs.annualClosingsDollarGoal)}
                      <input
                        type="number"
                        value={inputs.annualClosingsDollarGoal}
                        onChange={(e) => handleInputChange('annualClosingsDollarGoal', e.target.value)}
                      />
                    </td>
                  </tr>
                  <tr>
                    <td className="label-cell">Annual Closings Unit Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.annualClosingsUnitGoal || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Determine Your "Pull Through" %</td>
                    <td className="input-cell user-input">
                      {formatPercent(inputs.pullThroughRate)}
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={inputs.pullThroughRate}
                        onChange={(e) => handleInputChange('pullThroughRate', e.target.value)}
                      />
                    </td>
                  </tr>
                  <tr>
                    <td className="label-cell">Annual Origination Dollar Goal</td>
                    <td className="calculated-cell">{formatCurrency(calculated.annualOriginationDollarGoal || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Annual Origination Unit Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.annualOriginationUnitGoal || 0)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Part 2: Chunk Down */}
          <div className="goal-section">
            <h3>Part 2: Chunk Down - Building Consistency</h3>
            <div className="spreadsheet-table">
              <table>
                <tbody>
                  <tr>
                    <td className="label-cell">Annual Units Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.annualUnitsGoal || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Monthly Units Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.monthlyUnitsGoal || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Weekly Units Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.weeklyUnitsGoal || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Daily Units Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.dailyUnitsGoal || 0)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Part 3: Referred Pre-Qual Conversion */}
          <div className="goal-section">
            <h3>Part 3: Referred Pre-Qual Conversion and Follow-Up</h3>
            <div className="spreadsheet-table">
              <table>
                <tbody>
                  <tr>
                    <td className="label-cell">Daily Loans</td>
                    <td className="calculated-cell">{formatNumber(calculated.dailyLoans || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Conversion to Application</td>
                    <td className="input-cell user-input">
                      {formatPercent(inputs.conversionToApp)}
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={inputs.conversionToApp}
                        onChange={(e) => handleInputChange('conversionToApp', e.target.value)}
                      />
                    </td>
                  </tr>
                  <tr>
                    <td className="label-cell">Daily Referred Pre-Qualifications Needed</td>
                    <td className="calculated-cell">{formatNumber(calculated.dailyReferredPreQuals || 0)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Part 4: Referral Standards */}
          <div className="goal-section">
            <h3>Part 4: Referral Standards for Strategic Partners</h3>
            <div className="spreadsheet-table">
              <table>
                <tbody>
                  <tr>
                    <td className="label-cell">Monthly Referred Pre-Qual Conversations Needed</td>
                    <td className="calculated-cell">{formatNumber(calculated.monthlyReferredPreQuals || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Minimum Referred Pre-Qual Goal per Partner</td>
                    <td className="calculated-cell">{formatNumber(calculated.minPreQualPerPartner || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Total Referral Partners Needed</td>
                    <td className="input-cell user-input">
                      {inputs.totalReferralPartners}
                      <input
                        type="number"
                        value={inputs.totalReferralPartners}
                        onChange={(e) => handleInputChange('totalReferralPartners', e.target.value)}
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Summary Message */}
          <div className="goal-summary-message">
            <strong>I need {formatNumber(calculated.dailyUnitsGoal || 0)} loans every day</strong>
          </div>
        </div>

        {/* ========== HIGH TRUST BUSINESS PLAN ========== */}
        <div className="business-plan-section">
          <h2 className="plan-title">💎 High Trust Business Plan</h2>

          {/* Input Section */}
          <div className="goal-section">
            <h3>Your Goals</h3>
            <div className="spreadsheet-table high-trust-inputs">
              <table>
                <tbody>
                  <tr>
                    <td className="label-cell">Annual Income Goal ($)</td>
                    <td className="input-cell user-input">
                      {formatCurrency(inputs.annualIncomeGoal)}
                      <input
                        type="number"
                        value={inputs.annualIncomeGoal}
                        onChange={(e) => handleInputChange('annualIncomeGoal', e.target.value)}
                      />
                    </td>
                    <td className="label-cell">Average Loan Amount ($)</td>
                    <td className="calculated-cell">{formatCurrency(inputs.avgLoanAmount)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Average Commission Basis Points</td>
                    <td className="input-cell user-input">
                      {(inputs.avgCommissionBasisPoints * 100).toFixed(2)}%
                      <input
                        type="number"
                        step="0.001"
                        min="0"
                        max="1"
                        value={inputs.avgCommissionBasisPoints}
                        onChange={(e) => handleInputChange('avgCommissionBasisPoints', e.target.value)}
                      />
                    </td>
                    <td className="label-cell">Pre-Qual Conversation to Application Rate (%)</td>
                    <td className="input-cell user-input">
                      {formatPercent(inputs.preQualToAppRate)}
                      <input
                        type="number"
                        step="0.01"
                        min="0"
                        max="1"
                        value={inputs.preQualToAppRate}
                        onChange={(e) => handleInputChange('preQualToAppRate', e.target.value)}
                      />
                    </td>
                  </tr>
                  <tr>
                    <td className="label-cell">Monthly Pre-Qual Referral Goal Per Partner</td>
                    <td className="calculated-cell">{formatNumber(calculated.minPreQualPerPartner || 0)}</td>
                    <td className="label-cell">Pull-Through Rate (%)</td>
                    <td className="calculated-cell">{formatPercent(inputs.pullThroughRate)}</td>
                  </tr>
                  <tr className="highlight-row">
                    <td className="label-cell"><strong>Your Target Closings</strong></td>
                    <td className="calculated-cell"><strong>{formatCurrency(calculated.targetClosings || 0)}</strong></td>
                    <td className="label-cell"><strong>I need to get</strong></td>
                    <td className="calculated-cell"><strong>{formatNumber(calculated.ht_dailyUnitsGoal || 0)} loans every day</strong></td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Part 1: Volume Goals (High Trust) */}
          <div className="goal-section">
            <h3>Part 1: Volume Goals</h3>
            <div className="spreadsheet-table">
              <table>
                <tbody>
                  <tr>
                    <td className="label-cell">Annual Funded Unit Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.annualFundedUnitGoal || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Annual Submitted Origination Needed</td>
                    <td className="calculated-cell">{formatCurrency(calculated.annualSubmittedOrigination || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Annual Origination Unit Needed</td>
                    <td className="calculated-cell">{formatNumber(calculated.annualOriginationUnitNeeded || 0)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Part 2: Chunk Down (High Trust) */}
          <div className="goal-section">
            <h3>Part 2: Chunk Down</h3>
            <div className="spreadsheet-table">
              <table>
                <tbody>
                  <tr>
                    <td className="label-cell">Annual Origination Units Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_annualOriginationUnits || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Monthly Units Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_monthlyUnitsGoal || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Weekly Units Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_weeklyUnitsGoal || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Daily Units Goal</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_dailyUnitsGoal || 0)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Part 3: Referred Pre-Qual Conversations (High Trust) */}
          <div className="goal-section">
            <h3>Part 3: Referred Pre-Qual Conversations</h3>
            <div className="spreadsheet-table">
              <table>
                <thead>
                  <tr>
                    <th></th>
                    <th>Daily</th>
                    <th>Weekly</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="label-cell">Number of Loans</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_dailyLoans || 0)}</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_weeklyLoans || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Conversion to Application</td>
                    <td className="calculated-cell">{formatPercent(inputs.preQualToAppRate)}</td>
                    <td className="calculated-cell">{formatPercent(inputs.preQualToAppRate)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Pre-Quals Needed</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_dailyPreQualsNeeded || 0)}</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_weeklyPreQualsNeeded || 0)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>

          {/* Part 4: Strategic Partner Referral Standards (High Trust) */}
          <div className="goal-section">
            <h3>Part 4: Strategic Partner Referral Standards</h3>
            <div className="spreadsheet-table">
              <table>
                <tbody>
                  <tr>
                    <td className="label-cell">Monthly Referred Pre-Qual Inquiries Needed</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_monthlyPreQualInquiries || 0)}</td>
                  </tr>
                  <tr>
                    <td className="label-cell">Total Referral Partners Needed</td>
                    <td className="calculated-cell">{formatNumber(calculated.ht_totalPartnersNeeded || 0)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default GoalTracker;

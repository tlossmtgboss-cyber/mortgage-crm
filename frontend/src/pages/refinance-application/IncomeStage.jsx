import React from 'react';
import EmployerAutocomplete from '../../components/EmployerAutocomplete';
import { Icon } from '../application-shared';

/**
 * IncomeStage - Refinance income collection.
 * 2-step: 1) type selection (employed/self-employed/retired/other), 2) detail form.
 */
export default function IncomeStage({
  declarations,
  incomeData,
  setIncomeData,
  incomeStep,
  setIncomeStep,
  handleIncomeFieldChange,
  goToPrevStage,
  goToNextStage,
}) {
  const isSelfEmployed = declarations.self_employed === 'yes' || declarations.self_employed === 'side_business';

  // Step 1: Income type selection
  if (incomeStep === 1) {
    return (
      <div className="stage-content">
        <div className="stage-header">
          <h2>Tell us about your income</h2>
          <p>This helps determine your refinance options</p>
        </div>
        <div className="income-type-selector">
          <h3>How do you earn income?</h3>
          <div className="income-cards">
            {[
              { type: 'employed', icon: 'tie', label: 'Employed', desc: 'W-2 employee' },
              { type: 'self_employed', icon: 'building', label: 'Self-Employed', desc: 'Business owner' },
              { type: 'retired', icon: 'beach', label: 'Retired', desc: 'Pension/SS' },
              { type: 'other', icon: 'dollarSign', label: 'Other', desc: 'Rental, investments' },
            ].map(({ type, icon, label, desc }) => (
              <div
                key={type}
                className={`income-card ${incomeData.primaryType === type ? 'selected' : ''}`}
                onClick={() => setIncomeData(prev => ({ ...prev, primaryType: type }))}
              >
                <span className="card-icon"><Icon name={icon} size={28} /></span>
                <span className="card-label">{label}</span>
                <span className="card-desc">{desc}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => incomeData.primaryType && setIncomeStep(2)} disabled={!incomeData.primaryType}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Step 2: Income details based on type
  return (
    <div className="stage-content">
      <div className="stage-header">
        <h2>
          {incomeData.primaryType === 'employed' && 'Employment Details'}
          {incomeData.primaryType === 'self_employed' && 'Business Details'}
          {incomeData.primaryType === 'retired' && 'Retirement Income'}
          {incomeData.primaryType === 'other' && 'Other Income'}
        </h2>
        <p>Tell us more about your income</p>
      </div>

      {incomeData.primaryType === 'employed' && (
        <div className="form-card">
          <EmployerAutocomplete
            value={incomeData.employerName || ''}
            onChange={(value) => setIncomeData(prev => ({ ...prev, employerName: value }))}
            onEmployerSelect={(employer) => {
              setIncomeData(prev => ({
                ...prev,
                employerName: employer.name,
                employerAddress: employer.address,
                employerCity: employer.city,
                employerState: employer.state,
                employerPhone: employer.phone,
              }));
            }}
            label="Employer Name"
            placeholder="Start typing company name..."
            className="fun-input-wrapper"
          />
          <div className="form-group">
            <label>Employer Address</label>
            <input type="text" value={incomeData.employerAddress || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, employerAddress: e.target.value }))} className="fun-input" placeholder="Auto-filled from employer selection" />
          </div>
          <div className="form-group">
            <label>Employer Phone</label>
            <input type="tel" value={incomeData.employerPhone || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, employerPhone: e.target.value }))} className="fun-input" placeholder="Auto-filled from employer selection" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Job Title</label>
              <input type="text" value={incomeData.jobTitle || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, jobTitle: e.target.value }))} className="fun-input" />
            </div>
            <div className="form-group">
              <label>Years There</label>
              <input type="number" value={incomeData.yearsAtJob || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, yearsAtJob: e.target.value }))} className="fun-input" min="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Annual Base Salary</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={incomeData.annualSalary || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, annualSalary: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
        </div>
      )}

      {(incomeData.primaryType === 'self_employed' || isSelfEmployed) && (
        <div className="form-card">
          <div className="form-group">
            <label>Business Name</label>
            <input type="text" value={incomeData.businessName || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, businessName: e.target.value }))} className="fun-input" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Business Type</label>
              <select value={incomeData.businessType || ''} onChange={(e) => handleIncomeFieldChange('businessType', e.target.value, setIncomeData)} className="fun-input">
                <option value="">Select...</option>
                <option value="sole_prop">Sole Proprietorship</option>
                <option value="llc">LLC</option>
                <option value="s_corp">S-Corporation</option>
                <option value="c_corp">C-Corporation</option>
              </select>
            </div>
            <div className="form-group">
              <label>Ownership %</label>
              <input type="number" value={incomeData.ownershipPercent || ''} onChange={(e) => handleIncomeFieldChange('ownershipPercent', e.target.value, setIncomeData)} className="fun-input" min="0" max="100" placeholder="25" />
            </div>
          </div>
          <div className="form-group">
            <label>Annual Net Income (from business)</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={incomeData.businessIncome || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, businessIncome: e.target.value }))} className="fun-input" />
            </div>
            <span className="input-hint">Use your net income from Schedule C or K-1</span>
          </div>
        </div>
      )}

      {incomeData.primaryType === 'retired' && (
        <div className="form-card">
          <div className="form-group">
            <label>Monthly Social Security</label>
            <div className="input-with-prefix"><span className="input-prefix">$</span>
              <input type="number" value={incomeData.socialSecurity || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, socialSecurity: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Monthly Pension</label>
            <div className="input-with-prefix"><span className="input-prefix">$</span>
              <input type="number" value={incomeData.pension || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, pension: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Monthly Retirement Distributions (401k, IRA)</label>
            <div className="input-with-prefix"><span className="input-prefix">$</span>
              <input type="number" value={incomeData.retirementDistributions || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, retirementDistributions: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
        </div>
      )}

      {incomeData.primaryType === 'other' && (
        <div className="form-card">
          <div className="form-group">
            <label>Monthly Rental Income</label>
            <div className="input-with-prefix"><span className="input-prefix">$</span>
              <input type="number" value={incomeData.rentalIncome || ''} onChange={(e) => handleIncomeFieldChange('rentalIncome', e.target.value, setIncomeData)} className="fun-input" placeholder="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Monthly Investment Income</label>
            <div className="input-with-prefix"><span className="input-prefix">$</span>
              <input type="number" value={incomeData.investmentIncome || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, investmentIncome: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Other Monthly Income</label>
            <div className="input-with-prefix"><span className="input-prefix">$</span>
              <input type="number" value={incomeData.otherIncome || ''} onChange={(e) => handleIncomeFieldChange('otherIncome', e.target.value, setIncomeData)} className="fun-input" placeholder="0" />
            </div>
          </div>
        </div>
      )}

      <div className="stage-navigation">
        <button className="btn-back" onClick={() => setIncomeStep(1)}>{'←'} Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue {'→'}</button>
      </div>
    </div>
  );
}

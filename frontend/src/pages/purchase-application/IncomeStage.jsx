import React from 'react';
import EmployerAutocomplete from '../../components/EmployerAutocomplete';
import { Icon } from '../application-shared';

/**
 * IncomeStage - Employment and income details collection.
 * Supports primary + co-borrower, W-2 and self-employed flows.
 */
export default function IncomeStage({
  declarations,
  profileData,
  coBorrowerData,
  incomeData,
  setIncomeData,
  coBorrowerIncomeData,
  setCoBorrowerIncomeData,
  currentIncomeBorrower,
  setCurrentIncomeBorrower,
  hasMultipleBorrowers,
  getBorrowerCount,
  handleIncomeFieldChange,
  goToPrevStage,
  goToNextStage,
}) {
  const isCollectingCoBorrowerIncome = currentIncomeBorrower === 2;
  const currentIncomeDataState = isCollectingCoBorrowerIncome ? coBorrowerIncomeData : incomeData;
  const setCurrentIncomeData = isCollectingCoBorrowerIncome ? setCoBorrowerIncomeData : setIncomeData;

  const primaryBorrowerName = profileData?.firstName || 'Primary Borrower';
  const coBorrowerName = coBorrowerData?.firstName || 'Co-Borrower';
  const currentBorrowerName = isCollectingCoBorrowerIncome ? coBorrowerName : primaryBorrowerName;

  const getIncomeType = () => {
    if (isCollectingCoBorrowerIncome) {
      return coBorrowerIncomeData.incomeType || 'employed';
    }
    if (declarations.self_employed === 'yes') return 'self_employed';
    if (declarations.self_employed === 'side_business') return 'employed_with_business';
    return 'employed';
  };

  const currentIncomeType = getIncomeType();

  return (
    <div className="stage-content">
      <div className="stage-header">
        <h2>
          {isCollectingCoBorrowerIncome
            ? `${coBorrowerName}'s Employment Details`
            : (currentIncomeType === 'employed' && `${primaryBorrowerName}'s Employment Details`) ||
              (currentIncomeType === 'self_employed' && `${primaryBorrowerName}'s Business Details`) ||
              (currentIncomeType === 'employed_with_business' && `${primaryBorrowerName}'s Employment & Business Details`)
          }
        </h2>
        <p>{isCollectingCoBorrowerIncome
          ? `Tell us about ${coBorrowerName}'s income`
          : 'Tell us more about your income'}</p>
      </div>

      {hasMultipleBorrowers && (
        <div className="borrower-income-indicator" style={{
          background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
          border: '1px solid #22c55e',
          borderRadius: '12px',
          padding: '12px 16px',
          marginBottom: '20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <Icon name="income" size={20} style={{ color: '#16a34a' }} />
            <span style={{ color: '#166534', fontWeight: 600, fontSize: '14px' }}>
              {isCollectingCoBorrowerIncome
                ? `Collecting ${coBorrowerName}'s income information`
                : `Collecting ${primaryBorrowerName}'s income information`
              }
            </span>
          </div>
          <span style={{
            background: '#22c55e',
            color: 'white',
            padding: '4px 12px',
            borderRadius: '20px',
            fontSize: '12px',
            fontWeight: 600
          }}>
            Borrower {currentIncomeBorrower} of {getBorrowerCount()}
          </span>
        </div>
      )}

      {/* Co-borrower income type selection */}
      {isCollectingCoBorrowerIncome && !currentIncomeDataState.incomeType && (
        <div className="form-card" style={{ marginBottom: '20px' }}>
          <h3 style={{ marginBottom: '16px' }}>How does {coBorrowerName} earn income?</h3>
          <div className="income-type-selection" style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <button
              className={`income-type-btn ${currentIncomeDataState.incomeType === 'employed' ? 'selected' : ''}`}
              onClick={() => setCurrentIncomeData(prev => ({ ...prev, incomeType: 'employed' }))}
              style={{
                padding: '16px 24px',
                border: '2px solid #e5e7eb',
                borderRadius: '12px',
                background: currentIncomeDataState.incomeType === 'employed' ? '#0d9488' : 'white',
                color: currentIncomeDataState.incomeType === 'employed' ? 'white' : '#374151',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 500
              }}
            >
              W-2 Employee
            </button>
            <button
              className={`income-type-btn ${currentIncomeDataState.incomeType === 'self_employed' ? 'selected' : ''}`}
              onClick={() => setCurrentIncomeData(prev => ({ ...prev, incomeType: 'self_employed' }))}
              style={{
                padding: '16px 24px',
                border: '2px solid #e5e7eb',
                borderRadius: '12px',
                background: currentIncomeDataState.incomeType === 'self_employed' ? '#0d9488' : 'white',
                color: currentIncomeDataState.incomeType === 'self_employed' ? 'white' : '#374151',
                cursor: 'pointer',
                fontSize: '14px',
                fontWeight: 500
              }}
            >
              Self-Employed
            </button>
          </div>
        </div>
      )}

      {/* Employment form */}
      {((currentIncomeType === 'employed' || currentIncomeType === 'employed_with_business') ||
        (isCollectingCoBorrowerIncome && currentIncomeDataState.incomeType === 'employed')) && (
        <div className="form-card">
          <EmployerAutocomplete
            value={currentIncomeDataState.employerName || ''}
            onChange={(value) => setCurrentIncomeData(prev => ({ ...prev, employerName: value }))}
            onEmployerSelect={(employer) => {
              setCurrentIncomeData(prev => ({
                ...prev,
                employerName: employer.name,
                employerAddress: employer.address,
                employerCity: employer.city,
                employerState: employer.state,
                employerPhone: employer.phone,
              }));
            }}
            label={`${currentBorrowerName}'s Employer Name`}
            placeholder="Start typing company name..."
            className="fun-input-wrapper"
          />
          <div className="form-group">
            <label>Employer Address</label>
            <input
              type="text"
              value={currentIncomeDataState.employerAddress || ''}
              onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, employerAddress: e.target.value }))}
              className="fun-input"
              placeholder="Auto-filled from employer selection"
            />
          </div>
          <div className="form-group">
            <label>Employer Phone</label>
            <input
              type="tel"
              value={currentIncomeDataState.employerPhone || ''}
              onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, employerPhone: e.target.value }))}
              className="fun-input"
              placeholder="Auto-filled from employer selection"
            />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Job Title</label>
              <input
                type="text"
                value={currentIncomeDataState.jobTitle || ''}
                onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, jobTitle: e.target.value }))}
                className="fun-input"
              />
            </div>
            <div className="form-group">
              <label>Start Date</label>
              <input
                type="month"
                value={currentIncomeDataState.employmentStartDate || ''}
                onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, employmentStartDate: e.target.value }))}
                className="fun-input"
                max={new Date().toISOString().slice(0, 7)}
              />
            </div>
          </div>
          <div className="form-group">
            <label>Annual Base Salary</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input
                type="number"
                value={currentIncomeDataState.annualSalary || ''}
                onChange={(e) => setCurrentIncomeData(prev => ({ ...prev, annualSalary: e.target.value }))}
                className="fun-input"
                placeholder="0"
              />
            </div>
          </div>
        </div>
      )}

      {/* Previous Employer */}
      {(currentIncomeType === 'employed' || currentIncomeType === 'employed_with_business') &&
       incomeData.employmentStartDate && (() => {
         const startDate = new Date(incomeData.employmentStartDate + '-01');
         const twoYearsAgo = new Date();
         twoYearsAgo.setFullYear(twoYearsAgo.getFullYear() - 2);
         return startDate > twoYearsAgo;
       })() && (
        <div className="form-card">
          <h3>Previous Employer</h3>
          <p className="section-hint">Since you've been at your current job less than 2 years, we need your previous employment history.</p>
          <div className="form-group">
            <label>Previous Employer Name</label>
            <input type="text" value={incomeData.prevEmployerName || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, prevEmployerName: e.target.value }))} className="fun-input" placeholder="Previous company name" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Job Title</label>
              <input type="text" value={incomeData.prevJobTitle || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, prevJobTitle: e.target.value }))} className="fun-input" />
            </div>
            <div className="form-group">
              <label>Start Date</label>
              <input type="month" value={incomeData.prevEmploymentStartDate || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, prevEmploymentStartDate: e.target.value }))} className="fun-input" />
            </div>
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>End Date</label>
              <input type="month" value={incomeData.prevEmploymentEndDate || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, prevEmploymentEndDate: e.target.value }))} className="fun-input" />
            </div>
            <div className="form-group">
              <label>Annual Salary (at that job)</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input type="number" value={incomeData.prevAnnualSalary || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, prevAnnualSalary: e.target.value }))} className="fun-input" placeholder="0" />
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Second Job Question */}
      {(currentIncomeType === 'employed' || currentIncomeType === 'employed_with_business') && (
        <div className="form-card">
          <h3>Do you have a second job?</h3>
          <div className="yes-no-buttons">
            <button type="button" className={`yes-no-btn ${incomeData.hasSecondJob === 'yes' ? 'selected' : ''}`} onClick={() => setIncomeData(prev => ({ ...prev, hasSecondJob: 'yes' }))}>Yes</button>
            <button type="button" className={`yes-no-btn ${incomeData.hasSecondJob === 'no' ? 'selected' : ''}`} onClick={() => setIncomeData(prev => ({ ...prev, hasSecondJob: 'no' }))}>No</button>
          </div>
        </div>
      )}

      {/* Second Job Details */}
      {incomeData.hasSecondJob === 'yes' && (
        <div className="form-card">
          <h3>Second Job Details</h3>
          <div className="form-group">
            <label>Employer Name</label>
            <input type="text" value={incomeData.secondEmployerName || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, secondEmployerName: e.target.value }))} className="fun-input" placeholder="Second employer name" />
          </div>
          <div className="form-row">
            <div className="form-group">
              <label>Job Title</label>
              <input type="text" value={incomeData.secondJobTitle || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, secondJobTitle: e.target.value }))} className="fun-input" />
            </div>
            <div className="form-group">
              <label>Start Date</label>
              <input type="month" value={incomeData.secondEmploymentStartDate || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, secondEmploymentStartDate: e.target.value }))} className="fun-input" max={new Date().toISOString().slice(0, 7)} />
            </div>
          </div>
          <div className="form-group">
            <label>Annual Income (from second job)</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={incomeData.secondJobIncome || ''} onChange={(e) => setIncomeData(prev => ({ ...prev, secondJobIncome: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
        </div>
      )}

      {/* Self-employed / Business section */}
      {(currentIncomeType === 'self_employed' || currentIncomeType === 'employed_with_business') && (
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

      {/* Additional income */}
      <div className="form-card">
        <h3>Additional Income (Optional)</h3>
        <div className="form-row">
          <div className="form-group">
            <label>Monthly Rental Income</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={incomeData.rentalIncome || ''} onChange={(e) => handleIncomeFieldChange('rentalIncome', e.target.value, setIncomeData)} className="fun-input" placeholder="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Other Monthly Income</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={incomeData.otherIncome || ''} onChange={(e) => handleIncomeFieldChange('otherIncome', e.target.value, setIncomeData)} className="fun-input" placeholder="0" />
            </div>
          </div>
        </div>
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={() => {
          if (isCollectingCoBorrowerIncome) {
            setCurrentIncomeBorrower(1);
          } else {
            goToPrevStage();
          }
        }}>{'←'} Back</button>

        {!isCollectingCoBorrowerIncome && hasMultipleBorrowers ? (
          <button className="btn-continue" onClick={() => setCurrentIncomeBorrower(2)}>
            Continue to {coBorrowerName}'s Income {'→'}
          </button>
        ) : (
          <button className="btn-continue" onClick={() => {
            if (isCollectingCoBorrowerIncome) {
              setCurrentIncomeBorrower(1);
            }
            goToNextStage();
          }}>Continue {'→'}</button>
        )}
      </div>
    </div>
  );
}

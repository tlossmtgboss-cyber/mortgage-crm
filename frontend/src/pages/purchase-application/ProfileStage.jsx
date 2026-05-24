import React from 'react';
import { Icon, US_STATES } from '../application-shared';

/**
 * ProfileStage - Borrower personal information collection.
 * Supports primary + co-borrower with residence history.
 */
export default function ProfileStage({
  currentBorrower,
  setCurrentBorrower,
  profileData,
  setProfileData,
  coBorrowerData,
  setCoBorrowerData,
  ssnDisplay,
  ssnRaw,
  coBorrowerSsnDisplay,
  coBorrowerSsnRaw,
  handleSsnChange,
  declarations,
  hasMultipleBorrowers,
  getBorrowerCount,
  residenceHistory,
  coBorrowerResidenceHistory,
  addResidenceAddress,
  removeResidenceAddress,
  updateResidenceAddress,
  calculateTotalResidenceMonths,
  goToPrevStage,
  goToNextStage,
}) {
  const isCollectingCoBorrower = currentBorrower === 2;
  const borrowerData = isCollectingCoBorrower ? coBorrowerData : profileData;
  const setBorrowerData = isCollectingCoBorrower ? setCoBorrowerData : setProfileData;
  const currentSsnDisplay = isCollectingCoBorrower ? coBorrowerSsnDisplay : ssnDisplay;
  const currentSsnRaw = isCollectingCoBorrower ? coBorrowerSsnRaw : ssnRaw;

  const renderBorrowerForm = () => (
    <div className="form-card">
      {hasMultipleBorrowers && (
        <div className="borrower-indicator">
          <span className="borrower-badge">
            <Icon name="user" size={16} />
            {isCollectingCoBorrower ? 'Co-Borrower Information' : 'Primary Borrower Information'}
          </span>
          <span className="borrower-progress">
            Borrower {currentBorrower} of {getBorrowerCount()}
          </span>
        </div>
      )}
      <div className="form-row">
        <div className="form-group">
          <label>First Name</label>
          <input
            type="text"
            value={borrowerData.firstName || ''}
            onChange={(e) => setBorrowerData(prev => ({ ...prev, firstName: e.target.value }))}
            placeholder={isCollectingCoBorrower ? "Co-borrower's first name" : "Your first name"}
            className="fun-input"
          />
        </div>
        <div className="form-group">
          <label>Last Name</label>
          <input
            type="text"
            value={borrowerData.lastName || ''}
            onChange={(e) => setBorrowerData(prev => ({ ...prev, lastName: e.target.value }))}
            placeholder={isCollectingCoBorrower ? "Co-borrower's last name" : "Your last name"}
            className="fun-input"
          />
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Email</label>
          <input
            type="email"
            value={borrowerData.email || ''}
            onChange={(e) => setBorrowerData(prev => ({ ...prev, email: e.target.value }))}
            placeholder="email@example.com"
            className="fun-input"
          />
        </div>
        <div className="form-group">
          <label>Phone</label>
          <input
            type="tel"
            value={borrowerData.phone || ''}
            onChange={(e) => setBorrowerData(prev => ({ ...prev, phone: e.target.value }))}
            placeholder="(555) 123-4567"
            className="fun-input"
          />
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Date of Birth</label>
          <input
            type="date"
            value={borrowerData.dob || ''}
            onChange={(e) => setBorrowerData(prev => ({ ...prev, dob: e.target.value }))}
            className="fun-input"
          />
        </div>
        <div className="form-group">
          <label>Social Security Number</label>
          <input
            type="text"
            value={currentSsnDisplay}
            onChange={(e) => {
              const newVal = e.target.value;
              if (newVal.length < currentSsnDisplay.length) {
                const newRaw = currentSsnRaw.slice(0, -1);
                handleSsnChange(newRaw, isCollectingCoBorrower);
              } else {
                const lastChar = newVal.slice(-1);
                if (/\d/.test(lastChar)) {
                  handleSsnChange(currentSsnRaw + lastChar, isCollectingCoBorrower);
                }
              }
            }}
            placeholder="XXX-XX-1234"
            className="fun-input ssn-input"
            maxLength={11}
            autoComplete="off"
          />
          <span className="input-hint">Only the last 4 digits will be visible</span>
        </div>
      </div>
      {/* Residence History Section */}
      <div className="residence-history-section">
        {(isCollectingCoBorrower ? coBorrowerResidenceHistory : residenceHistory).map((address, index) => (
          <div key={index} className="residence-address-card">
            <div className="residence-header">
              <h4>{index === 0 ? '\u{1F3E0} Current Address' : `\u{1F4CD} Previous Address ${index}`}</h4>
              {index > 0 && (
                <button
                  type="button"
                  className="btn-remove-address"
                  onClick={() => removeResidenceAddress(index, isCollectingCoBorrower)}
                >
                  ✕ Remove
                </button>
              )}
            </div>
            <div className="form-group">
              <label>Street Address</label>
              <input
                type="text"
                value={address.street || ''}
                onChange={(e) => updateResidenceAddress(index, 'street', e.target.value, isCollectingCoBorrower)}
                placeholder="123 Main Street, Apt 4B"
                className="fun-input"
              />
            </div>
            <div className="form-row form-row-3">
              <div className="form-group">
                <label>City</label>
                <input
                  type="text"
                  value={address.city || ''}
                  onChange={(e) => updateResidenceAddress(index, 'city', e.target.value, isCollectingCoBorrower)}
                  placeholder="City"
                  className="fun-input"
                />
              </div>
              <div className="form-group">
                <label>State</label>
                <select
                  value={address.state || ''}
                  onChange={(e) => updateResidenceAddress(index, 'state', e.target.value, isCollectingCoBorrower)}
                  className="fun-input"
                >
                  {US_STATES.map(s => (
                    <option key={s.value} value={s.value}>{s.label}</option>
                  ))}
                </select>
              </div>
              <div className="form-group">
                <label>ZIP Code</label>
                <input
                  type="text"
                  value={address.zip || ''}
                  onChange={(e) => updateResidenceAddress(index, 'zip', e.target.value.replace(/\D/g, '').slice(0, 5), isCollectingCoBorrower)}
                  placeholder="12345"
                  className="fun-input"
                  maxLength={5}
                />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>How long at this address?</label>
                <div className="duration-inputs">
                  <div className="duration-field">
                    <input
                      type="number"
                      min="0"
                      max="99"
                      value={address.years || ''}
                      onChange={(e) => updateResidenceAddress(index, 'years', e.target.value, isCollectingCoBorrower)}
                      placeholder="0"
                      className="fun-input duration-input"
                    />
                    <span className="duration-label">Years</span>
                  </div>
                  <div className="duration-field">
                    <input
                      type="number"
                      min="0"
                      max="11"
                      value={address.months || ''}
                      onChange={(e) => updateResidenceAddress(index, 'months', e.target.value, isCollectingCoBorrower)}
                      placeholder="0"
                      className="fun-input duration-input"
                    />
                    <span className="duration-label">Months</span>
                  </div>
                </div>
              </div>
              <div className="form-group">
                <label>Housing Status</label>
                <select
                  value={address.housingStatus || ''}
                  onChange={(e) => updateResidenceAddress(index, 'housingStatus', e.target.value, isCollectingCoBorrower)}
                  className="fun-input"
                >
                  <option value="">Select...</option>
                  <option value="own">Own</option>
                  <option value="rent">Rent</option>
                  <option value="living_rent_free">Living Rent Free</option>
                </select>
              </div>
            </div>
          </div>
        ))}

        {/* Residence History Progress */}
        {(() => {
          const currentHistory = isCollectingCoBorrower ? coBorrowerResidenceHistory : residenceHistory;
          const totalMonths = calculateTotalResidenceMonths(currentHistory);
          const needsMore = totalMonths < 24;
          const progressPercent = Math.min((totalMonths / 24) * 100, 100);

          return (
            <div className="residence-progress">
              <div className="residence-progress-bar">
                <div
                  className="residence-progress-fill"
                  style={{ width: `${progressPercent}%`, backgroundColor: needsMore ? '#f59e0b' : '#2D7A52' }}
                />
              </div>
              <div className="residence-progress-text">
                {needsMore ? (
                  <>
                    <span className="warning-text">{'⚠️'} We need 2 years of residence history</span>
                    <span className="progress-detail">
                      {Math.floor(totalMonths / 12)} year{Math.floor(totalMonths / 12) !== 1 ? 's' : ''}, {totalMonths % 12} month{totalMonths % 12 !== 1 ? 's' : ''} provided
                      {' '}&mdash; need {24 - totalMonths} more month{24 - totalMonths !== 1 ? 's' : ''}
                    </span>
                  </>
                ) : (
                  <span className="success-text">{'✓'} 2-year residence history complete</span>
                )}
              </div>
              {needsMore && (
                <button
                  type="button"
                  className="btn-add-address"
                  onClick={() => addResidenceAddress(isCollectingCoBorrower)}
                >
                  + Add Previous Address
                </button>
              )}
            </div>
          );
        })()}
      </div>
      {!isCollectingCoBorrower && declarations.marital_status === 'married' && (
        <div className="spouse-section">
          <h3><Icon name="users" size={20} /> Spouse Information</h3>
          <div className="form-row">
            <div className="form-group">
              <label>Spouse's First Name</label>
              <input
                type="text"
                value={profileData.spouseFirstName || ''}
                onChange={(e) => setProfileData(prev => ({ ...prev, spouseFirstName: e.target.value }))}
                className="fun-input"
              />
            </div>
            <div className="form-group">
              <label>Spouse's Last Name</label>
              <input
                type="text"
                value={profileData.spouseLastName || ''}
                onChange={(e) => setProfileData(prev => ({ ...prev, spouseLastName: e.target.value }))}
                className="fun-input"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );

  return (
    <div className="stage-content">
      <div className="stage-header">
        <h2>{isCollectingCoBorrower ? `${coBorrowerData.firstName || "Co-Borrower"}'s Information` : "Let's get to know you"}</h2>
        <p>{isCollectingCoBorrower
          ? `Please enter ${coBorrowerData.firstName || "the co-borrower"}'s information`
          : "This should take about 2 minutes"}</p>
      </div>

      {hasMultipleBorrowers && !isCollectingCoBorrower && (
        <div className="multiple-borrower-disclaimer" style={{
          background: 'linear-gradient(135deg, #dbeafe 0%, #bfdbfe 100%)',
          border: '1px solid #3b82f6',
          borderRadius: '12px',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'flex-start',
          gap: '12px'
        }}>
          <Icon name="users" size={24} style={{ color: '#2563eb', flexShrink: 0, marginTop: '2px' }} />
          <div>
            <p style={{ margin: 0, color: '#1e40af', fontWeight: 600, fontSize: '15px', marginBottom: '6px' }}>
              Multiple Borrowers Detected
            </p>
            <p style={{ margin: 0, color: '#1e3a8a', fontSize: '13px', lineHeight: '1.6' }}>
              Since there are multiple people on this loan application, we'll collect information for each borrower separately.
              We'll start with you (the primary borrower), and once your section is complete, you'll proceed to enter information
              for the co-borrower. Each person's information will be clearly labeled throughout the process.
            </p>
          </div>
        </div>
      )}

      {renderBorrowerForm()}
      <div className="stage-navigation">
        <button className="btn-back" onClick={() => {
          if (isCollectingCoBorrower) {
            setCurrentBorrower(1);
          } else {
            goToPrevStage();
          }
        }}>{'←'} Back</button>

        {!isCollectingCoBorrower && hasMultipleBorrowers && currentBorrower === 1 ? (
          <button
            className="btn-continue btn-add-coborrower"
            onClick={() => setCurrentBorrower(2)}
          >
            Add Co-Borrower {'→'}
          </button>
        ) : (
          <button className="btn-continue" onClick={() => {
            if (isCollectingCoBorrower) {
              goToNextStage();
            } else if (hasMultipleBorrowers) {
              setCurrentBorrower(2);
            } else {
              goToNextStage();
            }
          }}>Continue {'→'}</button>
        )}
      </div>
    </div>
  );
}

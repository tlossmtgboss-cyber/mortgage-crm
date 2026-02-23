import React, { useState, useEffect, useCallback } from 'react';
import { leadsAPI, API_BASE_URL } from '../services/api';
import './EmploymentTab.css';

const VERIFICATION_STATUSES = {
  'PENDING': { label: 'Pending Verification', color: '#6b7280', bgColor: '#f3f4f6' },
  'DOCUMENTS_RECEIVED': { label: 'Docs Received', color: '#d97706', bgColor: '#fef3c7' },
  'VERIFIED': { label: 'Verified', color: '#059669', bgColor: '#d1fae5' },
  'NEEDS_VOE': { label: 'Needs VOE', color: '#dc2626', bgColor: '#fee2e2' },
  'VOE_ORDERED': { label: 'VOE Ordered', color: '#7c3aed', bgColor: '#ede9fe' },
  'VOE_COMPLETE': { label: 'VOE Complete', color: '#059669', bgColor: '#d1fae5' },
};

export default function EmploymentTab({ leadId, formData, onFieldChange, entityType = 'leads' }) {
  const [calculating, setCalculating] = useState(false);
  const [employmentVerification, setEmploymentVerification] = useState(null);
  const [linkedIncomeSource, setLinkedIncomeSource] = useState(null);
  const [lastPaystubUpdate, setLastPaystubUpdate] = useState(null);
  const [verificationLoading, setVerificationLoading] = useState(true);

  const token = localStorage.getItem('token');

  // Fetch employment verification status and linked income source
  const fetchVerificationStatus = useCallback(async () => {
    if (!leadId) return;

    setVerificationLoading(true);
    try {
      // Fetch income sources for this borrower to find linked employment income
      const response = await fetch(
        `${API_BASE_URL}/api/v1/income/borrowers/${leadId}/sources?income_type=W2_EMPLOYMENT`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        const sources = data.sources || [];

        if (sources.length > 0) {
          const primarySource = sources.find(s => s.is_primary) || sources[0];
          setLinkedIncomeSource(primarySource);
          setEmploymentVerification(primarySource.verification_status || 'PENDING');

          // Get last paystub update date
          if (primarySource.calculation_date) {
            setLastPaystubUpdate(new Date(primarySource.calculation_date));
          }
        }
      }
    } catch (err) {
      console.error('Error fetching verification status:', err);
    } finally {
      setVerificationLoading(false);
    }
  }, [leadId, token]);

  useEffect(() => {
    fetchVerificationStatus();
  }, [fetchVerificationStatus]);

  // Calculate AI scores when relevant fields change
  useEffect(() => {
    const calculateScores = async () => {
      if (!formData.job_title && !formData.leadership_level) return;

      setCalculating(true);
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/${entityType}/${leadId}/calculate-referral-scores`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          },
          body: JSON.stringify({
            job_title: formData.job_title,
            leadership_level: formData.leadership_level,
            employees_managed: formData.employees_managed,
            company_size: formData.company_size,
            annual_income: formData.annual_income,
            years_at_job: formData.years_at_job,
            referral_comfort_level: formData.referral_comfort_level
          })
        });

        if (response.ok) {
          const scores = await response.json();
          // Update computed fields
          if (scores.influence_score) onFieldChange('influence_score', scores.influence_score);
          if (scores.referral_industry_flag) onFieldChange('referral_industry_flag', scores.referral_industry_flag);
          if (scores.career_stability_score) onFieldChange('career_stability_score', scores.career_stability_score);
          if (scores.referral_source_score) onFieldChange('referral_source_score', scores.referral_source_score);
          if (scores.referral_source_rating) onFieldChange('referral_source_rating', scores.referral_source_rating);
        }
      } catch (error) {
        console.error('Failed to calculate referral scores:', error);
      }
      setCalculating(false);
    };

    const debounce = setTimeout(calculateScores, 1500);
    return () => clearTimeout(debounce);
  }, [
    formData.job_title,
    formData.leadership_level,
    formData.employees_managed,
    formData.company_size,
    formData.annual_income,
    formData.years_at_job,
    formData.referral_comfort_level,
    leadId,
    entityType,
    onFieldChange
  ]);

  const getVerificationStatus = (status) => {
    return VERIFICATION_STATUSES[status] || VERIFICATION_STATUSES['PENDING'];
  };

  const formatDate = (date) => {
    if (!date) return null;
    return new Date(date).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="employment-tab">
      {/* SECTION 1: Employment Overview */}
      <div className="employment-section">
        <h3 className="section-header-with-score">
          <span>Employment Overview</span>
          <div className="header-badges">
            {!verificationLoading && employmentVerification && (
              <span
                className="verification-badge"
                style={{
                  backgroundColor: getVerificationStatus(employmentVerification).bgColor,
                  color: getVerificationStatus(employmentVerification).color,
                }}
              >
                {getVerificationStatus(employmentVerification).label}
              </span>
            )}
            <span className="header-score">
              Referral Score: {formData.referral_source_rating || '...'} {formData.referral_source_score || 0}/100
            </span>
          </div>
        </h3>

        {/* Paystub Update Info */}
        {(lastPaystubUpdate || linkedIncomeSource) && (
          <div className="paystub-info-banner">
            {lastPaystubUpdate && (
              <span className="paystub-date">
                <span className="info-icon">📄</span>
                Last updated from paystub: {formatDate(lastPaystubUpdate)}
              </span>
            )}
            {linkedIncomeSource && (
              <span className="income-link">
                <span className="info-icon">💰</span>
                Linked to income source: {linkedIncomeSource.source_name || 'W-2 Employment'}
                {linkedIncomeSource.monthly_qualifying_income && (
                  <span className="income-amount">
                    ${linkedIncomeSource.monthly_qualifying_income.toLocaleString()}/mo
                  </span>
                )}
              </span>
            )}
          </div>
        )}

        <div className="info-grid compact">
          <div className="info-field">
            <label>Employment Status</label>
            <select
              value={formData.employment_status || ''}
              onChange={(e) => onFieldChange('employment_status', e.target.value)}
            >
              <option value="">Select status</option>
              <option value="Employed">Employed</option>
              <option value="Self-Employed">Self-Employed</option>
              <option value="Retired">Retired</option>
              <option value="Other">Other</option>
            </select>
          </div>
          <div className="info-field">
            <label>Employer Name</label>
            <input
              type="text"
              value={formData.employer_name || ''}
              onChange={(e) => onFieldChange('employer_name', e.target.value)}
              placeholder="Company name"
            />
          </div>
          <div className="info-field">
            <label>Job Title</label>
            <input
              type="text"
              value={formData.job_title || ''}
              onChange={(e) => onFieldChange('job_title', e.target.value)}
              placeholder="Position title"
            />
          </div>
          <div className="info-field">
            <label>Annual Income</label>
            <input
              type="number"
              value={formData.annual_income || ''}
              onChange={(e) => onFieldChange('annual_income', parseFloat(e.target.value))}
              placeholder="$"
            />
          </div>
          <div className="info-field">
            <label>Years at Job</label>
            <input
              type="number"
              step="0.1"
              value={formData.years_at_job || ''}
              onChange={(e) => onFieldChange('years_at_job', parseFloat(e.target.value))}
              placeholder="Years"
            />
          </div>
        </div>
      </div>

      {/* SECTION 2: Borrower Opportunity Score */}
      <div className="employment-section">
        <h3>Borrower Opportunity Score</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Leadership Level</label>
            <select
              value={formData.leadership_level || ''}
              onChange={(e) => onFieldChange('leadership_level', e.target.value)}
            >
              <option value="">Select level</option>
              <option value="Executive">Executive</option>
              <option value="Manager">Manager / Supervisor</option>
              <option value="Team Lead">Team Lead</option>
              <option value="Individual Contributor">Individual Contributor</option>
              <option value="Business Owner">Business Owner</option>
            </select>
          </div>
          <div className="info-field">
            <label>Number of Employees Managed</label>
            <input
              type="number"
              value={formData.employees_managed || ''}
              onChange={(e) => onFieldChange('employees_managed', parseInt(e.target.value))}
              placeholder="0"
            />
          </div>
          <div className="info-field">
            <label>Company Size</label>
            <select
              value={formData.company_size || ''}
              onChange={(e) => onFieldChange('company_size', e.target.value)}
            >
              <option value="">Select size</option>
              <option value="1-10">1-10</option>
              <option value="11-50">11-50</option>
              <option value="51-200">51-200</option>
              <option value="200-1000">200-1000</option>
              <option value="1000+">1000+</option>
            </select>
          </div>
          <div className="info-field">
            <label>Influence Score (AI Calculated)</label>
            <input
              type="text"
              value={formData.influence_score || (calculating ? 'Calculating...' : '')}
              disabled
              className="ai-calculated"
            />
          </div>
        </div>
      </div>

      {/* SECTION 3: Referral Potential Indicators */}
      <div className="employment-section">
        <h3>Referral Potential Indicators</h3>
        <div className="info-field full-width">
          <label>Works in Referral-Rich Industry? (AI Detected)</label>
          <div className="radio-group">
            <label className="radio-option">
              <input
                type="radio"
                name="referral_industry"
                value="High"
                checked={formData.referral_industry_flag === 'High'}
                onChange={(e) => onFieldChange('referral_industry_flag', e.target.value)}
              />
              Yes - High referral industry
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="referral_industry"
                value="Medium"
                checked={formData.referral_industry_flag === 'Medium'}
                onChange={(e) => onFieldChange('referral_industry_flag', e.target.value)}
              />
              Maybe - Moderate referral industry
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="referral_industry"
                value="Low"
                checked={formData.referral_industry_flag === 'Low'}
                onChange={(e) => onFieldChange('referral_industry_flag', e.target.value)}
              />
              No - Low referral industry
            </label>
          </div>
          <p className="field-hint">
            High-referral industries: Education, Healthcare, First Responders, Military, HR, Technology, Gig workforce, Real estate adjacent
          </p>
        </div>
      </div>

      {/* SECTION 4: Future Purchase Opportunity Score */}
      <div className="employment-section">
        <h3>Future Purchase Opportunity Score</h3>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Career Stability (AI Based)</label>
            <input
              type="text"
              value={formData.career_stability_score || (calculating ? 'Calculating...' : '')}
              disabled
              className="ai-calculated"
            />
          </div>
          <div className="info-field">
            <label>Likelihood of Future Home Purchase</label>
            <select
              value={formData.future_purchase_likelihood || ''}
              onChange={(e) => onFieldChange('future_purchase_likelihood', e.target.value)}
            >
              <option value="">Select likelihood</option>
              <option value="High">High</option>
              <option value="Medium">Medium</option>
              <option value="Low">Low</option>
            </select>
          </div>
          <div className="info-field">
            <label>Likely Timeline</label>
            <select
              value={formData.future_purchase_timeline || ''}
              onChange={(e) => onFieldChange('future_purchase_timeline', e.target.value)}
            >
              <option value="">Select timeline</option>
              <option value="1 year">1 year</option>
              <option value="2-3 years">2-3 years</option>
              <option value="3-5 years">3-5 years</option>
              <option value="5+ years">5+ years</option>
            </select>
          </div>
        </div>
      </div>

      {/* SECTION 5: Referral Network Mapping */}
      <div className="employment-section">
        <h3>Referral Network Mapping</h3>
        <div className="info-field full-width">
          <label>Does borrower manage or influence potential homebuyers?</label>
          <div className="radio-group">
            <label className="radio-option">
              <input
                type="radio"
                name="manages_buyers"
                value="Yes, directly"
                checked={formData.manages_potential_buyers === 'Yes, directly'}
                onChange={(e) => onFieldChange('manages_potential_buyers', e.target.value)}
              />
              Yes, directly
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="manages_buyers"
                value="Indirectly"
                checked={formData.manages_potential_buyers === 'Indirectly'}
                onChange={(e) => onFieldChange('manages_potential_buyers', e.target.value)}
              />
              Indirectly
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="manages_buyers"
                value="No"
                checked={formData.manages_potential_buyers === 'No'}
                onChange={(e) => onFieldChange('manages_potential_buyers', e.target.value)}
              />
              No
            </label>
          </div>
        </div>
        <div className="info-grid compact">
          <div className="info-field">
            <label>Does their employer hire employees frequently?</label>
            <select
              value={formData.employer_hiring_frequency || ''}
              onChange={(e) => onFieldChange('employer_hiring_frequency', e.target.value)}
            >
              <option value="">Select frequency</option>
              <option value="Yes - high turnover">Yes - high turnover</option>
              <option value="Yes - seasonal">Yes - seasonal</option>
              <option value="Moderate">Moderate</option>
              <option value="Rare">Rare</option>
            </select>
          </div>
        </div>
        <div className="info-field full-width">
          <label>Is borrower comfortable making referrals?</label>
          <div className="radio-group">
            <label className="radio-option">
              <input
                type="radio"
                name="referral_comfort"
                value="Very comfortable"
                checked={formData.referral_comfort_level === 'Very comfortable'}
                onChange={(e) => onFieldChange('referral_comfort_level', e.target.value)}
              />
              Very comfortable
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="referral_comfort"
                value="Somewhat comfortable"
                checked={formData.referral_comfort_level === 'Somewhat comfortable'}
                onChange={(e) => onFieldChange('referral_comfort_level', e.target.value)}
              />
              Somewhat comfortable
            </label>
            <label className="radio-option">
              <input
                type="radio"
                name="referral_comfort"
                value="Not comfortable"
                checked={formData.referral_comfort_level === 'Not comfortable'}
                onChange={(e) => onFieldChange('referral_comfort_level', e.target.value)}
              />
              Not comfortable
            </label>
          </div>
        </div>
      </div>
    </div>
  );
}

import React, { useState, useEffect, useCallback } from 'react';
import './UnifiedIncomeCalculator.css';
import { getToken } from '../../utils/tokenStore';

// Always use production API for deployed builds
const API_BASE = window.location.hostname === 'localhost'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// All 14 income types from the unified calculator
const INCOME_TYPES = [
  {
    id: 'W2_HOURLY',
    label: 'W-2 Hourly',
    icon: '⏰',
    endpoint: '/calculate/w2-hourly',
    description: 'Hourly rate × hours × 52/12',
  },
  {
    id: 'W2_SALARY',
    label: 'W-2 Salary',
    icon: '💼',
    endpoint: '/calculate/w2-salary',
    description: 'Salary with frequency multipliers',
  },
  {
    id: 'OT_BONUS',
    label: 'OT & Bonus',
    icon: '💰',
    endpoint: '/calculate/ot-bonus',
    description: '2-year average of overtime/bonus',
  },
  {
    id: 'COMMISSION',
    label: 'Commission',
    icon: '📊',
    endpoint: '/calculate/commission',
    description: 'Commission minus 2106 expenses',
  },
  {
    id: 'NONTAX_SS',
    label: 'Social Security',
    icon: '🏛️',
    endpoint: '/calculate/nontax-ss',
    description: 'Non-taxable with 25% gross-up',
  },
  {
    id: 'NONTAX_OTHER',
    label: 'Other Non-Tax',
    icon: '📋',
    endpoint: '/calculate/nontax-other',
    description: 'Pension, IRA, child support',
  },
  {
    id: 'BANK_PERSONAL',
    label: 'Bank Stmt Personal',
    icon: '🏦',
    endpoint: '/calculate/bank-statement-personal',
    description: 'Non-QM personal deposits',
  },
  {
    id: 'BANK_BUSINESS',
    label: 'Bank Stmt Business',
    icon: '🏢',
    endpoint: '/calculate/bank-statement-business',
    description: 'Non-QM business deposits',
  },
  {
    id: 'RENTAL_SCHEDULE_E',
    label: 'Rental (Sch E)',
    icon: '🏠',
    endpoint: '/calculate/rental-schedule-e',
    description: 'Schedule E with depreciation add-back',
  },
  {
    id: 'SELF_EMPLOYMENT_1084',
    label: 'Self-Employment (1084)',
    icon: '📑',
    endpoint: '/calculate/self-employment-1084',
    description: 'Schedule C, K-1, 1120',
  },
];

const PAY_FREQUENCIES = [
  { value: 'WEEKLY', label: 'Weekly (×52/12)', multiplier: 4.333 },
  { value: 'BI_WEEKLY', label: 'Bi-Weekly (×26/12)', multiplier: 2.167 },
  { value: 'SEMI_MONTHLY', label: 'Semi-Monthly (×24/12)', multiplier: 2 },
  { value: 'MONTHLY', label: 'Monthly (×1)', multiplier: 1 },
];

export default function UnifiedIncomeCalculator({ loanId, borrowerId, borrowerName, onSave, onClose }) {
  const [activeType, setActiveType] = useState('W2_SALARY');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [reviewQueue, setReviewQueue] = useState([]);
  const [existingSources, setExistingSources] = useState([]);
  const [loadingSources, setLoadingSources] = useState(false);

  // Form state for each income type
  const [formData, setFormData] = useState({
    // W2 Hourly
    hourlyRate: '',
    hoursPerPeriod: '40',
    payFrequency: 'BI_WEEKLY',
    ytdEarnings: '',
    ytdMonths: '',
    w2Year1Earnings: '',
    w2Year2Earnings: '',

    // W2 Salary
    baseSalary: '',
    salaryPayFrequency: 'MONTHLY',
    ytdSalary: '',

    // OT & Bonus
    ytdOTBonus: '',
    otBonusMonths: '',
    year1OTBonus: '',
    year2OTBonus: '',

    // Commission
    ytdCommission: '',
    ytdExpenses2106: '',
    commissionMonths: '',
    year1Commission: '',
    year1Expenses2106: '',
    year2Commission: '',
    year2Expenses2106: '',

    // Social Security
    annualSSBenefit: '',
    taxableSSPortion: '',
    nonTaxableSSPortion: '',
    hasSSDocumentation: false,

    // Other Non-Tax
    otherIncomeType: 'pension',
    otherAnnualAmount: '',
    isOtherTaxable: false,

    // Bank Statement Personal
    personalDeposits: '',
    personalExpenseFactor: '50',

    // Bank Statement Business
    businessDeposits: '',
    businessMethod: '1',
    businessExpenseRatio: '50',
    plNetIncome: '',
    ownershipPercentage: '100',

    // Rental Schedule E
    propertyAddress: '',
    grossRentsLine3: '',
    totalExpensesLine20: '',
    depreciationLine18: '',
    amortizationLine19: '',
    monthlyInsurance: '',
    monthlyMortgageInterest: '',
    monthlyTaxes: '',
    monthlyHOA: '',

    // Self-Employment 1084
    businessName: '',
    businessType: 'sole_prop',
    seOwnershipPct: '100',
    schCNetProfit: '',
    schCDepreciation: '',
    schCMileage: '',
    mileageRate: '0.28',
    k1OrdinaryIncome: '',
    k1GuaranteedPayments: '',
    form1120TaxableIncome: '',
    form1120Tax: '',
    form1120Depreciation: '',
  });

  const token = getToken();

  // Fetch existing income sources from application
  const fetchExistingSources = useCallback(async () => {
    if (!loanId) return;
    setLoadingSources(true);
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/income/loans/${loanId}/sources`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (response.ok) {
        const data = await response.json();
        setExistingSources(data.sources || []);
      }
    } catch (err) {
      console.error('Error fetching existing income sources:', err);
    } finally {
      setLoadingSources(false);
    }
  }, [loanId, token]);

  // Fetch review queue
  const fetchReviewQueue = useCallback(async () => {
    if (!loanId) return;
    try {
      const response = await fetch(
        `${API_BASE}/api/v1/unified-income/review/queue?loan_id=${loanId}`,
        { headers: { 'Authorization': `Bearer ${token}` } }
      );
      if (response.ok) {
        const data = await response.json();
        setReviewQueue(data.items || []);
      }
    } catch (err) {
      console.error('Error fetching review queue:', err);
    }
  }, [loanId, token]);

  useEffect(() => {
    fetchExistingSources();
    fetchReviewQueue();
  }, [fetchExistingSources, fetchReviewQueue]);

  const handleInputChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
    setResult(null);
    setError(null);
  };

  const parseMonthlyDeposits = (text) => {
    // Parse comma-separated or newline-separated numbers
    return text
      .split(/[,\n]+/)
      .map(s => parseFloat(s.trim()))
      .filter(n => !isNaN(n));
  };

  const calculateIncome = async () => {
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const incomeType = INCOME_TYPES.find(t => t.id === activeType);
      if (!incomeType) throw new Error('Invalid income type');

      let requestBody;

      switch (activeType) {
        case 'W2_HOURLY':
          requestBody = {
            hourly_rate: parseFloat(formData.hourlyRate) || 0,
            hours_per_period: parseFloat(formData.hoursPerPeriod) || 40,
            pay_frequency: formData.payFrequency,
            ytd_earnings: formData.ytdEarnings ? parseFloat(formData.ytdEarnings) : null,
            ytd_months: formData.ytdMonths ? parseInt(formData.ytdMonths) : null,
            w2_year1_earnings: formData.w2Year1Earnings ? parseFloat(formData.w2Year1Earnings) : null,
            w2_year2_earnings: formData.w2Year2Earnings ? parseFloat(formData.w2Year2Earnings) : null,
          };
          break;

        case 'W2_SALARY':
          requestBody = {
            base_salary: parseFloat(formData.baseSalary) || 0,
            pay_frequency: formData.salaryPayFrequency,
            ytd_salary: formData.ytdSalary ? parseFloat(formData.ytdSalary) : null,
            ytd_months: formData.ytdMonths ? parseInt(formData.ytdMonths) : null,
            w2_year1_earnings: formData.w2Year1Earnings ? parseFloat(formData.w2Year1Earnings) : null,
            w2_year2_earnings: formData.w2Year2Earnings ? parseFloat(formData.w2Year2Earnings) : null,
          };
          break;

        case 'OT_BONUS':
          requestBody = {
            ytd_ot_bonus: parseFloat(formData.ytdOTBonus) || 0,
            ytd_months: parseInt(formData.otBonusMonths) || 0,
            year1_ot_bonus: formData.year1OTBonus ? parseFloat(formData.year1OTBonus) : null,
            year2_ot_bonus: formData.year2OTBonus ? parseFloat(formData.year2OTBonus) : null,
          };
          break;

        case 'COMMISSION':
          requestBody = {
            ytd_commission: parseFloat(formData.ytdCommission) || 0,
            ytd_expenses_2106: parseFloat(formData.ytdExpenses2106) || 0,
            ytd_months: parseInt(formData.commissionMonths) || 0,
            year1_commission: formData.year1Commission ? parseFloat(formData.year1Commission) : null,
            year1_expenses_2106: parseFloat(formData.year1Expenses2106) || 0,
            year2_commission: formData.year2Commission ? parseFloat(formData.year2Commission) : null,
            year2_expenses_2106: parseFloat(formData.year2Expenses2106) || 0,
          };
          break;

        case 'NONTAX_SS':
          requestBody = {
            annual_benefit: parseFloat(formData.annualSSBenefit) || 0,
            taxable_portion: formData.taxableSSPortion ? parseFloat(formData.taxableSSPortion) : null,
            non_taxable_portion: formData.nonTaxableSSPortion ? parseFloat(formData.nonTaxableSSPortion) : null,
            has_documentation: formData.hasSSDocumentation,
          };
          break;

        case 'NONTAX_OTHER':
          requestBody = {
            income_type: formData.otherIncomeType,
            annual_amount: parseFloat(formData.otherAnnualAmount) || 0,
            is_taxable: formData.isOtherTaxable,
          };
          break;

        case 'BANK_PERSONAL':
          requestBody = {
            monthly_deposits: parseMonthlyDeposits(formData.personalDeposits),
            expense_factor: parseFloat(formData.personalExpenseFactor) || 50,
          };
          break;

        case 'BANK_BUSINESS':
          requestBody = {
            monthly_deposits: parseMonthlyDeposits(formData.businessDeposits),
            method: parseInt(formData.businessMethod),
            expense_ratio: parseFloat(formData.businessExpenseRatio) || 50,
            pl_net_income: formData.plNetIncome ? parseFloat(formData.plNetIncome) : null,
            ownership_percentage: parseFloat(formData.ownershipPercentage) || 100,
          };
          break;

        case 'RENTAL_SCHEDULE_E':
          requestBody = {
            property_address: formData.propertyAddress,
            gross_rents_line3: parseFloat(formData.grossRentsLine3) || 0,
            total_expenses_line20: parseFloat(formData.totalExpensesLine20) || 0,
            depreciation_line18: parseFloat(formData.depreciationLine18) || 0,
            amortization_casualty_line19: parseFloat(formData.amortizationLine19) || 0,
            monthly_insurance: parseFloat(formData.monthlyInsurance) || 0,
            monthly_mortgage_interest: parseFloat(formData.monthlyMortgageInterest) || 0,
            monthly_taxes: parseFloat(formData.monthlyTaxes) || 0,
            monthly_hoa: parseFloat(formData.monthlyHOA) || 0,
          };
          break;

        case 'SELF_EMPLOYMENT_1084':
          requestBody = {
            business_name: formData.businessName,
            business_type: formData.businessType,
            ownership_percentage: parseFloat(formData.seOwnershipPct) || 100,
            schedule_c_net_profit_line31: parseFloat(formData.schCNetProfit) || 0,
            schedule_c_depreciation_line13: parseFloat(formData.schCDepreciation) || 0,
            schedule_c_mileage: parseFloat(formData.schCMileage) || 0,
            mileage_depreciation_rate: parseFloat(formData.mileageRate) || 0.28,
            k1_1065_ordinary_income_line1: parseFloat(formData.k1OrdinaryIncome) || 0,
            k1_1065_guaranteed_payments_line4: parseFloat(formData.k1GuaranteedPayments) || 0,
            form_1120_taxable_income_line30: parseFloat(formData.form1120TaxableIncome) || 0,
            form_1120_total_tax_line31: parseFloat(formData.form1120Tax) || 0,
            form_1120_depreciation_line20: parseFloat(formData.form1120Depreciation) || 0,
          };
          break;

        default:
          throw new Error('Income type not yet implemented');
      }

      const response = await fetch(
        `${API_BASE}/api/v1/unified-income${incomeType.endpoint}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(requestBody),
        }
      );

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Calculation failed');
      }

      const data = await response.json();
      setResult(data);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    if (!amount) return '$0';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(amount);
  };

  const getConfidenceBadgeClass = (score) => {
    if (score >= 98) return 'confidence-auto-approve';
    if (score >= 90) return 'confidence-high';
    if (score >= 80) return 'confidence-medium';
    if (score >= 60) return 'confidence-low';
    return 'confidence-manual';
  };

  // Handle selecting an existing income source to pre-fill the form
  const handleSelectExistingSource = (source) => {
    // Switch to the correct income type tab (use income_type from backend)
    const incomeTypeId = source.income_type || source.income_type_id;
    setActiveType(incomeTypeId);
    setResult(null);
    setError(null);

    // Pre-fill form data based on income type
    const updates = {};
    const monthlyIncome = source.monthly_qualifying_income || source.monthly_income;
    const sourceName = source.source_name || source.employer_name;

    switch (incomeTypeId) {
      case 'W2_SALARY':
        if (monthlyIncome) {
          updates.baseSalary = (monthlyIncome).toFixed(2);
          updates.salaryPayFrequency = 'MONTHLY';
        }
        break;
      case 'W2_HOURLY':
        if (monthlyIncome) {
          // Estimate hourly rate from monthly (assume 40 hrs/week biweekly)
          updates.hourlyRate = (monthlyIncome / 173.33).toFixed(2);
          updates.hoursPerPeriod = '40';
          updates.payFrequency = 'BI_WEEKLY';
        }
        break;
      case 'NONTAX_SS':
        if (monthlyIncome) {
          updates.annualSSBenefit = (monthlyIncome * 12).toFixed(2);
          updates.hasSSDocumentation = false;
        }
        break;
      case 'NONTAX_OTHER':
        if (monthlyIncome) {
          updates.otherAnnualAmount = (monthlyIncome * 12).toFixed(2);
          updates.otherIncomeType = 'pension';
        }
        break;
      case 'SELF_EMPLOYMENT_1084':
        if (monthlyIncome) {
          updates.schCNetProfit = (monthlyIncome * 12).toFixed(2);
          updates.businessType = 'sole_prop';
          updates.seOwnershipPct = '100';
        }
        if (sourceName) {
          updates.businessName = sourceName;
        }
        break;
      case 'RENTAL_SCHEDULE_E':
        if (monthlyIncome) {
          updates.grossRentsLine3 = (monthlyIncome * 12).toFixed(2);
        }
        break;
      default:
        break;
    }

    setFormData(prev => ({ ...prev, ...updates }));
  };

  // Get status badge class
  const getStatusBadgeClass = (status) => {
    switch (status?.toLowerCase()) {
      case 'verified': return 'status-verified';
      case 'pending_verification': return 'status-pending';
      case 'needs_review': return 'status-review';
      default: return 'status-pending';
    }
  };

  // Get status display text
  const getStatusText = (status) => {
    switch (status?.toLowerCase()) {
      case 'verified': return 'Verified';
      case 'pending_verification': return 'Pending';
      case 'needs_review': return 'Needs Review';
      default: return 'Pending';
    }
  };

  const renderW2HourlyForm = () => (
    <div className="uic-form-section">
      <h4>W-2 Hourly Income</h4>
      <p className="form-description">Per Hour × # of hours × 52/12 = Monthly Income</p>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>Hourly Rate ($)</label>
          <input
            type="number"
            value={formData.hourlyRate}
            onChange={e => handleInputChange('hourlyRate', e.target.value)}
            placeholder="e.g., 25.00"
            step="0.01"
          />
        </div>

        <div className="form-field">
          <label>Hours per Period</label>
          <input
            type="number"
            value={formData.hoursPerPeriod}
            onChange={e => handleInputChange('hoursPerPeriod', e.target.value)}
            placeholder="40"
          />
        </div>

        <div className="form-field">
          <label>Pay Frequency</label>
          <select
            value={formData.payFrequency}
            onChange={e => handleInputChange('payFrequency', e.target.value)}
          >
            {PAY_FREQUENCIES.map(f => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="uic-form-divider">
        <span>Historical Data (for averaging)</span>
      </div>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>YTD Earnings ($)</label>
          <input
            type="number"
            value={formData.ytdEarnings}
            onChange={e => handleInputChange('ytdEarnings', e.target.value)}
            placeholder="Optional"
          />
        </div>

        <div className="form-field">
          <label>YTD Months</label>
          <input
            type="number"
            value={formData.ytdMonths}
            onChange={e => handleInputChange('ytdMonths', e.target.value)}
            placeholder="e.g., 6"
            min="1"
            max="12"
          />
        </div>

        <div className="form-field">
          <label>W-2 Year 1 Earnings ($)</label>
          <input
            type="number"
            value={formData.w2Year1Earnings}
            onChange={e => handleInputChange('w2Year1Earnings', e.target.value)}
            placeholder="Optional"
          />
        </div>

        <div className="form-field">
          <label>W-2 Year 2 Earnings ($)</label>
          <input
            type="number"
            value={formData.w2Year2Earnings}
            onChange={e => handleInputChange('w2Year2Earnings', e.target.value)}
            placeholder="Optional"
          />
        </div>
      </div>
    </div>
  );

  const renderW2SalaryForm = () => (
    <div className="uic-form-section">
      <h4>W-2 Salary Income</h4>
      <p className="form-description">Base salary with frequency multipliers</p>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>Base Salary ($)</label>
          <input
            type="number"
            value={formData.baseSalary}
            onChange={e => handleInputChange('baseSalary', e.target.value)}
            placeholder="e.g., 5000"
          />
        </div>

        <div className="form-field">
          <label>Pay Frequency</label>
          <select
            value={formData.salaryPayFrequency}
            onChange={e => handleInputChange('salaryPayFrequency', e.target.value)}
          >
            {PAY_FREQUENCIES.map(f => (
              <option key={f.value} value={f.value}>{f.label}</option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label>YTD Salary ($)</label>
          <input
            type="number"
            value={formData.ytdSalary}
            onChange={e => handleInputChange('ytdSalary', e.target.value)}
            placeholder="Optional"
          />
        </div>
      </div>
    </div>
  );

  const renderOTBonusForm = () => (
    <div className="uic-form-section">
      <h4>Overtime & Bonus Income</h4>
      <p className="form-description">2-year average, uses lowest calculation</p>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>YTD OT/Bonus ($)</label>
          <input
            type="number"
            value={formData.ytdOTBonus}
            onChange={e => handleInputChange('ytdOTBonus', e.target.value)}
            placeholder="e.g., 5000"
          />
        </div>

        <div className="form-field">
          <label>YTD Months</label>
          <input
            type="number"
            value={formData.otBonusMonths}
            onChange={e => handleInputChange('otBonusMonths', e.target.value)}
            placeholder="e.g., 6"
          />
        </div>

        <div className="form-field">
          <label>Year 1 OT/Bonus ($)</label>
          <input
            type="number"
            value={formData.year1OTBonus}
            onChange={e => handleInputChange('year1OTBonus', e.target.value)}
            placeholder="Optional"
          />
        </div>

        <div className="form-field">
          <label>Year 2 OT/Bonus ($)</label>
          <input
            type="number"
            value={formData.year2OTBonus}
            onChange={e => handleInputChange('year2OTBonus', e.target.value)}
            placeholder="Optional"
          />
        </div>
      </div>
    </div>
  );

  const renderCommissionForm = () => (
    <div className="uic-form-section">
      <h4>Commission Income</h4>
      <p className="form-description">Commission minus 2106 unreimbursed expenses</p>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>YTD Commission ($)</label>
          <input
            type="number"
            value={formData.ytdCommission}
            onChange={e => handleInputChange('ytdCommission', e.target.value)}
            placeholder="e.g., 25000"
          />
        </div>

        <div className="form-field">
          <label>YTD 2106 Expenses ($)</label>
          <input
            type="number"
            value={formData.ytdExpenses2106}
            onChange={e => handleInputChange('ytdExpenses2106', e.target.value)}
            placeholder="0"
          />
        </div>

        <div className="form-field">
          <label>YTD Months</label>
          <input
            type="number"
            value={formData.commissionMonths}
            onChange={e => handleInputChange('commissionMonths', e.target.value)}
            placeholder="e.g., 6"
          />
        </div>

        <div className="form-field">
          <label>Year 1 Commission ($)</label>
          <input
            type="number"
            value={formData.year1Commission}
            onChange={e => handleInputChange('year1Commission', e.target.value)}
            placeholder="Optional"
          />
        </div>

        <div className="form-field">
          <label>Year 1 2106 Expenses ($)</label>
          <input
            type="number"
            value={formData.year1Expenses2106}
            onChange={e => handleInputChange('year1Expenses2106', e.target.value)}
            placeholder="0"
          />
        </div>

        <div className="form-field">
          <label>Year 2 Commission ($)</label>
          <input
            type="number"
            value={formData.year2Commission}
            onChange={e => handleInputChange('year2Commission', e.target.value)}
            placeholder="Optional"
          />
        </div>
      </div>
    </div>
  );

  const renderSocialSecurityForm = () => (
    <div className="uic-form-section">
      <h4>Social Security Income</h4>
      <p className="form-description">Non-taxable portion receives 25% gross-up</p>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>Annual Benefit ($)</label>
          <input
            type="number"
            value={formData.annualSSBenefit}
            onChange={e => handleInputChange('annualSSBenefit', e.target.value)}
            placeholder="e.g., 24000"
          />
        </div>

        <div className="form-field checkbox-field">
          <label>
            <input
              type="checkbox"
              checked={formData.hasSSDocumentation}
              onChange={e => handleInputChange('hasSSDocumentation', e.target.checked)}
            />
            Has SSA-1099 Documentation
          </label>
        </div>

        {formData.hasSSDocumentation && (
          <>
            <div className="form-field">
              <label>Taxable Portion ($)</label>
              <input
                type="number"
                value={formData.taxableSSPortion}
                onChange={e => handleInputChange('taxableSSPortion', e.target.value)}
                placeholder="From 1040 Line 5a"
              />
            </div>

            <div className="form-field">
              <label>Non-Taxable Portion ($)</label>
              <input
                type="number"
                value={formData.nonTaxableSSPortion}
                onChange={e => handleInputChange('nonTaxableSSPortion', e.target.value)}
                placeholder="Line 5a - 5b"
              />
            </div>
          </>
        )}
      </div>

      {!formData.hasSSDocumentation && (
        <p className="form-note">
          Without documentation: 85% taxable, 15% non-taxable (25% gross-up on non-taxable)
        </p>
      )}
    </div>
  );

  const renderRentalScheduleEForm = () => (
    <div className="uic-form-section">
      <h4>Rental Income (Schedule E)</h4>
      <p className="form-description">Gross rents - expenses + depreciation add-back - PITIA</p>

      <div className="form-field full-width">
        <label>Property Address</label>
        <input
          type="text"
          value={formData.propertyAddress}
          onChange={e => handleInputChange('propertyAddress', e.target.value)}
          placeholder="123 Main St, City, State"
        />
      </div>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>Gross Rents (Line 3)</label>
          <input
            type="number"
            value={formData.grossRentsLine3}
            onChange={e => handleInputChange('grossRentsLine3', e.target.value)}
            placeholder="Annual gross rents"
          />
        </div>

        <div className="form-field">
          <label>Total Expenses (Line 20)</label>
          <input
            type="number"
            value={formData.totalExpensesLine20}
            onChange={e => handleInputChange('totalExpensesLine20', e.target.value)}
            placeholder="Annual expenses"
          />
        </div>

        <div className="form-field">
          <label>Depreciation (Line 18)</label>
          <input
            type="number"
            value={formData.depreciationLine18}
            onChange={e => handleInputChange('depreciationLine18', e.target.value)}
            placeholder="Add-back amount"
          />
        </div>

        <div className="form-field">
          <label>Amortization (Line 19)</label>
          <input
            type="number"
            value={formData.amortizationLine19}
            onChange={e => handleInputChange('amortizationLine19', e.target.value)}
            placeholder="Add-back amount"
          />
        </div>
      </div>

      <div className="uic-form-divider">
        <span>PITIA (Monthly)</span>
      </div>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>Insurance</label>
          <input
            type="number"
            value={formData.monthlyInsurance}
            onChange={e => handleInputChange('monthlyInsurance', e.target.value)}
            placeholder="0"
          />
        </div>

        <div className="form-field">
          <label>Mortgage Interest</label>
          <input
            type="number"
            value={formData.monthlyMortgageInterest}
            onChange={e => handleInputChange('monthlyMortgageInterest', e.target.value)}
            placeholder="0"
          />
        </div>

        <div className="form-field">
          <label>Taxes</label>
          <input
            type="number"
            value={formData.monthlyTaxes}
            onChange={e => handleInputChange('monthlyTaxes', e.target.value)}
            placeholder="0"
          />
        </div>

        <div className="form-field">
          <label>HOA</label>
          <input
            type="number"
            value={formData.monthlyHOA}
            onChange={e => handleInputChange('monthlyHOA', e.target.value)}
            placeholder="0"
          />
        </div>
      </div>
    </div>
  );

  const renderSelfEmploymentForm = () => (
    <div className="uic-form-section">
      <h4>Self-Employment (Fannie Mae 1084)</h4>
      <p className="form-description">Schedule C, K-1, or 1120 with add-backs</p>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>Business Name</label>
          <input
            type="text"
            value={formData.businessName}
            onChange={e => handleInputChange('businessName', e.target.value)}
            placeholder="Business name"
          />
        </div>

        <div className="form-field">
          <label>Business Type</label>
          <select
            value={formData.businessType}
            onChange={e => handleInputChange('businessType', e.target.value)}
          >
            <option value="sole_prop">Sole Proprietorship (Sch C)</option>
            <option value="partnership">Partnership (K-1 1065)</option>
            <option value="s_corp">S-Corporation (K-1 1120S)</option>
            <option value="c_corp">C-Corporation (1120)</option>
          </select>
        </div>

        <div className="form-field">
          <label>Ownership %</label>
          <input
            type="number"
            value={formData.seOwnershipPct}
            onChange={e => handleInputChange('seOwnershipPct', e.target.value)}
            min="0"
            max="100"
          />
        </div>
      </div>

      {formData.businessType === 'sole_prop' && (
        <>
          <div className="uic-form-divider">
            <span>Schedule C</span>
          </div>
          <div className="uic-form-grid">
            <div className="form-field">
              <label>Net Profit (Line 31)</label>
              <input
                type="number"
                value={formData.schCNetProfit}
                onChange={e => handleInputChange('schCNetProfit', e.target.value)}
              />
            </div>
            <div className="form-field">
              <label>Depreciation (Line 13)</label>
              <input
                type="number"
                value={formData.schCDepreciation}
                onChange={e => handleInputChange('schCDepreciation', e.target.value)}
              />
            </div>
            <div className="form-field">
              <label>Business Miles</label>
              <input
                type="number"
                value={formData.schCMileage}
                onChange={e => handleInputChange('schCMileage', e.target.value)}
              />
            </div>
            <div className="form-field">
              <label>Mileage Rate ($/mi)</label>
              <input
                type="number"
                value={formData.mileageRate}
                onChange={e => handleInputChange('mileageRate', e.target.value)}
                step="0.01"
              />
            </div>
          </div>
        </>
      )}

      {(formData.businessType === 'partnership' || formData.businessType === 's_corp') && (
        <>
          <div className="uic-form-divider">
            <span>K-1 Data</span>
          </div>
          <div className="uic-form-grid">
            <div className="form-field">
              <label>Ordinary Income (Line 1)</label>
              <input
                type="number"
                value={formData.k1OrdinaryIncome}
                onChange={e => handleInputChange('k1OrdinaryIncome', e.target.value)}
              />
            </div>
            {formData.businessType === 'partnership' && (
              <div className="form-field">
                <label>Guaranteed Payments (Line 4)</label>
                <input
                  type="number"
                  value={formData.k1GuaranteedPayments}
                  onChange={e => handleInputChange('k1GuaranteedPayments', e.target.value)}
                />
              </div>
            )}
          </div>
        </>
      )}

      {formData.businessType === 'c_corp' && (
        <>
          <div className="uic-form-divider">
            <span>Form 1120 (requires 100% ownership)</span>
          </div>
          <div className="uic-form-grid">
            <div className="form-field">
              <label>Taxable Income (Line 30)</label>
              <input
                type="number"
                value={formData.form1120TaxableIncome}
                onChange={e => handleInputChange('form1120TaxableIncome', e.target.value)}
              />
            </div>
            <div className="form-field">
              <label>Total Tax (Line 31)</label>
              <input
                type="number"
                value={formData.form1120Tax}
                onChange={e => handleInputChange('form1120Tax', e.target.value)}
              />
            </div>
            <div className="form-field">
              <label>Depreciation (Line 20)</label>
              <input
                type="number"
                value={formData.form1120Depreciation}
                onChange={e => handleInputChange('form1120Depreciation', e.target.value)}
              />
            </div>
          </div>
        </>
      )}
    </div>
  );

  const renderBankStatementForm = () => (
    <div className="uic-form-section">
      <h4>Bank Statement Income (Non-QM)</h4>
      <p className="form-description">Enter 12 or 24 months of deposits (comma-separated)</p>

      <div className="uic-form-grid">
        <div className="form-field full-width">
          <label>Monthly Deposits (comma-separated)</label>
          <textarea
            value={activeType === 'BANK_PERSONAL' ? formData.personalDeposits : formData.businessDeposits}
            onChange={e => handleInputChange(
              activeType === 'BANK_PERSONAL' ? 'personalDeposits' : 'businessDeposits',
              e.target.value
            )}
            placeholder="15000, 16500, 14800, 17200, ..."
            rows={3}
          />
        </div>

        <div className="form-field">
          <label>Expense Factor %</label>
          <input
            type="number"
            value={activeType === 'BANK_PERSONAL' ? formData.personalExpenseFactor : formData.businessExpenseRatio}
            onChange={e => handleInputChange(
              activeType === 'BANK_PERSONAL' ? 'personalExpenseFactor' : 'businessExpenseRatio',
              e.target.value
            )}
            min="0"
            max="100"
          />
        </div>

        {activeType === 'BANK_BUSINESS' && (
          <>
            <div className="form-field">
              <label>Calculation Method</label>
              <select
                value={formData.businessMethod}
                onChange={e => handleInputChange('businessMethod', e.target.value)}
              >
                <option value="1">Method 1: Deposits - Expenses</option>
                <option value="2">Method 2: Expense Ratio</option>
                <option value="3">Method 3: P&L Verification</option>
              </select>
            </div>

            <div className="form-field">
              <label>Ownership %</label>
              <input
                type="number"
                value={formData.ownershipPercentage}
                onChange={e => handleInputChange('ownershipPercentage', e.target.value)}
                min="0"
                max="100"
              />
            </div>

            {formData.businessMethod === '3' && (
              <div className="form-field">
                <label>P&L Net Income (Annual)</label>
                <input
                  type="number"
                  value={formData.plNetIncome}
                  onChange={e => handleInputChange('plNetIncome', e.target.value)}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );

  const renderOtherNonTaxForm = () => (
    <div className="uic-form-section">
      <h4>Other Non-Taxable Income</h4>
      <p className="form-description">Pension, IRA, child support, disability (25% gross-up if non-taxable)</p>

      <div className="uic-form-grid">
        <div className="form-field">
          <label>Income Type</label>
          <select
            value={formData.otherIncomeType}
            onChange={e => handleInputChange('otherIncomeType', e.target.value)}
          >
            <option value="pension">Pension</option>
            <option value="ira">IRA Distribution</option>
            <option value="child_support">Child Support</option>
            <option value="alimony">Alimony</option>
            <option value="disability">Disability</option>
            <option value="other">Other</option>
          </select>
        </div>

        <div className="form-field">
          <label>Annual Amount ($)</label>
          <input
            type="number"
            value={formData.otherAnnualAmount}
            onChange={e => handleInputChange('otherAnnualAmount', e.target.value)}
            placeholder="e.g., 18000"
          />
        </div>

        <div className="form-field checkbox-field">
          <label>
            <input
              type="checkbox"
              checked={formData.isOtherTaxable}
              onChange={e => handleInputChange('isOtherTaxable', e.target.checked)}
            />
            Is Taxable (no gross-up)
          </label>
        </div>
      </div>
    </div>
  );

  const renderActiveForm = () => {
    switch (activeType) {
      case 'W2_HOURLY':
        return renderW2HourlyForm();
      case 'W2_SALARY':
        return renderW2SalaryForm();
      case 'OT_BONUS':
        return renderOTBonusForm();
      case 'COMMISSION':
        return renderCommissionForm();
      case 'NONTAX_SS':
        return renderSocialSecurityForm();
      case 'NONTAX_OTHER':
        return renderOtherNonTaxForm();
      case 'BANK_PERSONAL':
      case 'BANK_BUSINESS':
        return renderBankStatementForm();
      case 'RENTAL_SCHEDULE_E':
        return renderRentalScheduleEForm();
      case 'SELF_EMPLOYMENT_1084':
        return renderSelfEmploymentForm();
      default:
        return <p>Select an income type to begin</p>;
    }
  };

  return (
    <div className="unified-income-calculator">
      {/* Existing Income Sources from Application */}
      {(existingSources.length > 0 || loadingSources) && (
        <div className="uic-existing-sources">
          <div className="existing-sources-header">
            <h4>Income Sources from Application</h4>
            <span className="sources-count">{existingSources.length} source{existingSources.length !== 1 ? 's' : ''}</span>
          </div>

          {loadingSources ? (
            <div className="loading-sources">Loading income sources...</div>
          ) : (
            <div className="existing-sources-grid">
              {existingSources.map((source, idx) => {
                const incomeTypeId = source.income_type || source.income_type_id;
                const incomeType = INCOME_TYPES.find(t => t.id === incomeTypeId);
                const monthlyIncome = source.monthly_qualifying_income || source.monthly_income;
                const sourceName = source.source_name || source.employer_name;
                return (
                  <div
                    key={source.id || idx}
                    className={`existing-source-card ${activeType === incomeTypeId ? 'active' : ''}`}
                    onClick={() => handleSelectExistingSource(source)}
                  >
                    <div className="source-icon">{incomeType?.icon || '💵'}</div>
                    <div className="source-info">
                      <div className="source-type">{incomeType?.label || incomeTypeId}</div>
                      {sourceName && (
                        <div className="source-employer">{sourceName}</div>
                      )}
                      <div className="source-amount">
                        {monthlyIncome ? formatCurrency(monthlyIncome) + '/mo' : 'Needs calculation'}
                      </div>
                    </div>
                    <div className={`source-status ${getStatusBadgeClass(source.verification_status)}`}>
                      {getStatusText(source.verification_status)}
                    </div>
                  </div>
                );
              })}
            </div>
          )}

          <div className="existing-sources-hint">
            Click on a source to pre-fill the calculator and verify the income
          </div>
        </div>
      )}

      {/* Income Type Tabs */}
      <div className="uic-tabs">
        {INCOME_TYPES.map(type => (
          <button
            key={type.id}
            className={`uic-tab ${activeType === type.id ? 'active' : ''}`}
            onClick={() => {
              setActiveType(type.id);
              setResult(null);
              setError(null);
            }}
          >
            <span className="tab-icon">{type.icon}</span>
            <span className="tab-label">{type.label}</span>
          </button>
        ))}
      </div>

      {/* Form Area */}
      <div className="uic-form-container">
        {renderActiveForm()}

        {/* Calculate Button */}
        <div className="uic-actions">
          <button
            className="uic-calculate-btn"
            onClick={calculateIncome}
            disabled={loading}
          >
            {loading ? 'Calculating...' : 'Calculate Income'}
          </button>
        </div>

        {/* Error Display */}
        {error && (
          <div className="uic-error">
            {error}
          </div>
        )}

        {/* Results Display */}
        {result && result.success && (
          <div className="uic-results">
            <div className="results-header">
              <h4>Calculation Results</h4>
              <span className={`confidence-badge ${getConfidenceBadgeClass(result.confidence_score)}`}>
                {result.confidence_score}% Confidence
              </span>
            </div>

            <div className="results-income">
              <div className="income-box">
                <label>Monthly Qualifying Income</label>
                <span className="amount">{formatCurrency(result.monthly_income)}</span>
              </div>
              <div className="income-box">
                <label>Annual Qualifying Income</label>
                <span className="amount">{formatCurrency(result.annual_income)}</span>
              </div>
            </div>

            <div className="results-method">
              <span>Method: {result.calculation_method}</span>
            </div>

            {result.warnings && result.warnings.length > 0 && (
              <div className="results-warnings">
                {result.warnings.map((warning, idx) => (
                  <div key={idx} className="warning-item">{warning}</div>
                ))}
              </div>
            )}

            {/* Calculation Steps */}
            {result.calculation_steps && result.calculation_steps.length > 0 && (
              <div className="results-steps">
                <h5>Calculation Steps</h5>
                {result.calculation_steps.map((step, idx) => (
                  <div key={idx} className="step-item">
                    <span className="step-num">{step.step}.</span>
                    <span className="step-desc">{step.description}</span>
                    <span className="step-result">{formatCurrency(step.result)}</span>
                  </div>
                ))}
              </div>
            )}

            {result.confidence_score >= 98 && (
              <div className="auto-approve-banner">
                Eligible for auto-approval (98%+ confidence)
              </div>
            )}
          </div>
        )}
      </div>

      {/* Review Queue Summary */}
      {reviewQueue.length > 0 && (
        <div className="uic-review-queue">
          <h5>Income Sources for This Loan ({reviewQueue.length})</h5>
          <div className="queue-items">
            {reviewQueue.map(item => (
              <div key={item.id} className={`queue-item status-${item.status.toLowerCase()}`}>
                <span className="item-type">{item.income_type}</span>
                <span className="item-amount">{formatCurrency(item.monthly_income)}/mo</span>
                <span className="item-status">{item.status}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

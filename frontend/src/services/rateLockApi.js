// Use shared api instance for CSRF, auth, and impersonation support
import api from './api';
import { generateMockRecommendation } from './mockRateLockLogic';

// Rate Lock Intelligence - integrated into main CRM backend
const RATE_LOCK_BASE = '/api/v1/rate-lock-intelligence';
const rateLockApi = api;

export const rateLockAPI = {
  // Get quick recommendation with intelligent fallback
  getQuickRecommendation: async (loanData) => {
    // Prepare loan data for mock
    const daysUntilClosing = loanData.daysUntilClosing || calculateDaysUntilClosing(loanData.closingDate || loanData.closing_date);
    const loanAmount = loanData.loanAmount || loanData.amount || 400000;
    const ltv = loanData.ltv || 80;
    const currentRate = loanData.currentRate || loanData.rate || 6.75;
    const fico = loanData.fico || 720;

    const mockInput = {
      loan_amount: loanAmount,
      current_rate: currentRate,
      ltv: ltv,
      fico: fico,
      days_until_closing: daysUntilClosing,
      rate_sensitivity: loanData.rateSensitivity || 'high',
      payment_sensitivity: loanData.paymentSensitivity || 'high',
      certainty_preference: loanData.certaintyPreference || 'high',
    };

    try {
      // Try real API first
      const propertyValue = loanData.propertyValue || loanData.appraisal_value || (loanAmount / (ltv / 100));
      const today = new Date();
      const closeDate = loanData.closingDate || loanData.closing_date
        ? new Date(loanData.closingDate || loanData.closing_date)
        : new Date(today.getTime() + daysUntilClosing * 24 * 60 * 60 * 1000);
      const ctcDate = new Date(closeDate.getTime() - 5 * 24 * 60 * 60 * 1000);

      const scenario = {
        loan_amount: loanAmount,
        property_value: propertyValue,
        ltv: ltv,
        fico: fico,
        dti: loanData.dti || 36,
        purpose: loanData.loanPurpose || loanData.purpose || 'purchase',
        occupancy: loanData.occupancy || 'primary_residence',
        property_type: loanData.propertyType || 'single_family',
        loan_program: loanData.loanProgram || loanData.program || loanData.loan_type || 'conventional_30',
        contract_close_date: closeDate.toISOString().split('T')[0],
        estimated_clear_to_close_date: ctcDate.toISOString().split('T')[0],
        file_status: loanData.fileStatus || 'in_processing',
        conditions_remaining: loanData.conditionsRemaining || 5,
        current_rate: currentRate,
        par_rate: loanData.parRate || (currentRate - 0.125),
        price_at_current_rate: loanData.priceAtCurrentRate || 100.5,
        price_at_par: loanData.priceAtPar || 100.0,
        rate_sheet_timestamp: new Date().toISOString(),
        volatility_indicator: loanData.volatilityIndicator || 'normal',
        recent_price_changes_bps: loanData.recentPriceChangesBps || 5,
        treasury_10yr_yield: loanData.treasury10yrYield || 4.25,
        mbs_current_coupon: loanData.mbsCurrentCoupon || 6.0,
        mbs_price: loanData.mbsPrice || 100.5,
        market_trend: loanData.marketTrend || 'stable',
        available_lock_terms: loanData.availableLockTerms || [15, 30, 45, 60],
        extension_cost_bps_per_15_days: loanData.extensionCostBps || 19,
        relock_policy: loanData.relockPolicy || 'worse_of_two',
        lock_cutoff_time_local: loanData.lockCutoffTime || '15:00',
        lock_desk_open: loanData.lockDeskOpen !== false,
        rate_sensitivity: loanData.rateSensitivity || 'high',
        payment_sensitivity: loanData.paymentSensitivity || 'high',
        certainty_preference: loanData.certaintyPreference || 'high',
      };

      const response = await rateLockApi.post(`${RATE_LOCK_BASE}/v1/recommendations/quick`, { scenario });
      return response.data;
    } catch (error) {
      console.warn('Rate Lock API unavailable, using intelligent mock:', error.message);
      // Fallback to intelligent mock
      return generateMockRecommendation(mockInput);
    }
  },

  // Get current market conditions
  getMarketSnapshot: async () => {
    try {
      const response = await rateLockApi.get(`${RATE_LOCK_BASE}/v1/market/snapshot`);
      return response.data;
    } catch (error) {
      console.warn('Market snapshot failed:', error.message);
      return {
        timestamp: new Date().toISOString(),
        treasury_10yr_yield: 4.25,
        mbs_current_coupon: 5.5,
        mbs_price: 100.5,
        volatility_indicator: 'normal',
        market_trend: 'stable',
        is_mock: true
      };
    }
  },

  // Check service health
  checkHealth: async () => {
    try {
      const response = await rateLockApi.get(`${RATE_LOCK_BASE}/health`);
      return response.data;
    } catch (error) {
      return { status: 'unavailable', error: error.message };
    }
  },
};

// Helper function to calculate days until closing
function calculateDaysUntilClosing(closingDate) {
  if (!closingDate) return 30;

  const closing = new Date(closingDate);
  const today = new Date();
  const diffTime = closing - today;
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  return Math.max(1, diffDays);
}

export default rateLockAPI;

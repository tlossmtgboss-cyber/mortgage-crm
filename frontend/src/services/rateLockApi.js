import axios from 'axios';

// Rate Lock Intelligence Microservice
const RATE_LOCK_API_URL = 'https://rate-lock-intelligence-production.up.railway.app';

// Create separate axios instance for rate lock service
const rateLockApi = axios.create({
  baseURL: RATE_LOCK_API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 10000, // 10 second timeout for AI analysis
});

export const rateLockAPI = {
  // Get quick recommendation (< 100ms)
  getQuickRecommendation: async (loanData) => {
    const response = await rateLockApi.post('/v1/recommendations/quick', {
      loan_amount: loanData.loanAmount || loanData.amount,
      ltv: loanData.ltv || 80,
      fico: loanData.fico || 720,
      current_rate: loanData.currentRate || loanData.rate || 6.75,
      days_until_closing: loanData.daysUntilClosing || calculateDaysUntilClosing(loanData.closingDate),
      loan_purpose: loanData.loanPurpose || 'purchase',
      rate_sensitivity: loanData.rateSensitivity || 'high',
      payment_sensitivity: loanData.paymentSensitivity || 'high',
      certainty_preference: loanData.certaintyPreference || 'high',
    });
    return response.data;
  },

  // Get full AI-powered analysis (2-3 seconds)
  getFullAnalysis: async (loanData) => {
    const response = await rateLockApi.post('/v1/recommendations/analyze', {
      loan_amount: loanData.loanAmount || loanData.amount,
      property_value: loanData.propertyValue || loanData.appraisal_value,
      ltv: loanData.ltv || 80,
      fico: loanData.fico || 720,
      dti: loanData.dti || 36,
      loan_program: loanData.loanProgram || loanData.program || 'Conventional',
      contract_close_date: loanData.closingDate || loanData.closing_date,
      days_until_closing: loanData.daysUntilClosing || calculateDaysUntilClosing(loanData.closingDate || loanData.closing_date),
      current_rate: loanData.currentRate || loanData.rate || 6.75,
      par_rate: loanData.parRate || (loanData.rate ? loanData.rate - 0.125 : 6.625),
      rate_sensitivity: loanData.rateSensitivity || 'high',
      payment_sensitivity: loanData.paymentSensitivity || 'high',
      certainty_preference: loanData.certaintyPreference || 'high',
      loan_purpose: loanData.loanPurpose || 'purchase',
      earnest_money_at_risk: loanData.earnestMoneyAtRisk || 10000,
    });
    return response.data;
  },

  // Get current market conditions
  getMarketSnapshot: async () => {
    const response = await rateLockApi.get('/v1/market/snapshot');
    return response.data;
  },

  // Check service health
  checkHealth: async () => {
    const response = await rateLockApi.get('/health');
    return response.data;
  },
};

// Helper function to calculate days until closing
function calculateDaysUntilClosing(closingDate) {
  if (!closingDate) return 30; // Default to 30 days

  const closing = new Date(closingDate);
  const today = new Date();
  const diffTime = closing - today;
  const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

  return Math.max(1, diffDays); // At least 1 day
}

export default rateLockAPI;

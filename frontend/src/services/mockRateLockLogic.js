/**
 * Mock Rate Lock Recommendation Logic
 *
 * Provides intelligent recommendations based on real decision factors
 * until the backend decision_tree.py is implemented.
 */

/**
 * Generate a realistic rate lock recommendation based on loan data
 */
export function generateMockRecommendation(loanData) {
  const {
    loan_amount = 400000,
    current_rate = 6.75,
    ltv = 80,
    fico = 720,
    days_until_closing = 30,
    rate_sensitivity = 'high',
    payment_sensitivity = 'high',
    certainty_preference = 'high'
  } = loanData;

  // Calculate risk factors
  const timeRisk = calculateTimeRisk(days_until_closing);
  const loanRisk = calculateLoanRisk(ltv, fico);
  const borrowerRisk = calculateBorrowerRisk(rate_sensitivity, payment_sensitivity, certainty_preference);

  // Overall risk score (0-100, higher = more risk = more lock urgency)
  const overallRisk = Math.round((timeRisk * 0.4) + (loanRisk * 0.3) + (borrowerRisk * 0.3));

  // Determine recommendation based on risk score
  let recommendation, urgency, confidence, keyReasons;

  if (overallRisk >= 70) {
    recommendation = 'lock_now';
    urgency = days_until_closing <= 25 ? 'immediate' : 'high';
    confidence = 80 + Math.min(15, Math.floor(overallRisk / 5));
    keyReasons = [
      days_until_closing <= 30
        ? `Only ${days_until_closing} days until closing requires immediate action`
        : 'Time pressure increases extension risk significantly',
      'Locking now protects against potential rate increases',
      ltv >= 80
        ? 'High LTV loans have stricter underwriting - lock to ensure approval'
        : 'Current rate is competitive for this loan profile',
      certainty_preference === 'very_high' || certainty_preference === 'high'
        ? 'Your preference for certainty strongly favors locking'
        : undefined
    ].filter(Boolean).slice(0, 5);

  } else if (overallRisk >= 45) {
    recommendation = 'float_cautious';
    urgency = days_until_closing <= 35 ? 'high' : 'moderate';
    confidence = 70 + Math.floor(overallRisk / 10);
    keyReasons = [
      `${days_until_closing} days to closing provides some flexibility`,
      'Market conditions are relatively stable for cautious floating',
      'Monitor daily for rate changes and be ready to lock',
      'Consider locking if rates worsen by 0.125% or more'
    ].slice(0, 4);

  } else {
    recommendation = overallRisk < 30 ? 'float_aggressive' : 'monitor_only';
    urgency = days_until_closing <= 45 ? 'moderate' : 'low';
    confidence = 65 + Math.floor((50 - overallRisk) / 3);
    keyReasons = [
      `${days_until_closing} days provides ample time to capture rate improvements`,
      'Strong loan profile allows for strategic rate timing',
      'Current market volatility is low to moderate',
      fico >= 740
        ? 'Excellent credit score provides pricing flexibility'
        : 'Good credit position for floating',
      'Set up daily rate monitoring to catch opportunities'
    ].slice(0, 4);
  }

  const extensionRisk = calculateExtensionRisk(days_until_closing, ltv);
  const suggestedLockTerm = calculateSuggestedLockTerm(days_until_closing);

  return {
    recommendation,
    confidence_score: confidence,
    urgency,
    key_reasons: keyReasons,
    suggested_lock_term_days: suggestedLockTerm,
    quantitative_summary: {
      days_to_close: days_until_closing,
      extension_risk_percentage: extensionRisk,
      loan_risk_score: loanRisk,
      market_volatility_score: 5,
      net_expected_value: calculateNetExpectedValue(loan_amount, current_rate, days_until_closing)
    },
    timestamp: new Date().toISOString(),
    is_mock: true
  };
}

function calculateTimeRisk(daysToClose) {
  if (daysToClose <= 20) return 95;
  if (daysToClose <= 25) return 85;
  if (daysToClose <= 30) return 75;
  if (daysToClose <= 35) return 65;
  if (daysToClose <= 40) return 55;
  if (daysToClose <= 45) return 45;
  if (daysToClose <= 55) return 35;
  if (daysToClose <= 65) return 25;
  return 15;
}

function calculateLoanRisk(ltv, fico) {
  let score = 0;

  // LTV component (0-50 points)
  if (ltv >= 95) score += 50;
  else if (ltv >= 90) score += 45;
  else if (ltv >= 85) score += 40;
  else if (ltv >= 80) score += 30;
  else if (ltv >= 75) score += 20;
  else score += 10;

  // FICO component (0-50 points)
  if (fico < 620) score += 50;
  else if (fico < 640) score += 45;
  else if (fico < 660) score += 40;
  else if (fico < 680) score += 30;
  else if (fico < 700) score += 20;
  else if (fico < 740) score += 10;
  else score += 5;

  return Math.min(100, score);
}

function calculateBorrowerRisk(rateSens, paymentSens, certaintyPref) {
  const sensMap = {
    'very_low': 0,
    'low': 20,
    'medium': 40,
    'high': 60,
    'very_high': 80
  };

  const rateScore = sensMap[rateSens] || 40;
  const paymentScore = sensMap[paymentSens] || 40;
  const certaintyScore = sensMap[certaintyPref] || 40;

  return Math.round((rateScore + paymentScore + certaintyScore) / 3);
}

function calculateExtensionRisk(daysToClose, ltv) {
  let baseRisk;

  if (daysToClose <= 20) baseRisk = 60;
  else if (daysToClose <= 25) baseRisk = 45;
  else if (daysToClose <= 30) baseRisk = 30;
  else if (daysToClose <= 35) baseRisk = 20;
  else if (daysToClose <= 40) baseRisk = 15;
  else baseRisk = 10;

  if (ltv >= 90) baseRisk += 10;
  else if (ltv >= 85) baseRisk += 5;

  return Math.min(95, baseRisk);
}

function calculateSuggestedLockTerm(daysToClose) {
  const withBuffer = daysToClose + 7;

  if (withBuffer <= 30) return 30;
  if (withBuffer <= 45) return 45;
  if (withBuffer <= 60) return 60;
  return 75;
}

function calculateNetExpectedValue(loanAmount, currentRate, daysToClose) {
  const timeFactor = (daysToClose - 30) / 30;
  const rateFactor = (7.0 - currentRate) / 7.0;

  return Math.round(loanAmount * 0.001 * timeFactor * rateFactor);
}

export default { generateMockRecommendation };

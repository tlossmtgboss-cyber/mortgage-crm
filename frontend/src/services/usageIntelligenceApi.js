/**
 * Usage Intelligence API Service
 *
 * Provides methods for fetching usage costs, projections, and pricing recommendations.
 * Owner-only access.
 */

import { API_BASE_URL } from './api';
import { getToken } from '../utils/tokenStore';

const API_BASE = API_BASE_URL;

/**
 * Get dashboard overview data with KPIs
 */
export const getDashboardOverview = async () => {
  const response = await fetch(`${API_BASE}/api/v1/usage-intelligence/dashboard`, {
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error('Failed to fetch dashboard data');
  }

  return response.json();
};

/**
 * Get user costs for the specified period
 */
export const getUserCosts = async (days = 30, limit = 50) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/users?days=${days}&limit=${limit}`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch user costs');
  }

  return response.json();
};

/**
 * Get detailed costs for a specific user
 */
export const getUserCostDetail = async (userId, days = 30) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/users/${userId}?days=${days}`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch user detail');
  }

  return response.json();
};

/**
 * Get team costs for the specified period
 */
export const getTeamCosts = async (days = 30) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/teams?days=${days}`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch team costs');
  }

  return response.json();
};

/**
 * Get organization-wide cost summary
 */
export const getOrganizationCosts = async (days = 30) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/organization?days=${days}`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch organization costs');
  }

  return response.json();
};

/**
 * Get organization cost trend for charting
 */
export const getOrganizationTrend = async (days = 30) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/organization/trend?days=${days}`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch cost trend');
  }

  return response.json();
};

/**
 * Get cost projections
 */
export const getProjections = async (scopeType = 'organization', scopeId = null, period = 30) => {
  let url = `${API_BASE}/api/v1/usage-intelligence/projections/${scopeType}?period=${period}`;
  if (scopeId) {
    url += `&scope_id=${scopeId}`;
  }

  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error('Failed to fetch projections');
  }

  return response.json();
};

/**
 * Get pricing recommendations
 */
export const getPricingRecommendation = async (targetMargin = 200, periodDays = 30) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/pricing-calculator?target_margin=${targetMargin}&period_days=${periodDays}`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch pricing recommendation');
  }

  return response.json();
};

/**
 * Simulate custom pricing
 */
export const simulatePricing = async (basePrice, perUserPrice) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/pricing-calculator/simulate?base_price=${basePrice}&per_user_price=${perUserPrice}`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to simulate pricing');
  }

  return response.json();
};

/**
 * Get AI model cost breakdown
 */
export const getAIModelCosts = async (days = 30) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/ai-models?days=${days}`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch AI model costs');
  }

  return response.json();
};

/**
 * Get AI model pricing configuration
 */
export const getAIModelPricing = async () => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/ai-models/pricing`,
    {
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to fetch AI model pricing');
  }

  return response.json();
};

/**
 * Get usage alerts
 */
export const getUsageAlerts = async (status = null, limit = 50) => {
  let url = `${API_BASE}/api/v1/usage-intelligence/alerts?limit=${limit}`;
  if (status) {
    url += `&status=${status}`;
  }

  const response = await fetch(url, {
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json'
    }
  });

  if (!response.ok) {
    throw new Error('Failed to fetch alerts');
  }

  return response.json();
};

/**
 * Acknowledge an alert
 */
export const acknowledgeAlert = async (alertId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/alerts/${alertId}/acknowledge`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to acknowledge alert');
  }

  return response.json();
};

/**
 * Resolve an alert
 */
export const resolveAlert = async (alertId) => {
  const response = await fetch(
    `${API_BASE}/api/v1/usage-intelligence/alerts/${alertId}/resolve`,
    {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getToken()}`,
        'Content-Type': 'application/json'
      }
    }
  );

  if (!response.ok) {
    throw new Error('Failed to resolve alert');
  }

  return response.json();
};

/**
 * Format currency for display
 */
export const formatCurrency = (value) => {
  if (value === null || value === undefined) return '$0.00';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(value);
};

/**
 * Format large numbers with abbreviations
 */
export const formatNumber = (value) => {
  if (value === null || value === undefined) return '0';
  if (value >= 1000000) {
    return (value / 1000000).toFixed(1) + 'M';
  }
  if (value >= 1000) {
    return (value / 1000).toFixed(1) + 'K';
  }
  return value.toLocaleString();
};

/**
 * Format percentage
 */
export const formatPercent = (value) => {
  if (value === null || value === undefined) return '0%';
  return `${value >= 0 ? '+' : ''}${value.toFixed(1)}%`;
};

export default {
  getDashboardOverview,
  getUserCosts,
  getUserCostDetail,
  getTeamCosts,
  getOrganizationCosts,
  getOrganizationTrend,
  getProjections,
  getPricingRecommendation,
  simulatePricing,
  getAIModelCosts,
  getAIModelPricing,
  getUsageAlerts,
  acknowledgeAlert,
  resolveAlert,
  formatCurrency,
  formatNumber,
  formatPercent
};

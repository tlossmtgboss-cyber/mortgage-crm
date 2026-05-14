import { getToken } from '../../../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || '';

// Utility function for API calls
export const fetchWithAuth = async (endpoint) => {
  const response = await fetch(`${API_URL}${endpoint}`, {
    headers: {
      'Authorization': `Bearer ${getToken()}`,
      'Content-Type': 'application/json'
    }
  });
  if (!response.ok) throw new Error('API request failed');
  return response.json();
};

// Format currency
export const formatCurrency = (amount) => {
  if (!amount) return '$0';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0
  }).format(amount);
};

// Format percentage
export const formatPercent = (value) => {
  if (!value) return '0%';
  return `${Math.round(value)}%`;
};

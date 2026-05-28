import { getAuthHeaders } from './auth';
import { toast } from './toast';

const isProduction = typeof window !== 'undefined'
  && window.location.hostname !== 'localhost'
  && window.location.hostname !== '127.0.0.1';
const API_BASE = isProduction
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

export async function clickToDial(phone, { contactName = '', leadId = null, loanId = null } = {}) {
  const cleanPhone = phone.replace(/[^\d+]/g, '');
  const dialNumber = cleanPhone.startsWith('+') ? cleanPhone : `+1${cleanPhone}`;

  const payload = { phone_number: dialNumber, contact_name: contactName };
  if (leadId) payload.lead_id = leadId;
  if (loanId) payload.loan_id = loanId;

  try {
    const response = await fetch(`${API_BASE}/api/v1/dialer/click-to-dial`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || errorData.message || `Call failed (${response.status})`);
    }

    toast.success('Call initiated — your cell will ring first');
    return true;
  } catch (err) {
    toast.error(err.message || 'Failed to initiate call');
    return false;
  }
}

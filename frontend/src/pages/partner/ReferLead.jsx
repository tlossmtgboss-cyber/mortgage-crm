/**
 * ReferLead.jsx
 *
 * Form for partners to refer a new buyer/lead to their loan officer.
 * Submits to POST /api/v1/partner/leads/refer.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  CardContent,
  TextField,
  Button,
  Alert,
  Grid,
  CircularProgress,
  MenuItem,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  Send as SendIcon,
} from '@mui/icons-material';
import { API_BASE_URL } from '../../services/api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PARTNER_SESSION_KEY = 'partner_session';

function getPartnerToken() {
  try {
    const session = JSON.parse(localStorage.getItem(PARTNER_SESSION_KEY) || '{}');
    return session.session_token || null;
  } catch {
    return null;
  }
}

async function partnerFetch(path, options = {}) {
  const token = getPartnerToken();
  if (!token) throw new Error('Not authenticated');
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers || {}),
    },
  });
  if (res.status === 401) {
    localStorage.removeItem(PARTNER_SESSION_KEY);
    window.location.href = '/partner/login';
    throw new Error('Session expired');
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed (${res.status})`);
  }
  return res.json();
}

const LOAN_TYPES = [
  'Conventional',
  'FHA',
  'VA',
  'USDA',
  'Jumbo',
  'Other',
];

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function ReferLead() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    loan_type: '',
    property_address: '',
    estimated_purchase_price: '',
    notes: '',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);

  const handleChange = (e) => {
    setForm((prev) => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!form.first_name.trim() || !form.last_name.trim()) {
      setError('First and last name are required.');
      return;
    }
    if (!form.email.trim() && !form.phone.trim()) {
      setError('At least one of email or phone is required.');
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        first_name: form.first_name.trim(),
        last_name: form.last_name.trim(),
        email: form.email.trim() || null,
        phone: form.phone.trim() || null,
        loan_type: form.loan_type || null,
        property_address: form.property_address.trim() || null,
        estimated_purchase_price: form.estimated_purchase_price.trim() || null,
        notes: form.notes.trim() || null,
      };

      const result = await partnerFetch('/api/v1/partner/leads/refer', {
        method: 'POST',
        body: JSON.stringify(payload),
      });

      setSuccess(`${result.borrower_name} has been referred successfully.`);
      setForm({
        first_name: '',
        last_name: '',
        email: '',
        phone: '',
        loan_type: '',
        property_address: '',
        estimated_purchase_price: '',
        notes: '',
      });
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Box sx={{ p: 3, maxWidth: 700, mx: 'auto' }}>
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate('/partner')}
        sx={{ mb: 2 }}
      >
        Back to Dashboard
      </Button>

      <Typography variant="h5" fontWeight={700} mb={2}>
        Refer a New Buyer
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}
      {success && (
        <Alert severity="success" sx={{ mb: 2 }}>
          {success}
        </Alert>
      )}

      <Card>
        <CardContent>
          <Box component="form" onSubmit={handleSubmit}>
            <Grid container spacing={2}>
              <Grid item xs={12} sm={6}>
                <TextField
                  label="First Name"
                  name="first_name"
                  value={form.first_name}
                  onChange={handleChange}
                  fullWidth
                  required
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  label="Last Name"
                  name="last_name"
                  value={form.last_name}
                  onChange={handleChange}
                  fullWidth
                  required
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  label="Email"
                  name="email"
                  type="email"
                  value={form.email}
                  onChange={handleChange}
                  fullWidth
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  label="Phone"
                  name="phone"
                  value={form.phone}
                  onChange={handleChange}
                  fullWidth
                />
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  select
                  label="Loan Type"
                  name="loan_type"
                  value={form.loan_type}
                  onChange={handleChange}
                  fullWidth
                >
                  <MenuItem value="">
                    <em>Select...</em>
                  </MenuItem>
                  {LOAN_TYPES.map((t) => (
                    <MenuItem key={t} value={t}>
                      {t}
                    </MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid item xs={12} sm={6}>
                <TextField
                  label="Estimated Purchase Price"
                  name="estimated_purchase_price"
                  value={form.estimated_purchase_price}
                  onChange={handleChange}
                  fullWidth
                  placeholder="$400,000"
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  label="Property Address"
                  name="property_address"
                  value={form.property_address}
                  onChange={handleChange}
                  fullWidth
                />
              </Grid>
              <Grid item xs={12}>
                <TextField
                  label="Notes"
                  name="notes"
                  value={form.notes}
                  onChange={handleChange}
                  fullWidth
                  multiline
                  rows={3}
                  placeholder="Any details about the buyer, timeline, or special circumstances..."
                />
              </Grid>
              <Grid item xs={12}>
                <Button
                  type="submit"
                  variant="contained"
                  size="large"
                  startIcon={submitting ? <CircularProgress size={18} /> : <SendIcon />}
                  disabled={submitting}
                  fullWidth
                >
                  {submitting ? 'Submitting...' : 'Submit Referral'}
                </Button>
              </Grid>
            </Grid>
          </Box>
        </CardContent>
      </Card>
    </Box>
  );
}

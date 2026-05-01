/**
 * Assets step — Bank accounts, investments, other assets.
 * URLA Section 2a.
 */
import React, { useCallback } from 'react';
import {
  Box,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Grid,
  Typography,
  Button,
  InputAdornment,
  IconButton,
  Paper,
  FormControlLabel,
  Switch,
} from '@mui/material';
import { Add as AddIcon, Delete as DeleteIcon, KeyboardArrowLeft } from '@mui/icons-material';

const ACCOUNT_TYPES = [
  { value: 'checking', label: 'Checking' },
  { value: 'savings', label: 'Savings' },
  { value: 'money_market', label: 'Money market' },
  { value: 'cd', label: 'Certificate of deposit' },
  { value: 'retirement_401k', label: '401(k)' },
  { value: 'retirement_ira', label: 'IRA' },
  { value: 'brokerage', label: 'Brokerage' },
  { value: 'gift', label: 'Gift funds' },
];

const GIFT_RELATIONSHIPS = [
  { value: 'parent', label: 'Parent' },
  { value: 'spouse', label: 'Spouse / Partner' },
  { value: 'sibling', label: 'Sibling' },
  { value: 'grandparent', label: 'Grandparent' },
  { value: 'other_family', label: 'Other family' },
  { value: 'employer', label: 'Employer' },
  { value: 'other', label: 'Other' },
];

export default function Assets({ section, onChange, onComplete, onBack, isFirstStep }) {
  const data = section?.data || {};
  const accounts = data.accounts || [{}];

  const updateField = useCallback((field, value) => {
    onChange({ ...data, [field]: value });
  }, [data, onChange]);

  const updateAccount = useCallback((idx, key, value) => {
    const next = accounts.map((a, i) => (i === idx ? { ...a, [key]: value } : a));
    onChange({ ...data, accounts: next });
  }, [data, accounts, onChange]);

  const addAccount = useCallback(() => {
    onChange({ ...data, accounts: [...accounts, {}] });
  }, [data, accounts, onChange]);

  const removeAccount = useCallback((idx) => {
    if (accounts.length <= 1) return;
    onChange({ ...data, accounts: accounts.filter((_, i) => i !== idx) });
  }, [data, accounts, onChange]);

  return (
    <Box>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
        Bank, retirement, and brokerage accounts
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Add every account you would like to use for the down payment, closing costs, or as reserves.
      </Typography>

      {accounts.map((acct, idx) => (
        <Paper
          key={idx}
          variant="outlined"
          sx={{ p: 2, mb: 2, position: 'relative' }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="subtitle2">Account {idx + 1}</Typography>
            {accounts.length > 1 && (
              <IconButton
                size="small"
                onClick={() => removeAccount(idx)}
                color="error"
              >
                <DeleteIcon fontSize="small" />
              </IconButton>
            )}
          </Box>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={3}>
              <FormControl fullWidth size="small" required>
                <InputLabel>Type</InputLabel>
                <Select
                  value={acct.type || ''}
                  label="Type"
                  onChange={e => updateAccount(idx, 'type', e.target.value)}
                >
                  {ACCOUNT_TYPES.map(opt => (
                    <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                label="Institution"
                required
                value={acct.institution || ''}
                onChange={e => updateAccount(idx, 'institution', e.target.value)}
                size="small"
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                fullWidth
                label="Last 4 digits"
                value={acct.account_number_last4 || ''}
                onChange={e => updateAccount(idx, 'account_number_last4', e.target.value)}
                size="small"
                inputProps={{ maxLength: 4, inputMode: 'numeric' }}
              />
            </Grid>
            <Grid item xs={6} sm={3}>
              <TextField
                fullWidth
                label="Balance"
                type="number"
                required
                value={acct.balance ?? ''}
                onChange={e =>
                  updateAccount(
                    idx,
                    'balance',
                    e.target.value === '' ? null : Number(e.target.value)
                  )
                }
                size="small"
                InputProps={{
                  startAdornment: <InputAdornment position="start">$</InputAdornment>,
                }}
              />
            </Grid>
          </Grid>
        </Paper>
      ))}

      <Button
        variant="text"
        startIcon={<AddIcon />}
        onClick={addAccount}
        sx={{ mb: 3 }}
      >
        Add another account
      </Button>

      {/* Gift funds */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 2, mb: 2 }}>
        Gift funds
      </Typography>
      <FormControlLabel
        control={
          <Switch
            checked={data.receiving_gift || false}
            onChange={e => updateField('receiving_gift', e.target.checked)}
          />
        }
        label="Are you receiving any gift money for this loan?"
        sx={{ mb: 2 }}
      />

      {data.receiving_gift && (
        <Grid container spacing={2}>
          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth
              label="Gift amount"
              type="number"
              value={data.gift_amount ?? ''}
              onChange={e =>
                updateField(
                  'gift_amount',
                  e.target.value === '' ? null : Number(e.target.value)
                )
              }
              size="small"
              InputProps={{
                startAdornment: <InputAdornment position="start">$</InputAdornment>,
              }}
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            <TextField
              fullWidth
              label="Donor name"
              value={data.gift_donor || ''}
              onChange={e => updateField('gift_donor', e.target.value)}
              size="small"
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            <FormControl fullWidth size="small">
              <InputLabel>Relationship</InputLabel>
              <Select
                value={data.gift_relationship || ''}
                label="Relationship"
                onChange={e => updateField('gift_relationship', e.target.value)}
              >
                {GIFT_RELATIONSHIPS.map(opt => (
                  <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
      )}

      {/* Actions */}
      <Box sx={{ mt: 4, display: 'flex', justifyContent: 'space-between' }}>
        {!isFirstStep && (
          <Button variant="outlined" onClick={onBack} startIcon={<KeyboardArrowLeft />}>
            Back
          </Button>
        )}
        <Button variant="contained" onClick={onComplete} size="large" sx={{ ml: 'auto' }}>
          Save & Continue
        </Button>
      </Box>
    </Box>
  );
}

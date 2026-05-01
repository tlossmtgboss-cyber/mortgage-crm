/**
 * Liabilities step — Existing debts, monthly obligations.
 * URLA Section 2c.
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

const LIABILITY_TYPES = [
  { value: 'credit_card', label: 'Credit card' },
  { value: 'auto_loan', label: 'Auto loan' },
  { value: 'student_loan', label: 'Student loan' },
  { value: 'personal_loan', label: 'Personal loan' },
  { value: 'child_support', label: 'Child support' },
  { value: 'alimony', label: 'Alimony' },
  { value: 'tax_lien', label: 'Tax lien' },
  { value: 'other', label: 'Other' },
];

export default function Liabilities({ section, onChange, onComplete, onBack }) {
  const data = section?.data || {};
  const liabilities = data.liabilities || [{}];

  const updateLiability = useCallback((idx, key, value) => {
    const next = liabilities.map((l, i) => (i === idx ? { ...l, [key]: value } : l));
    onChange({ ...data, liabilities: next });
  }, [data, liabilities, onChange]);

  const addLiability = useCallback(() => {
    onChange({ ...data, liabilities: [...liabilities, {}] });
  }, [data, liabilities, onChange]);

  const removeLiability = useCallback((idx) => {
    if (liabilities.length <= 1) return;
    onChange({ ...data, liabilities: liabilities.filter((_, i) => i !== idx) });
  }, [data, liabilities, onChange]);

  return (
    <Box>
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
        Monthly debts & obligations
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Add credit cards, auto loans, student loans, child support, alimony, and other recurring obligations.
      </Typography>

      {liabilities.map((liab, idx) => (
        <Paper
          key={idx}
          variant="outlined"
          sx={{ p: 2, mb: 2 }}
        >
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 1 }}>
            <Typography variant="subtitle2">Debt {idx + 1}</Typography>
            {liabilities.length > 1 && (
              <IconButton
                size="small"
                onClick={() => removeLiability(idx)}
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
                  value={liab.type || ''}
                  label="Type"
                  onChange={e => updateLiability(idx, 'type', e.target.value)}
                >
                  {LIABILITY_TYPES.map(opt => (
                    <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            <Grid item xs={12} sm={3}>
              <TextField
                fullWidth
                label="Creditor"
                required
                value={liab.creditor || ''}
                onChange={e => updateLiability(idx, 'creditor', e.target.value)}
                size="small"
              />
            </Grid>
            <Grid item xs={6} sm={2}>
              <TextField
                fullWidth
                label="Balance"
                type="number"
                value={liab.balance ?? ''}
                onChange={e =>
                  updateLiability(
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
            <Grid item xs={6} sm={2}>
              <TextField
                fullWidth
                label="Monthly pmt"
                type="number"
                required
                value={liab.monthly_payment ?? ''}
                onChange={e =>
                  updateLiability(
                    idx,
                    'monthly_payment',
                    e.target.value === '' ? null : Number(e.target.value)
                  )
                }
                size="small"
                InputProps={{
                  startAdornment: <InputAdornment position="start">$</InputAdornment>,
                }}
              />
            </Grid>
            <Grid item xs={12} sm={2}>
              <FormControlLabel
                control={
                  <Switch
                    checked={liab.pay_off_at_close || false}
                    onChange={e => updateLiability(idx, 'pay_off_at_close', e.target.checked)}
                    size="small"
                  />
                }
                label="Pay off at close?"
                sx={{ mt: 0.5 }}
              />
            </Grid>
          </Grid>
        </Paper>
      ))}

      <Button
        variant="text"
        startIcon={<AddIcon />}
        onClick={addLiability}
        sx={{ mb: 3 }}
      >
        Add another debt
      </Button>

      {/* Actions */}
      <Box sx={{ mt: 4, display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="outlined" onClick={onBack} startIcon={<KeyboardArrowLeft />}>
          Back
        </Button>
        <Button variant="contained" onClick={onComplete} size="large">
          Save & Continue
        </Button>
      </Box>
    </Box>
  );
}

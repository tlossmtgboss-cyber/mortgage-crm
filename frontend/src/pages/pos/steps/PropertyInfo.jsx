/**
 * PropertyInfo step — Subject property, loan purpose, down payment.
 * URLA Sections 3-4.
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
  Divider,
  Button,
  InputAdornment,
} from '@mui/material';
import { KeyboardArrowLeft } from '@mui/icons-material';

const LOAN_PURPOSES = [
  { value: 'purchase', label: 'Purchase' },
  { value: 'refinance', label: 'Refinance' },
  { value: 'cash_out_refi', label: 'Cash-out refinance' },
  { value: 'construction', label: 'Construction' },
];

const LOAN_TYPES = [
  { value: 'conventional', label: 'Conventional' },
  { value: 'fha', label: 'FHA' },
  { value: 'va', label: 'VA' },
  { value: 'usda', label: 'USDA' },
  { value: 'jumbo', label: 'Jumbo' },
];

const PROPERTY_TYPES = [
  { value: 'sfr', label: 'Single-family' },
  { value: 'condo', label: 'Condo' },
  { value: 'townhouse', label: 'Townhouse' },
  { value: 'multi_2_4', label: '2-4 units' },
  { value: 'manufactured', label: 'Manufactured home' },
];

const OCCUPANCY_OPTIONS = [
  { value: 'primary', label: 'Primary residence' },
  { value: 'second_home', label: 'Second home' },
  { value: 'investment', label: 'Investment property' },
];

export default function PropertyInfo({ section, onChange, onComplete, onBack }) {
  const data = section?.data || {};
  const property = data.property || {};

  const updateField = useCallback((field, value) => {
    onChange({ ...data, [field]: value });
  }, [data, onChange]);

  const updateProperty = useCallback((key, value) => {
    onChange({
      ...data,
      property: { ...property, [key]: value },
    });
  }, [data, property, onChange]);

  return (
    <Box>
      {/* Loan info */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        What kind of loan are you applying for?
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={4}>
          <FormControl fullWidth size="small" required>
            <InputLabel>Loan purpose</InputLabel>
            <Select
              value={data.loan_purpose || ''}
              label="Loan purpose"
              onChange={e => updateField('loan_purpose', e.target.value)}
            >
              {LOAN_PURPOSES.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} sm={4}>
          <FormControl fullWidth size="small" required>
            <InputLabel>Loan type</InputLabel>
            <Select
              value={data.loan_type || ''}
              label="Loan type"
              onChange={e => updateField('loan_type', e.target.value)}
            >
              {LOAN_TYPES.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Requested loan amount"
            type="number"
            required
            value={data.loan_amount ?? ''}
            onChange={e =>
              updateField(
                'loan_amount',
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

      <Divider sx={{ my: 3 }} />

      {/* Subject property */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        The property
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <TextField
            fullWidth
            label="Property address"
            required
            value={property.address || ''}
            onChange={e => updateProperty('address', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <FormControl fullWidth size="small" required>
            <InputLabel>Property type</InputLabel>
            <Select
              value={property.type || ''}
              label="Property type"
              onChange={e => updateProperty('type', e.target.value)}
            >
              {PROPERTY_TYPES.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} sm={4}>
          <FormControl fullWidth size="small" required>
            <InputLabel>Occupancy</InputLabel>
            <Select
              value={property.occupancy || ''}
              label="Occupancy"
              onChange={e => updateProperty('occupancy', e.target.value)}
            >
              {OCCUPANCY_OPTIONS.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Purchase price / Est. value"
            type="number"
            required
            value={property.value ?? ''}
            onChange={e =>
              updateProperty(
                'value',
                e.target.value === '' ? null : Number(e.target.value)
              )
            }
            size="small"
            InputProps={{
              startAdornment: <InputAdornment position="start">$</InputAdornment>,
            }}
          />
        </Grid>
        <Grid item xs={6} sm={3}>
          <TextField
            fullWidth
            label="Year built"
            type="number"
            value={property.year_built ?? ''}
            onChange={e =>
              updateProperty(
                'year_built',
                e.target.value === '' ? null : Number(e.target.value)
              )
            }
            size="small"
          />
        </Grid>
      </Grid>

      <Divider sx={{ my: 3 }} />

      {/* Down payment */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        Down payment
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Down payment amount"
            type="number"
            value={data.down_payment ?? ''}
            onChange={e =>
              updateField(
                'down_payment',
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
          <FormControl fullWidth size="small">
            <InputLabel>Source of down payment</InputLabel>
            <Select
              value={data.down_payment_source || ''}
              label="Source of down payment"
              onChange={e => updateField('down_payment_source', e.target.value)}
            >
              <MenuItem value="savings">Savings</MenuItem>
              <MenuItem value="gift">Gift</MenuItem>
              <MenuItem value="sale_of_property">Sale of property</MenuItem>
              <MenuItem value="retirement">Retirement funds</MenuItem>
              <MenuItem value="other">Other</MenuItem>
            </Select>
          </FormControl>
        </Grid>
      </Grid>

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

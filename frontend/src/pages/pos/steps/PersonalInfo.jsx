/**
 * PersonalInfo step — Name, DOB, SSN, contact, citizenship, housing.
 *
 * Wraps the existing PersonalPanel and ResidencePanel from features/pos
 * with Material UI styling. Auto-saves on blur/change via the parent's
 * onChange callback (debounced 800ms in usePOSApplication).
 */
import React, { useState, useCallback } from 'react';
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
  FormHelperText,
  Alert,
} from '@mui/material';

const MARITAL_OPTIONS = [
  { value: 'married', label: 'Married' },
  { value: 'single', label: 'Single' },
  { value: 'separated', label: 'Separated' },
  { value: 'unmarried', label: 'Unmarried (widowed/divorced)' },
];

const CITIZENSHIP_OPTIONS = [
  { value: 'us_citizen', label: 'U.S. Citizen' },
  { value: 'permanent_resident', label: 'Permanent Resident Alien' },
  { value: 'non_permanent_resident', label: 'Non-Permanent Resident Alien' },
];

const HOUSING_OPTIONS = [
  { value: 'own', label: 'Own' },
  { value: 'rent', label: 'Rent' },
  { value: 'no_charge', label: 'Living rent-free' },
];

export default function PersonalInfo({
  section,
  application,
  onChange,
  onComplete,
  isFirstStep,
}) {
  const data = section?.data || {};
  const [ssn, setSSN] = useState('');
  const [dob, setDOB] = useState('');

  const updateField = useCallback((field, value) => {
    onChange({ ...data, [field]: value });
  }, [data, onChange]);

  const updateNested = useCallback((parent, child, value) => {
    const parentData = data[parent] || {};
    onChange({
      ...data,
      [parent]: { ...parentData, [child]: value },
    });
  }, [data, onChange]);

  return (
    <Box>
      {/* Name */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        Tell us about yourself
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="First name"
            required
            value={data.first_name || ''}
            onChange={e => updateField('first_name', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Middle name"
            value={data.middle_name || ''}
            onChange={e => updateField('middle_name', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Last name"
            required
            value={data.last_name || ''}
            onChange={e => updateField('last_name', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={3}>
          <FormControl fullWidth size="small">
            <InputLabel>Suffix</InputLabel>
            <Select
              value={data.suffix || ''}
              label="Suffix"
              onChange={e => updateField('suffix', e.target.value)}
            >
              <MenuItem value="">None</MenuItem>
              <MenuItem value="Jr">Jr.</MenuItem>
              <MenuItem value="Sr">Sr.</MenuItem>
              <MenuItem value="II">II</MenuItem>
              <MenuItem value="III">III</MenuItem>
            </Select>
          </FormControl>
        </Grid>
      </Grid>

      {/* Contact */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 3, mb: 2 }}>
        Contact information
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="Email"
            type="email"
            required
            value={data.email || ''}
            onChange={e => updateField('email', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="Phone"
            type="tel"
            required
            value={data.phone || ''}
            onChange={e => updateField('phone', e.target.value)}
            size="small"
          />
        </Grid>
      </Grid>

      {/* Identity */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 3, mb: 1 }}>
        Identity
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        This information is encrypted at rest and never shared without your consent.
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="Social Security Number"
            required
            value={ssn}
            onChange={e => setSSN(e.target.value)}
            placeholder="XXX-XX-XXXX"
            inputProps={{ inputMode: 'numeric' }}
            size="small"
            helperText={
              application?.has_ssn
                ? 'Already on file - leave blank to keep'
                : undefined
            }
          />
        </Grid>
        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="Date of birth"
            type="date"
            required
            value={dob}
            onChange={e => setDOB(e.target.value)}
            InputLabelProps={{ shrink: true }}
            size="small"
            helperText={
              application?.has_dob
                ? 'Already on file - leave blank to keep'
                : undefined
            }
          />
        </Grid>
      </Grid>

      {/* Citizenship */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 3, mb: 2 }}>
        Citizenship
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6}>
          <FormControl fullWidth size="small">
            <InputLabel>Citizenship status</InputLabel>
            <Select
              value={data.citizenship_status || ''}
              label="Citizenship status"
              onChange={e => updateField('citizenship_status', e.target.value)}
            >
              {CITIZENSHIP_OPTIONS.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
      </Grid>

      {/* Marital & Dependents */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 3, mb: 2 }}>
        Marital status & dependents
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6}>
          <FormControl fullWidth size="small" required>
            <InputLabel>Marital status</InputLabel>
            <Select
              value={data.marital_status || ''}
              label="Marital status"
              onChange={e => updateField('marital_status', e.target.value)}
            >
              {MARITAL_OPTIONS.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} sm={3}>
          <TextField
            fullWidth
            label="Dependents"
            type="number"
            value={data.dependents_count ?? ''}
            onChange={e =>
              updateField(
                'dependents_count',
                e.target.value === '' ? null : Number(e.target.value)
              )
            }
            size="small"
            inputProps={{ min: 0, max: 20 }}
          />
        </Grid>
      </Grid>

      <Divider sx={{ my: 3 }} />

      {/* Current housing */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        Current address
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12}>
          <TextField
            fullWidth
            label="Street address"
            required
            value={data.current?.street || ''}
            onChange={e => updateNested('current', 'street', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="City"
            required
            value={data.current?.city || ''}
            onChange={e => updateNested('current', 'city', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="State"
            required
            value={data.current?.state || ''}
            onChange={e => updateNested('current', 'state', e.target.value)}
            size="small"
            inputProps={{ maxLength: 2 }}
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="ZIP code"
            required
            value={data.current?.zip || ''}
            onChange={e => updateNested('current', 'zip', e.target.value)}
            size="small"
            inputProps={{ inputMode: 'numeric', maxLength: 10 }}
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <FormControl fullWidth size="small">
            <InputLabel>Housing</InputLabel>
            <Select
              value={data.current?.housing_status || ''}
              label="Housing"
              onChange={e => updateNested('current', 'housing_status', e.target.value)}
            >
              {HOUSING_OPTIONS.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="Years at address"
            type="number"
            value={data.current?.years_at_address ?? ''}
            onChange={e =>
              updateNested(
                'current',
                'years_at_address',
                e.target.value === '' ? null : Number(e.target.value)
              )
            }
            size="small"
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="Monthly cost"
            type="number"
            value={data.current?.monthly_cost ?? ''}
            onChange={e =>
              updateNested(
                'current',
                'monthly_cost',
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

      {/* Action */}
      <Box sx={{ mt: 4, display: 'flex', justifyContent: 'flex-end' }}>
        <Button variant="contained" onClick={onComplete} size="large">
          Save & Continue
        </Button>
      </Box>
    </Box>
  );
}

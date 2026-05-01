/**
 * Employment step — Current + previous employers, income.
 * URLA Section 1e.
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
  FormControlLabel,
  Switch,
} from '@mui/material';
import { KeyboardArrowLeft } from '@mui/icons-material';

const EMPLOYMENT_TYPES = [
  { value: 'employee', label: 'W-2 Employee' },
  { value: 'self_employed', label: 'Self-employed' },
  { value: 'contractor', label: '1099 Contractor' },
  { value: 'retired', label: 'Retired' },
  { value: 'military', label: 'Military' },
  { value: 'other', label: 'Other' },
];

export default function Employment({ section, onChange, onComplete, onBack, isFirstStep }) {
  const data = section?.data || {};

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

  const employer = data.employer || {};
  const income = data.income || {};

  return (
    <Box>
      {/* Employment type */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        Current employment
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6}>
          <FormControl fullWidth size="small" required>
            <InputLabel>Employment type</InputLabel>
            <Select
              value={data.employment_type || ''}
              label="Employment type"
              onChange={e => updateField('employment_type', e.target.value)}
            >
              {EMPLOYMENT_TYPES.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>
        <Grid item xs={12} sm={6}>
          <TextField
            fullWidth
            label="Years in profession"
            type="number"
            value={data.years_in_profession ?? ''}
            onChange={e =>
              updateField(
                'years_in_profession',
                e.target.value === '' ? null : Number(e.target.value)
              )
            }
            size="small"
            inputProps={{ min: 0 }}
          />
        </Grid>
      </Grid>

      {/* Employer details */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mt: 3, mb: 2 }}>
        Employer details
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={8}>
          <TextField
            fullWidth
            label="Employer name"
            required
            value={employer.name || ''}
            onChange={e => updateNested('employer', 'name', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Position / Job title"
            required
            value={employer.position || ''}
            onChange={e => updateNested('employer', 'position', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Start date"
            type="date"
            required
            value={employer.start_date || ''}
            onChange={e => updateNested('employer', 'start_date', e.target.value)}
            InputLabelProps={{ shrink: true }}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Employer phone"
            type="tel"
            value={employer.phone || ''}
            onChange={e => updateNested('employer', 'phone', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <FormControlLabel
            control={
              <Switch
                checked={employer.is_self_employed || false}
                onChange={e => updateNested('employer', 'is_self_employed', e.target.checked)}
              />
            }
            label="Self-employed?"
          />
        </Grid>
      </Grid>

      {/* Employer address */}
      <Grid container spacing={2} sx={{ mt: 1 }}>
        <Grid item xs={12}>
          <TextField
            fullWidth
            label="Employer address"
            value={employer.street || ''}
            onChange={e => updateNested('employer', 'street', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="City"
            value={employer.city || ''}
            onChange={e => updateNested('employer', 'city', e.target.value)}
            size="small"
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="State"
            value={employer.state || ''}
            onChange={e => updateNested('employer', 'state', e.target.value)}
            size="small"
            inputProps={{ maxLength: 2 }}
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="ZIP"
            value={employer.zip || ''}
            onChange={e => updateNested('employer', 'zip', e.target.value)}
            size="small"
          />
        </Grid>
      </Grid>

      <Divider sx={{ my: 3 }} />

      {/* Monthly income */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
        Monthly income
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Enter gross monthly amounts before taxes.
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={4}>
          <TextField
            fullWidth
            label="Base income"
            type="number"
            required
            value={income.base ?? ''}
            onChange={e =>
              updateNested('income', 'base', e.target.value === '' ? null : Number(e.target.value))
            }
            size="small"
            InputProps={{
              startAdornment: <InputAdornment position="start">$</InputAdornment>,
            }}
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="Overtime"
            type="number"
            value={income.overtime ?? ''}
            onChange={e =>
              updateNested('income', 'overtime', e.target.value === '' ? null : Number(e.target.value))
            }
            size="small"
            InputProps={{
              startAdornment: <InputAdornment position="start">$</InputAdornment>,
            }}
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="Bonus"
            type="number"
            value={income.bonus ?? ''}
            onChange={e =>
              updateNested('income', 'bonus', e.target.value === '' ? null : Number(e.target.value))
            }
            size="small"
            InputProps={{
              startAdornment: <InputAdornment position="start">$</InputAdornment>,
            }}
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="Commission"
            type="number"
            value={income.commission ?? ''}
            onChange={e =>
              updateNested('income', 'commission', e.target.value === '' ? null : Number(e.target.value))
            }
            size="small"
            InputProps={{
              startAdornment: <InputAdornment position="start">$</InputAdornment>,
            }}
          />
        </Grid>
        <Grid item xs={6} sm={4}>
          <TextField
            fullWidth
            label="Other income"
            type="number"
            value={income.other ?? ''}
            onChange={e =>
              updateNested('income', 'other', e.target.value === '' ? null : Number(e.target.value))
            }
            size="small"
            InputProps={{
              startAdornment: <InputAdornment position="start">$</InputAdornment>,
            }}
            helperText="Military allowances, etc."
          />
        </Grid>
      </Grid>

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

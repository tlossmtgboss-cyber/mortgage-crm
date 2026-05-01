/**
 * Declarations step — URLA Section 5 yes/no questions + Demographics (Section 8).
 *
 * Every "yes" potentially triggers an underwriting condition or document
 * request. Demographics are voluntary per ECOA.
 */
import React, { useCallback } from 'react';
import {
  Box,
  Typography,
  Button,
  Divider,
  FormControl,
  FormLabel,
  RadioGroup,
  Radio,
  FormControlLabel,
  Grid,
  Select,
  MenuItem,
  InputLabel,
  Checkbox,
  FormGroup,
  Alert,
} from '@mui/material';
import { KeyboardArrowLeft } from '@mui/icons-material';

const DECLARATION_QUESTIONS = [
  {
    key: 'will_occupy_as_primary',
    label: 'Will you occupy the property as your primary residence?',
  },
  {
    key: 'has_recent_ownership',
    label: 'Have you had an ownership interest in another property in the last 3 years?',
  },
  {
    key: 'other_mortgage_on_property',
    label: 'Are you taking out any other loan or mortgage on this property?',
  },
  {
    key: 'borrowed_down_payment',
    label: 'Will any portion of the down payment be borrowed?',
  },
  {
    key: 'cosigner_on_other_loans',
    label: 'Are you a co-signer or guarantor on any other loans?',
  },
  {
    key: 'outstanding_judgments',
    label: 'Are there any outstanding judgments against you?',
  },
  {
    key: 'bankruptcy_7_years',
    label: 'Have you been declared bankrupt within the past 7 years?',
  },
  {
    key: 'foreclosure_7_years',
    label: 'Have you had property foreclosed on in the last 7 years?',
  },
  {
    key: 'party_to_lawsuit',
    label: 'Are you a party to a lawsuit?',
  },
  {
    key: 'federal_debt_delinquent',
    label: 'Are you currently delinquent on any federal debt (e.g., student loans, taxes)?',
  },
  {
    key: 'us_citizen',
    label: 'Are you a U.S. citizen?',
  },
  {
    key: 'permanent_resident',
    label: 'Are you a permanent resident alien?',
  },
];

const ETHNICITY_OPTIONS = [
  { value: 'hispanic_or_latino', label: 'Hispanic or Latino' },
  { value: 'not_hispanic_or_latino', label: 'Not Hispanic or Latino' },
  { value: 'prefer_not_to_say', label: 'I do not wish to provide' },
];

const RACE_OPTIONS = [
  { value: 'american_indian', label: 'American Indian or Alaska Native' },
  { value: 'asian', label: 'Asian' },
  { value: 'black', label: 'Black or African American' },
  { value: 'pacific_islander', label: 'Native Hawaiian or Other Pacific Islander' },
  { value: 'white', label: 'White' },
  { value: 'prefer_not_to_say', label: 'I do not wish to provide' },
];

const SEX_OPTIONS = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'prefer_not_to_say', label: 'I do not wish to provide' },
];

export default function Declarations({ section, onChange, onComplete, onBack }) {
  const data = section?.data || {};

  const updateField = useCallback((field, value) => {
    onChange({ ...data, [field]: value });
  }, [data, onChange]);

  const toggleRace = useCallback((raceValue) => {
    const current = data.race || [];
    if (current.includes(raceValue)) {
      onChange({ ...data, race: current.filter(r => r !== raceValue) });
    } else {
      onChange({ ...data, race: [...current, raceValue] });
    }
  }, [data, onChange]);

  return (
    <Box>
      {/* Declarations */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
        About the property and your finances
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        A few standard questions required by the URLA. Answer accurately —
        discrepancies discovered later can delay or jeopardize your loan.
      </Typography>

      {DECLARATION_QUESTIONS.map(q => (
        <Box key={q.key} sx={{ mb: 2 }}>
          <FormControl component="fieldset">
            <FormLabel sx={{ fontSize: '0.875rem', color: 'text.primary', mb: 0.5 }}>
              {q.label}
            </FormLabel>
            <RadioGroup
              row
              value={
                data[q.key] === true ? 'yes' : data[q.key] === false ? 'no' : ''
              }
              onChange={e => updateField(q.key, e.target.value === 'yes')}
            >
              <FormControlLabel value="yes" control={<Radio size="small" />} label="Yes" />
              <FormControlLabel value="no" control={<Radio size="small" />} label="No" />
            </RadioGroup>
          </FormControl>
        </Box>
      ))}

      <Divider sx={{ my: 4 }} />

      {/* Demographics — URLA Section 8 (voluntary) */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
        Demographics
      </Typography>
      <Alert severity="info" variant="outlined" sx={{ mb: 3 }}>
        The following information is requested by the federal government to
        monitor compliance with equal credit opportunity and fair lending laws.
        You are not required to provide this information, and it will not affect
        your application.
      </Alert>

      <Grid container spacing={3}>
        {/* Ethnicity */}
        <Grid item xs={12} sm={4}>
          <FormControl fullWidth size="small">
            <InputLabel>Ethnicity</InputLabel>
            <Select
              value={data.ethnicity || ''}
              label="Ethnicity"
              onChange={e => updateField('ethnicity', e.target.value)}
            >
              <MenuItem value="">Select...</MenuItem>
              {ETHNICITY_OPTIONS.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>

        {/* Sex */}
        <Grid item xs={12} sm={4}>
          <FormControl fullWidth size="small">
            <InputLabel>Sex</InputLabel>
            <Select
              value={data.sex || ''}
              label="Sex"
              onChange={e => updateField('sex', e.target.value)}
            >
              <MenuItem value="">Select...</MenuItem>
              {SEX_OPTIONS.map(opt => (
                <MenuItem key={opt.value} value={opt.value}>{opt.label}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Grid>

        {/* Race (multi-select via checkboxes) */}
        <Grid item xs={12}>
          <FormControl component="fieldset">
            <FormLabel sx={{ fontSize: '0.875rem', mb: 1 }}>
              Race (select all that apply)
            </FormLabel>
            <FormGroup row>
              {RACE_OPTIONS.map(opt => (
                <FormControlLabel
                  key={opt.value}
                  control={
                    <Checkbox
                      checked={(data.race || []).includes(opt.value)}
                      onChange={() => toggleRace(opt.value)}
                      size="small"
                    />
                  }
                  label={opt.label}
                />
              ))}
            </FormGroup>
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

/**
 * ReviewSubmit step — Review all sections and submit the application.
 *
 * Shows:
 *   1. Section-by-section completion recap
 *   2. Three required certifications (truth, eSign, credit auth)
 *   3. Submit button (disabled until all sections complete + all certs checked)
 *   4. Confirmation view after successful submission
 */
import React, { useState, useMemo } from 'react';
import {
  Box,
  Typography,
  Button,
  Divider,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Checkbox,
  FormControlLabel,
  Alert,
  Paper,
  CircularProgress,
  Chip,
} from '@mui/material';
import {
  CheckCircle as CheckIcon,
  RadioButtonUnchecked as PendingIcon,
  KeyboardArrowLeft,
  Send as SendIcon,
} from '@mui/icons-material';

const SECTION_NAMES = {
  personal: 'Personal Information',
  residence: 'Residence History',
  employment: 'Employment & Income',
  assets: 'Assets',
  liabilities: 'Liabilities',
  reo: 'Real Estate Owned',
  loan: 'Loan & Property',
  declarations: 'Declarations & Demographics',
};

const CERTIFICATIONS = [
  {
    key: 'truth_certification',
    title: 'Truth certification',
    description:
      'I certify that the information provided is true and complete to the ' +
      'best of my knowledge. I understand that knowingly making false statements ' +
      'on this application is a federal offense.',
  },
  {
    key: 'esign_consent',
    title: 'Electronic signature consent',
    description:
      'I consent to use electronic records and signatures for this application ' +
      'and acknowledge that my electronic signature has the same legal effect as ' +
      'a handwritten one.',
  },
  {
    key: 'credit_authorization',
    title: 'Credit authorization',
    description:
      'I authorize Perennia and its lending partners to obtain my credit report ' +
      'and verify the information on this application.',
  },
];

export default function ReviewSubmit({ application, onSubmit, onBack }) {
  const [acks, setAcks] = useState({
    truth_certification: false,
    esign_consent: false,
    credit_authorization: false,
  });
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState(null);
  const [submitted, setSubmitted] = useState(null);

  const sectionsComplete = application?.sections_complete || {};

  const allSectionsComplete = useMemo(() => {
    const required = Object.keys(SECTION_NAMES);
    return required.every(k => sectionsComplete[k] === true);
  }, [sectionsComplete]);

  const allAcked = acks.truth_certification && acks.esign_consent && acks.credit_authorization;
  const canSubmit = allSectionsComplete && allAcked && !submitting;

  const handleSubmit = async () => {
    if (!onSubmit || !canSubmit) return;
    setSubmitting(true);
    setSubmitError(null);

    const result = await onSubmit({
      appointment_id: null,
      acknowledged_certifications: Object.entries(acks)
        .filter(([, v]) => v)
        .map(([k]) => k),
    });

    setSubmitting(false);
    if (result) {
      setSubmitted(result);
    } else {
      setSubmitError(
        'We could not submit your application. Please check that every section is complete.'
      );
    }
  };

  // ---------- Confirmation view ----------
  if (submitted) {
    return (
      <Box sx={{ textAlign: 'center', py: 4 }}>
        <CheckIcon sx={{ fontSize: 64, color: 'success.main', mb: 2 }} />
        <Typography variant="h5" gutterBottom>
          Application submitted
        </Typography>
        <Typography variant="body1" color="text.secondary" gutterBottom>
          Confirmation number: <strong>{submitted.confirmation_number}</strong>
        </Typography>

        <Paper variant="outlined" sx={{ p: 3, mt: 3, textAlign: 'left', maxWidth: 500, mx: 'auto' }}>
          <Typography variant="subtitle1" fontWeight={600} gutterBottom>
            What happens next
          </Typography>
          <List dense>
            {submitted.next_steps.map((step, i) => (
              <ListItem key={i}>
                <ListItemIcon sx={{ minWidth: 32 }}>
                  <Chip label={i + 1} size="small" color="primary" />
                </ListItemIcon>
                <ListItemText primary={step} />
              </ListItem>
            ))}
          </List>
        </Paper>
      </Box>
    );
  }

  // ---------- Main review view ----------
  return (
    <Box>
      {/* Section recap */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 2 }}>
        Application summary
      </Typography>
      <Paper variant="outlined" sx={{ mb: 3 }}>
        <List disablePadding>
          {Object.entries(SECTION_NAMES).map(([key, label]) => {
            const isComplete = sectionsComplete[key] === true;
            return (
              <ListItem
                key={key}
                divider
                sx={{
                  bgcolor: isComplete ? 'success.50' : 'warning.50',
                }}
              >
                <ListItemIcon>
                  {isComplete ? (
                    <CheckIcon color="success" />
                  ) : (
                    <PendingIcon color="warning" />
                  )}
                </ListItemIcon>
                <ListItemText
                  primary={label}
                  secondary={isComplete ? 'Complete' : 'Incomplete'}
                />
              </ListItem>
            );
          })}
        </List>
      </Paper>

      {!allSectionsComplete && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          Some sections are still incomplete. Go back and finish them before submitting.
        </Alert>
      )}

      <Divider sx={{ my: 3 }} />

      {/* Certifications */}
      <Typography variant="subtitle1" fontWeight={600} sx={{ mb: 1 }}>
        Certifications & eSign
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Please review and confirm the following before submitting.
      </Typography>

      {CERTIFICATIONS.map(cert => (
        <Paper
          key={cert.key}
          variant="outlined"
          sx={{
            p: 2,
            mb: 2,
            borderColor: acks[cert.key] ? 'success.main' : 'divider',
            bgcolor: acks[cert.key] ? 'success.50' : 'transparent',
          }}
        >
          <FormControlLabel
            control={
              <Checkbox
                checked={acks[cert.key]}
                onChange={e =>
                  setAcks(prev => ({ ...prev, [cert.key]: e.target.checked }))
                }
              />
            }
            label={
              <Box>
                <Typography variant="subtitle2">{cert.title}</Typography>
                <Typography variant="body2" color="text.secondary">
                  {cert.description}
                </Typography>
              </Box>
            }
            sx={{ alignItems: 'flex-start', m: 0 }}
          />
        </Paper>
      ))}

      {submitError && (
        <Alert severity="error" sx={{ mt: 2, mb: 2 }}>
          {submitError}
        </Alert>
      )}

      {/* Actions */}
      <Box sx={{ mt: 4, display: 'flex', justifyContent: 'space-between' }}>
        <Button variant="outlined" onClick={onBack} startIcon={<KeyboardArrowLeft />}>
          Back
        </Button>
        <Button
          variant="contained"
          onClick={handleSubmit}
          disabled={!canSubmit}
          size="large"
          startIcon={
            submitting ? (
              <CircularProgress size={20} color="inherit" />
            ) : (
              <SendIcon />
            )
          }
        >
          {submitting ? 'Submitting...' : 'Submit Application'}
        </Button>
      </Box>
    </Box>
  );
}

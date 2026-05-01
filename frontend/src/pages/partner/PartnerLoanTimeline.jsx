/**
 * PartnerLoanTimeline.jsx
 *
 * Visual milestone timeline for a specific loan.
 * Partners see which stages have been reached, without any financial details.
 */

import { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Button,
  CircularProgress,
  Alert,
  Stepper,
  Step,
  StepLabel,
  StepConnector,
  Chip,
  Paper,
} from '@mui/material';
import {
  ArrowBack as ArrowBackIcon,
  CheckCircle as CheckCircleIcon,
  RadioButtonUnchecked as PendingIcon,
} from '@mui/icons-material';
import { styled } from '@mui/material/styles';
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

async function partnerFetch(path) {
  const token = getPartnerToken();
  if (!token) throw new Error('Not authenticated');
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
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

// Custom step connector with color
const ColorConnector = styled(StepConnector)(({ theme }) => ({
  '& .MuiStepConnector-line': {
    borderColor: theme.palette.grey[300],
    borderTopWidth: 3,
    borderRadius: 1,
  },
  '&.Mui-active .MuiStepConnector-line, &.Mui-completed .MuiStepConnector-line': {
    borderColor: theme.palette.primary.main,
  },
}));

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PartnerLoanTimeline() {
  const { loanId } = useParams();
  const navigate = useNavigate();
  const [timeline, setTimeline] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!getPartnerToken()) {
      navigate('/partner/login');
      return;
    }

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await partnerFetch(`/api/v1/partner/loans/${loanId}/status`);
        setTimeline(data);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [loanId, navigate]);

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress />
      </Box>
    );
  }

  if (error) {
    return (
      <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate('/partner')}>
          Back to Dashboard
        </Button>
        <Alert severity="error" sx={{ mt: 2 }}>
          {error}
        </Alert>
      </Box>
    );
  }

  if (!timeline) return null;

  // Determine which step is active (first non-reached milestone)
  const activeStep = timeline.milestones.findIndex((m) => !m.reached);
  const completedAll = activeStep === -1;

  return (
    <Box sx={{ p: 3, maxWidth: 900, mx: 'auto' }}>
      {/* Back button */}
      <Button
        startIcon={<ArrowBackIcon />}
        onClick={() => navigate('/partner')}
        sx={{ mb: 2 }}
      >
        Back to Dashboard
      </Button>

      {/* Loan header */}
      <Paper sx={{ p: 3, mb: 3 }}>
        <Box display="flex" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="h5" fontWeight={700}>
              {timeline.borrower_name}
            </Typography>
            <Typography variant="body1" color="text.secondary">
              Loan #{timeline.loan_id}
            </Typography>
          </Box>
          <Chip
            label={timeline.current_stage_label}
            color={completedAll ? 'success' : 'primary'}
            size="medium"
          />
        </Box>
      </Paper>

      {/* Milestone stepper */}
      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} mb={3}>
            Loan Progress
          </Typography>

          <Stepper
            activeStep={completedAll ? timeline.milestones.length : activeStep}
            alternativeLabel
            connector={<ColorConnector />}
          >
            {timeline.milestones.map((milestone, idx) => (
              <Step key={milestone.stage} completed={milestone.reached}>
                <StepLabel
                  StepIconComponent={() =>
                    milestone.reached ? (
                      <CheckCircleIcon color="primary" />
                    ) : (
                      <PendingIcon color="disabled" />
                    )
                  }
                >
                  <Typography
                    variant="caption"
                    fontWeight={milestone.reached ? 600 : 400}
                    color={milestone.reached ? 'text.primary' : 'text.secondary'}
                  >
                    {milestone.label}
                  </Typography>
                  {milestone.reached_at && (
                    <Typography variant="caption" display="block" color="text.secondary">
                      {new Date(milestone.reached_at).toLocaleDateString()}
                    </Typography>
                  )}
                </StepLabel>
              </Step>
            ))}
          </Stepper>

          {completedAll && (
            <Alert severity="success" sx={{ mt: 3 }}>
              This loan has been funded. Congratulations!
            </Alert>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}

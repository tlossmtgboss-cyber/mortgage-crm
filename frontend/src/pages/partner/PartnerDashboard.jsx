/**
 * PartnerDashboard.jsx
 *
 * Main dashboard for the Realtor/Partner Portal.
 * Shows referred loans with statuses, quick actions for referrals
 * and pre-approval letter requests.
 *
 * Partners authenticate separately from LO users — they use
 * session tokens stored in localStorage under "partner_session".
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Typography,
  Card,
  CardContent,
  Grid,
  Chip,
  Button,
  CircularProgress,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Avatar,
  Divider,
} from '@mui/material';
import {
  Home as HomeIcon,
  Send as SendIcon,
  Description as DescriptionIcon,
  TrendingUp as TrendingUpIcon,
  AccessTime as AccessTimeIcon,
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

// Stage colors for the chip component
const stageColor = (stage) => {
  const map = {
    APPLICATION: 'info',
    DISCLOSED: 'info',
    PROCESSING: 'warning',
    SUBMITTED: 'warning',
    UNDERWRITING: 'warning',
    CONDITIONAL_APPROVAL: 'success',
    APPROVED: 'success',
    CLEAR_TO_CLOSE: 'success',
    CTC: 'success',
    CLOSING: 'success',
    DOCS: 'success',
    DOCS_OUT: 'success',
    FUNDED: 'success',
    CANCELLED: 'error',
    DENIED: 'error',
    DEAD: 'error',
    WITHDRAWN: 'default',
  };
  return map[stage] || 'default';
};

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export default function PartnerDashboard() {
  const navigate = useNavigate();
  const [loans, setLoans] = useState([]);
  const [letters, setLetters] = useState([]);
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [loansRes, lettersRes, profileRes] = await Promise.all([
        partnerFetch('/api/v1/partner/loans'),
        partnerFetch('/api/v1/partner/prequal-letters'),
        partnerFetch('/api/v1/partner/profile'),
      ]);
      setLoans(loansRes.loans || []);
      setLetters(lettersRes.letters || []);
      setProfile(profileRes);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!getPartnerToken()) {
      navigate('/partner/login');
      return;
    }
    fetchData();
  }, [fetchData, navigate]);

  // Derived stats
  const activeLoans = loans.filter(
    (l) => !['FUNDED', 'CANCELLED', 'DENIED', 'DEAD', 'WITHDRAWN'].includes(l.stage)
  );
  const fundedLoans = loans.filter((l) => l.stage === 'FUNDED');

  if (loading) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="60vh">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      {/* Header */}
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Box>
          <Typography variant="h4" fontWeight={700}>
            Partner Portal
          </Typography>
          {profile && (
            <Typography variant="body1" color="text.secondary">
              Welcome back, {profile.name}
            </Typography>
          )}
        </Box>
        <Box display="flex" gap={1}>
          <Button
            variant="contained"
            startIcon={<SendIcon />}
            onClick={() => navigate('/partner/refer')}
          >
            Refer a Buyer
          </Button>
          <Button
            variant="outlined"
            startIcon={<DescriptionIcon />}
            onClick={() => navigate('/partner/prequal-request')}
          >
            Request Pre-Approval
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {/* Summary cards */}
      <Grid container spacing={2} mb={3}>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1}>
                <Avatar sx={{ bgcolor: 'primary.main' }}>
                  <HomeIcon />
                </Avatar>
                <Box>
                  <Typography variant="h5" fontWeight={700}>
                    {loans.length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Total Referrals
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1}>
                <Avatar sx={{ bgcolor: 'warning.main' }}>
                  <TrendingUpIcon />
                </Avatar>
                <Box>
                  <Typography variant="h5" fontWeight={700}>
                    {activeLoans.length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Active Loans
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card>
            <CardContent>
              <Box display="flex" alignItems="center" gap={1}>
                <Avatar sx={{ bgcolor: 'success.main' }}>
                  <AccessTimeIcon />
                </Avatar>
                <Box>
                  <Typography variant="h5" fontWeight={700}>
                    {fundedLoans.length}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    Funded Loans
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Loans table */}
      <Typography variant="h6" fontWeight={600} mb={1}>
        Referred Loans
      </Typography>
      <TableContainer component={Paper} sx={{ mb: 4 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Borrower</TableCell>
              <TableCell>Loan Type</TableCell>
              <TableCell>Status</TableCell>
              <TableCell>Days in Stage</TableCell>
              <TableCell>Est. Close</TableCell>
              <TableCell />
            </TableRow>
          </TableHead>
          <TableBody>
            {loans.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} align="center">
                  <Typography color="text.secondary" py={2}>
                    No referred loans yet. Use "Refer a Buyer" to get started.
                  </Typography>
                </TableCell>
              </TableRow>
            ) : (
              loans.map((loan) => (
                <TableRow
                  key={loan.loan_id}
                  hover
                  sx={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/partner/loans/${loan.loan_id}`)}
                >
                  <TableCell>{loan.borrower_name}</TableCell>
                  <TableCell>{loan.loan_type || '--'}</TableCell>
                  <TableCell>
                    <Chip
                      label={loan.stage_label}
                      color={stageColor(loan.stage)}
                      size="small"
                    />
                  </TableCell>
                  <TableCell>{loan.days_in_stage}</TableCell>
                  <TableCell>
                    {loan.closing_date
                      ? new Date(loan.closing_date).toLocaleDateString()
                      : '--'}
                  </TableCell>
                  <TableCell>
                    <Button size="small" onClick={(e) => { e.stopPropagation(); navigate(`/partner/loans/${loan.loan_id}`); }}>
                      Timeline
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </TableContainer>

      {/* Pre-approval letter requests */}
      <Typography variant="h6" fontWeight={600} mb={1}>
        Pre-Approval Letter Requests
      </Typography>
      <Divider sx={{ mb: 2 }} />
      {letters.length === 0 ? (
        <Typography color="text.secondary" mb={4}>
          No letter requests yet.
        </Typography>
      ) : (
        <Grid container spacing={2} mb={4}>
          {letters.map((letter) => (
            <Grid item xs={12} sm={6} md={4} key={letter.id}>
              <Card variant="outlined">
                <CardContent>
                  <Typography fontWeight={600}>{letter.buyer_name}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {letter.property_address || 'No address'}
                  </Typography>
                  <Box mt={1}>
                    <Chip
                      label={letter.status}
                      color={
                        letter.status === 'generated'
                          ? 'success'
                          : letter.status === 'denied'
                          ? 'error'
                          : 'warning'
                      }
                      size="small"
                    />
                  </Box>
                  {letter.letter_url && (
                    <Button
                      size="small"
                      href={letter.letter_url}
                      target="_blank"
                      sx={{ mt: 1 }}
                    >
                      Download Letter
                    </Button>
                  )}
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}
    </Box>
  );
}

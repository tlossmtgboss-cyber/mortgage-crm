import React, { useState, useEffect } from 'react';
import {
  Box,
  Card,
  CardContent,
  Typography,
  Grid,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
  Button,
  TextField,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Tabs,
  Tab,
  IconButton,
  Tooltip,
  Alert,
  CircularProgress,
  Select,
  MenuItem,
  FormControl,
  InputLabel
} from '@mui/material';
import {
  Email as EmailIcon,
  CheckCircle as CheckIcon,
  Warning as WarningIcon,
  Delete as DeleteIcon,
  Add as AddIcon,
  Refresh as RefreshIcon,
  Science as TestIcon,
  FilterList as FilterIcon
} from '@mui/icons-material';
import api from '../services/api';

const EmailMonitorDashboard = () => {
  const [tabValue, setTabValue] = useState(0);
  const [stats, setStats] = useState([]);
  const [capturedEmails, setCapturedEmails] = useState([]);
  const [analysisLog, setAnalysisLog] = useState([]);
  const [whitelist, setWhitelist] = useState([]);
  const [blacklist, setBlacklist] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filter states
  const [providerFilter, setProviderFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');

  // Dialog states
  const [testDialogOpen, setTestDialogOpen] = useState(false);
  const [whitelistDialogOpen, setWhitelistDialogOpen] = useState(false);
  const [blacklistDialogOpen, setBlacklistDialogOpen] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [testLoading, setTestLoading] = useState(false);

  // Form states
  const [testForm, setTestForm] = useState({
    from_email: '',
    subject: '',
    body_preview: ''
  });
  const [whitelistForm, setWhitelistForm] = useState({
    email_pattern: '',
    description: '',
    whitelist_type: 'email',
    auto_assign_category: ''
  });
  const [blacklistForm, setBlacklistForm] = useState({
    email_pattern: '',
    description: '',
    blacklist_type: 'email',
    reason: ''
  });

  useEffect(() => {
    fetchData();
  }, [providerFilter, statusFilter]);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [statsRes, emailsRes, logRes, whitelistRes, blacklistRes] = await Promise.all([
        api.get('/api/v1/email-monitor/stats'),
        api.get('/api/v1/email-monitor/captured', {
          params: {
            provider: providerFilter || undefined,
            status: statusFilter || undefined,
            limit: 50
          }
        }),
        api.get('/api/v1/email-monitor/analysis-log', { params: { limit: 100 } }),
        api.get('/api/v1/email-monitor/whitelist'),
        api.get('/api/v1/email-monitor/blacklist')
      ]);

      setStats(statsRes.data);
      setCapturedEmails(emailsRes.data);
      setAnalysisLog(logRes.data);
      setWhitelist(whitelistRes.data);
      setBlacklist(blacklistRes.data);
      setError(null);
    } catch (err) {
      setError('Failed to fetch email monitor data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleTestAnalysis = async () => {
    setTestLoading(true);
    try {
      const response = await api.post('/api/v1/email-monitor/test-analysis', testForm);
      setTestResult(response.data);
    } catch (err) {
      setError('Test analysis failed');
    } finally {
      setTestLoading(false);
    }
  };

  const handleAddWhitelist = async () => {
    try {
      await api.post('/api/v1/email-monitor/whitelist', whitelistForm);
      setWhitelistDialogOpen(false);
      setWhitelistForm({ email_pattern: '', description: '', whitelist_type: 'email', auto_assign_category: '' });
      fetchData();
    } catch (err) {
      setError('Failed to add to whitelist');
    }
  };

  const handleRemoveWhitelist = async (id) => {
    try {
      await api.delete(`/email-monitor/whitelist/${id}`);
      fetchData();
    } catch (err) {
      setError('Failed to remove from whitelist');
    }
  };

  const handleAddBlacklist = async () => {
    try {
      await api.post('/api/v1/email-monitor/blacklist', blacklistForm);
      setBlacklistDialogOpen(false);
      setBlacklistForm({ email_pattern: '', description: '', blacklist_type: 'email', reason: '' });
      fetchData();
    } catch (err) {
      setError('Failed to add to blacklist');
    }
  };

  const handleRemoveBlacklist = async (id) => {
    try {
      await api.delete(`/email-monitor/blacklist/${id}`);
      fetchData();
    } catch (err) {
      setError('Failed to remove from blacklist');
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'assigned': return 'success';
      case 'captured': return 'info';
      case 'manual_review': return 'warning';
      case 'failed': return 'error';
      default: return 'default';
    }
  };

  const getCategoryColor = (category) => {
    switch (category) {
      case 'LOAN_COMMUNICATION': return '#4caf50';
      case 'LEAD_INQUIRY': return '#2196f3';
      case 'CLIENT_COMMUNICATION': return '#9c27b0';
      case 'REFERRAL_PARTNER': return '#ff9800';
      case 'THIRD_PARTY_VENDOR': return '#795548';
      case 'SPAM': return '#f44336';
      case 'IRRELEVANT': return '#9e9e9e';
      default: return '#757575';
    }
  };

  if (loading && stats.length === 0) {
    return (
      <Box display="flex" justifyContent="center" alignItems="center" minHeight="400px">
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box sx={{ p: 3 }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">
          <EmailIcon sx={{ mr: 1, verticalAlign: 'middle' }} />
          Intelligent Email Monitor
        </Typography>
        <Box>
          <Button
            variant="outlined"
            startIcon={<TestIcon />}
            onClick={() => setTestDialogOpen(true)}
            sx={{ mr: 1 }}
          >
            Test Analysis
          </Button>
          <Button
            variant="contained"
            startIcon={<RefreshIcon />}
            onClick={fetchData}
          >
            Refresh
          </Button>
        </Box>
      </Box>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {/* Stats Cards */}
      <Grid container spacing={3} mb={3}>
        {stats.map((stat) => (
          <Grid item xs={12} md={6} key={stat.email_provider}>
            <Card>
              <CardContent>
                <Typography variant="h6" gutterBottom>
                  {stat.email_provider === 'gmail' ? 'Gmail' : 'Outlook'}
                </Typography>
                <Grid container spacing={2}>
                  <Grid item xs={3}>
                    <Typography variant="h4">{stat.total_captured}</Typography>
                    <Typography variant="body2" color="textSecondary">Captured</Typography>
                  </Grid>
                  <Grid item xs={3}>
                    <Typography variant="h4" color="success.main">{stat.auto_linked_count}</Typography>
                    <Typography variant="body2" color="textSecondary">Auto-Linked</Typography>
                  </Grid>
                  <Grid item xs={3}>
                    <Typography variant="h4" color="warning.main">{stat.pending_review}</Typography>
                    <Typography variant="body2" color="textSecondary">Review</Typography>
                  </Grid>
                  <Grid item xs={3}>
                    <Typography variant="h4">{(stat.avg_confidence * 100).toFixed(0)}%</Typography>
                    <Typography variant="body2" color="textSecondary">Confidence</Typography>
                  </Grid>
                </Grid>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Tabs */}
      <Tabs value={tabValue} onChange={(e, v) => setTabValue(v)} sx={{ mb: 2 }}>
        <Tab label="Captured Emails" />
        <Tab label="Analysis Log" />
        <Tab label="Whitelist" />
        <Tab label="Blacklist" />
      </Tabs>

      {/* Tab Content */}
      {tabValue === 0 && (
        <Box>
          {/* Filters */}
          <Box display="flex" gap={2} mb={2}>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Provider</InputLabel>
              <Select
                value={providerFilter}
                label="Provider"
                onChange={(e) => setProviderFilter(e.target.value)}
              >
                <MenuItem value="">All</MenuItem>
                <MenuItem value="gmail">Gmail</MenuItem>
                <MenuItem value="outlook">Outlook</MenuItem>
              </Select>
            </FormControl>
            <FormControl size="small" sx={{ minWidth: 120 }}>
              <InputLabel>Status</InputLabel>
              <Select
                value={statusFilter}
                label="Status"
                onChange={(e) => setStatusFilter(e.target.value)}
              >
                <MenuItem value="">All</MenuItem>
                <MenuItem value="captured">Captured</MenuItem>
                <MenuItem value="assigned">Assigned</MenuItem>
                <MenuItem value="manual_review">Review</MenuItem>
              </Select>
            </FormControl>
          </Box>

          <TableContainer component={Paper}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Provider</TableCell>
                  <TableCell>From</TableCell>
                  <TableCell>Subject</TableCell>
                  <TableCell>Date</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell>Confidence</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {capturedEmails.map((email) => (
                  <TableRow key={email.id} hover>
                    <TableCell>
                      <Chip
                        label={email.email_provider}
                        size="small"
                        color={email.email_provider === 'gmail' ? 'error' : 'primary'}
                      />
                    </TableCell>
                    <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {email.from_email}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 300, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {email.subject}
                    </TableCell>
                    <TableCell>
                      {new Date(email.received_date).toLocaleDateString()}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={email.processing_status}
                        size="small"
                        color={getStatusColor(email.processing_status)}
                      />
                    </TableCell>
                    <TableCell>
                      {email.relevance_category && (
                        <Chip
                          label={email.relevance_category}
                          size="small"
                          sx={{ backgroundColor: getCategoryColor(email.relevance_category), color: 'white' }}
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      {email.ai_confidence ? `${(email.ai_confidence * 100).toFixed(0)}%` : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      {tabValue === 1 && (
        <TableContainer component={Paper}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell>From</TableCell>
                <TableCell>Subject</TableCell>
                <TableCell>Relevant</TableCell>
                <TableCell>Category</TableCell>
                <TableCell>Confidence</TableCell>
                <TableCell>Stage</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {analysisLog.map((log) => (
                <TableRow key={log.id} hover>
                  <TableCell>
                    {new Date(log.created_at).toLocaleTimeString()}
                  </TableCell>
                  <TableCell sx={{ maxWidth: 150, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {log.from_email}
                  </TableCell>
                  <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {log.subject}
                  </TableCell>
                  <TableCell>
                    {log.is_relevant ? (
                      <CheckIcon color="success" fontSize="small" />
                    ) : (
                      <WarningIcon color="error" fontSize="small" />
                    )}
                  </TableCell>
                  <TableCell>
                    <Chip
                      label={log.category}
                      size="small"
                      sx={{ backgroundColor: getCategoryColor(log.category), color: 'white' }}
                    />
                  </TableCell>
                  <TableCell>{(log.confidence * 100).toFixed(0)}%</TableCell>
                  <TableCell>{log.filter_stage}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {tabValue === 2 && (
        <Box>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setWhitelistDialogOpen(true)}
            sx={{ mb: 2 }}
          >
            Add to Whitelist
          </Button>
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Pattern</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Description</TableCell>
                  <TableCell>Category</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {whitelist.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{entry.email_pattern}</TableCell>
                    <TableCell>{entry.whitelist_type}</TableCell>
                    <TableCell>{entry.description}</TableCell>
                    <TableCell>{entry.auto_assign_category}</TableCell>
                    <TableCell>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleRemoveWhitelist(entry.id)}
                      >
                        <DeleteIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      {tabValue === 3 && (
        <Box>
          <Button
            variant="contained"
            startIcon={<AddIcon />}
            onClick={() => setBlacklistDialogOpen(true)}
            sx={{ mb: 2 }}
          >
            Add to Blacklist
          </Button>
          <TableContainer component={Paper}>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Pattern</TableCell>
                  <TableCell>Type</TableCell>
                  <TableCell>Reason</TableCell>
                  <TableCell>Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {blacklist.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell>{entry.email_pattern}</TableCell>
                    <TableCell>{entry.blacklist_type}</TableCell>
                    <TableCell>{entry.reason}</TableCell>
                    <TableCell>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => handleRemoveBlacklist(entry.id)}
                      >
                        <DeleteIcon />
                      </IconButton>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Box>
      )}

      {/* Test Analysis Dialog */}
      <Dialog open={testDialogOpen} onClose={() => setTestDialogOpen(false)} maxWidth="md" fullWidth>
        <DialogTitle>Test Email Analysis</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="From Email"
            value={testForm.from_email}
            onChange={(e) => setTestForm({ ...testForm, from_email: e.target.value })}
            margin="normal"
          />
          <TextField
            fullWidth
            label="Subject"
            value={testForm.subject}
            onChange={(e) => setTestForm({ ...testForm, subject: e.target.value })}
            margin="normal"
          />
          <TextField
            fullWidth
            label="Body Preview"
            value={testForm.body_preview}
            onChange={(e) => setTestForm({ ...testForm, body_preview: e.target.value })}
            margin="normal"
            multiline
            rows={4}
          />
          {testResult && (
            <Box mt={2} p={2} bgcolor="grey.100" borderRadius={1}>
              <Typography variant="subtitle2">Result:</Typography>
              <Typography>
                Relevant: {testResult.is_relevant ? 'Yes' : 'No'}
              </Typography>
              <Typography>Category: {testResult.category}</Typography>
              <Typography>Confidence: {(testResult.confidence * 100).toFixed(0)}%</Typography>
              <Typography>Stage: {testResult.filter_stage}</Typography>
              <Typography>Reason: {testResult.reason}</Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTestDialogOpen(false)}>Close</Button>
          <Button
            variant="contained"
            onClick={handleTestAnalysis}
            disabled={testLoading}
          >
            {testLoading ? <CircularProgress size={24} /> : 'Analyze'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Whitelist Dialog */}
      <Dialog open={whitelistDialogOpen} onClose={() => setWhitelistDialogOpen(false)}>
        <DialogTitle>Add to Whitelist</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="Email Pattern"
            value={whitelistForm.email_pattern}
            onChange={(e) => setWhitelistForm({ ...whitelistForm, email_pattern: e.target.value })}
            margin="normal"
            helperText="Use * for wildcards, e.g., *@docusign.com"
          />
          <FormControl fullWidth margin="normal">
            <InputLabel>Type</InputLabel>
            <Select
              value={whitelistForm.whitelist_type}
              label="Type"
              onChange={(e) => setWhitelistForm({ ...whitelistForm, whitelist_type: e.target.value })}
            >
              <MenuItem value="email">Email</MenuItem>
              <MenuItem value="domain">Domain</MenuItem>
              <MenuItem value="pattern">Pattern</MenuItem>
            </Select>
          </FormControl>
          <TextField
            fullWidth
            label="Description"
            value={whitelistForm.description}
            onChange={(e) => setWhitelistForm({ ...whitelistForm, description: e.target.value })}
            margin="normal"
          />
          <TextField
            fullWidth
            label="Auto-Assign Category"
            value={whitelistForm.auto_assign_category}
            onChange={(e) => setWhitelistForm({ ...whitelistForm, auto_assign_category: e.target.value })}
            margin="normal"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setWhitelistDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleAddWhitelist}>Add</Button>
        </DialogActions>
      </Dialog>

      {/* Blacklist Dialog */}
      <Dialog open={blacklistDialogOpen} onClose={() => setBlacklistDialogOpen(false)}>
        <DialogTitle>Add to Blacklist</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="Email Pattern"
            value={blacklistForm.email_pattern}
            onChange={(e) => setBlacklistForm({ ...blacklistForm, email_pattern: e.target.value })}
            margin="normal"
            helperText="Use * for wildcards"
          />
          <FormControl fullWidth margin="normal">
            <InputLabel>Type</InputLabel>
            <Select
              value={blacklistForm.blacklist_type}
              label="Type"
              onChange={(e) => setBlacklistForm({ ...blacklistForm, blacklist_type: e.target.value })}
            >
              <MenuItem value="email">Email</MenuItem>
              <MenuItem value="domain">Domain</MenuItem>
              <MenuItem value="pattern">Pattern</MenuItem>
            </Select>
          </FormControl>
          <TextField
            fullWidth
            label="Description"
            value={blacklistForm.description}
            onChange={(e) => setBlacklistForm({ ...blacklistForm, description: e.target.value })}
            margin="normal"
          />
          <TextField
            fullWidth
            label="Reason"
            value={blacklistForm.reason}
            onChange={(e) => setBlacklistForm({ ...blacklistForm, reason: e.target.value })}
            margin="normal"
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBlacklistDialogOpen(false)}>Cancel</Button>
          <Button variant="contained" onClick={handleAddBlacklist}>Add</Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default EmailMonitorDashboard;

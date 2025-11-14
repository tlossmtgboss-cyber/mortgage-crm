import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI } from '../services/api';
import MissionControl from './MissionControl';
import './Settings.css';

function Settings() {
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState('integrations');
  const [expandedSections, setExpandedSections] = useState({
    integrations: false,
    organizational: false,
    scheduling: false,
    onboarding: false,
    masterAdmin: false
  });
  const [searchTerm, setSearchTerm] = useState('');
  const [connectedIntegrations, setConnectedIntegrations] = useState(new Set());
  const [calendlyEventTypes, setCalendlyEventTypes] = useState([]);
  const [calendarMappings, setCalendarMappings] = useState([]);
  const [loadingCalendly, setLoadingCalendly] = useState(false);
  const [selectedStage, setSelectedStage] = useState('');
  const [selectedEventType, setSelectedEventType] = useState('');
  const [onboardingSteps, setOnboardingSteps] = useState([]);
  const [loadingSteps, setLoadingSteps] = useState(false);
  const [editingSteps, setEditingSteps] = useState([]);
  const [processTree, setProcessTree] = useState(null);
  const [apiKeys, setApiKeys] = useState([]);
  const [loadingApiKeys, setLoadingApiKeys] = useState(false);
  const [newApiKeyName, setNewApiKeyName] = useState('');
  const [createdKey, setCreatedKey] = useState(null);

  // User Management state
  const [users, setUsers] = useState([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [usersError, setUsersError] = useState(null);
  const [editingUser, setEditingUser] = useState(null);

  // Microsoft 365 integration state
  const [microsoftStatus, setMicrosoftStatus] = useState({
    connected: false,
    email_address: null,
    sync_enabled: false,
    last_sync_at: null
  });
  const [loadingMicrosoft, setLoadingMicrosoft] = useState(false);
  const [syncCompleted, setSyncCompleted] = useState(false);
  const [syncProgress, setSyncProgress] = useState({ current: 0, total: 0 });
  const [reprocessing, setReprocessing] = useState(false);
  const [syncingCalendar, setSyncingCalendar] = useState(false);

  // Team members state
  const [teamMembers, setTeamMembers] = useState([]);
  const [availableRoles, setAvailableRoles] = useState([]);
  const [loadingTeam, setLoadingTeam] = useState(false);

  // Calendly integration state
  const [calendlyApiKey, setCalendlyApiKey] = useState('');
  const [showCalendlyModal, setShowCalendlyModal] = useState(false);

  // Phone Integration state
  const [twilioStatus, setTwilioStatus] = useState({
    configured: false,
    phone_number: null,
    message: ''
  });
  const [loadingTwilio, setLoadingTwilio] = useState(false);
  const [testPhoneNumber, setTestPhoneNumber] = useState('');
  const [testResults, setTestResults] = useState([]);

  // Debug: Log when component mounts
  useEffect(() => {
    console.log('Settings component mounted');
    console.log('showCalendlyModal initial state:', showCalendlyModal);
  }, []);

  const toggleSection = (section) => {
    setExpandedSections({
      ...expandedSections,
      [section]: !expandedSections[section]
    });
  };

  const loadTeamMembers = async () => {
    setLoadingTeam(true);
    try {
      const data = await teamAPI.getWorkflowMembers();
      setTeamMembers(data.team_members || []);
      setAvailableRoles([]); // Workflow members don't use the role system
    } catch (error) {
      console.error('Error loading team members:', error);
    } finally {
      setLoadingTeam(false);
    }
  };

  useEffect(() => {
    if (activeSection === 'team-members') {
      loadTeamMembers();
    }
  }, [activeSection]);

  const leadStages = [
    { value: 'new', label: 'New Lead' },
    { value: 'contacted', label: 'Contacted' },
    { value: 'qualified', label: 'Qualified' },
    { value: 'meeting_scheduled', label: 'Meeting Scheduled' },
    { value: 'application_started', label: 'Application Started' },
    { value: 'processing', label: 'Processing' },
    { value: 'approved', label: 'Approved' },
    { value: 'closed', label: 'Closed' },
    { value: 'lost', label: 'Lost' }
  ];

  const connectCalendly = () => {
    console.log('Connect Calendly button clicked!');
    console.log('Current showCalendlyModal state:', showCalendlyModal);
    setShowCalendlyModal(true);
    console.log('Modal should now be visible');
  };

  const saveCalendlyConnection = async () => {
    if (!calendlyApiKey.trim()) {
      alert('Please enter your Calendly API key');
      return;
    }

    console.log('[Calendly] Saving API key...');
    setLoadingCalendly(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/connect`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ api_key: calendlyApiKey })
      });

      console.log('[Calendly] Save response status:', response.status);

      if (response.ok) {
        const result = await response.json();
        console.log('[Calendly] Save result:', result);
        alert('Calendly connected successfully! Fetching your event types...');
        setShowCalendlyModal(false);
        setCalendlyApiKey('');

        console.log('[Calendly] Now fetching event types...');
        await fetchCalendlyEventTypes();
        console.log('[Calendly] Done fetching event types');
      } else {
        const error = await response.json();
        console.error('[Calendly] Save failed:', error);
        alert(`Failed to connect Calendly: ${error.detail || 'Please check your API key'}`);
      }
    } catch (error) {
      console.error('[Calendly] Error connecting:', error);
      alert('Error connecting to Calendly: ' + error.message);
    } finally {
      setLoadingCalendly(false);
    }
  };

  const fetchCalendlyEventTypes = async () => {
    setLoadingCalendly(true);
    try {
      console.log('[Calendly] Fetching event types...');
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/event-types`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      console.log('[Calendly] Response status:', response.status);

      if (response.ok) {
        const data = await response.json();
        console.log('[Calendly] Event types data:', data);
        setCalendlyEventTypes(data.event_types || []);

        // Update connected integrations status
        const newConnected = new Set(connectedIntegrations);
        if (data.event_types && data.event_types.length > 0) {
          newConnected.add('calendly');
          console.log('[Calendly] ✓ Connected! Found', data.event_types.length, 'event types');
        } else {
          newConnected.delete('calendly');
          console.log('[Calendly] ✗ No event types found');
        }
        setConnectedIntegrations(newConnected);
      } else {
        const errorText = await response.text();
        console.error('[Calendly] Failed to fetch event types. Status:', response.status, 'Error:', errorText);
        setCalendlyEventTypes([]);

        // Mark as disconnected
        const newConnected = new Set(connectedIntegrations);
        newConnected.delete('calendly');
        setConnectedIntegrations(newConnected);
      }
    } catch (error) {
      console.error('[Calendly] Error fetching event types:', error);
      setCalendlyEventTypes([]);

      // Mark as disconnected on error
      const newConnected = new Set(connectedIntegrations);
      newConnected.delete('calendly');
      setConnectedIntegrations(newConnected);
    } finally {
      setLoadingCalendly(false);
    }
  };

  const fetchCalendarMappings = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/calendar-mappings`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const data = await response.json();
      setCalendarMappings(data.mappings || []);
    } catch (error) {
      console.error('Error fetching calendar mappings:', error);
    }
  };

  const loadProcessTree = () => {
    try {
      const userStr = localStorage.getItem('user');
      if (userStr) {
        const user = JSON.parse(userStr);
        // Check if user has completed onboarding and stored process tree
        const savedProcessTree = localStorage.getItem('onboardingProcessTree');
        if (savedProcessTree) {
          setProcessTree(JSON.parse(savedProcessTree));
        }
      }
    } catch (error) {
      console.error('Error loading process tree:', error);
    }
  };

  const fetchOnboardingSteps = async () => {
    setLoadingSteps(true);
    try {
      const response = await fetch('/api/v1/onboarding/steps', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const data = await response.json();
      setOnboardingSteps(data.steps || []);
      setEditingSteps(data.steps || []);
    } catch (error) {
      console.error('Error fetching onboarding steps:', error);
    } finally {
      setLoadingSteps(false);
    }
  };

  const updateOnboardingSteps = async () => {
    try {
      const response = await fetch('/api/v1/onboarding/steps', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          steps: editingSteps
        })
      });

      if (response.ok) {
        alert('Onboarding process updated successfully!');
        fetchOnboardingSteps();
      } else {
        alert('Failed to update onboarding process');
      }
    } catch (error) {
      console.error('Error updating onboarding steps:', error);
      alert('Error updating onboarding process');
    }
  };

  const addOnboardingStep = () => {
    const newStep = {
      step_number: editingSteps.length + 1,
      title: 'New Step',
      description: 'Describe what the user should do in this step',
      icon: '📌',
      required: false,
      fields: []
    };
    setEditingSteps([...editingSteps, newStep]);
  };

  const removeOnboardingStep = (index) => {
    const updated = editingSteps.filter((_, i) => i !== index);
    // Renumber steps
    updated.forEach((step, i) => {
      step.step_number = i + 1;
    });
    setEditingSteps(updated);
  };

  const updateStep = (index, field, value) => {
    const updated = [...editingSteps];
    updated[index] = {
      ...updated[index],
      [field]: value
    };
    setEditingSteps(updated);
  };

  const createCalendarMapping = async () => {
    if (!selectedStage || !selectedEventType) {
      alert('Please select both a lead stage and a calendar type');
      return;
    }

    const eventType = calendlyEventTypes.find(et => et.uri.includes(selectedEventType));
    if (!eventType) {
      alert('Event type not found');
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/calendly/calendar-mappings`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          stage: selectedStage,
          event_type_uuid: selectedEventType,
          event_type_name: eventType.name,
          event_type_url: eventType.scheduling_url
        })
      });

      if (response.ok) {
        alert('Calendar mapping saved successfully!');
        setSelectedStage('');
        setSelectedEventType('');
        fetchCalendarMappings();
      } else {
        alert('Failed to save calendar mapping');
      }
    } catch (error) {
      console.error('Error creating calendar mapping:', error);
      alert('Error saving calendar mapping');
    }
  };

  const fetchApiKeys = async () => {
    setLoadingApiKeys(true);
    try {
      const response = await fetch(`${process.env.REACT_APP_API_URL}/api/v1/api-keys`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (!response.ok) {
        throw new Error(`API returned ${response.status}`);
      }

      const data = await response.json();
      console.log('API Keys response:', data);

      // Ensure data is an array
      if (Array.isArray(data)) {
        setApiKeys(data);
      } else {
        console.error('API keys response is not an array:', data);
        setApiKeys([]);
      }
    } catch (error) {
      console.error('Error fetching API keys:', error);
      setApiKeys([]);
    } finally {
      setLoadingApiKeys(false);
    }
  };

  const createApiKey = async () => {
    if (!newApiKeyName.trim()) {
      alert('Please enter a name for the API key');
      return;
    }

    try {
      const response = await fetch(`${process.env.REACT_APP_API_URL}/api/v1/api-keys`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name: newApiKeyName })
      });

      console.log('Create API key response status:', response.status);

      if (response.ok) {
        const data = await response.json();
        console.log('API key created:', data);
        setCreatedKey(data.key);
        setNewApiKeyName('');
        fetchApiKeys();
        alert('API key created successfully! Make sure to copy it now - you won\'t be able to see it again.');
      } else {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        console.error('Failed to create API key:', response.status, errorData);
        alert(`Failed to create API key: ${errorData.detail || errorData.message || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Error creating API key:', error);
      alert(`Error creating API key: ${error.message}`);
    }
  };

  const revokeApiKey = async (keyId, keyName) => {
    if (!window.confirm(`Are you sure you want to revoke the API key "${keyName}"? This cannot be undone.`)) {
      return;
    }

    try {
      const response = await fetch(`${process.env.REACT_APP_API_URL}/api/v1/api-keys/${keyId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        alert('API key revoked successfully');
        fetchApiKeys();
      } else {
        alert('Failed to revoke API key');
      }
    } catch (error) {
      console.error('Error revoking API key:', error);
      alert('Error revoking API key');
    }
  };

  // Microsoft 365 Integration Functions
  const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
  const MICROSOFT_CLIENT_ID = process.env.REACT_APP_MICROSOFT_CLIENT_ID || 'YOUR_MICROSOFT_CLIENT_ID'; // Replace with actual client ID
  const MICROSOFT_REDIRECT_URI = `${window.location.origin}/settings`; // OAuth callback

  const checkMicrosoftStatus = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/status`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setMicrosoftStatus(data);

        // Update connected integrations
        const newConnected = new Set(connectedIntegrations);
        if (data.connected) {
          newConnected.add('outlook');
        } else {
          newConnected.delete('outlook');
        }
        setConnectedIntegrations(newConnected);
      }
    } catch (error) {
      console.error('Error checking Microsoft status:', error);
    }
  };

  const connectMicrosoft365 = () => {
    // Check if Microsoft Client ID is configured
    if (!MICROSOFT_CLIENT_ID || MICROSOFT_CLIENT_ID === 'YOUR_MICROSOFT_CLIENT_ID') {
      alert('Microsoft 365 integration is not configured yet. Please set up your Azure App Registration and add the MICROSOFT_CLIENT_ID to your environment variables in Vercel.\n\nSee the console for setup instructions.');
      console.log('%c🔧 Microsoft 365 Setup Required', 'color: #0078d4; font-size: 16px; font-weight: bold;');
      console.log('1. Create an Azure App Registration at https://portal.azure.com');
      console.log('2. Add REACT_APP_MICROSOFT_CLIENT_ID to Vercel environment variables');
      console.log('3. Add MICROSOFT_CLIENT_ID and MICROSOFT_CLIENT_SECRET to Railway environment variables');
      console.log('4. Redeploy both frontend and backend');
      return;
    }

    // Microsoft OAuth URL
    const scopes = 'https://graph.microsoft.com/Mail.Read offline_access';
    const authUrl = `https://login.microsoftonline.com/common/oauth2/v2.0/authorize?client_id=${MICROSOFT_CLIENT_ID}&response_type=code&redirect_uri=${encodeURIComponent(MICROSOFT_REDIRECT_URI)}&response_mode=query&scope=${encodeURIComponent(scopes)}&state=12345`;

    console.log('Opening Microsoft login popup...');
    console.log('Redirect URI:', MICROSOFT_REDIRECT_URI);

    // Open OAuth popup
    const width = 600;
    const height = 700;
    const left = (window.screen.width / 2) - (width / 2);
    const top = (window.screen.height / 2) - (height / 2);

    const popup = window.open(
      authUrl,
      'Microsoft 365 Login',
      `width=${width},height=${height},top=${top},left=${left}`
    );

    if (!popup) {
      alert('Popup was blocked! Please allow popups for this site and try again.');
      return;
    }

    // Listen for the callback
    const checkPopup = setInterval(() => {
      try {
        if (popup.closed) {
          clearInterval(checkPopup);
          checkMicrosoftStatus(); // Refresh status after popup closes
        }

        // Check if popup redirected back with code
        if (popup.location.href.includes(window.location.origin)) {
          const urlParams = new URLSearchParams(popup.location.search);
          const code = urlParams.get('code');

          if (code) {
            clearInterval(checkPopup);
            popup.close();
            handleMicrosoftCallback(code);
          }
        }
      } catch (e) {
        // Ignore cross-origin errors
      }
    }, 500);
  };

  const handleMicrosoftCallback = async (authorizationCode) => {
    setLoadingMicrosoft(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/connect`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          authorization_code: authorizationCode,
          redirect_uri: MICROSOFT_REDIRECT_URI
        })
      });

      if (response.ok) {
        const data = await response.json();
        alert(`Microsoft 365 connected successfully! ${data.email_address}`);
        await checkMicrosoftStatus();
      } else {
        const error = await response.json();
        alert(`Failed to connect Microsoft 365: ${error.detail}`);
      }
    } catch (error) {
      console.error('Error connecting Microsoft 365:', error);
      alert('Error connecting to Microsoft 365');
    } finally {
      setLoadingMicrosoft(false);
    }
  };

  const disconnectMicrosoft365 = async () => {
    if (!window.confirm('Are you sure you want to disconnect Microsoft 365?')) {
      return;
    }

    setLoadingMicrosoft(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/disconnect`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        alert('Microsoft 365 disconnected successfully');
        await checkMicrosoftStatus();
      } else {
        alert('Failed to disconnect Microsoft 365');
      }
    } catch (error) {
      console.error('Error disconnecting Microsoft 365:', error);
      alert('Error disconnecting Microsoft 365');
    } finally {
      setLoadingMicrosoft(false);
    }
  };

  const syncMicrosoftNow = async () => {
    setLoadingMicrosoft(true);
    setSyncCompleted(false);
    setSyncProgress({ current: 0, total: 50 }); // Show immediately with expected total

    // Simulate progress animation during sync (visual feedback)
    let simulatedProgress = 0;
    const progressInterval = setInterval(() => {
      simulatedProgress += Math.random() * 8;
      if (simulatedProgress < 45) { // Cap at 90% until real result
        setSyncProgress(prev => ({
          current: Math.floor(simulatedProgress),
          total: prev.total
        }));
      }
    }, 300);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/sync-now`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      clearInterval(progressInterval); // Stop simulation

      if (response.ok) {
        const data = await response.json();

        // Update with actual final counts
        setSyncProgress({ current: data.processed_count, total: data.fetched_count });

        alert(`Synced ${data.processed_count}/${data.fetched_count} emails successfully!`);
        await checkMicrosoftStatus();

        // Show "Synced" status for 3 seconds
        setLoadingMicrosoft(false);
        setSyncCompleted(true);
        setTimeout(() => {
          setSyncCompleted(false);
          setSyncProgress({ current: 0, total: 0 });
        }, 3000);
      } else {
        clearInterval(progressInterval);
        let errorMessage = 'Failed to sync emails';
        try {
          const error = await response.json();
          errorMessage = error.detail || error.message || errorMessage;
        } catch (e) {
          errorMessage = `HTTP ${response.status}: ${response.statusText}`;
        }
        console.error('Sync error response:', errorMessage);
        alert(`Failed to sync emails: ${errorMessage}`);
        setLoadingMicrosoft(false);
        setSyncProgress({ current: 0, total: 0 });
      }
    } catch (error) {
      clearInterval(progressInterval);
      console.error('Error syncing emails:', error);
      alert(`Error syncing emails: ${error.message || 'Network error'}`);
      setLoadingMicrosoft(false);
      setSyncProgress({ current: 0, total: 0 });
    }
  };

  const reprocessFailedEmails = async () => {
    setReprocessing(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/reprocess-emails`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        alert(`Found ${data.total_found} unextracted emails\nReprocessed ${data.reprocessed_count} successfully!\n\nGo to Tasks → Reconciliation to see them!`);
      } else {
        const error = await response.json();
        alert(`Failed to reprocess: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Reprocessing error:', error);
      alert(`Error: ${error.message}`);
    } finally {
      setReprocessing(false);
    }
  };

  const syncMicrosoftCalendar = async () => {
    setSyncingCalendar(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/sync-calendar`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        alert(`Synced ${data.synced_count} calendar events successfully!\n\nGo to Calendar page to see them!`);
      } else {
        const error = await response.json();
        alert(`Failed to sync calendar: ${error.detail || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Calendar sync error:', error);
      alert(`Error: ${error.message}`);
    } finally {
      setSyncingCalendar(false);
    }
  };

  // User Management Functions
  const loadUsers = async () => {
    setLoadingUsers(true);
    setUsersError(null);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        throw new Error(`Failed to load users: ${response.status}`);
      }

      const data = await response.json();
      setUsers(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Failed to load users:', err);
      setUsersError('Failed to load users. Please try again.');
      setUsers([]);
    } finally {
      setLoadingUsers(false);
    }
  };

  const handleToggleActive = async (userId, currentStatus) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ is_active: !currentStatus })
      });

      if (!response.ok) {
        throw new Error('Failed to update user status');
      }

      await loadUsers();
    } catch (err) {
      console.error('Failed to update user:', err);
      alert('Failed to update user status');
    }
  };

  const handleToggleVerified = async (userId, currentStatus) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email_verified: !currentStatus })
      });

      if (!response.ok) {
        throw new Error('Failed to update verification');
      }

      await loadUsers();
    } catch (err) {
      console.error('Failed to update user:', err);
      alert('Failed to update user verification');
    }
  };

  const handleUpdateRole = async (userId, newRole) => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ role: newRole })
      });

      if (!response.ok) {
        throw new Error('Failed to update role');
      }

      await loadUsers();
      setEditingUser(null);
    } catch (err) {
      console.error('Failed to update role:', err);
      alert('Failed to update user role');
    }
  };

  const handleDeleteUser = async (userId) => {
    const currentUser = JSON.parse(localStorage.getItem('user') || '{}');

    if (currentUser.id === userId) {
      alert('You cannot delete your own account. Please contact another administrator.');
      return;
    }

    if (!window.confirm('Are you sure you want to delete this user? This action cannot be undone.')) {
      return;
    }

    try {
      const token = localStorage.getItem('token');

      if (!token) {
        alert('You are not authenticated. Please log in again.');
        return;
      }

      const response = await fetch(`${API_BASE_URL}/api/v1/admin/users/${userId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || 'Failed to delete user');
      }

      alert('User deleted successfully');
      await loadUsers();
    } catch (err) {
      console.error('Failed to delete user:', err);
      alert(err.message || 'Failed to delete user');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    return date.toLocaleDateString() + ' ' + date.toLocaleTimeString();
  };

  // Phone Integration Functions
  const checkTwilioStatus = async () => {
    setLoadingTwilio(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/integrations/status`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        const smsIntegration = data.sms;

        if (smsIntegration) {
          setTwilioStatus({
            configured: smsIntegration.enabled,
            phone_number: smsIntegration.from_number || null,
            message: smsIntegration.enabled ? 'Twilio is configured and ready' : 'Twilio is not configured'
          });

          // Update connected integrations
          const newConnected = new Set(connectedIntegrations);
          if (smsIntegration.enabled) {
            newConnected.add('twilio');
          } else {
            newConnected.delete('twilio');
          }
          setConnectedIntegrations(newConnected);
        }
      }
    } catch (error) {
      console.error('Error checking Twilio status:', error);
      setTwilioStatus({
        configured: false,
        phone_number: null,
        message: 'Error checking Twilio status'
      });
    } finally {
      setLoadingTwilio(false);
    }
  };

  const testClickToCall = () => {
    if (!testPhoneNumber) {
      addTestResult('Click-to-Call', 'error', 'Please enter a phone number');
      return;
    }

    try {
      const cleanPhone = testPhoneNumber.replace(/[^0-9+]/g, '');
      window.open(`tel:${cleanPhone}`, '_self');
      addTestResult('Click-to-Call', 'success', `Dialer opened for ${testPhoneNumber}`);
    } catch (error) {
      addTestResult('Click-to-Call', 'error', `Failed: ${error.message}`);
    }
  };

  const testSMS = () => {
    if (!testPhoneNumber) {
      addTestResult('SMS', 'error', 'Please enter a phone number');
      return;
    }

    try {
      const cleanPhone = testPhoneNumber.replace(/[^0-9+]/g, '');
      window.open(`sms:${cleanPhone}`, '_blank');
      addTestResult('SMS', 'success', `Messaging app opened for ${testPhoneNumber}`);
    } catch (error) {
      addTestResult('SMS', 'error', `Failed: ${error.message}`);
    }
  };

  const addTestResult = (feature, status, message) => {
    const result = {
      feature,
      status,
      message,
      timestamp: new Date().toLocaleTimeString()
    };
    setTestResults(prev => [result, ...prev].slice(0, 5)); // Keep last 5 results
  };

  const availableIntegrations = [
    {
      id: 'outlook',
      name: 'Outlook Email',
      description: 'Sync emails and automatically extract lead information with AI',
      icon: '📧',
      color: '#0078d4',
      category: 'Email'
    },
    {
      id: 'outlook-calendar',
      name: 'Outlook Calendar',
      description: 'Sync calendar events and schedule appointments',
      icon: '📅',
      color: '#0078d4',
      category: 'Calendar'
    },
    {
      id: 'teams',
      name: 'Microsoft Teams',
      description: 'Send messages, make calls, and collaborate with your team',
      icon: '💬',
      color: '#6264a7',
      category: 'Communication'
    },
    {
      id: 'zoom',
      name: 'Zoom',
      description: 'Host virtual meetings and consultations with clients',
      icon: '📹',
      color: '#2d8cff',
      category: 'Communication'
    },
    {
      id: 'calendly',
      name: 'Calendly',
      description: 'Automated scheduling for client meetings',
      icon: '🗓️',
      color: '#006bff',
      category: 'Scheduling'
    },
    {
      id: 'docusign',
      name: 'DocuSign',
      description: 'Send and sign loan documents electronically',
      icon: '📝',
      color: '#ffd500',
      category: 'Documents'
    },
    {
      id: 'salesforce',
      name: 'Salesforce',
      description: 'Sync contacts and deals with your Salesforce CRM',
      icon: '☁️',
      color: '#00a1e0',
      category: 'CRM'
    },
    {
      id: 'hubspot',
      name: 'HubSpot',
      description: 'Marketing automation and lead nurturing',
      icon: '🎯',
      color: '#ff7a59',
      category: 'Marketing'
    },
    {
      id: 'mailchimp',
      name: 'Mailchimp',
      description: 'Email marketing campaigns for your clients',
      icon: '✉️',
      color: '#ffe01b',
      category: 'Marketing'
    },
    {
      id: 'twilio',
      name: 'Twilio SMS',
      description: 'Send SMS messages to leads and clients',
      icon: '📱',
      color: '#f22f46',
      category: 'Communication'
    },
    {
      id: 'ringcentral',
      name: 'RingCentral',
      description: 'Click-to-call and SMS via RingCentral phone system',
      icon: '📞',
      color: '#0073ae',
      category: 'Communication'
    },
    {
      id: 'slack',
      name: 'Slack',
      description: 'Get notifications and updates in your Slack workspace',
      icon: '💼',
      color: '#4a154b',
      category: 'Communication'
    },
    {
      id: 'zapier',
      name: 'Zapier',
      description: 'Connect with 5,000+ apps through automated workflows',
      icon: '⚡',
      color: '#ff4a00',
      category: 'Automation'
    },
    {
      id: 'synthflow',
      name: 'Synthflow AI',
      description: 'AI-powered voice agents for automated client calls and lead qualification',
      icon: '🤖',
      color: '#6366f1',
      category: 'AI & Automation'
    },
    {
      id: 'recallai',
      name: 'Recall.ai',
      description: 'Record and transcribe meetings from Zoom, Teams, and Google Meet with AI',
      icon: '🎙️',
      color: '#8b5cf6',
      category: 'AI & Automation'
    },
    {
      id: 'stripe',
      name: 'Stripe',
      description: 'Collect payments and processing fees',
      icon: '💳',
      color: '#635bff',
      category: 'Payments'
    },
    {
      id: 'quickbooks',
      name: 'QuickBooks',
      description: 'Sync financial data and commission tracking',
      icon: '💰',
      color: '#2ca01c',
      category: 'Accounting'
    },
    {
      id: 'google-calendar',
      name: 'Google Calendar',
      description: 'Sync appointments with Google Calendar',
      icon: '📆',
      color: '#4285f4',
      category: 'Calendar'
    },
    {
      id: 'google-drive',
      name: 'Google Drive',
      description: 'Store and share loan documents in Google Drive',
      icon: '📂',
      color: '#4285f4',
      category: 'Documents'
    }
  ];

  const toggleIntegration = (integrationId) => {
    // Handle Outlook specially - use OAuth flow
    if (integrationId === 'outlook') {
      if (microsoftStatus.connected) {
        disconnectMicrosoft365();
      } else {
        connectMicrosoft365();
      }
      return;
    }

    // For other integrations, toggle normally
    const newConnected = new Set(connectedIntegrations);
    if (newConnected.has(integrationId)) {
      newConnected.delete(integrationId);
    } else {
      newConnected.add(integrationId);
    }
    setConnectedIntegrations(newConnected);
  };

  const filteredIntegrations = availableIntegrations.filter(integration =>
    integration.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
    integration.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
    integration.category.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const featuredIntegrations = filteredIntegrations.filter(i =>
    ['outlook', 'outlook-calendar', 'teams', 'zoom', 'docusign', 'calendly'].includes(i.id)
  );

  useEffect(() => {
    if (activeSection === 'integration-marketplace' || activeSection === 'outlook-email' || activeSection === 'outlook-calendar') {
      checkMicrosoftStatus();
    }
    if (activeSection === 'calendly' || activeSection === 'calendar-settings') {
      fetchCalendlyEventTypes();
      fetchCalendarMappings();
    }
    if (activeSection === 'twilio-sms') {
      checkTwilioStatus();
    }
    if (activeSection === 'onboarding-current') {
      loadProcessTree();
    }
    if (activeSection === 'onboarding-update') {
      fetchOnboardingSteps();
    }
  }, [activeSection]);

  return (
    <div className="settings-page">
      <div className="settings-header">
        <h1>Settings</h1>
        <p>Manage your integrations and preferences</p>
      </div>

      <div className="settings-content">
        {/* Sidebar */}
        <div className="settings-sidebar">
          <button
            className={`sidebar-btn ${activeSection === 'mission-control' ? 'active' : ''}`}
            onClick={() => setActiveSection('mission-control')}
          >
            <span className="icon">🎯</span>
            <span>Mission Control</span>
          </button>

          {/* Integrations - Expandable */}
          <button
            className={`sidebar-btn parent ${expandedSections.integrations ? 'expanded' : ''}`}
            onClick={() => toggleSection('integrations')}
          >
            <span className="icon">🔌</span>
            <span>Integrations</span>
            <span className="expand-icon">{expandedSections.integrations ? '▼' : '▶'}</span>
          </button>
          {expandedSections.integrations && (
            <div className="sidebar-children">
              <button
                className={`sidebar-btn child ${activeSection === 'outlook-email' ? 'active' : ''}`}
                onClick={() => setActiveSection('outlook-email')}
              >
                <span>📧 Outlook Email</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'outlook-calendar' ? 'active' : ''}`}
                onClick={() => setActiveSection('outlook-calendar')}
              >
                <span>📅 Outlook Calendar</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'teams' ? 'active' : ''}`}
                onClick={() => setActiveSection('teams')}
              >
                <span>💬 Microsoft Teams</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'calendly' ? 'active' : ''}`}
                onClick={() => setActiveSection('calendly')}
              >
                <span>🗓️ Calendly</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'twilio-sms' ? 'active' : ''}`}
                onClick={() => setActiveSection('twilio-sms')}
              >
                <span>📱 Twilio SMS</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'docusign' ? 'active' : ''}`}
                onClick={() => setActiveSection('docusign')}
              >
                <span>📝 DocuSign</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'zoom' ? 'active' : ''}`}
                onClick={() => setActiveSection('zoom')}
              >
                <span>📹 Zoom</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'integration-marketplace' ? 'active' : ''}`}
                onClick={() => setActiveSection('integration-marketplace')}
              >
                <span>🏪 All Integrations</span>
              </button>
            </div>
          )}

          <button
            className={`sidebar-btn ${activeSection === 'api-keys' ? 'active' : ''}`}
            onClick={() => {
              setActiveSection('api-keys');
              fetchApiKeys();
            }}
          >
            <span className="icon">🔑</span>
            <span>API Keys</span>
          </button>

          {/* Organizational Settings - Expandable */}
          <button
            className={`sidebar-btn parent ${expandedSections.organizational ? 'expanded' : ''}`}
            onClick={() => toggleSection('organizational')}
          >
            <span className="icon">🏢</span>
            <span>Organizational Settings</span>
            <span className="expand-icon">{expandedSections.organizational ? '▼' : '▶'}</span>
          </button>
          {expandedSections.organizational && (
            <div className="sidebar-children">
              <button
                className={`sidebar-btn child ${activeSection === 'company-info' ? 'active' : ''}`}
                onClick={() => setActiveSection('company-info')}
              >
                <span>Company Info</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'team-members' ? 'active' : ''}`}
                onClick={() => navigate('/team-members')}
              >
                <span>Team Members</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'branding' ? 'active' : ''}`}
                onClick={() => setActiveSection('branding')}
              >
                <span>Branding</span>
              </button>
            </div>
          )}

          {/* Scheduling Settings - Expandable */}
          <button
            className={`sidebar-btn parent ${expandedSections.scheduling ? 'expanded' : ''}`}
            onClick={() => toggleSection('scheduling')}
          >
            <span className="icon">📅</span>
            <span>Scheduling Settings</span>
            <span className="expand-icon">{expandedSections.scheduling ? '▼' : '▶'}</span>
          </button>
          {expandedSections.scheduling && (
            <div className="sidebar-children">
              <button
                className={`sidebar-btn child ${activeSection === 'business-hours' ? 'active' : ''}`}
                onClick={() => setActiveSection('business-hours')}
              >
                <span>Business Hours</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'appointment-types' ? 'active' : ''}`}
                onClick={() => setActiveSection('appointment-types')}
              >
                <span>Appointment Types</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'calendar-settings' ? 'active' : ''}`}
                onClick={() => setActiveSection('calendar-settings')}
              >
                <span>Calendar Settings</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'availability' ? 'active' : ''}`}
                onClick={() => setActiveSection('availability')}
              >
                <span>Availability</span>
              </button>
            </div>
          )}

          <button
            className={`sidebar-btn ${activeSection === 'profile' ? 'active' : ''}`}
            onClick={() => setActiveSection('profile')}
          >
            <span className="icon">👤</span>
            <span>Profile</span>
          </button>
          <button
            className={`sidebar-btn ${activeSection === 'notifications' ? 'active' : ''}`}
            onClick={() => setActiveSection('notifications')}
          >
            <span className="icon">🔔</span>
            <span>Notifications</span>
          </button>
          <button
            className={`sidebar-btn parent ${expandedSections.onboarding ? 'expanded' : ''}`}
            onClick={() => toggleSection('onboarding')}
          >
            <span className="icon">🚀</span>
            <span>Onboarding</span>
            <span className="expand-icon">{expandedSections.onboarding ? '▼' : '▶'}</span>
          </button>
          {expandedSections.onboarding && (
            <div className="sidebar-children">
              <button
                className={`sidebar-btn child ${activeSection === 'onboarding-current' ? 'active' : ''}`}
                onClick={() => setActiveSection('onboarding-current')}
              >
                <span>Current Process</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'onboarding-update' ? 'active' : ''}`}
                onClick={() => setActiveSection('onboarding-update')}
              >
                <span>Update Process</span>
              </button>
            </div>
          )}

          <button
            className={`sidebar-btn ${activeSection === 'data-management' ? 'active' : ''}`}
            onClick={() => navigate('/data-upload')}
          >
            <span className="icon">📊</span>
            <span>Data Management</span>
          </button>

          {/* Master Administrator - Expandable */}
          <button
            className={`sidebar-btn parent ${expandedSections.masterAdmin ? 'expanded' : ''}`}
            onClick={() => toggleSection('masterAdmin')}
          >
            <span className="icon">👑</span>
            <span>Master Administrator</span>
            <span className="expand-icon">{expandedSections.masterAdmin ? '▼' : '▶'}</span>
          </button>
          {expandedSections.masterAdmin && (
            <div className="sidebar-children">
              <button
                className={`sidebar-btn child ${activeSection === 'user-management' ? 'active' : ''}`}
                onClick={() => {
                  setActiveSection('user-management');
                  loadUsers();
                }}
              >
                <span>User Management</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'clear-data' ? 'active' : ''}`}
                onClick={() => setActiveSection('clear-data')}
              >
                <span>Clear Dummy Data</span>
              </button>
            </div>
          )}
        </div>

        {/* Main Content */}
        <div className="settings-main">
          {activeSection === 'mission-control' && (
            <MissionControl />
          )}

          {/* OUTLOOK EMAIL */}
          {activeSection === 'outlook-email' && (
            <div className="integration-detail-section">
              <h2>📧 Outlook Email Integration</h2>
              <p className="section-description">
                Sync emails and automatically extract lead information with AI
              </p>

              {microsoftStatus.connected ? (
                <div className="microsoft-status-panel">
                  <div className="status-header">
                    <div className="status-icon" style={{background: '#0078d4'}}>📧</div>
                    <div className="status-info">
                      <h3>Microsoft 365 Connected</h3>
                      <p>{microsoftStatus.email_address}</p>
                    </div>
                    <div className="status-actions">
                      <button className="btn-sync" onClick={(e) => { e.stopPropagation(); syncMicrosoftNow(); }} disabled={loadingMicrosoft || reprocessing}>
                        {loadingMicrosoft ? 'Syncing...' : syncCompleted ? '✓ Synced' : '🔄 Sync Now'}
                      </button>
                      <button className="btn-sync" onClick={(e) => { e.stopPropagation(); reprocessFailedEmails(); }} disabled={loadingMicrosoft || reprocessing} style={{background: '#ff9800'}}>
                        {reprocessing ? 'Processing...' : '🔄 Reprocess Failed'}
                      </button>
                      <button className="btn-disconnect" onClick={(e) => { e.stopPropagation(); disconnectMicrosoft365(); }} disabled={loadingMicrosoft || reprocessing}>
                        Disconnect
                      </button>
                    </div>
                  </div>
                  {(loadingMicrosoft || syncCompleted) && syncProgress.total > 0 && (
                    <div className="sync-progress-container">
                      <div className="sync-progress-bar">
                        <div className="sync-progress-fill" style={{ width: `${(syncProgress.current / syncProgress.total) * 100}%` }}></div>
                      </div>
                      <div className="sync-progress-text">
                        {syncCompleted ? <span className="progress-complete">✓ {syncProgress.current}/{syncProgress.total} emails synced</span> : <span>Syncing {syncProgress.current}/{syncProgress.total} emails...</span>}
                      </div>
                    </div>
                  )}
                  {microsoftStatus.last_sync_at && <div className="status-meta">Last synced: {new Date(microsoftStatus.last_sync_at).toLocaleString()}</div>}
                </div>
              ) : (
                <div className="integration-connect-card">
                  <div className="connect-icon" style={{background: '#0078d4'}}>📧</div>
                  <h3>Connect Outlook Email</h3>
                  <p>Connect your Microsoft 365 account to sync emails and extract lead information automatically</p>
                  <button className="btn-connect" onClick={() => connectMicrosoft365()}>Connect Outlook Email</button>
                </div>
              )}
            </div>
          )}

          {/* OUTLOOK CALENDAR */}
          {activeSection === 'outlook-calendar' && (
            <div className="integration-detail-section">
              <h2>📅 Outlook Calendar Integration</h2>
              <p className="section-description">Sync calendar events and schedule appointments</p>
              {microsoftStatus.connected ? (
                <div className="integration-status-card">
                  <div className="status-icon-large" style={{background: '#0078d4'}}>📅</div>
                  <h3>Calendar Connected</h3>
                  <p>Your Outlook Calendar is connected and syncing</p>
                  <p className="status-detail">Account: {microsoftStatus.email_address}</p>
                </div>
              ) : (
                <div className="integration-connect-card">
                  <div className="connect-icon" style={{background: '#0078d4'}}>📅</div>
                  <h3>Connect Outlook Calendar</h3>
                  <p>Connect your Microsoft 365 account to sync calendar events</p>
                  <button className="btn-connect" onClick={() => connectMicrosoft365()}>Connect Outlook Calendar</button>
                </div>
              )}
            </div>
          )}

          {/* MICROSOFT TEAMS */}
          {activeSection === 'teams' && (
            <div className="integration-detail-section">
              <h2>💬 Microsoft Teams Integration</h2>
              <p className="section-description">Send messages, make calls, and collaborate with your team</p>
              <div className="integration-coming-soon">
                <div className="coming-soon-icon">💬</div>
                <h3>Coming Soon</h3>
                <p>Microsoft Teams integration is currently in development</p>
              </div>
            </div>
          )}

          {/* CALENDLY */}
          {activeSection === 'calendly' && (
            <div className="integration-detail-section">
              <h2>🗓️ Calendly Integration</h2>
              <p className="section-description">Automated scheduling for client meetings</p>
              {calendlyEventTypes.length > 0 ? (
                <div className="calendly-connected-section">
                  <div className="integration-status-card">
                    <div className="status-icon-large" style={{background: '#006bff'}}>🗓️</div>
                    <h3>Calendly Connected</h3>
                    <p>Found {calendlyEventTypes.length} event types</p>
                  </div>
                  <div className="calendar-mappings-section">
                    <h3>Event Type Mappings</h3>
                    <p className="section-description">Map Calendly event types to lead pipeline stages</p>
                    {calendarMappings.length > 0 && (
                      <div className="mappings-list">
                        {calendarMappings.map((mapping, index) => (
                          <div key={index} className="mapping-item">
                            <div className="mapping-info">
                              <span className="mapping-stage">{mapping.stage_name}</span>
                              <span className="mapping-arrow">→</span>
                              <span className="mapping-event">{mapping.event_type_name}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                    <div className="add-mapping-form">
                      <select value={selectedStage} onChange={(e) => setSelectedStage(e.target.value)} className="form-select">
                        <option value="">Select Lead Stage</option>
                        {leadStages.map((stage) => (<option key={stage.value} value={stage.value}>{stage.label}</option>))}
                      </select>
                      <select value={selectedEventType} onChange={(e) => setSelectedEventType(e.target.value)} className="form-select">
                        <option value="">Select Calendly Event Type</option>
                        {calendlyEventTypes.map((eventType) => (<option key={eventType.uri} value={eventType.uri}>{eventType.name}</option>))}
                      </select>
                      <button onClick={saveCalendarMapping} disabled={!selectedStage || !selectedEventType} className="btn-primary">Add Mapping</button>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="integration-connect-card">
                  <div className="connect-icon" style={{background: '#006bff'}}>🗓️</div>
                  <h3>Connect Calendly</h3>
                  <p>Configure your Calendly API key in Settings → API Keys to enable scheduling integration</p>
                </div>
              )}
            </div>
          )}

          {/* TWILIO SMS */}
          {activeSection === 'twilio-sms' && (
            <div className="phone-integration-section">
              <h2>📱 Twilio SMS Integration</h2>
              <p className="section-description">Send SMS messages to leads and clients</p>
              <div className="phone-status-card">
                <div className="card-header">
                  <h3>Integration Status</h3>
                  <button className="btn-refresh" onClick={checkTwilioStatus} disabled={loadingTwilio}>{loadingTwilio ? 'Checking...' : '🔄 Refresh'}</button>
                </div>
                <div className="status-grid">
                  <div className="status-item">
                    <div className="status-icon" style={{background: twilioStatus.configured ? '#f22f46' : '#6b7280'}}>📱</div>
                    <div className="status-info">
                      <h4>Twilio SMS API</h4>
                      <p>{twilioStatus.message || 'Advanced SMS features'}</p>
                      <span className={`status-badge ${twilioStatus.configured ? 'connected' : 'disconnected'}`}>{twilioStatus.configured ? '✓ Active' : 'Not Configured'}</span>
                      {twilioStatus.configured && twilioStatus.phone_number && <p className="status-detail">From: {twilioStatus.phone_number}</p>}
                    </div>
                  </div>
                </div>
              </div>
              <div className="phone-test-card">
                <h3>Test SMS Features</h3>
                <p className="section-description">Test your SMS integration to make sure everything is working</p>
                <div className="test-form">
                  <div className="form-group">
                    <label>Test Phone Number</label>
                    <input type="tel" className="form-input" placeholder="Enter phone number (e.g., 555-123-4567)" value={testPhoneNumber} onChange={(e) => setTestPhoneNumber(e.target.value)} />
                  </div>
                  <div className="test-actions">
                    <button className="btn-test sms" onClick={testSMS} disabled={!testPhoneNumber}>💬 Test SMS</button>
                  </div>
                </div>
                {testResults.length > 0 && (
                  <div className="test-results">
                    <h4>Recent Tests</h4>
                    <div className="results-list">
                      {testResults.map((result, index) => (
                        <div key={index} className={`result-item ${result.status}`}>
                          <span className="result-icon">{result.status === 'success' ? '✅' : '❌'}</span>
                          <div className="result-content">
                            <div className="result-feature">{result.feature}</div>
                            <div className="result-message">{result.message}</div>
                          </div>
                          <div className="result-time">{result.timestamp}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
              <div className="info-card">
                <div className="info-icon">💡</div>
                <div className="info-content">
                  <h3>Twilio SMS Features</h3>
                  <ul>
                    <li>Send SMS directly from CRM without using your phone</li>
                    <li>Bulk SMS campaigns to multiple leads</li>
                    <li>SMS templates and automation</li>
                    <li>Track delivery status and history</li>
                    <li>Requires backend configuration (see setup guide)</li>
                  </ul>
                </div>
              </div>
            </div>
          )}

          {/* DOCUSIGN */}
          {activeSection === 'docusign' && (
            <div className="integration-detail-section">
              <h2>📝 DocuSign Integration</h2>
              <p className="section-description">Send and sign loan documents electronically</p>
              <div className="integration-coming-soon">
                <div className="coming-soon-icon">📝</div>
                <h3>Coming Soon</h3>
                <p>DocuSign integration is currently in development</p>
              </div>
            </div>
          )}

          {/* ZOOM */}
          {activeSection === 'zoom' && (
            <div className="integration-detail-section">
              <h2>📹 Zoom Integration</h2>
              <p className="section-description">Host virtual meetings and consultations with clients</p>
              <div className="integration-coming-soon">
                <div className="coming-soon-icon">📹</div>
                <h3>Coming Soon</h3>
                <p>Zoom integration is currently in development</p>
              </div>
            </div>
          )}

          {activeSection === 'integration-marketplace' && (
            <div className="integrations-marketplace">
              <div className="marketplace-header">
                <div className="header-text">
                  <h2>Integrations & Apps</h2>
                  <p className="section-description">
                    Discover ({availableIntegrations.length}) | Manage ({connectedIntegrations.size})
                  </p>
                </div>
                <div className="search-box">
                  <input
                    type="text"
                    placeholder="Find integrations, apps, and more"
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="integration-search"
                  />
                </div>
              </div>

              {/* Microsoft 365 Status Panel */}
              {microsoftStatus.connected && (
                <div className="microsoft-status-panel">
                  <div className="status-header">
                    <div className="status-icon" style={{background: '#0078d4'}}>
                      📧
                    </div>
                    <div className="status-info">
                      <h3>Microsoft 365 Connected</h3>
                      <p>{microsoftStatus.email_address}</p>
                    </div>
                    <div className="status-actions">
                      <button
                        className="btn-sync"
                        onClick={(e) => {
                          e.stopPropagation();
                          syncMicrosoftNow();
                        }}
                        disabled={loadingMicrosoft || reprocessing || syncingCalendar}
                      >
                        {loadingMicrosoft ? 'Syncing...' : syncCompleted ? '✓ Synced' : '🔄 Sync Now'}
                      </button>
                      <button
                        className="btn-sync"
                        onClick={(e) => {
                          e.stopPropagation();
                          reprocessFailedEmails();
                        }}
                        disabled={loadingMicrosoft || reprocessing || syncingCalendar}
                        style={{background: '#ff9800'}}
                      >
                        {reprocessing ? 'Processing...' : '🔄 Reprocess Failed'}
                      </button>
                      <button
                        className="btn-sync"
                        onClick={(e) => {
                          e.stopPropagation();
                          syncMicrosoftCalendar();
                        }}
                        disabled={loadingMicrosoft || reprocessing || syncingCalendar}
                        style={{background: '#9c27b0'}}
                      >
                        {syncingCalendar ? 'Syncing...' : '📅 Sync Calendar'}
                      </button>
                      <button
                        className="btn-disconnect"
                        onClick={(e) => {
                          e.stopPropagation();
                          disconnectMicrosoft365();
                        }}
                        disabled={loadingMicrosoft || reprocessing || syncingCalendar}
                      >
                        Disconnect
                      </button>
                    </div>
                  </div>

                  {/* Sync Progress Bar */}
                  {(loadingMicrosoft || syncCompleted) && syncProgress.total > 0 && (
                    <div className="sync-progress-container">
                      <div className="sync-progress-bar">
                        <div
                          className="sync-progress-fill"
                          style={{ width: `${(syncProgress.current / syncProgress.total) * 100}%` }}
                        ></div>
                      </div>
                      <div className="sync-progress-text">
                        {syncCompleted ? (
                          <span className="progress-complete">✓ {syncProgress.current}/{syncProgress.total} emails synced</span>
                        ) : (
                          <span>Syncing {syncProgress.current}/{syncProgress.total} emails...</span>
                        )}
                      </div>
                    </div>
                  )}

                  {microsoftStatus.last_sync_at && (
                    <div className="status-meta">
                      Last synced: {new Date(microsoftStatus.last_sync_at).toLocaleString()}
                    </div>
                  )}
                </div>
              )}

              {/* All Integrations Grid */}
              <div className="all-integrations-section">
                <div className="integrations-grid">
                  {filteredIntegrations.map(integration => (
                    <div
                      key={integration.id}
                      className="integration-grid-card"
                      onClick={() => toggleIntegration(integration.id)}
                    >
                      <div className="card-icon" style={{background: integration.color}}>
                        {integration.icon}
                      </div>
                      <div className="card-content">
                        <div className="card-header">
                          <h4>{integration.name}</h4>
                          {connectedIntegrations.has(integration.id) && (
                            <span className="connected-badge">Connected</span>
                          )}
                        </div>
                        <p className="card-description">{integration.description}</p>
                      </div>
                    </div>
                  ))}
                </div>

                {filteredIntegrations.length === 0 && (
                  <div className="no-results">
                    <p>No integrations found matching "{searchTerm}"</p>
                  </div>
                )}
              </div>
            </div>
          )}

          {activeSection === 'phone-integration' && (
            <div className="phone-integration-section">
              <h2>Phone Integration</h2>
              <p className="section-description">
                Manage phone, SMS, and calling features for your CRM
              </p>

              {/* Integration Status Card */}
              <div className="phone-status-card">
                <div className="card-header">
                  <h3>Integration Status</h3>
                  <button
                    className="btn-refresh"
                    onClick={checkTwilioStatus}
                    disabled={loadingTwilio}
                  >
                    {loadingTwilio ? 'Checking...' : '🔄 Refresh'}
                  </button>
                </div>

                <div className="status-grid">
                  {/* Native Phone Features */}
                  <div className="status-item">
                    <div className="status-icon" style={{background: '#10b981'}}>📞</div>
                    <div className="status-info">
                      <h4>Click-to-Call</h4>
                      <p>Native phone integration</p>
                      <span className="status-badge connected">✓ Active</span>
                    </div>
                  </div>

                  <div className="status-item">
                    <div className="status-icon" style={{background: '#3b82f6'}}>💬</div>
                    <div className="status-info">
                      <h4>SMS/Text</h4>
                      <p>Native messaging integration</p>
                      <span className="status-badge connected">✓ Active</span>
                    </div>
                  </div>

                  {/* Twilio SMS API */}
                  <div className="status-item">
                    <div className="status-icon" style={{background: twilioStatus.configured ? '#f22f46' : '#6b7280'}}>
                      📱
                    </div>
                    <div className="status-info">
                      <h4>Twilio SMS API</h4>
                      <p>{twilioStatus.message || 'Advanced SMS features'}</p>
                      <span className={`status-badge ${twilioStatus.configured ? 'connected' : 'disconnected'}`}>
                        {twilioStatus.configured ? '✓ Active' : 'Not Configured'}
                      </span>
                      {twilioStatus.configured && twilioStatus.phone_number && (
                        <p className="status-detail">From: {twilioStatus.phone_number}</p>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              {/* Test Features Card */}
              <div className="phone-test-card">
                <h3>Test Phone Features</h3>
                <p className="section-description">
                  Test your phone integration to make sure everything is working
                </p>

                <div className="test-form">
                  <div className="form-group">
                    <label>Test Phone Number</label>
                    <input
                      type="tel"
                      className="form-input"
                      placeholder="Enter phone number (e.g., 555-123-4567)"
                      value={testPhoneNumber}
                      onChange={(e) => setTestPhoneNumber(e.target.value)}
                    />
                  </div>

                  <div className="test-actions">
                    <button
                      className="btn-test call"
                      onClick={testClickToCall}
                      disabled={!testPhoneNumber}
                    >
                      📞 Test Click-to-Call
                    </button>
                    <button
                      className="btn-test sms"
                      onClick={testSMS}
                      disabled={!testPhoneNumber}
                    >
                      💬 Test SMS
                    </button>
                  </div>
                </div>

                {/* Test Results */}
                {testResults.length > 0 && (
                  <div className="test-results">
                    <h4>Recent Tests</h4>
                    <div className="results-list">
                      {testResults.map((result, index) => (
                        <div key={index} className={`result-item ${result.status}`}>
                          <span className="result-icon">
                            {result.status === 'success' ? '✅' : '❌'}
                          </span>
                          <div className="result-content">
                            <div className="result-feature">{result.feature}</div>
                            <div className="result-message">{result.message}</div>
                          </div>
                          <div className="result-time">{result.timestamp}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              {/* How It Works Card */}
              <div className="info-card">
                <div className="info-icon">💡</div>
                <div className="info-content">
                  <h3>How Phone Integration Works</h3>
                  <p><strong>Native Features (Always Active):</strong></p>
                  <ul>
                    <li><strong>Click-to-Call:</strong> Click any phone number in the CRM to open your phone dialer</li>
                    <li><strong>SMS/Text:</strong> Click the 💬 button to open your messaging app</li>
                    <li>Works with any carrier (Verizon, AT&T, T-Mobile, etc.)</li>
                    <li>No configuration required - works immediately!</li>
                  </ul>
                  <p><strong>Twilio SMS API (Optional):</strong></p>
                  <ul>
                    <li>Send SMS directly from CRM without using your phone</li>
                    <li>Bulk SMS campaigns to multiple leads</li>
                    <li>SMS templates and automation</li>
                    <li>Track delivery status and history</li>
                    <li>Requires backend configuration (see setup guide)</li>
                  </ul>
                </div>
              </div>

              {/* Quick Links Card */}
              <div className="quick-links-card">
                <h3>Quick Links</h3>
                <div className="links-grid">
                  <a
                    href="/verizon-test"
                    className="link-item"
                    onClick={(e) => {
                      e.preventDefault();
                      navigate('/verizon-test');
                    }}
                  >
                    <div className="link-icon">🧪</div>
                    <div className="link-info">
                      <h4>Full Test Page</h4>
                      <p>Comprehensive testing interface</p>
                    </div>
                  </a>
                  <a
                    href="https://docs.claude.com"
                    className="link-item"
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    <div className="link-icon">📚</div>
                    <div className="link-info">
                      <h4>Setup Guide</h4>
                      <p>Step-by-step instructions</p>
                    </div>
                  </a>
                  {twilioStatus.configured && (
                    <a
                      href="https://console.twilio.com"
                      className="link-item"
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      <div className="link-icon">🗄️</div>
                      <div className="link-info">
                        <h4>Twilio Console</h4>
                        <p>Manage your Twilio account</p>
                      </div>
                    </a>
                  )}
                </div>
              </div>

              {/* Setup Instructions */}
              {!twilioStatus.configured && (
                <div className="setup-card">
                  <h3>Want Advanced SMS Features?</h3>
                  <p>To enable Twilio SMS API, add these environment variables to your Railway backend:</p>
                  <div className="code-block">
                    <code>
                      TWILIO_ACCOUNT_SID=your_account_sid<br/>
                      TWILIO_AUTH_TOKEN=your_auth_token<br/>
                      TWILIO_PHONE_NUMBER=+15551234567
                    </code>
                  </div>
                  <p className="help-text">
                    See <strong>BACKEND_ENVIRONMENT_SETUP.md</strong> for detailed instructions.
                  </p>
                </div>
              )}
            </div>
          )}

          {activeSection === 'api-keys' && (
            <div className="api-keys-section">
              <h2>API Keys</h2>
              <p className="section-description">
                Generate and manage API keys for integrations like Zapier
              </p>

              {/* Create New API Key */}
              <div className="api-key-create-card">
                <h3>Create New API Key</h3>
                <div className="form-group">
                  <input
                    type="text"
                    placeholder="Enter API key name (e.g., 'Zapier Integration')"
                    value={newApiKeyName}
                    onChange={(e) => setNewApiKeyName(e.target.value)}
                    className="input-field"
                  />
                  <button
                    onClick={createApiKey}
                    className="btn-create-key"
                    disabled={!newApiKeyName.trim()}
                  >
                    Generate API Key
                  </button>
                </div>

                {createdKey && (
                  <div className="key-created-alert">
                    <h4>🎉 API Key Created Successfully!</h4>
                    <p>Copy this key now - you won't be able to see it again:</p>
                    <div className="key-display">
                      <code>{createdKey}</code>
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(createdKey);
                          alert('API key copied to clipboard!');
                        }}
                        className="btn-copy"
                      >
                        Copy
                      </button>
                    </div>
                    <button
                      onClick={() => setCreatedKey(null)}
                      className="btn-dismiss"
                    >
                      I've saved it
                    </button>
                  </div>
                )}
              </div>

              {/* Existing API Keys */}
              <div className="api-keys-list-card">
                <h3>Your API Keys</h3>
                {loadingApiKeys ? (
                  <p>Loading API keys...</p>
                ) : apiKeys.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">🔑</div>
                    <p>No API keys yet.</p>
                    <p className="empty-hint">Create your first API key above to get started with integrations.</p>
                  </div>
                ) : (
                  <div className="api-keys-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Name</th>
                          <th>Key</th>
                          <th>Created</th>
                          <th>Last Used</th>
                          <th>Status</th>
                          <th>Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {apiKeys.map((key) => (
                          <tr key={key.id}>
                            <td><strong>{key.name}</strong></td>
                            <td><code>sk_••••••••••••••••</code></td>
                            <td>{new Date(key.created_at).toLocaleDateString()}</td>
                            <td>{key.last_used_at ? new Date(key.last_used_at).toLocaleDateString() : 'Never'}</td>
                            <td>
                              <span className={`status-badge ${key.is_active ? 'active' : 'inactive'}`}>
                                {key.is_active ? '✓ Active' : '✗ Revoked'}
                              </span>
                            </td>
                            <td>
                              {key.is_active && (
                                <button
                                  onClick={() => revokeApiKey(key.id, key.name)}
                                  className="btn-revoke"
                                >
                                  Revoke
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Help Section */}
              <div className="help-card">
                <h4>How to use API Keys</h4>
                <ol>
                  <li>Generate an API key by entering a name and clicking "Generate API Key"</li>
                  <li>Copy the API key immediately - it will only be shown once</li>
                  <li>Use the API key in your integrations (e.g., Zapier) by adding it to the Authorization header:
                    <br/><code>Authorization: Bearer sk_your_api_key_here</code>
                  </li>
                  <li>The API key will work exactly like your login token for all API requests</li>
                  <li>Revoke an API key anytime if you suspect it's been compromised</li>
                </ol>
              </div>
            </div>
          )}

          {activeSection === 'profile' && (
            <div className="profile-section">
              <h2>Profile Settings</h2>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'notifications' && (
            <div className="notifications-section">
              <h2>Notification Preferences</h2>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'onboarding-current' && (
            <div className="onboarding-current-section">
              <h2>Current Process Tree</h2>
              <p className="section-description">
                Visual representation of your loan process milestones and tasks
              </p>

              {!processTree ? (
                <div className="empty-state">
                  <div className="empty-icon">📋</div>
                  <h3>No Process Tree Found</h3>
                  <p>You haven't created a process tree yet during onboarding.</p>
                  <p className="empty-hint">
                    Complete the onboarding wizard and upload your process documents to generate your process tree.
                  </p>
                </div>
              ) : (
                <>
                  <div className="info-card" style={{ marginBottom: '24px' }}>
                    <div className="info-icon">🤖</div>
                    <div className="info-content">
                      <h3>Process Overview</h3>
                      <p>
                        Your process tree contains <strong>{processTree.milestones}</strong> milestones
                        with <strong>{processTree.tasks}</strong> total tasks across <strong>{processTree.roles}</strong> roles.
                      </p>
                      <p>
                        This was generated from your uploaded process documents and defines your loan workflow.
                      </p>
                    </div>
                  </div>

                  <div className="process-tree-visual">
                    {processTree.milestonesData && processTree.milestonesData.map((milestone, idx) => (
                      <div key={idx} className="milestone-card">
                        <div className="milestone-header">
                          <div className="milestone-number">{idx + 1}</div>
                          <div className="milestone-info">
                            <h3>{milestone.name}</h3>
                            <span className="task-count-badge">{milestone.tasks.length} tasks</span>
                          </div>
                        </div>

                        <div className="milestone-tasks">
                          {milestone.tasks.map((task, taskIdx) => (
                            <div key={taskIdx} className="process-task-item">
                              <div className="task-left">
                                <div className="task-number">{taskIdx + 1}</div>
                                <div className="task-details">
                                  <div className="task-name">{task.name}</div>
                                  <div className="task-meta">
                                    <span className="task-owner">👤 {task.owner}</span>
                                    <span className="task-sla">⏱️ {task.sla} {task.slaUnit}</span>
                                    {task.aiAuto && (
                                      <span className="task-ai-badge">🤖 AI Auto</span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>

                  <div className="process-summary-stats">
                    <div className="stat-box">
                      <div className="stat-value">{processTree.milestones}</div>
                      <div className="stat-label">Milestones</div>
                    </div>
                    <div className="stat-box">
                      <div className="stat-value">{processTree.tasks}</div>
                      <div className="stat-label">Total Tasks</div>
                    </div>
                    <div className="stat-box">
                      <div className="stat-value">{processTree.roles}</div>
                      <div className="stat-label">Roles</div>
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {activeSection === 'onboarding-update' && (
            <div className="onboarding-update-section">
              <h2>Update Onboarding Process</h2>
              <p className="section-description">
                Customize the onboarding steps for new users
              </p>

              {loadingSteps ? (
                <div className="loading-spinner">Loading...</div>
              ) : (
                <>
                  <div className="help-card" style={{ marginBottom: '24px' }}>
                    <h4>How to Customize</h4>
                    <p>
                      Edit the title, description, icon, and fields for each step below. You can
                      also add or remove steps. Changes will apply to all new users going through
                      onboarding.
                    </p>
                  </div>

                  <div className="editing-steps-list">
                    {editingSteps.map((step, index) => (
                      <div key={index} className="editing-step-card">
                        <div className="step-header-edit">
                          <h4>Step {index + 1}</h4>
                          <button
                            className="btn-remove-step"
                            onClick={() => removeOnboardingStep(index)}
                            disabled={editingSteps.length === 1}
                          >
                            ✕ Remove
                          </button>
                        </div>

                        <div className="form-row">
                          <div className="form-group">
                            <label>Title</label>
                            <input
                              type="text"
                              value={step.title}
                              onChange={(e) => updateStep(index, 'title', e.target.value)}
                              className="text-input"
                              placeholder="Step Title"
                            />
                          </div>

                          <div className="form-group">
                            <label>Icon (Emoji)</label>
                            <input
                              type="text"
                              value={step.icon}
                              onChange={(e) => updateStep(index, 'icon', e.target.value)}
                              className="text-input"
                              placeholder="📄"
                              maxLength="2"
                              style={{ width: '80px' }}
                            />
                          </div>
                        </div>

                        <div className="form-group">
                          <label>Description</label>
                          <textarea
                            value={step.description}
                            onChange={(e) => updateStep(index, 'description', e.target.value)}
                            className="text-input"
                            placeholder="Describe what the user should do..."
                            rows="3"
                          />
                        </div>

                        <div className="form-group">
                          <label className="checkbox-label">
                            <input
                              type="checkbox"
                              checked={step.required || false}
                              onChange={(e) => updateStep(index, 'required', e.target.checked)}
                            />
                            Required Step (user must complete to finish onboarding)
                          </label>
                        </div>
                      </div>
                    ))}
                  </div>

                  <button className="btn-add-step" onClick={addOnboardingStep}>
                    + Add Step
                  </button>

                  <div className="update-actions" style={{ marginTop: '32px', display: 'flex', gap: '12px' }}>
                    <button className="btn-primary" onClick={updateOnboardingSteps}>
                      Save Changes
                    </button>
                    <button
                      className="btn-secondary"
                      onClick={() => {
                        fetchOnboardingSteps();
                        alert('Changes discarded');
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </>
              )}
            </div>
          )}

          {/* Organizational Settings Sections */}
          {activeSection === 'company-info' && (
            <div className="company-info-section">
              <h2>Company Information</h2>
              <p className="section-description">
                Manage your company profile and contact information
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'team-members' && (
            <div className="team-members-section">
              <div className="section-header">
                <div>
                  <h2>Team Members ({teamMembers.length})</h2>
                  <p className="section-description">
                    Team members involved in your loan workflow (processors, underwriters, loan officers, etc.)
                  </p>
                </div>
                <button
                  className="btn-primary"
                  onClick={() => navigate('/team-members')}
                >
                  Manage Team Members
                </button>
              </div>

              {loadingTeam ? (
                <div className="loading-state">Loading team members...</div>
              ) : (
                <>
                  {teamMembers.length === 0 ? (
                    <div className="empty-state">
                      <div className="empty-icon">👥</div>
                      <p>No workflow team members found. Team members will appear once they are assigned to loans.</p>
                    </div>
                  ) : (
                    <div className="team-members-table-container">
                      <table className="team-members-table">
                        <thead>
                          <tr>
                            <th>Member</th>
                            <th>Role</th>
                            <th>Email</th>
                            <th>Loans</th>
                            <th>Actions</th>
                          </tr>
                        </thead>
                        <tbody>
                          {teamMembers.map((member, index) => (
                            <tr
                              key={`${member.name}-${member.role}-${index}`}
                              className="team-member-row"
                              onClick={() => {
                                // Navigate to team member profile if they have a user_id
                                if (member.user_id) {
                                  navigate(`/team/${member.user_id}`);
                                }
                              }}
                              style={{ cursor: member.user_id ? 'pointer' : 'default' }}
                            >
                              <td>
                                <div className="member-info-cell">
                                  <div className="member-avatar-small">
                                    {member.name.charAt(0).toUpperCase()}
                                  </div>
                                  <div>
                                    <div className="member-name">{member.name}</div>
                                  </div>
                                </div>
                              </td>
                              <td>
                                <span className="role-badge-inline">{member.role}</span>
                              </td>
                              <td>
                                <span className="member-email-text">{member.email || 'N/A'}</span>
                              </td>
                              <td>
                                <span className="loan-count-badge">
                                  📋 {member.loan_count} {member.loan_count === 1 ? 'loan' : 'loans'}
                                </span>
                              </td>
                              <td>
                                <button
                                  className="btn-view-profile"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    if (member.user_id) {
                                      navigate(`/team/${member.user_id}`);
                                    }
                                  }}
                                  disabled={!member.user_id}
                                >
                                  View Profile
                                </button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {activeSection === 'branding' && (
            <div className="branding-section">
              <h2>Branding</h2>
              <p className="section-description">
                Customize your company's branding and appearance
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {/* Scheduling Settings Sections */}
          {activeSection === 'business-hours' && (
            <div className="business-hours-section">
              <h2>Business Hours</h2>
              <p className="section-description">
                Set your operating hours and holidays
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'appointment-types' && (
            <div className="appointment-types-section">
              <h2>Appointment Types</h2>
              <p className="section-description">
                Configure different types of appointments and their durations
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'calendar-settings' && (
            <div className="calendar-settings-section">
              <h2>AI Scheduling - Calendar Mappings</h2>
              <p className="section-description">
                Map each lead stage to a specific Calendly event type for automatic AI scheduling
              </p>

              {/* Calendly Connection Status */}
              <div className="calendly-connection-card">
                <div className="connection-header">
                  <div className="connection-icon" style={{background: '#006bff'}}>
                    🗓️
                  </div>
                  <div className="connection-info">
                    <h3>Calendly Integration</h3>
                    <p>Connect your Calendly account to sync event types</p>
                  </div>
                  <div className="connection-status">
                    {calendlyEventTypes.length > 0 ? (
                      <span className="status-badge connected">✓ Connected</span>
                    ) : (
                      <span className="status-badge disconnected">Not Connected</span>
                    )}
                  </div>
                </div>

                {/* Debug info */}
                <div style={{padding: '10px', background: '#f0f0f0', marginBottom: '10px', fontSize: '12px'}}>
                  Debug: calendlyEventTypes.length = {calendlyEventTypes.length},
                  loadingCalendly = {loadingCalendly ? 'true' : 'false'},
                  showCalendlyModal = {showCalendlyModal ? 'true' : 'false'}
                </div>

                <div className="connection-actions">
                  {calendlyEventTypes.length > 0 ? (
                    <>
                      <button
                        className="btn-refresh"
                        onClick={fetchCalendlyEventTypes}
                        disabled={loadingCalendly}
                      >
                        {loadingCalendly ? 'Refreshing...' : '🔄 Refresh Event Types'}
                      </button>
                      <span className="connection-detail">
                        {calendlyEventTypes.length} event types loaded
                      </span>
                    </>
                  ) : (
                    <>
                      <button
                        className="btn-connect-calendly"
                        onClick={(e) => {
                          console.log('Button clicked!', e);
                          connectCalendly();
                        }}
                        disabled={loadingCalendly}
                        style={{position: 'relative', zIndex: 9999}}
                      >
                        {loadingCalendly ? 'Connecting...' : 'Connect Calendly'}
                      </button>
                      <button
                        onClick={() => alert('Test button works!')}
                        style={{marginLeft: '10px', padding: '10px', background: 'red', color: 'white', border: 'none', cursor: 'pointer'}}
                      >
                        TEST
                      </button>
                    </>
                  )}
                </div>
              </div>

              {/* Explanation Card */}
              <div className="info-card">
                <div className="info-icon">🤖</div>
                <div className="info-content">
                  <h3>How AI Scheduling Works</h3>
                  <p>When AI schedules appointments with leads, it automatically selects the right calendar based on the lead's current stage. For example:</p>
                  <ul>
                    <li><strong>New Lead</strong> → Discovery Call (30 min)</li>
                    <li><strong>Qualified</strong> → Consultation (60 min)</li>
                    <li><strong>Application Started</strong> → Application Review (45 min)</li>
                  </ul>
                  <p>Configure your mappings below to tell the AI which calendar to use for each stage.</p>
                </div>
              </div>

              {/* Create New Mapping */}
              <div className="mapping-form-card">
                <h3>Create Calendar Mapping</h3>
                <div className="mapping-form">
                  <div className="form-row">
                    <div className="form-group">
                      <label>Lead Stage</label>
                      <select
                        value={selectedStage}
                        onChange={(e) => setSelectedStage(e.target.value)}
                        className="form-select"
                      >
                        <option value="">Select a stage...</option>
                        {leadStages.map(stage => (
                          <option key={stage.value} value={stage.value}>
                            {stage.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Calendly Event Type</label>
                      {loadingCalendly ? (
                        <div className="loading-spinner">Loading calendars...</div>
                      ) : (
                        <select
                          value={selectedEventType}
                          onChange={(e) => setSelectedEventType(e.target.value)}
                          className="form-select"
                        >
                          <option value="">Select a calendar...</option>
                          {calendlyEventTypes.map(eventType => {
                            const uuid = eventType.uri.split('/').pop();
                            return (
                              <option key={uuid} value={uuid}>
                                {eventType.name} ({eventType.duration} min)
                              </option>
                            );
                          })}
                        </select>
                      )}
                    </div>

                    <div className="form-actions">
                      <button
                        onClick={createCalendarMapping}
                        disabled={!selectedStage || !selectedEventType}
                        className="btn-save-mapping"
                      >
                        Save Mapping
                      </button>
                    </div>
                  </div>
                </div>
              </div>

              {/* Current Mappings */}
              <div className="current-mappings-card">
                <h3>Current Mappings</h3>
                {calendarMappings.length === 0 ? (
                  <div className="empty-state">
                    <div className="empty-icon">📅</div>
                    <p>No calendar mappings configured yet.</p>
                    <p className="empty-hint">Create your first mapping above to get started.</p>
                  </div>
                ) : (
                  <div className="mappings-table">
                    <table>
                      <thead>
                        <tr>
                          <th>Lead Stage</th>
                          <th>Calendar Type</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {calendarMappings.map(mapping => {
                          const stageLabel = leadStages.find(s => s.value === mapping.stage)?.label || mapping.stage;
                          return (
                            <tr key={mapping.id}>
                              <td>
                                <div className="stage-cell">
                                  <span className="stage-badge">{stageLabel}</span>
                                </div>
                              </td>
                              <td>
                                <div className="calendar-cell">
                                  <strong>{mapping.event_type_name}</strong>
                                  <br />
                                  <span className="calendar-uuid">{mapping.event_type_uuid}</span>
                                </div>
                              </td>
                              <td>
                                <span className="status-badge active">✓ Active</span>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>

              {/* Help Section */}
              <div className="help-card">
                <h4>Need Help?</h4>
                <p>To get your Calendly event types:</p>
                <ol>
                  <li>Go to <a href="https://calendly.com/event_types/user/me" target="_blank" rel="noopener noreferrer">calendly.com/event_types</a></li>
                  <li>Create different event types for each stage (e.g., "Discovery Call", "Consultation")</li>
                  <li>Come back here and map each stage to the appropriate event type</li>
                  <li>The AI will automatically use the right calendar when scheduling!</li>
                </ol>
              </div>
            </div>
          )}

          {activeSection === 'availability' && (
            <div className="availability-section">
              <h2>Availability</h2>
              <p className="section-description">
                Set your personal availability and time-off
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {/* Master Administrator - User Management */}
          {activeSection === 'user-management' && (
            <div className="user-management-section">
              <div className="page-header">
                <div>
                  <h2>User Management</h2>
                  <p className="section-description">
                    Manage all registered users and their permissions
                  </p>
                </div>
                <div className="header-stats">
                  <div className="stat-box">
                    <div className="stat-value">{users.length}</div>
                    <div className="stat-label">Total Users</div>
                  </div>
                  <div className="stat-box">
                    <div className="stat-value">{users.filter(u => u.is_active).length}</div>
                    <div className="stat-label">Active</div>
                  </div>
                  <div className="stat-box">
                    <div className="stat-value">{users.filter(u => u.email_verified).length}</div>
                    <div className="stat-label">Verified</div>
                  </div>
                </div>
              </div>

              {usersError && <div className="error-message">{usersError}</div>}

              {loadingUsers ? (
                <div className="loading">Loading users...</div>
              ) : (
                <div className="users-table-container">
                  <table className="users-table">
                    <thead>
                      <tr>
                        <th>User</th>
                        <th>Email</th>
                        <th>Role</th>
                        <th>Status</th>
                        <th>Verified</th>
                        <th>Onboarded</th>
                        <th>Registered</th>
                        <th>Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map((user) => {
                        const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
                        const isCurrentUser = user.id === currentUser.id;
                        return (
                          <tr
                            key={user.id}
                            className={`clickable-user-row ${!user.is_active ? 'inactive-user' : ''}`}
                            onClick={() => navigate(`/users/${user.id}`)}
                            style={{ cursor: 'pointer' }}
                          >
                            <td>
                              <div className="user-info">
                                <div className="user-avatar">{user.full_name?.charAt(0) || user.email.charAt(0)}</div>
                                <div>
                                  <div className="user-name">
                                    {user.full_name || 'Unnamed User'}
                                    {isCurrentUser && <span className="current-user-badge">You</span>}
                                  </div>
                                  <div className="user-id">ID: {user.id}</div>
                                </div>
                              </div>
                            </td>
                            <td>{user.email}</td>
                            <td>
                              {editingUser === user.id ? (
                                <select
                                  value={user.role}
                                  onChange={(e) => handleUpdateRole(user.id, e.target.value)}
                                  onBlur={() => setEditingUser(null)}
                                  onClick={(e) => e.stopPropagation()}
                                  autoFocus
                                  className="role-select"
                                >
                                  <option value="loan_officer">Loan Officer</option>
                                  <option value="admin">Admin</option>
                                  <option value="processor">Processor</option>
                                  <option value="underwriter">Underwriter</option>
                                  <option value="manager">Manager</option>
                                </select>
                              ) : (
                                <span
                                  className="role-badge"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setEditingUser(user.id);
                                  }}
                                  title="Click to edit"
                                >
                                  {user.role || 'loan_officer'}
                                </span>
                              )}
                            </td>
                            <td>
                              <button
                                className={`status-badge ${user.is_active ? 'active' : 'inactive'}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleToggleActive(user.id, user.is_active);
                                }}
                              >
                                {user.is_active ? 'Active' : 'Inactive'}
                              </button>
                            </td>
                            <td>
                              <button
                                className={`verify-badge ${user.email_verified ? 'verified' : 'unverified'}`}
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleToggleVerified(user.id, user.email_verified);
                                }}
                              >
                                {user.email_verified ? '✓ Verified' : '✗ Not Verified'}
                              </button>
                            </td>
                            <td>
                              <span className={`onboarding-badge ${user.onboarding_completed ? 'completed' : 'pending'}`}>
                                {user.onboarding_completed ? 'Completed' : 'Pending'}
                              </span>
                            </td>
                            <td className="date-cell">{formatDate(user.created_at)}</td>
                            <td>
                              <button
                                className="btn-delete"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  handleDeleteUser(user.id);
                                }}
                                disabled={isCurrentUser}
                                title={isCurrentUser ? "You cannot delete your own account" : "Delete user"}
                              >
                                Delete
                              </button>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>

                  {users.length === 0 && (
                    <div className="empty-state">
                      <div className="empty-icon">👥</div>
                      <p>No users found</p>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Clear Dummy Data Section */}
          {activeSection === 'clear-data' && (
            <div className="clear-data-section">
              <div className="page-header">
                <div>
                  <h2>Clear Dummy Data</h2>
                  <p className="section-description">
                    Remove all sample/test data to prepare for workflow-based tasks
                  </p>
                </div>
              </div>

              <div className="warning-card" style={{background: '#fff3cd', border: '2px solid #ffc107', padding: '24px', borderRadius: '8px', marginBottom: '24px'}}>
                <div style={{display: 'flex', alignItems: 'start', gap: '16px'}}>
                  <div style={{fontSize: '32px'}}>⚠️</div>
                  <div>
                    <h3 style={{margin: '0 0 12px 0', color: '#856404'}}>Warning: This action cannot be undone!</h3>
                    <p style={{margin: '0 0 12px 0', color: '#856404'}}>This will permanently delete:</p>
                    <ul style={{margin: '0', paddingLeft: '20px', color: '#856404'}}>
                      <li>All outstanding tasks (AI tasks, regular tasks, process tasks)</li>
                      <li>All pending approval reconciliation events</li>
                      <li>All unified messages (SMS, Email, Teams)</li>
                      <li>All loans and leads</li>
                      <li>All activities, conversations, and referral partners</li>
                      <li>Client for Life data (closed loans)</li>
                    </ul>
                    <p style={{margin: '12px 0 0 0', fontWeight: 'bold', color: '#856404'}}>
                      Your user accounts and settings will be preserved.
                    </p>
                  </div>
                </div>
              </div>

              <div className="info-card" style={{marginBottom: '24px'}}>
                <div className="info-icon">📋</div>
                <div className="info-content">
                  <h3>What happens after clearing?</h3>
                  <p>After clearing all dummy data, you'll have a clean slate to:</p>
                  <ul>
                    <li>Create tasks based on your actual loan workflow</li>
                    <li>Import real leads and loans</li>
                    <li>Start with production-ready data</li>
                    <li>Test your workflow from scratch</li>
                  </ul>
                </div>
              </div>

              <div style={{display: 'flex', gap: '16px', justifyContent: 'center', padding: '32px'}}>
                <button
                  className="btn-danger"
                  onClick={async () => {
                    if (window.confirm('⚠️ Are you absolutely sure you want to clear ALL dummy data?\n\nThis will delete:\n- All tasks\n- All pending approvals\n- All messages\n- All loans and leads\n- All activities\n\nThis action CANNOT be undone!')) {
                      try {
                        const response = await fetch(`${process.env.REACT_APP_API_URL}/api/v1/admin/clear-sample-data`, {
                          method: 'POST',
                          headers: {
                            'Authorization': `Bearer ${localStorage.getItem('token')}`,
                            'Content-Type': 'application/json'
                          }
                        });

                        if (response.ok) {
                          const result = await response.json();
                          alert(`✅ Success! Cleared:\n` +
                                `- ${result.deleted.tasks || 0} tasks\n` +
                                `- ${result.deleted.ai_tasks || 0} AI tasks\n` +
                                `- ${result.deleted.process_tasks || 0} process tasks\n` +
                                `- ${result.deleted.reconciliation_events || 0} reconciliation events\n` +
                                `- ${result.deleted.sms_messages || 0} SMS messages\n` +
                                `- ${result.deleted.email_messages || 0} emails\n` +
                                `- ${result.deleted.teams_messages || 0} Teams messages\n` +
                                `- ${result.deleted.loans || 0} loans\n` +
                                `- ${result.deleted.leads || 0} leads\n` +
                                `- ${result.deleted.activities || 0} activities\n\n` +
                                `Your CRM is now ready for workflow-based tasks!`);
                        } else {
                          const error = await response.json();
                          alert(`❌ Error: ${error.detail || 'Failed to clear data'}`);
                        }
                      } catch (error) {
                        console.error('Error clearing data:', error);
                        alert(`❌ Error clearing data: ${error.message}`);
                      }
                    }
                  }}
                  style={{
                    padding: '16px 48px',
                    fontSize: '18px',
                    fontWeight: 'bold',
                    background: '#dc3545',
                    color: 'white',
                    border: 'none',
                    borderRadius: '8px',
                    cursor: 'pointer'
                  }}
                >
                  🗑️ Clear All Dummy Data
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Calendly Connection Modal */}
      {showCalendlyModal && (
        <div className="connection-modal-overlay" onClick={() => setShowCalendlyModal(false)}>
          <div className="connection-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={() => setShowCalendlyModal(false)}>×</button>
            <div className="modal-header">
              <span className="modal-icon">🗓️</span>
              <h3>Connect Calendly</h3>
              <p className="modal-description">Enter your Calendly API key to sync event types</p>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Calendly API Key</label>
                <input
                  type="password"
                  className="form-input"
                  placeholder="Enter your Calendly API key"
                  value={calendlyApiKey}
                  onChange={(e) => setCalendlyApiKey(e.target.value)}
                />
              </div>
              <div className="help-text">
                <h4>How to get your API key:</h4>
                <ol>
                  <li>Go to <a href="https://calendly.com/integrations/api_webhooks" target="_blank" rel="noopener noreferrer">Calendly Integrations</a></li>
                  <li>Click "Generate New Token"</li>
                  <li>Copy the token and paste it above</li>
                </ol>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowCalendlyModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={saveCalendlyConnection}
                disabled={!calendlyApiKey.trim()}
              >
                Connect
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Settings;

import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './Settings.css';

function Settings() {
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState('integrations');
  const [expandedSections, setExpandedSections] = useState({
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

  const toggleSection = (section) => {
    setExpandedSections({
      ...expandedSections,
      [section]: !expandedSections[section]
    });
  };

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

  const fetchCalendlyEventTypes = async () => {
    setLoadingCalendly(true);
    try {
      const response = await fetch('/api/v1/calendly/event-types', {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });
      const data = await response.json();
      setCalendlyEventTypes(data.event_types || []);
    } catch (error) {
      console.error('Error fetching Calendly event types:', error);
    } finally {
      setLoadingCalendly(false);
    }
  };

  const fetchCalendarMappings = async () => {
    try {
      const response = await fetch('/api/v1/calendly/calendar-mappings', {
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
      const response = await fetch('/api/v1/calendly/calendar-mappings', {
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
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/sync-now`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        alert(`Synced ${data.processed_count}/${data.fetched_count} emails successfully!`);
        await checkMicrosoftStatus();
      } else {
        const error = await response.json();
        alert(`Failed to sync emails: ${error.detail}`);
      }
    } catch (error) {
      console.error('Error syncing emails:', error);
      alert('Error syncing emails');
    } finally {
      setLoadingMicrosoft(false);
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
    if (activeSection === 'integrations') {
      checkMicrosoftStatus();
    }
    if (activeSection === 'calendar-settings') {
      fetchCalendlyEventTypes();
      fetchCalendarMappings();
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
            className={`sidebar-btn ${activeSection === 'integrations' ? 'active' : ''}`}
            onClick={() => setActiveSection('integrations')}
          >
            <span className="icon">🔌</span>
            <span>Integrations</span>
          </button>

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
                onClick={() => setActiveSection('team-members')}
              >
                <span>Team Members</span>
              </button>
              <button
                className={`sidebar-btn child ${activeSection === 'roles-permissions' ? 'active' : ''}`}
                onClick={() => setActiveSection('roles-permissions')}
              >
                <span>Roles & Permissions</span>
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
            </div>
          )}
        </div>

        {/* Main Content */}
        <div className="settings-main">
          {activeSection === 'integrations' && (
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
                        disabled={loadingMicrosoft}
                      >
                        {loadingMicrosoft ? 'Syncing...' : '🔄 Sync Now'}
                      </button>
                      <button
                        className="btn-disconnect"
                        onClick={(e) => {
                          e.stopPropagation();
                          disconnectMicrosoft365();
                        }}
                        disabled={loadingMicrosoft}
                      >
                        Disconnect
                      </button>
                    </div>
                  </div>
                  {microsoftStatus.last_sync_at && (
                    <div className="status-meta">
                      Last synced: {new Date(microsoftStatus.last_sync_at).toLocaleString()}
                    </div>
                  )}
                </div>
              )}

              {/* Featured Section */}
              {featuredIntegrations.length > 0 && !searchTerm && (
                <div className="featured-section">
                  <h3>Featured</h3>
                  <div className="featured-grid">
                    {featuredIntegrations.slice(0, 2).map(integration => (
                      <div
                        key={integration.id}
                        className="featured-card"
                        onClick={() => toggleIntegration(integration.id)}
                      >
                        <div className="featured-icon" style={{background: integration.color}}>
                          <span>{integration.icon}</span>
                        </div>
                        <div className="featured-info">
                          <h4>{integration.name}</h4>
                          <p>{integration.description}</p>
                          <span className={`status-badge ${connectedIntegrations.has(integration.id) ? 'connected' : ''}`}>
                            {connectedIntegrations.has(integration.id) ? 'Connected' : 'Connect'}
                          </span>
                        </div>
                      </div>
                    ))}
                  </div>
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
              <h2>Team Members</h2>
              <p className="section-description">
                Add and manage your team members
              </p>
              <p>Coming soon...</p>
            </div>
          )}

          {activeSection === 'roles-permissions' && (
            <div className="roles-permissions-section">
              <h2>Roles & Permissions</h2>
              <p className="section-description">
                Configure user roles and access levels
              </p>
              <p>Coming soon...</p>
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
        </div>
      </div>
    </div>
  );
}

export default Settings;

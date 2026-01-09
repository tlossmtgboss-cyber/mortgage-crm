/**
 * Twilio Self-Service Setup Page (Subaccount Model)
 *
 * Wizard flow for users to set up their Twilio communications:
 * 1. Initialize subaccount (automatic)
 * 2. Search and purchase phone number
 * 3. Create messaging service
 * 4. Register A2P Brand
 * 5. Register A2P Campaign
 *
 * All billing goes through the master account - users don't need their own Twilio account.
 */

import React, { useState, useEffect, useCallback } from 'react';
import './TwilioSetup.css';

const API_URL = process.env.REACT_APP_API_URL || '';

const TwilioSetup = () => {
  const [currentStep, setCurrentStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [setupStatus, setSetupStatus] = useState(null);

  // Step 2: Phone Number
  const [phoneSearch, setPhoneSearch] = useState({
    country: 'US',
    area_code: '',
    contains: ''
  });
  const [availableNumbers, setAvailableNumbers] = useState([]);
  const [selectedNumber, setSelectedNumber] = useState(null);

  // Step 3: Messaging Service
  const [messagingService, setMessagingService] = useState({
    friendly_name: 'Perennia Messaging'
  });

  // Step 4: Brand Registration
  const [brand, setBrand] = useState({
    brand_name: '',
    brand_type: 'PRIVATE_PROFIT',
    ein: '',
    vertical: 'REAL_ESTATE',
    website: '',
    street: '',
    city: '',
    state: '',
    postal_code: '',
    country: 'US',
    first_name: '',
    last_name: '',
    email: '',
    phone: ''
  });

  // Step 5: Campaign Registration
  const [campaign, setCampaign] = useState({
    use_case: 'MIXED',
    description: '',
    sample_messages: [''],
    opt_in_message: 'You have opted in to receive messages from us. Reply STOP to unsubscribe.',
    opt_out_message: 'You have been unsubscribed and will no longer receive messages from us.',
    help_message: 'For help, contact us at support@example.com or call 1-800-XXX-XXXX.'
  });

  // API call helper
  const apiCall = async (endpoint, method = 'GET', body = null) => {
    const token = localStorage.getItem('token');
    const options = {
      method,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      }
    };
    if (body) options.body = JSON.stringify(body);

    const response = await fetch(`${API_URL}${endpoint}`, options);
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || data.message || 'Request failed');
    }
    return data;
  };

  // Fetch setup status on mount
  const fetchStatus = useCallback(async () => {
    try {
      const data = await apiCall('/api/v1/twilio-setup/status');
      if (data.success) {
        setSetupStatus(data.data);
        // Set current step based on completion status
        const steps = data.data.steps;
        if (!steps.subaccount.complete) setCurrentStep(1);
        else if (!steps.phone_number.complete) setCurrentStep(2);
        else if (!steps.messaging_service.complete) setCurrentStep(3);
        else if (!steps.brand_registration.complete) setCurrentStep(4);
        else if (!steps.campaign_registration.complete) setCurrentStep(5);
        else setCurrentStep(6); // All complete
      }
    } catch (err) {
      console.error('Error fetching status:', err);
    } finally {
      setInitializing(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  // Step 1: Initialize Subaccount
  const initializeAccount = async () => {
    setLoading(true);
    setError(null);
    try {
      await apiCall('/api/v1/twilio-setup/initialize', 'POST');
      setSuccess('Account initialized successfully!');
      setTimeout(() => {
        setSuccess(null);
        setCurrentStep(2);
        fetchStatus();
      }, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Search Phone Numbers
  const searchNumbers = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiCall('/api/v1/twilio-setup/phone-numbers/search', 'POST', phoneSearch);
      setAvailableNumbers(data.data.numbers || []);
      if (data.data.numbers?.length === 0) {
        setError('No numbers found. Try different search criteria.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Step 2: Purchase Phone Number
  const purchaseNumber = async () => {
    if (!selectedNumber) {
      setError('Please select a phone number');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await apiCall('/api/v1/twilio-setup/phone-numbers/purchase', 'POST', {
        phone_number: selectedNumber
      });
      setSuccess('Phone number purchased!');
      setTimeout(() => {
        setSuccess(null);
        setCurrentStep(3);
        fetchStatus();
      }, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Step 3: Create Messaging Service
  const createMessagingService = async () => {
    setLoading(true);
    setError(null);
    try {
      await apiCall('/api/v1/twilio-setup/messaging-service', 'POST', messagingService);
      setSuccess('Messaging service created!');
      setTimeout(() => {
        setSuccess(null);
        setCurrentStep(4);
        fetchStatus();
      }, 1500);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Step 4: Register Brand
  const registerBrand = async () => {
    setLoading(true);
    setError(null);
    try {
      await apiCall('/api/v1/twilio-setup/a2p/brand', 'POST', brand);
      setSuccess('Brand registration submitted! Review typically takes 1-7 business days.');
      setTimeout(() => {
        setSuccess(null);
        setCurrentStep(5);
        fetchStatus();
      }, 2000);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Step 5: Register Campaign
  const registerCampaign = async () => {
    if (!setupStatus?.steps?.brand_registration?.brand_sid) {
      setError('Brand registration required first');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await apiCall('/api/v1/twilio-setup/a2p/campaign', 'POST', {
        ...campaign,
        brand_sid: setupStatus.steps.brand_registration.brand_sid
      });
      setSuccess('Campaign registration submitted! Review typically takes 1-3 business days.');
      setTimeout(() => {
        setSuccess(null);
        setCurrentStep(6);
        fetchStatus();
      }, 2000);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const steps = [
    { number: 1, title: 'Get Started', description: 'Initialize your account' },
    { number: 2, title: 'Phone Number', description: 'Get a phone number' },
    { number: 3, title: 'Messaging', description: 'Setup messaging service' },
    { number: 4, title: 'Brand', description: 'Register your brand' },
    { number: 5, title: 'Campaign', description: 'Register A2P campaign' }
  ];

  if (initializing) {
    return (
      <div className="twilio-setup-page">
        <div className="setup-content" style={{ textAlign: 'center', padding: '60px' }}>
          <p>Loading setup status...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="twilio-setup-page">
      <div className="twilio-setup-header">
        <h1>Twilio Setup</h1>
        <p>Configure SMS and voice communications for your account</p>
      </div>

      {/* Progress Steps */}
      <div className="setup-progress">
        {steps.map((step) => (
          <div
            key={step.number}
            className={`progress-step ${currentStep === step.number ? 'active' : ''} ${
              setupStatus?.steps && Object.values(setupStatus.steps)[step.number - 1]?.complete ? 'complete' : ''
            }`}
            onClick={() => {
              // Only allow clicking on completed steps or current step
              const stepComplete = setupStatus?.steps && Object.values(setupStatus.steps)[step.number - 1]?.complete;
              if (stepComplete || step.number <= currentStep) {
                setCurrentStep(step.number);
              }
            }}
          >
            <div className="step-number">
              {setupStatus?.steps && Object.values(setupStatus.steps)[step.number - 1]?.complete ? '✓' : step.number}
            </div>
            <div className="step-info">
              <span className="step-title">{step.title}</span>
              <span className="step-desc">{step.description}</span>
            </div>
          </div>
        ))}
      </div>

      {/* Error/Success Messages */}
      {error && <div className="setup-error">{error}</div>}
      {success && <div className="setup-success">{success}</div>}

      {/* Step Content */}
      <div className="setup-content">
        {/* Step 1: Initialize Account */}
        {currentStep === 1 && (
          <div className="setup-step">
            <h2>Get Started with Twilio</h2>
            <p className="step-instructions">
              Click the button below to set up your Twilio communications account.
              This will enable SMS and voice features in your CRM.
            </p>

            <div style={{ background: '#f0fdf4', padding: '16px', borderRadius: '8px', marginBottom: '24px' }}>
              <h4 style={{ margin: '0 0 8px 0', color: '#166534' }}>What's included:</h4>
              <ul style={{ margin: 0, paddingLeft: '20px', color: '#166534' }}>
                <li>Your own dedicated phone number</li>
                <li>SMS messaging capabilities</li>
                <li>A2P 10DLC registration for reliable delivery</li>
                <li>All billing handled through your CRM subscription</li>
              </ul>
            </div>

            <button className="btn-primary" onClick={initializeAccount} disabled={loading}>
              {loading ? 'Setting up...' : 'Initialize Account'}
            </button>
          </div>
        )}

        {/* Step 2: Phone Number */}
        {currentStep === 2 && (
          <div className="setup-step">
            <h2>Get a Phone Number</h2>
            <p className="step-instructions">
              Search for available phone numbers and select one for your account.
            </p>

            <div className="search-form">
              <div className="form-row">
                <div className="form-group">
                  <label>Country</label>
                  <select
                    value={phoneSearch.country}
                    onChange={(e) => setPhoneSearch({ ...phoneSearch, country: e.target.value })}
                  >
                    <option value="US">United States</option>
                    <option value="CA">Canada</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Area Code (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. 415"
                    maxLength={3}
                    value={phoneSearch.area_code}
                    onChange={(e) => setPhoneSearch({ ...phoneSearch, area_code: e.target.value })}
                  />
                </div>

                <div className="form-group">
                  <label>Contains (optional)</label>
                  <input
                    type="text"
                    placeholder="e.g. 1234"
                    value={phoneSearch.contains}
                    onChange={(e) => setPhoneSearch({ ...phoneSearch, contains: e.target.value })}
                  />
                </div>
              </div>

              <button className="btn-secondary" onClick={searchNumbers} disabled={loading}>
                {loading ? 'Searching...' : 'Search Numbers'}
              </button>
            </div>

            {availableNumbers.length > 0 && (
              <div className="numbers-list">
                <h3>Available Numbers</h3>
                <div className="numbers-grid">
                  {availableNumbers.map((number) => (
                    <div
                      key={number.phone_number}
                      className={`number-card ${selectedNumber === number.phone_number ? 'selected' : ''}`}
                      onClick={() => setSelectedNumber(number.phone_number)}
                    >
                      <span className="phone-number">{number.friendly_name}</span>
                      <span className="location">{number.locality}, {number.region}</span>
                      <div className="capabilities">
                        {number.capabilities.sms && <span className="cap">SMS</span>}
                        {number.capabilities.voice && <span className="cap">Voice</span>}
                        {number.capabilities.mms && <span className="cap">MMS</span>}
                      </div>
                    </div>
                  ))}
                </div>

                <button
                  className="btn-primary"
                  onClick={purchaseNumber}
                  disabled={loading || !selectedNumber}
                >
                  {loading ? 'Purchasing...' : `Select ${selectedNumber || 'a Number'}`}
                </button>
              </div>
            )}
          </div>
        )}

        {/* Step 3: Messaging Service */}
        {currentStep === 3 && (
          <div className="setup-step">
            <h2>Create Messaging Service</h2>
            <p className="step-instructions">
              A messaging service groups your phone numbers and handles message routing.
            </p>

            <div className="form-group">
              <label>Service Name</label>
              <input
                type="text"
                placeholder="e.g. My Company Messaging"
                value={messagingService.friendly_name}
                onChange={(e) => setMessagingService({ ...messagingService, friendly_name: e.target.value })}
              />
            </div>

            <button className="btn-primary" onClick={createMessagingService} disabled={loading}>
              {loading ? 'Creating...' : 'Create Messaging Service'}
            </button>
          </div>
        )}

        {/* Step 4: Brand Registration */}
        {currentStep === 4 && (
          <div className="setup-step">
            <h2>Register Your Brand (A2P 10DLC)</h2>
            <p className="step-instructions">
              A2P 10DLC registration is required for sending SMS in the US. This helps ensure message deliverability.
            </p>

            <div className="form-section">
              <h3>Business Information</h3>
              <div className="form-row">
                <div className="form-group">
                  <label>Business Name *</label>
                  <input
                    type="text"
                    value={brand.brand_name}
                    onChange={(e) => setBrand({ ...brand, brand_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>EIN (Tax ID)</label>
                  <input
                    type="text"
                    placeholder="XX-XXXXXXX"
                    value={brand.ein}
                    onChange={(e) => setBrand({ ...brand, ein: e.target.value })}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Business Type</label>
                  <select
                    value={brand.brand_type}
                    onChange={(e) => setBrand({ ...brand, brand_type: e.target.value })}
                  >
                    <option value="PRIVATE_PROFIT">Private For-Profit</option>
                    <option value="PUBLIC_PROFIT">Public For-Profit</option>
                    <option value="NON_PROFIT">Non-Profit</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Industry</label>
                  <select
                    value={brand.vertical}
                    onChange={(e) => setBrand({ ...brand, vertical: e.target.value })}
                  >
                    <option value="REAL_ESTATE">Real Estate</option>
                    <option value="FINANCIAL">Financial Services</option>
                    <option value="INSURANCE">Insurance</option>
                    <option value="PROFESSIONAL">Professional Services</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Website</label>
                <input
                  type="url"
                  placeholder="https://yourcompany.com"
                  value={brand.website}
                  onChange={(e) => setBrand({ ...brand, website: e.target.value })}
                />
              </div>
            </div>

            <div className="form-section">
              <h3>Business Address</h3>
              <div className="form-group">
                <label>Street Address *</label>
                <input
                  type="text"
                  value={brand.street}
                  onChange={(e) => setBrand({ ...brand, street: e.target.value })}
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>City *</label>
                  <input
                    type="text"
                    value={brand.city}
                    onChange={(e) => setBrand({ ...brand, city: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>State *</label>
                  <input
                    type="text"
                    maxLength={2}
                    placeholder="CA"
                    value={brand.state}
                    onChange={(e) => setBrand({ ...brand, state: e.target.value.toUpperCase() })}
                  />
                </div>
                <div className="form-group">
                  <label>ZIP Code *</label>
                  <input
                    type="text"
                    value={brand.postal_code}
                    onChange={(e) => setBrand({ ...brand, postal_code: e.target.value })}
                  />
                </div>
              </div>
            </div>

            <div className="form-section">
              <h3>Contact Information</h3>
              <div className="form-row">
                <div className="form-group">
                  <label>First Name *</label>
                  <input
                    type="text"
                    value={brand.first_name}
                    onChange={(e) => setBrand({ ...brand, first_name: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Last Name *</label>
                  <input
                    type="text"
                    value={brand.last_name}
                    onChange={(e) => setBrand({ ...brand, last_name: e.target.value })}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Email *</label>
                  <input
                    type="email"
                    value={brand.email}
                    onChange={(e) => setBrand({ ...brand, email: e.target.value })}
                  />
                </div>
                <div className="form-group">
                  <label>Phone *</label>
                  <input
                    type="tel"
                    placeholder="+1XXXXXXXXXX"
                    value={brand.phone}
                    onChange={(e) => setBrand({ ...brand, phone: e.target.value })}
                  />
                </div>
              </div>
            </div>

            <button className="btn-primary" onClick={registerBrand} disabled={loading}>
              {loading ? 'Submitting...' : 'Submit Brand Registration'}
            </button>
          </div>
        )}

        {/* Step 5: Campaign Registration */}
        {currentStep === 5 && (
          <div className="setup-step">
            <h2>Register Your Campaign</h2>
            <p className="step-instructions">
              Describe how you'll use SMS messaging. This helps carriers approve your messages.
            </p>

            <div className="form-group">
              <label>Use Case</label>
              <select
                value={campaign.use_case}
                onChange={(e) => setCampaign({ ...campaign, use_case: e.target.value })}
              >
                <option value="MIXED">Mixed (Transactional + Marketing)</option>
                <option value="CUSTOMER_CARE">Customer Care</option>
                <option value="MARKETING">Marketing</option>
                <option value="ACCOUNT_NOTIFICATION">Account Notifications</option>
              </select>
            </div>

            <div className="form-group">
              <label>Campaign Description *</label>
              <textarea
                rows={4}
                placeholder="Describe how you will use SMS messaging. Include the types of messages you'll send and who will receive them. (Min 40 characters)"
                value={campaign.description}
                onChange={(e) => setCampaign({ ...campaign, description: e.target.value })}
              />
              <span className="help-text">{campaign.description.length}/40 minimum characters</span>
            </div>

            <div className="form-group">
              <label>Sample Messages *</label>
              {campaign.sample_messages.map((msg, idx) => (
                <input
                  key={idx}
                  type="text"
                  placeholder={`Sample message ${idx + 1}`}
                  value={msg}
                  onChange={(e) => {
                    const newMessages = [...campaign.sample_messages];
                    newMessages[idx] = e.target.value;
                    setCampaign({ ...campaign, sample_messages: newMessages });
                  }}
                  style={{ marginBottom: '8px' }}
                />
              ))}
              {campaign.sample_messages.length < 5 && (
                <button
                  type="button"
                  className="btn-text"
                  onClick={() => setCampaign({
                    ...campaign,
                    sample_messages: [...campaign.sample_messages, '']
                  })}
                >
                  + Add another sample
                </button>
              )}
            </div>

            <div className="form-section">
              <h3>Compliance Messages</h3>
              <div className="form-group">
                <label>Opt-In Confirmation</label>
                <textarea
                  rows={2}
                  value={campaign.opt_in_message}
                  onChange={(e) => setCampaign({ ...campaign, opt_in_message: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Opt-Out Confirmation</label>
                <textarea
                  rows={2}
                  value={campaign.opt_out_message}
                  onChange={(e) => setCampaign({ ...campaign, opt_out_message: e.target.value })}
                />
              </div>
              <div className="form-group">
                <label>Help Response</label>
                <textarea
                  rows={2}
                  value={campaign.help_message}
                  onChange={(e) => setCampaign({ ...campaign, help_message: e.target.value })}
                />
              </div>
            </div>

            <button className="btn-primary" onClick={registerCampaign} disabled={loading}>
              {loading ? 'Submitting...' : 'Submit Campaign Registration'}
            </button>
          </div>
        )}

        {/* Step 6: Complete */}
        {currentStep === 6 && (
          <div className="setup-step setup-complete">
            <div className="complete-icon">✓</div>
            <h2>Setup Complete!</h2>
            <p>Your Twilio account is fully configured and ready to use.</p>

            {setupStatus && (
              <div className="status-summary">
                <div className="status-item">
                  <span className="status-label">Phone Number:</span>
                  <span className="status-value">{setupStatus.config?.phone_number || 'Configured'}</span>
                </div>
                <div className="status-item">
                  <span className="status-label">A2P Status:</span>
                  <span className={`status-value status-${setupStatus.config?.a2p_status}`}>
                    {setupStatus.config?.a2p_status || 'Pending'}
                  </span>
                </div>
              </div>
            )}

            <p className="note">
              Note: A2P registration may take 1-7 business days to be approved by carriers.
              You can check the status anytime on this page.
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default TwilioSetup;

import React, { useState } from 'react';
import './VerizonTest.css';

function VerizonTest() {
  const [testPhone, setTestPhone] = useState('555-123-4567');
  const [testEmail, setTestEmail] = useState('test@example.com');
  const [testResults, setTestResults] = useState([]);

  const addTestResult = (test, status, message) => {
    const result = {
      id: Date.now(),
      test,
      status,
      message,
      timestamp: new Date().toLocaleTimeString()
    };
    setTestResults(prev => [result, ...prev]);
  };

  const testClickToCall = () => {
    try {
      const cleanPhone = testPhone.replace(/[^0-9+]/g, '');
      window.open(`tel:${cleanPhone}`, '_self');
      addTestResult(
        'Click-to-Call',
        'success',
        `Attempted to dial ${testPhone}. Your phone dialer should have opened.`
      );
    } catch (error) {
      addTestResult(
        'Click-to-Call',
        'error',
        `Failed: ${error.message}`
      );
    }
  };

  const testSMS = () => {
    try {
      const cleanPhone = testPhone.replace(/[^0-9+]/g, '');
      window.open(`sms:${cleanPhone}`, '_blank');
      addTestResult(
        'SMS/Text',
        'success',
        `Attempted to send SMS to ${testPhone}. Your messaging app should have opened.`
      );
    } catch (error) {
      addTestResult(
        'SMS/Text',
        'error',
        `Failed: ${error.message}`
      );
    }
  };

  const testEmailClick = () => {
    try {
      window.open(`mailto:${testEmail}`, '_blank');
      addTestResult(
        'Email',
        'success',
        `Attempted to email ${testEmail}. Your email app should have opened.`
      );
    } catch (error) {
      addTestResult(
        'Email',
        'error',
        `Failed: ${error.message}`
      );
    }
  };

  const testAllFeatures = () => {
    addTestResult('Test Suite', 'info', 'Starting comprehensive test...');
    setTimeout(() => testClickToCall(), 500);
    setTimeout(() => testSMS(), 1500);
    setTimeout(() => testEmailClick(), 2500);
  };

  const clearResults = () => {
    setTestResults([]);
  };

  return (
    <div className="verizon-test-page">
      <div className="test-header">
        <h1>📱 Verizon Integration Test Page</h1>
        <p>Test click-to-call and SMS features with your Verizon service</p>
      </div>

      {/* Test Configuration */}
      <div className="test-config-section">
        <h2>Test Configuration</h2>
        <div className="config-grid">
          <div className="config-field">
            <label>Test Phone Number</label>
            <input
              type="tel"
              value={testPhone}
              onChange={(e) => setTestPhone(e.target.value)}
              placeholder="Enter phone number to test"
            />
            <small>Use your own phone number to test</small>
          </div>
          <div className="config-field">
            <label>Test Email</label>
            <input
              type="email"
              value={testEmail}
              onChange={(e) => setTestEmail(e.target.value)}
              placeholder="Enter email to test"
            />
            <small>Use your own email to test</small>
          </div>
        </div>
      </div>

      {/* Test Actions */}
      <div className="test-actions-section">
        <h2>Run Tests</h2>
        <div className="test-buttons">
          <button className="test-btn call-btn" onClick={testClickToCall}>
            <span className="btn-icon">📞</span>
            <div>
              <strong>Test Click-to-Call</strong>
              <small>Opens phone dialer</small>
            </div>
          </button>
          <button className="test-btn sms-btn" onClick={testSMS}>
            <span className="btn-icon">💬</span>
            <div>
              <strong>Test SMS</strong>
              <small>Opens messaging app</small>
            </div>
          </button>
          <button className="test-btn email-btn" onClick={testEmailClick}>
            <span className="btn-icon">✉️</span>
            <div>
              <strong>Test Email</strong>
              <small>Opens email client</small>
            </div>
          </button>
          <button className="test-btn all-btn" onClick={testAllFeatures}>
            <span className="btn-icon">🚀</span>
            <div>
              <strong>Test All Features</strong>
              <small>Run comprehensive test</small>
            </div>
          </button>
        </div>
      </div>

      {/* Integration Status */}
      <div className="integration-status-section">
        <h2>Integration Status</h2>
        <div className="status-grid">
          <div className="status-card">
            <div className="status-icon success">✅</div>
            <h3>Native Phone Integration</h3>
            <p>Uses tel: protocol</p>
            <span className="status-badge active">Active</span>
          </div>
          <div className="status-card">
            <div className="status-icon success">✅</div>
            <h3>SMS Integration</h3>
            <p>Uses sms: protocol</p>
            <span className="status-badge active">Active</span>
          </div>
          <div className="status-card">
            <div className="status-icon warning">⚠️</div>
            <h3>Telnyx SMS API</h3>
            <p>Advanced features</p>
            <span className="status-badge inactive">Not Configured</span>
          </div>
        </div>
      </div>

      {/* Test Results */}
      <div className="test-results-section">
        <div className="results-header">
          <h2>Test Results</h2>
          {testResults.length > 0 && (
            <button className="btn-clear" onClick={clearResults}>
              Clear Results
            </button>
          )}
        </div>

        {testResults.length === 0 ? (
          <div className="empty-results">
            <p>No tests run yet. Click a test button above to begin.</p>
          </div>
        ) : (
          <div className="results-list">
            {testResults.map(result => (
              <div key={result.id} className={`result-item ${result.status}`}>
                <div className="result-icon">
                  {result.status === 'success' && '✅'}
                  {result.status === 'error' && '❌'}
                  {result.status === 'info' && 'ℹ️'}
                </div>
                <div className="result-content">
                  <div className="result-header-row">
                    <strong>{result.test}</strong>
                    <span className="result-time">{result.timestamp}</span>
                  </div>
                  <p>{result.message}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Instructions */}
      <div className="instructions-section">
        <h2>How It Works</h2>
        <div className="instructions-grid">
          <div className="instruction-card">
            <div className="instruction-number">1</div>
            <h3>Click-to-Call</h3>
            <p>
              When you click the call button, it uses the <code>tel:</code> protocol
              to open your phone's native dialer. This works with any carrier including
              Verizon, AT&T, T-Mobile, etc.
            </p>
          </div>
          <div className="instruction-card">
            <div className="instruction-number">2</div>
            <h3>SMS/Text</h3>
            <p>
              The SMS button uses the <code>sms:</code> protocol to open your messaging
              app with the phone number pre-filled. You can then type and send your message
              using your Verizon service.
            </p>
          </div>
          <div className="instruction-card">
            <div className="instruction-number">3</div>
            <h3>Email</h3>
            <p>
              Email buttons use the <code>mailto:</code> protocol to open your default
              email client (Gmail, Outlook, Apple Mail, etc.) with the recipient pre-filled.
            </p>
          </div>
        </div>
      </div>

      {/* Telnyx Setup */}
      <div className="telnyx-setup-section">
        <h2>🚀 Advanced: Telnyx Integration</h2>
        <p>
          For advanced SMS features (bulk messaging, templates, tracking), you can integrate
          with Telnyx. Your CRM is already Telnyx-ready!
        </p>
        <div className="telnyx-benefits">
          <h3>Telnyx Benefits:</h3>
          <ul>
            <li>✅ Send SMS directly from CRM without using your phone</li>
            <li>✅ Bulk SMS campaigns to multiple leads</li>
            <li>✅ SMS templates and automation</li>
            <li>✅ Track delivery and responses</li>
            <li>✅ Keep your Verizon number (port to Telnyx)</li>
          </ul>
        </div>
        <button className="btn-setup-telnyx" onClick={() => window.open('https://telnyx.com/sign-up', '_blank')}>
          Get Started with Telnyx →
        </button>
      </div>
    </div>
  );
}

export default VerizonTest;

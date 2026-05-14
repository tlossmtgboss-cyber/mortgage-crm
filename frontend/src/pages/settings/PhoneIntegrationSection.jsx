import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { formatPhoneNumber } from '../../utils/phoneUtils';

const PhoneIntegrationSection = () => {
  const navigate = useNavigate();
  const [testPhoneNumber, setTestPhoneNumber] = useState('');
  const [testResults, setTestResults] = useState([]);

  const addTestResult = (feature, status, message) => {
    const result = { feature, status, message, timestamp: new Date().toLocaleTimeString() };
    setTestResults(prev => [result, ...prev].slice(0, 5));
  };

  const testClickToCall = () => {
    if (!testPhoneNumber) { addTestResult('Click-to-Call', 'error', 'Please enter a phone number'); return; }
    try {
      const cleanPhone = testPhoneNumber.replace(/[^0-9+]/g, '');
      window.open(`tel:${cleanPhone}`, '_self');
      addTestResult('Click-to-Call', 'success', `Dialer opened for ${testPhoneNumber}`);
    } catch (error) { addTestResult('Click-to-Call', 'error', `Failed: ${error.message}`); }
  };

  const testSMS = () => {
    if (!testPhoneNumber) { addTestResult('SMS', 'error', 'Please enter a phone number'); return; }
    try {
      const cleanPhone = testPhoneNumber.replace(/[^0-9+]/g, '');
      window.open(`sms:${cleanPhone}`, '_blank');
      addTestResult('SMS', 'success', `Messaging app opened for ${testPhoneNumber}`);
    } catch (error) { addTestResult('SMS', 'error', `Failed: ${error.message}`); }
  };

  return (
    <div className="phone-integration-section">
      <h2>Phone Integration</h2>
      <p className="section-description">Manage phone, SMS, and calling features for your CRM</p>

      <div className="phone-status-card">
        <div className="card-header"><h3>Integration Status</h3></div>
        <div className="status-grid">
          <div className="status-item">
            <div className="status-info">
              <h4>Click-to-Call</h4><p>Native phone integration</p>
              <span className="status-badge connected">Active</span>
            </div>
          </div>
          <div className="status-item">
            <div className="status-info">
              <h4>SMS/Text</h4><p>Native messaging integration</p>
              <span className="status-badge connected">Active</span>
            </div>
          </div>
        </div>
      </div>

      <div className="phone-test-card">
        <h3>Test Phone Features</h3>
        <p className="section-description">Test your phone integration to make sure everything is working</p>
        <div className="test-form">
          <div className="form-group">
            <label>Test Phone Number</label>
            <input type="tel" className="form-input" placeholder="Enter phone number (e.g., 555-123-4567)"
              value={testPhoneNumber} onChange={(e) => setTestPhoneNumber(formatPhoneNumber(e.target.value))} />
          </div>
          <div className="test-actions">
            <button className="btn-test call" onClick={testClickToCall} disabled={!testPhoneNumber}>Test Click-to-Call</button>
            <button className="btn-test sms" onClick={testSMS} disabled={!testPhoneNumber}>Test SMS</button>
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
        <div className="info-content">
          <h3>How Phone Integration Works</h3>
          <p><strong>Native Features (Always Active):</strong></p>
          <ul>
            <li><strong>Click-to-Call:</strong> Click any phone number in the CRM to open your phone dialer</li>
            <li><strong>SMS/Text:</strong> Click the button to open your messaging app</li>
            <li>Works with any carrier (Verizon, AT&T, T-Mobile, etc.)</li>
            <li>No configuration required - works immediately!</li>
          </ul>
        </div>
      </div>

      <div className="quick-links-card">
        <h3>Quick Links</h3>
        <div className="links-grid">
          <a href="/verizon-test" className="link-item" onClick={(e) => { e.preventDefault(); navigate('/verizon-test'); }}>
            <div className="link-icon">&#129514;</div>
            <div className="link-info"><h4>Full Test Page</h4><p>Comprehensive testing interface</p></div>
          </a>
          <a href="https://docs.claude.com" className="link-item" target="_blank" rel="noopener noreferrer">
            <div className="link-icon">&#128218;</div>
            <div className="link-info"><h4>Setup Guide</h4><p>Step-by-step instructions</p></div>
          </a>
        </div>
      </div>
    </div>
  );
};

export default PhoneIntegrationSection;

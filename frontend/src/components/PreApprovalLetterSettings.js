import React, { useState, useEffect } from 'react';
import { emailSignatureAPI, API_BASE_URL } from '../services/api';
import { getToken } from '../utils/tokenStore';

function PreApprovalLetterSettings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [error, setError] = useState(null);
  const [signature, setSignature] = useState(null);
  const [letterSettings, setLetterSettings] = useState({
    company_name: '',
    company_address: '',
    company_phone: '',
    company_nmls: '',
    letter_header: 'Pre-Approval Letter',
    opening_paragraph: 'This letter is to confirm that the below-named borrower(s) have been pre-approved for a mortgage loan based on a preliminary review of their credit and financial information.',
    conditions_intro: 'This pre-approval is subject to the following conditions:',
    default_conditions: [
      'Verification of employment and income',
      'Satisfactory property appraisal',
      'Clear title search',
      'Verification of assets and funds for closing',
      'No material changes to financial condition'
    ],
    closing_paragraph: 'This pre-approval is valid for 90 days from the date of this letter. Please note that this is not a commitment to lend and is subject to final underwriting approval.',
    disclaimer: 'This pre-approval letter is based on the information provided by the applicant and is subject to verification. Final loan approval is contingent upon satisfactory completion of all underwriting requirements.',
    show_nmls: true,
    show_equal_housing: true
  });

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      setLoading(true);

      // Load email signature for logo and signature info
      const signatureData = await emailSignatureAPI.get();
      setSignature(signatureData);

      // Load pre-approval letter settings
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/settings/pre-approval-letter`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (response.ok) {
        const data = await response.json();
        if (data) {
          setLetterSettings(prev => ({ ...prev, ...data }));
        }
      }
    } catch (err) {
      console.error('Error loading settings:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field, value) => {
    setLetterSettings(prev => ({ ...prev, [field]: value }));
  };

  const handleConditionChange = (index, value) => {
    const newConditions = [...letterSettings.default_conditions];
    newConditions[index] = value;
    setLetterSettings(prev => ({ ...prev, default_conditions: newConditions }));
  };

  const addCondition = () => {
    setLetterSettings(prev => ({
      ...prev,
      default_conditions: [...prev.default_conditions, '']
    }));
  };

  const removeCondition = (index) => {
    setLetterSettings(prev => ({
      ...prev,
      default_conditions: prev.default_conditions.filter((_, i) => i !== index)
    }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);

      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/settings/pre-approval-letter`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(letterSettings)
      });

      if (response.ok) {
        setSuccessMessage('Pre-approval letter settings saved successfully!');
        setTimeout(() => setSuccessMessage(''), 3000);
      } else {
        throw new Error('Failed to save settings');
      }
    } catch (err) {
      console.error('Error saving settings:', err);
      setError('Failed to save pre-approval letter settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#6b7280' }}>
        Loading pre-approval letter settings...
      </div>
    );
  }

  return (
    <div className="marketing-section">
      <h3>Pre-Approval Letter Configuration</h3>
      <p style={{ color: '#6b7280', marginBottom: '24px' }}>
        Customize the content and branding for your pre-approval letters. The company logo from your email signature will be used on the letter.
      </p>

      {error && (
        <div style={{
          background: '#fee2e2',
          color: '#991b1b',
          padding: '12px 16px',
          borderRadius: '8px',
          marginBottom: '16px'
        }}>
          {error}
        </div>
      )}

      {successMessage && (
        <div style={{
          background: '#d1fae5',
          color: '#065f46',
          padding: '12px 16px',
          borderRadius: '8px',
          marginBottom: '16px'
        }}>
          {successMessage}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        {/* Left Column - Settings Form */}
        <div>
          {/* Company Information */}
          <div style={{
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: '12px',
            padding: '20px',
            marginBottom: '20px'
          }}>
            <h4 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>🏢</span> Company Information
            </h4>

            <div style={{ display: 'grid', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Company Name
                </label>
                <input
                  type="text"
                  value={letterSettings.company_name}
                  onChange={(e) => handleChange('company_name', e.target.value)}
                  placeholder="Your Company Name"
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Company Address
                </label>
                <input
                  type="text"
                  value={letterSettings.company_address}
                  onChange={(e) => handleChange('company_address', e.target.value)}
                  placeholder="123 Main St, City, State ZIP"
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                    Phone Number
                  </label>
                  <input
                    type="text"
                    value={letterSettings.company_phone}
                    onChange={(e) => handleChange('company_phone', e.target.value)}
                    placeholder="(555) 123-4567"
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      border: '1px solid #d1d5db',
                      borderRadius: '8px',
                      fontSize: '14px'
                    }}
                  />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                    Company NMLS #
                  </label>
                  <input
                    type="text"
                    value={letterSettings.company_nmls}
                    onChange={(e) => handleChange('company_nmls', e.target.value)}
                    placeholder="123456"
                    style={{
                      width: '100%',
                      padding: '10px 12px',
                      border: '1px solid #d1d5db',
                      borderRadius: '8px',
                      fontSize: '14px'
                    }}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* Letter Content */}
          <div style={{
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: '12px',
            padding: '20px',
            marginBottom: '20px'
          }}>
            <h4 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>📝</span> Letter Content
            </h4>

            <div style={{ display: 'grid', gap: '16px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Letter Header
                </label>
                <input
                  type="text"
                  value={letterSettings.letter_header}
                  onChange={(e) => handleChange('letter_header', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Opening Paragraph
                </label>
                <textarea
                  value={letterSettings.opening_paragraph}
                  onChange={(e) => handleChange('opening_paragraph', e.target.value)}
                  rows={3}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px',
                    resize: 'vertical'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Conditions Introduction
                </label>
                <input
                  type="text"
                  value={letterSettings.conditions_intro}
                  onChange={(e) => handleChange('conditions_intro', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Default Conditions
                </label>
                {letterSettings.default_conditions.map((condition, index) => (
                  <div key={index} style={{ display: 'flex', gap: '8px', marginBottom: '8px' }}>
                    <input
                      type="text"
                      value={condition}
                      onChange={(e) => handleConditionChange(index, e.target.value)}
                      placeholder={`Condition ${index + 1}`}
                      style={{
                        flex: 1,
                        padding: '8px 12px',
                        border: '1px solid #d1d5db',
                        borderRadius: '6px',
                        fontSize: '14px'
                      }}
                    />
                    <button
                      onClick={() => removeCondition(index)}
                      style={{
                        padding: '8px 12px',
                        background: '#fee2e2',
                        color: '#991b1b',
                        border: 'none',
                        borderRadius: '6px',
                        cursor: 'pointer',
                        fontSize: '14px'
                      }}
                    >
                      ×
                    </button>
                  </div>
                ))}
                <button
                  onClick={addCondition}
                  style={{
                    padding: '8px 16px',
                    background: '#f3f4f6',
                    color: '#374151',
                    border: '1px solid #d1d5db',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontSize: '14px',
                    marginTop: '8px'
                  }}
                >
                  + Add Condition
                </button>
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Closing Paragraph
                </label>
                <textarea
                  value={letterSettings.closing_paragraph}
                  onChange={(e) => handleChange('closing_paragraph', e.target.value)}
                  rows={3}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px',
                    resize: 'vertical'
                  }}
                />
              </div>

              <div>
                <label style={{ display: 'block', fontSize: '13px', fontWeight: '500', color: '#374151', marginBottom: '6px' }}>
                  Disclaimer Text
                </label>
                <textarea
                  value={letterSettings.disclaimer}
                  onChange={(e) => handleChange('disclaimer', e.target.value)}
                  rows={2}
                  style={{
                    width: '100%',
                    padding: '10px 12px',
                    border: '1px solid #d1d5db',
                    borderRadius: '8px',
                    fontSize: '14px',
                    resize: 'vertical'
                  }}
                />
              </div>
            </div>
          </div>

          {/* Display Options */}
          <div style={{
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: '12px',
            padding: '20px',
            marginBottom: '20px'
          }}>
            <h4 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>⚙️</span> Display Options
            </h4>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={letterSettings.show_nmls}
                  onChange={(e) => handleChange('show_nmls', e.target.checked)}
                  style={{ width: '18px', height: '18px' }}
                />
                <span style={{ fontSize: '14px', color: '#374151' }}>Show NMLS number on letter</span>
              </label>

              <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer' }}>
                <input
                  type="checkbox"
                  checked={letterSettings.show_equal_housing}
                  onChange={(e) => handleChange('show_equal_housing', e.target.checked)}
                  style={{ width: '18px', height: '18px' }}
                />
                <span style={{ fontSize: '14px', color: '#374151' }}>Show Equal Housing Lender logo</span>
              </label>
            </div>
          </div>

          {/* Save Button */}
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              width: '100%',
              padding: '12px 24px',
              background: saving ? '#9ca3af' : '#c9a227',
              color: 'white',
              border: 'none',
              borderRadius: '8px',
              fontSize: '15px',
              fontWeight: '600',
              cursor: saving ? 'not-allowed' : 'pointer'
            }}
          >
            {saving ? 'Saving...' : 'Save Settings'}
          </button>
        </div>

        {/* Right Column - Preview */}
        <div>
          <div style={{
            background: '#fff',
            border: '1px solid #e5e7eb',
            borderRadius: '12px',
            padding: '20px',
            position: 'sticky',
            top: '20px'
          }}>
            <h4 style={{ margin: '0 0 16px', fontSize: '16px', fontWeight: '600', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span>👁️</span> Letter Preview
            </h4>

            {/* Letter Preview */}
            <div style={{
              background: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: '8px',
              padding: '24px',
              fontSize: '12px',
              lineHeight: '1.6',
              maxHeight: '600px',
              overflowY: 'auto'
            }}>
              {/* Logo */}
              <div style={{ textAlign: 'center', marginBottom: '20px' }}>
                {signature?.company_logo_url ? (
                  <img
                    src={signature.company_logo_url}
                    alt="Company Logo"
                    style={{ maxHeight: '60px', maxWidth: '200px', objectFit: 'contain' }}
                  />
                ) : (
                  <div style={{
                    background: '#f3f4f6',
                    padding: '20px',
                    borderRadius: '8px',
                    color: '#6b7280',
                    fontSize: '11px'
                  }}>
                    Company logo will appear here<br/>
                    <span style={{ fontSize: '10px' }}>(Set in Email Signature settings)</span>
                  </div>
                )}
              </div>

              {/* Company Info */}
              <div style={{ textAlign: 'center', marginBottom: '20px', color: '#374151' }}>
                <div style={{ fontWeight: '600' }}>{letterSettings.company_name || '[Company Name]'}</div>
                <div>{letterSettings.company_address || '[Company Address]'}</div>
                <div>{letterSettings.company_phone || '[Phone Number]'}</div>
                {letterSettings.show_nmls && letterSettings.company_nmls && (
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>NMLS #{letterSettings.company_nmls}</div>
                )}
              </div>

              {/* Date */}
              <div style={{ marginBottom: '20px', color: '#6b7280' }}>
                {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' })}
              </div>

              {/* Header */}
              <div style={{
                textAlign: 'center',
                fontSize: '16px',
                fontWeight: '700',
                marginBottom: '20px',
                color: '#1e40af'
              }}>
                {letterSettings.letter_header}
              </div>

              {/* Borrower Info Placeholder */}
              <div style={{ marginBottom: '16px' }}>
                <div><strong>Borrower(s):</strong> [Borrower Name(s)]</div>
                <div><strong>Property Address:</strong> [Property Address]</div>
                <div><strong>Pre-Approved Amount:</strong> $[Amount]</div>
                <div><strong>Loan Type:</strong> [Loan Type]</div>
              </div>

              {/* Opening Paragraph */}
              <div style={{ marginBottom: '16px', textAlign: 'justify' }}>
                {letterSettings.opening_paragraph}
              </div>

              {/* Conditions */}
              <div style={{ marginBottom: '16px' }}>
                <div style={{ marginBottom: '8px' }}>{letterSettings.conditions_intro}</div>
                <ul style={{ margin: 0, paddingLeft: '20px' }}>
                  {letterSettings.default_conditions.filter(c => c).map((condition, index) => (
                    <li key={index} style={{ marginBottom: '4px' }}>{condition}</li>
                  ))}
                </ul>
              </div>

              {/* Closing Paragraph */}
              <div style={{ marginBottom: '20px', textAlign: 'justify' }}>
                {letterSettings.closing_paragraph}
              </div>

              {/* Signature Block */}
              <div style={{ marginBottom: '20px' }}>
                <div style={{ marginBottom: '8px' }}>Sincerely,</div>
                <div style={{ marginTop: '40px', borderTop: '1px solid #000', width: '200px', paddingTop: '4px' }}>
                  <div style={{ fontWeight: '600' }}>{signature?.name || '[Loan Officer Name]'}</div>
                  <div style={{ fontSize: '11px', color: '#6b7280' }}>{signature?.title || '[Title]'}</div>
                  {signature?.nmls_id && (
                    <div style={{ fontSize: '10px', color: '#6b7280' }}>NMLS #{signature.nmls_id}</div>
                  )}
                  <div style={{ fontSize: '11px' }}>{signature?.phone || '[Phone]'}</div>
                  <div style={{ fontSize: '11px' }}>{signature?.email || '[Email]'}</div>
                </div>
              </div>

              {/* Disclaimer */}
              <div style={{
                fontSize: '9px',
                color: '#6b7280',
                borderTop: '1px solid #e5e7eb',
                paddingTop: '12px',
                fontStyle: 'italic'
              }}>
                {letterSettings.disclaimer}
              </div>

              {/* Equal Housing */}
              {letterSettings.show_equal_housing && (
                <div style={{
                  textAlign: 'center',
                  marginTop: '16px',
                  fontSize: '10px',
                  color: '#6b7280'
                }}>
                  Equal Housing Lender
                </div>
              )}
            </div>

            <p style={{
              fontSize: '11px',
              color: '#6b7280',
              marginTop: '12px',
              textAlign: 'center'
            }}>
              Signature information is pulled from your Email Signature settings (without headshot)
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default PreApprovalLetterSettings;

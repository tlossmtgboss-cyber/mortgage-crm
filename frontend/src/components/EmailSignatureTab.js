import React, { useState, useEffect, useRef } from 'react';
import { emailSignatureAPI } from '../services/api';
import './EmailSignatureTab.css';

function EmailSignatureTab() {
  const [signature, setSignature] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);
  const [successMessage, setSuccessMessage] = useState('');
  const [activeSection, setActiveSection] = useState('personal');

  const headshotInputRef = useRef(null);
  const logoInputRef = useRef(null);

  useEffect(() => {
    loadSignature();
  }, []);

  const loadSignature = async () => {
    try {
      setLoading(true);
      const data = await emailSignatureAPI.get();
      setSignature(data);
    } catch (err) {
      console.error('Error loading signature:', err);
      setError('Failed to load email signature');
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (field, value) => {
    setSignature(prev => ({ ...prev, [field]: value }));
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      setError(null);
      await emailSignatureAPI.save(signature);
      setSuccessMessage('Email signature saved successfully!');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      console.error('Error saving signature:', err);
      setError('Failed to save email signature');
    } finally {
      setSaving(false);
    }
  };

  const handleImageUpload = async (e, imageType) => {
    const file = e.target.files[0];
    if (!file) return;

    try {
      setSaving(true);
      await emailSignatureAPI.uploadImage(file, imageType);
      // Reload to get updated URLs
      await loadSignature();
      setSuccessMessage(`${imageType === 'headshot' ? 'Headshot' : 'Logo'} uploaded successfully!`);
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      console.error('Error uploading image:', err);
      setError(`Failed to upload ${imageType}`);
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="signature-loading">Loading email signature...</div>;
  }

  const sections = [
    { id: 'personal', label: 'Personal Info', icon: '👤' },
    { id: 'contact', label: 'Contact', icon: '📞' },
    { id: 'links', label: 'Links', icon: '🔗' },
    { id: 'social', label: 'Social', icon: '📱' },
    { id: 'branding', label: 'Branding', icon: '🎨' },
  ];

  return (
    <div className="email-signature-tab">
      <div className="signature-header">
        <h2>Email Signature</h2>
        <p className="signature-description">
          Customize your professional email signature. Fields left empty will not appear in your signature.
        </p>
      </div>

      {error && <div className="signature-error">{error}</div>}
      {successMessage && <div className="signature-success">{successMessage}</div>}

      <div className="signature-layout">
        {/* Left: Form */}
        <div className="signature-form-container">
          {/* Section Tabs */}
          <div className="signature-section-tabs">
            {sections.map(section => (
              <button
                key={section.id}
                className={`section-tab ${activeSection === section.id ? 'active' : ''}`}
                onClick={() => setActiveSection(section.id)}
              >
                <span className="section-icon">{section.icon}</span>
                {section.label}
              </button>
            ))}
          </div>

          {/* Personal Info Section */}
          {activeSection === 'personal' && (
            <div className="signature-section">
              <h3>Personal Information</h3>

              <div className="image-upload-row">
                <div className="image-upload-box">
                  <label>Headshot Photo</label>
                  <div
                    className="image-preview headshot-preview"
                    onClick={() => headshotInputRef.current?.click()}
                  >
                    {signature?.headshot_url ? (
                      <img src={signature.headshot_url} alt="Headshot" />
                    ) : (
                      <div className="upload-placeholder">
                        <span className="upload-icon">📷</span>
                        <span>Click to upload</span>
                      </div>
                    )}
                  </div>
                  <input
                    ref={headshotInputRef}
                    type="file"
                    accept="image/*"
                    onChange={(e) => handleImageUpload(e, 'headshot')}
                    style={{ display: 'none' }}
                  />
                </div>

                <div className="image-upload-box">
                  <label>Company Logo</label>
                  <div
                    className="image-preview logo-preview"
                    onClick={() => logoInputRef.current?.click()}
                  >
                    {signature?.company_logo_url ? (
                      <img src={signature.company_logo_url} alt="Company Logo" />
                    ) : (
                      <div className="upload-placeholder">
                        <span className="upload-icon">🏢</span>
                        <span>Click to upload</span>
                      </div>
                    )}
                  </div>
                  <input
                    ref={logoInputRef}
                    type="file"
                    accept="image/*"
                    onChange={(e) => handleImageUpload(e, 'logo')}
                    style={{ display: 'none' }}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>First Name</label>
                  <input
                    type="text"
                    value={signature?.first_name || ''}
                    onChange={(e) => handleChange('first_name', e.target.value)}
                    placeholder="Tim"
                  />
                </div>
                <div className="form-group">
                  <label>Last Name</label>
                  <input
                    type="text"
                    value={signature?.last_name || ''}
                    onChange={(e) => handleChange('last_name', e.target.value)}
                    placeholder="Loss"
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Team Name</label>
                <input
                  type="text"
                  value={signature?.team_name || ''}
                  onChange={(e) => handleChange('team_name', e.target.value)}
                  placeholder="Tim Loss Team"
                />
              </div>

              <div className="form-group">
                <label>Title</label>
                <input
                  type="text"
                  value={signature?.title || ''}
                  onChange={(e) => handleChange('title', e.target.value)}
                  placeholder="Branch Manager"
                />
              </div>
            </div>
          )}

          {/* Contact Section */}
          {activeSection === 'contact' && (
            <div className="signature-section">
              <h3>Contact Information</h3>

              <div className="form-group">
                <label>Email Address</label>
                <input
                  type="email"
                  value={signature?.email || ''}
                  onChange={(e) => handleChange('email', e.target.value)}
                  placeholder="tloss@cmghomeloans.com"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Office Phone</label>
                  <input
                    type="tel"
                    value={signature?.office_phone || ''}
                    onChange={(e) => handleChange('office_phone', e.target.value)}
                    placeholder="(843) 834-5251"
                  />
                </div>
                <div className="form-group">
                  <label>Cell Phone</label>
                  <input
                    type="tel"
                    value={signature?.cell_phone || ''}
                    onChange={(e) => handleChange('cell_phone', e.target.value)}
                    placeholder="(843) 834-4997"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Fax</label>
                <input
                  type="tel"
                  value={signature?.fax || ''}
                  onChange={(e) => handleChange('fax', e.target.value)}
                  placeholder="(854) 444-8067"
                />
              </div>

              <div className="form-group">
                <label>Address</label>
                <textarea
                  value={signature?.address || ''}
                  onChange={(e) => handleChange('address', e.target.value)}
                  placeholder="975 Johnnie Dodds Blvd. Suite A, Mt. Pleasant, SC 29464"
                  rows={2}
                />
              </div>
            </div>
          )}

          {/* Links Section */}
          {activeSection === 'links' && (
            <div className="signature-section">
              <h3>Quick Links</h3>

              <div className="form-group">
                <label>Apply Now URL</label>
                <input
                  type="url"
                  value={signature?.apply_now_url || ''}
                  onChange={(e) => handleChange('apply_now_url', e.target.value)}
                  placeholder="https://apply.cmghomeloans.com/tloss"
                />
              </div>

              <div className="form-group">
                <label>Website URL</label>
                <input
                  type="url"
                  value={signature?.website_url || ''}
                  onChange={(e) => handleChange('website_url', e.target.value)}
                  placeholder="https://www.cmghomeloans.com/tloss"
                />
              </div>

              <div className="form-group">
                <label>Document Upload URL</label>
                <input
                  type="url"
                  value={signature?.doc_upload_url || ''}
                  onChange={(e) => handleChange('doc_upload_url', e.target.value)}
                  placeholder="https://upload.cmghomeloans.com/tloss"
                />
              </div>

              <div className="form-group">
                <label>Schedule Appointment URL</label>
                <input
                  type="url"
                  value={signature?.schedule_url || ''}
                  onChange={(e) => handleChange('schedule_url', e.target.value)}
                  placeholder="https://calendly.com/tloss"
                />
              </div>
            </div>
          )}

          {/* Social Section */}
          {activeSection === 'social' && (
            <div className="signature-section">
              <h3>Social Media</h3>

              <div className="form-group">
                <label>LinkedIn URL</label>
                <input
                  type="url"
                  value={signature?.linkedin_url || ''}
                  onChange={(e) => handleChange('linkedin_url', e.target.value)}
                  placeholder="https://linkedin.com/in/timloss"
                />
              </div>

              <div className="form-group">
                <label>Facebook URL</label>
                <input
                  type="url"
                  value={signature?.facebook_url || ''}
                  onChange={(e) => handleChange('facebook_url', e.target.value)}
                  placeholder="https://facebook.com/timloss"
                />
              </div>

              <div className="form-group">
                <label>Instagram URL</label>
                <input
                  type="url"
                  value={signature?.instagram_url || ''}
                  onChange={(e) => handleChange('instagram_url', e.target.value)}
                  placeholder="https://instagram.com/timloss"
                />
              </div>

              <div className="form-group">
                <label>Twitter/X URL</label>
                <input
                  type="url"
                  value={signature?.twitter_url || ''}
                  onChange={(e) => handleChange('twitter_url', e.target.value)}
                  placeholder="https://twitter.com/timloss"
                />
              </div>
            </div>
          )}

          {/* Branding Section */}
          {activeSection === 'branding' && (
            <div className="signature-section">
              <h3>Branding & Licensing</h3>

              <div className="form-row">
                <div className="form-group">
                  <label>NMLS #</label>
                  <input
                    type="text"
                    value={signature?.nmls_id || ''}
                    onChange={(e) => handleChange('nmls_id', e.target.value)}
                    placeholder="187037"
                  />
                </div>
                <div className="form-group">
                  <label>Branch NMLS #</label>
                  <input
                    type="text"
                    value={signature?.branch_nmls_id || ''}
                    onChange={(e) => handleChange('branch_nmls_id', e.target.value)}
                    placeholder="1594871"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Corporate NMLS #</label>
                <input
                  type="text"
                  value={signature?.corporate_nmls_id || ''}
                  onChange={(e) => handleChange('corporate_nmls_id', e.target.value)}
                  placeholder="1820"
                />
              </div>

              <div className="form-group">
                <label>Tagline</label>
                <input
                  type="text"
                  value={signature?.tagline || ''}
                  onChange={(e) => handleChange('tagline', e.target.value)}
                  placeholder="SIMPLIFIED. TRUSTED. COMMITTED."
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Primary Color</label>
                  <div className="color-input-wrapper">
                    <input
                      type="color"
                      value={signature?.primary_color || '#006B6B'}
                      onChange={(e) => handleChange('primary_color', e.target.value)}
                    />
                    <input
                      type="text"
                      value={signature?.primary_color || '#006B6B'}
                      onChange={(e) => handleChange('primary_color', e.target.value)}
                      className="color-text-input"
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label>Secondary Color</label>
                  <div className="color-input-wrapper">
                    <input
                      type="color"
                      value={signature?.secondary_color || '#1B3A4B'}
                      onChange={(e) => handleChange('secondary_color', e.target.value)}
                    />
                    <input
                      type="text"
                      value={signature?.secondary_color || '#1B3A4B'}
                      onChange={(e) => handleChange('secondary_color', e.target.value)}
                      className="color-text-input"
                    />
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Save Button */}
          <div className="signature-actions">
            <button
              className="btn-save-signature"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Signature'}
            </button>
          </div>
        </div>

        {/* Right: Preview */}
        <div className="signature-preview-container">
          <h3>Live Preview</h3>
          <div className="signature-preview-box">
            <EmailSignaturePreview signature={signature} />
          </div>
          <p className="preview-note">
            This is how your signature will appear at the bottom of your emails.
          </p>
        </div>
      </div>
    </div>
  );
}

// Inline Preview Component
function EmailSignaturePreview({ signature }) {
  if (!signature) return null;

  const primaryColor = signature.primary_color || '#006B6B';
  const secondaryColor = signature.secondary_color || '#1B3A4B';

  // Check if any content exists
  const hasContent = signature.full_name || signature.email || signature.office_phone ||
                     signature.cell_phone || signature.address;

  if (!hasContent) {
    return (
      <div className="preview-empty">
        <p>Fill in the form to see your signature preview</p>
      </div>
    );
  }

  return (
    <div className="signature-preview">
      <table cellPadding="0" cellSpacing="0" style={{ fontFamily: 'Arial, sans-serif', fontSize: '13px', color: '#333', maxWidth: '500px' }}>
        <tbody>
          <tr>
            {signature.headshot_url && (
              <td style={{ verticalAlign: 'top', paddingRight: '15px' }}>
                <img
                  src={signature.headshot_url}
                  alt={signature.full_name || 'Photo'}
                  style={{
                    width: '100px',
                    height: '100px',
                    borderRadius: '50%',
                    objectFit: 'cover',
                    border: `2px solid ${primaryColor}`
                  }}
                />
              </td>
            )}
            <td style={{ verticalAlign: 'top' }}>
              <table cellPadding="0" cellSpacing="0">
                <tbody>
                  {signature.full_name && (
                    <tr>
                      <td style={{ fontSize: '18px', fontWeight: 'bold', color: primaryColor }}>
                        {signature.full_name}
                      </td>
                    </tr>
                  )}
                  {signature.team_name && (
                    <tr>
                      <td style={{ fontSize: '13px', color: '#666' }}>{signature.team_name}</td>
                    </tr>
                  )}
                  {signature.title && (
                    <tr>
                      <td style={{ fontSize: '13px', color: '#666' }}>{signature.title}</td>
                    </tr>
                  )}
                  <tr><td style={{ height: '8px' }}></td></tr>
                  {signature.email && (
                    <tr>
                      <td>
                        <a href={`mailto:${signature.email}`} style={{ color: primaryColor, textDecoration: 'none' }}>
                          ✉ {signature.email}
                        </a>
                      </td>
                    </tr>
                  )}
                  {(signature.office_phone || signature.cell_phone || signature.fax) && (
                    <tr>
                      <td>
                        {signature.office_phone && <span style={{ color: '#333' }}>☎ {signature.office_phone}</span>}
                        {signature.office_phone && signature.cell_phone && ' | '}
                        {signature.cell_phone && <span style={{ color: '#333' }}>📱 {signature.cell_phone}</span>}
                        {(signature.office_phone || signature.cell_phone) && signature.fax && ' | '}
                        {signature.fax && <span style={{ color: '#333' }}>📠 {signature.fax}</span>}
                      </td>
                    </tr>
                  )}
                  {signature.address && (
                    <tr>
                      <td style={{ paddingTop: '5px' }}>📍 {signature.address}</td>
                    </tr>
                  )}
                  <tr><td style={{ height: '10px' }}></td></tr>
                  {(signature.apply_now_url || signature.website_url || signature.doc_upload_url || signature.schedule_url) && (
                    <tr>
                      <td>
                        {signature.apply_now_url && (
                          <a href={signature.apply_now_url} style={{ color: primaryColor, textDecoration: 'none', fontWeight: 'bold', marginRight: '10px' }}>
                            APPLY NOW
                          </a>
                        )}
                        {signature.website_url && (
                          <a href={signature.website_url} style={{ color: primaryColor, textDecoration: 'none', fontWeight: 'bold', marginRight: '10px' }}>
                            MYSITE
                          </a>
                        )}
                        {signature.doc_upload_url && (
                          <a href={signature.doc_upload_url} style={{ color: primaryColor, textDecoration: 'none', fontWeight: 'bold', marginRight: '10px' }}>
                            DOC UPLOAD
                          </a>
                        )}
                        {signature.schedule_url && (
                          <a href={signature.schedule_url} style={{ color: primaryColor, textDecoration: 'none', fontWeight: 'bold' }}>
                            SCHEDULE
                          </a>
                        )}
                      </td>
                    </tr>
                  )}
                  {(signature.linkedin_url || signature.facebook_url || signature.instagram_url || signature.twitter_url) && (
                    <tr>
                      <td style={{ paddingTop: '8px' }}>
                        {signature.linkedin_url && (
                          <a href={signature.linkedin_url} style={{ marginRight: '8px' }}>
                            <img src="https://cdn-icons-png.flaticon.com/24/174/174857.png" alt="LinkedIn" width="20" height="20" />
                          </a>
                        )}
                        {signature.facebook_url && (
                          <a href={signature.facebook_url} style={{ marginRight: '8px' }}>
                            <img src="https://cdn-icons-png.flaticon.com/24/733/733547.png" alt="Facebook" width="20" height="20" />
                          </a>
                        )}
                        {signature.instagram_url && (
                          <a href={signature.instagram_url} style={{ marginRight: '8px' }}>
                            <img src="https://cdn-icons-png.flaticon.com/24/2111/2111463.png" alt="Instagram" width="20" height="20" />
                          </a>
                        )}
                        {signature.twitter_url && (
                          <a href={signature.twitter_url}>
                            <img src="https://cdn-icons-png.flaticon.com/24/733/733579.png" alt="Twitter" width="20" height="20" />
                          </a>
                        )}
                      </td>
                    </tr>
                  )}
                  <tr><td style={{ height: '10px' }}></td></tr>
                  {(signature.nmls_id || signature.branch_nmls_id || signature.corporate_nmls_id) && (
                    <tr>
                      <td style={{ fontSize: '10px', color: '#888' }}>
                        {signature.nmls_id && `NMLS# ${signature.nmls_id}`}
                        {signature.nmls_id && signature.branch_nmls_id && ' | '}
                        {signature.branch_nmls_id && `BRANCH NMLS# ${signature.branch_nmls_id}`}
                        {(signature.nmls_id || signature.branch_nmls_id) && signature.corporate_nmls_id && ' | '}
                        {signature.corporate_nmls_id && `CORPORATE NMLS# ${signature.corporate_nmls_id}`}
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </td>
          </tr>
          {signature.company_logo_url && (
            <tr>
              <td colSpan="2" style={{ paddingTop: '10px' }}>
                <img
                  src={signature.company_logo_url}
                  alt="Company Logo"
                  style={{ maxHeight: '50px', maxWidth: '200px' }}
                />
                {signature.tagline && (
                  <span style={{
                    background: secondaryColor,
                    color: 'white',
                    padding: '5px 15px',
                    fontSize: '11px',
                    fontWeight: 'bold',
                    marginLeft: '10px'
                  }}>
                    {signature.tagline}
                  </span>
                )}
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

export default EmailSignatureTab;

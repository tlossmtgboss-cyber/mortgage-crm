import React, { useState, useEffect } from 'react';
import './Step2ProfileSetup.css';

const Step2ProfileSetup = ({ data, onChange, inviteData }) => {
  const [formData, setFormData] = useState({
    first_name: inviteData?.first_name || '',
    last_name: inviteData?.last_name || '',
    phone: '',
    profile_photo: null,
    department: '',
    job_title: '',
    preferred_contact_method: 'email',
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'America/New_York',
    ...data
  });

  const [errors, setErrors] = useState({});
  const [previewUrl, setPreviewUrl] = useState(null);

  const departments = [
    { value: 'sales', label: 'Sales' },
    { value: 'processing', label: 'Loan Processing' },
    { value: 'underwriting', label: 'Underwriting' },
    { value: 'closing', label: 'Closing' },
    { value: 'management', label: 'Management' },
    { value: 'admin', label: 'Administration' }
  ];

  const timezones = [
    { value: 'America/New_York', label: 'Eastern Time (ET)' },
    { value: 'America/Chicago', label: 'Central Time (CT)' },
    { value: 'America/Denver', label: 'Mountain Time (MT)' },
    { value: 'America/Los_Angeles', label: 'Pacific Time (PT)' },
    { value: 'America/Phoenix', label: 'Arizona (MST)' },
    { value: 'America/Anchorage', label: 'Alaska Time (AKT)' },
    { value: 'Pacific/Honolulu', label: 'Hawaii Time (HST)' }
  ];

  useEffect(() => {
    onChange(formData);
  }, [formData]);

  const handleChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));

    if (errors[field]) {
      setErrors(prev => ({
        ...prev,
        [field]: null
      }));
    }
  };

  const handlePhoneChange = (value) => {
    const cleaned = value.replace(/\D/g, '');
    let formatted = cleaned;

    if (cleaned.length >= 6) {
      formatted = `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6, 10)}`;
    } else if (cleaned.length >= 3) {
      formatted = `(${cleaned.slice(0, 3)}) ${cleaned.slice(3)}`;
    }

    handleChange('phone', formatted);
  };

  const handlePhotoUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        setErrors(prev => ({
          ...prev,
          profile_photo: 'Image must be less than 5MB'
        }));
        return;
      }

      if (!file.type.startsWith('image/')) {
        setErrors(prev => ({
          ...prev,
          profile_photo: 'Please select an image file'
        }));
        return;
      }

      const reader = new FileReader();
      reader.onloadend = () => {
        setPreviewUrl(reader.result);
        handleChange('profile_photo', reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.first_name?.trim()) {
      newErrors.first_name = 'First name is required';
    }

    if (!formData.last_name?.trim()) {
      newErrors.last_name = 'Last name is required';
    }

    const phoneDigits = formData.phone?.replace(/\D/g, '') || '';
    if (phoneDigits && phoneDigits.length !== 10) {
      newErrors.phone = 'Phone number must be 10 digits';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  return (
    <div className="step2-profile-setup">
      <h2>Complete Your Profile</h2>
      <p className="step-description">
        Let's set up your profile so your team can identify and contact you easily.
      </p>

      <div className="form-section">
        <div className="photo-upload-section">
          <div className="photo-preview">
            {previewUrl || formData.profile_photo ? (
              <img src={previewUrl || formData.profile_photo} alt="Profile preview" />
            ) : (
              <div className="photo-placeholder">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                  <circle cx="12" cy="7" r="4" />
                </svg>
              </div>
            )}
          </div>
          <div className="photo-upload-controls">
            <label htmlFor="photo-upload" className="upload-button">
              Choose Photo
            </label>
            <input
              id="photo-upload"
              type="file"
              accept="image/*"
              onChange={handlePhotoUpload}
              hidden
            />
            <span className="photo-hint">Optional. Max 5MB. JPG, PNG, or GIF.</span>
          </div>
          {errors.profile_photo && (
            <span className="error-message">{errors.profile_photo}</span>
          )}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="first_name">First Name *</label>
            <input
              id="first_name"
              type="text"
              value={formData.first_name}
              onChange={(e) => handleChange('first_name', e.target.value)}
              className={errors.first_name ? 'error' : ''}
              placeholder="John"
            />
            {errors.first_name && <span className="error-message">{errors.first_name}</span>}
          </div>

          <div className="form-group">
            <label htmlFor="last_name">Last Name *</label>
            <input
              id="last_name"
              type="text"
              value={formData.last_name}
              onChange={(e) => handleChange('last_name', e.target.value)}
              className={errors.last_name ? 'error' : ''}
              placeholder="Smith"
            />
            {errors.last_name && <span className="error-message">{errors.last_name}</span>}
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="phone">Phone Number</label>
          <input
            id="phone"
            type="tel"
            value={formData.phone}
            onChange={(e) => handlePhoneChange(e.target.value)}
            className={errors.phone ? 'error' : ''}
            placeholder="(555) 123-4567"
            maxLength="14"
          />
          {errors.phone && <span className="error-message">{errors.phone}</span>}
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="department">Department</label>
            <select
              id="department"
              value={formData.department}
              onChange={(e) => handleChange('department', e.target.value)}
            >
              <option value="">Select department</option>
              {departments.map(dept => (
                <option key={dept.value} value={dept.value}>{dept.label}</option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="job_title">Job Title</label>
            <input
              id="job_title"
              type="text"
              value={formData.job_title}
              onChange={(e) => handleChange('job_title', e.target.value)}
              placeholder="Loan Officer"
            />
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label htmlFor="preferred_contact_method">Preferred Contact Method</label>
            <select
              id="preferred_contact_method"
              value={formData.preferred_contact_method}
              onChange={(e) => handleChange('preferred_contact_method', e.target.value)}
            >
              <option value="email">Email</option>
              <option value="phone">Phone</option>
              <option value="sms">SMS/Text</option>
            </select>
          </div>

          <div className="form-group">
            <label htmlFor="timezone">Your Timezone</label>
            <select
              id="timezone"
              value={formData.timezone}
              onChange={(e) => handleChange('timezone', e.target.value)}
            >
              {timezones.map(tz => (
                <option key={tz.value} value={tz.value}>{tz.label}</option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Step2ProfileSetup;

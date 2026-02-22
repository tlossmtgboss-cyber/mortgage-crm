import React, { useState, useEffect } from 'react';
import VerificationModal from './VerificationModal';
import './Step1Registration.css';
import { toast } from '../../../utils/toast';

const Step1Registration = ({ data, onChange }) => {
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    nmls_number: '',
    business_address: '',
    current_role: '',
    business_hours: {
      monday: { open: '09:00', close: '17:00' },
      tuesday: { open: '09:00', close: '17:00' },
      wednesday: { open: '09:00', close: '17:00' },
      thursday: { open: '09:00', close: '17:00' },
      friday: { open: '09:00', close: '17:00' },
      saturday: { closed: true },
      sunday: { closed: true }
    },
    email_verified: false,
    phone_verified: false,
    ...data
  });

  const [errors, setErrors] = useState({});
  const [showEmailModal, setShowEmailModal] = useState(false);
  const [showPhoneModal, setShowPhoneModal] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    onChange(formData);
  }, [formData]);

  const handleChange = (field, value) => {
    setFormData(prev => ({
      ...prev,
      [field]: value
    }));

    // Clear error when user starts typing
    if (errors[field]) {
      setErrors(prev => ({
        ...prev,
        [field]: null
      }));
    }
  };

  const handlePhoneChange = (value) => {
    // Auto-format phone number
    const cleaned = value.replace(/\D/g, '');
    let formatted = cleaned;

    if (cleaned.length >= 6) {
      formatted = `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6, 10)}`;
    } else if (cleaned.length >= 3) {
      formatted = `(${cleaned.slice(0, 3)}) ${cleaned.slice(3)}`;
    }

    handleChange('phone', formatted);
  };

  const handleBusinessHoursChange = (day, field, value) => {
    setFormData(prev => ({
      ...prev,
      business_hours: {
        ...prev.business_hours,
        [day]: {
          ...prev.business_hours[day],
          [field]: value
        }
      }
    }));
  };

  const validateForm = () => {
    const newErrors = {};

    if (!formData.first_name || formData.first_name.trim().length === 0) {
      newErrors.first_name = 'First name is required';
    }

    if (!formData.last_name || formData.last_name.trim().length === 0) {
      newErrors.last_name = 'Last name is required';
    }

    if (!formData.email || !formData.email.includes('@')) {
      newErrors.email = 'Valid email is required';
    }

    const phoneDigits = formData.phone.replace(/\D/g, '');
    if (!phoneDigits || phoneDigits.length !== 10) {
      newErrors.phone = 'Phone number must be 10 digits';
    }

    if (!formData.nmls_number || !/^\d+$/.test(formData.nmls_number)) {
      newErrors.nmls_number = 'NMLS number must contain only digits';
    }

    if (!formData.business_address || formData.business_address.trim().length === 0) {
      newErrors.business_address = 'Business address is required';
    }

    if (!formData.current_role || formData.current_role.trim().length === 0) {
      newErrors.current_role = 'Current role is required';
    }

    if (!formData.email_verified) {
      newErrors.email_verified = 'Please verify your email';
    }

    if (!formData.phone_verified) {
      newErrors.phone_verified = 'Please verify your phone number';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const sendEmailVerification = async () => {
    if (!formData.email || !formData.email.includes('@')) {
      setErrors(prev => ({
        ...prev,
        email: 'Please enter a valid email address first'
      }));
      return;
    }

    setIsSubmitting(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('https://api.perenniaai.com/api/v1/onboarding/step-1/send-email-verification', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ email: formData.email })
      });

      if (response.ok) {
        setShowEmailModal(true);
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to send verification email');
      }
    } catch (error) {
      console.error('Error sending email verification:', error);
      toast.error('Failed to send verification email');
    } finally {
      setIsSubmitting(false);
    }
  };

  const sendPhoneVerification = async () => {
    const phoneDigits = formData.phone.replace(/\D/g, '');
    if (!phoneDigits || phoneDigits.length !== 10) {
      setErrors(prev => ({
        ...prev,
        phone: 'Please enter a valid 10-digit phone number first'
      }));
      return;
    }

    setIsSubmitting(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('https://api.perenniaai.com/api/v1/onboarding/step-1/send-sms-verification', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ phone: formData.phone })
      });

      if (response.ok) {
        setShowPhoneModal(true);
      } else {
        const error = await response.json();
        toast.error(error.detail || 'Failed to send verification SMS');
      }
    } catch (error) {
      console.error('Error sending SMS verification:', error);
      toast.error('Failed to send verification SMS');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleEmailVerified = () => {
    setFormData(prev => ({
      ...prev,
      email_verified: true
    }));
    setShowEmailModal(false);
    setErrors(prev => {
      const newErrors = { ...prev };
      delete newErrors.email_verified;
      return newErrors;
    });
  };

  const handlePhoneVerified = () => {
    setFormData(prev => ({
      ...prev,
      phone_verified: true
    }));
    setShowPhoneModal(false);
    setErrors(prev => {
      const newErrors = { ...prev };
      delete newErrors.phone_verified;
      return newErrors;
    });
  };

  return (
    <div className="step1-registration">
      <h2>Basic Information</h2>
      <p className="step-description">
        Let's start with your basic contact and business information.
      </p>

      <div className="form-section">
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="first_name">First Name *</label>
            <input
              id="first_name"
              type="text"
              value={formData.first_name}
              onChange={(e) => handleChange('first_name', e.target.value)}
              className={errors.first_name ? 'error' : ''}
              placeholder="First name"
            />
            {errors.first_name && <span className="error-text">{errors.first_name}</span>}
          </div>
          <div className="form-group">
            <label htmlFor="last_name">Last Name *</label>
            <input
              id="last_name"
              type="text"
              value={formData.last_name}
              onChange={(e) => handleChange('last_name', e.target.value)}
              className={errors.last_name ? 'error' : ''}
              placeholder="Last name"
            />
            {errors.last_name && <span className="error-text">{errors.last_name}</span>}
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="email">Email Address *</label>
          <div className="input-with-button">
            <input
              id="email"
              type="email"
              value={formData.email}
              onChange={(e) => handleChange('email', e.target.value)}
              className={errors.email ? 'error' : ''}
              placeholder="email@example.com"
            />
            <button
              type="button"
              onClick={sendEmailVerification}
              disabled={isSubmitting || formData.email_verified}
              className={formData.email_verified ? 'verified' : ''}
            >
              {formData.email_verified ? '✓ Verified' : 'Verify'}
            </button>
          </div>
          {errors.email && <span className="error-message">{errors.email}</span>}
          {errors.email_verified && <span className="error-message">{errors.email_verified}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="phone">Phone Number *</label>
          <div className="input-with-button">
            <input
              id="phone"
              type="tel"
              value={formData.phone}
              onChange={(e) => handlePhoneChange(e.target.value)}
              className={errors.phone ? 'error' : ''}
              placeholder="(555) 123-4567"
              maxLength="14"
            />
            <button
              type="button"
              onClick={sendPhoneVerification}
              disabled={isSubmitting || formData.phone_verified}
              className={formData.phone_verified ? 'verified' : ''}
            >
              {formData.phone_verified ? '✓ Verified' : 'Verify'}
            </button>
          </div>
          {errors.phone && <span className="error-message">{errors.phone}</span>}
          {errors.phone_verified && <span className="error-message">{errors.phone_verified}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="nmls_number">NMLS Number *</label>
          <input
            id="nmls_number"
            type="text"
            value={formData.nmls_number}
            onChange={(e) => handleChange('nmls_number', e.target.value)}
            className={errors.nmls_number ? 'error' : ''}
            placeholder="123456"
          />
          {errors.nmls_number && <span className="error-message">{errors.nmls_number}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="business_address">Business Address *</label>
          <textarea
            id="business_address"
            value={formData.business_address}
            onChange={(e) => handleChange('business_address', e.target.value)}
            className={errors.business_address ? 'error' : ''}
            placeholder="123 Main St, Suite 100, City, State 12345"
            rows="3"
          />
          {errors.business_address && <span className="error-message">{errors.business_address}</span>}
        </div>

        <div className="form-group">
          <label htmlFor="current_role">Current Role *</label>
          <select
            id="current_role"
            value={formData.current_role}
            onChange={(e) => handleChange('current_role', e.target.value)}
            className={errors.current_role ? 'error' : ''}
          >
            <option value="">Select your role</option>
            <option value="Loan Officer">Loan Officer</option>
            <option value="Loan Processor">Loan Processor</option>
            <option value="Branch Manager">Branch Manager</option>
            <option value="Owner">Owner</option>
            <option value="Other">Other</option>
          </select>
          {errors.current_role && <span className="error-message">{errors.current_role}</span>}
        </div>
      </div>

      <div className="form-section">
        <h3>Business Hours</h3>
        <p className="section-description">Set your typical business hours for each day of the week.</p>

        <div className="business-hours-grid">
          {['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map(day => (
            <div key={day} className="business-hours-row">
              <label className="day-label">
                {day.charAt(0).toUpperCase() + day.slice(1)}
              </label>

              <label className="checkbox-wrapper">
                <input
                  type="checkbox"
                  checked={formData.business_hours[day]?.closed || false}
                  onChange={(e) => {
                    if (e.target.checked) {
                      handleBusinessHoursChange(day, 'closed', true);
                      setFormData(prev => {
                        const newHours = { ...prev.business_hours };
                        delete newHours[day].open;
                        delete newHours[day].close;
                        return {
                          ...prev,
                          business_hours: newHours
                        };
                      });
                    } else {
                      setFormData(prev => ({
                        ...prev,
                        business_hours: {
                          ...prev.business_hours,
                          [day]: { open: '09:00', close: '17:00' }
                        }
                      }));
                    }
                  }}
                />
                Closed
              </label>

              {!formData.business_hours[day]?.closed && (
                <>
                  <input
                    type="time"
                    value={formData.business_hours[day]?.open || '09:00'}
                    onChange={(e) => handleBusinessHoursChange(day, 'open', e.target.value)}
                    className="time-input"
                  />
                  <span className="time-separator">to</span>
                  <input
                    type="time"
                    value={formData.business_hours[day]?.close || '17:00'}
                    onChange={(e) => handleBusinessHoursChange(day, 'close', e.target.value)}
                    className="time-input"
                  />
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      {showEmailModal && (
        <VerificationModal
          type="email"
          contact={formData.email}
          onClose={() => setShowEmailModal(false)}
          onVerified={handleEmailVerified}
        />
      )}

      {showPhoneModal && (
        <VerificationModal
          type="phone"
          contact={formData.phone}
          onClose={() => setShowPhoneModal(false)}
          onVerified={handlePhoneVerified}
        />
      )}
    </div>
  );
};

export default Step1Registration;

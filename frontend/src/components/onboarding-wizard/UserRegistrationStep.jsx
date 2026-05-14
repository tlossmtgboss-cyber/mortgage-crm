import React from 'react';

const UserRegistrationStep = ({ formData, setFormData }) => {
  const handleInputChange = (field, value) => {
    setFormData(prevData => ({
      ...prevData,
      [field]: value
    }));
    const updatedData = { ...formData, [field]: value };
    localStorage.setItem('onboarding_user_registration', JSON.stringify(updatedData));
  };

  const isFormValid = () => {
    return formData.firstName &&
           formData.lastName &&
           formData.userEmail &&
           formData.userPhone &&
           formData.businessAddress &&
           formData.currentRole;
  };

  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">👤</div>
        <h2>User Registration</h2>
        <p className="step-description">
          Let's start by setting up your account with your basic information.
        </p>
      </div>

      <div className="registration-form">
        <div className="form-row">
          <div className="form-group">
            <label htmlFor="firstName">First Name *</label>
            <input
              type="text"
              id="firstName"
              placeholder="First name"
              value={formData.firstName}
              onChange={(e) => handleInputChange('firstName', e.target.value)}
              className="form-input"
            />
          </div>
          <div className="form-group">
            <label htmlFor="lastName">Last Name *</label>
            <input
              type="text"
              id="lastName"
              placeholder="Last name"
              value={formData.lastName}
              onChange={(e) => handleInputChange('lastName', e.target.value)}
              className="form-input"
            />
          </div>
        </div>

        <div className="form-group">
          <label htmlFor="userEmail">Email Address *</label>
          <input
            type="email"
            id="userEmail"
            placeholder="your.email@company.com"
            value={formData.userEmail}
            onChange={(e) => handleInputChange('userEmail', e.target.value)}
            className="form-input"
          />
        </div>

        <div className="form-group">
          <label htmlFor="userPhone">Phone Number *</label>
          <input
            type="tel"
            id="userPhone"
            placeholder="(555) 123-4567"
            value={formData.userPhone}
            onChange={(e) => handleInputChange('userPhone', e.target.value)}
            className="form-input"
          />
        </div>

        <div className="form-group">
          <label htmlFor="businessAddress">Business Address *</label>
          <textarea
            id="businessAddress"
            placeholder="Enter your business address"
            value={formData.businessAddress}
            onChange={(e) => handleInputChange('businessAddress', e.target.value)}
            className="form-textarea"
            rows="3"
          />
        </div>

        <div className="form-group">
          <label htmlFor="currentRole">Current Role *</label>
          <select
            id="currentRole"
            value={formData.currentRole}
            onChange={(e) => handleInputChange('currentRole', e.target.value)}
            className="form-select"
          >
            <option value="">Select your role</option>
            <option value="Loan Officer">Loan Officer</option>
            <option value="Branch Manager">Branch Manager</option>
            <option value="Loan Processor">Loan Processor</option>
            <option value="Underwriter">Underwriter</option>
            <option value="Operations Manager">Operations Manager</option>
            <option value="Sales Manager">Sales Manager</option>
            <option value="Executive">Executive</option>
            <option value="Other">Other</option>
          </select>
        </div>

        <div className="form-group-row">
          <div className="form-group">
            <label htmlFor="businessHoursStart">Business Hours Start</label>
            <input
              type="time"
              id="businessHoursStart"
              value={formData.businessHoursStart}
              onChange={(e) => handleInputChange('businessHoursStart', e.target.value)}
              className="form-input"
            />
          </div>

          <div className="form-group">
            <label htmlFor="businessHoursEnd">Business Hours End</label>
            <input
              type="time"
              id="businessHoursEnd"
              value={formData.businessHoursEnd}
              onChange={(e) => handleInputChange('businessHoursEnd', e.target.value)}
              className="form-input"
            />
          </div>
        </div>

        <div className="form-info">
          <span className="info-icon">ℹ️</span>
          <p>Your progress is automatically saved. You can return to complete this later.</p>
        </div>

        {!isFormValid() && (
          <div className="form-warning">
            <span className="warning-icon">⚠️</span>
            <p>Please fill in all required fields (*) to continue.</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default UserRegistrationStep;

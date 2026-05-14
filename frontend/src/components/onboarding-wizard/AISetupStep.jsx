import React from 'react';

const AISetupStep = ({ formData }) => {
  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🤖</div>
        <h2>AI Receptionist Setup</h2>
        <p className="step-description">
          Configure your Smart AI Receptionist with phone number, voice selection, and call routing rules.
        </p>
      </div>

      <div className="ai-setup-container">
        <div className="form-group">
          <label>Phone Number</label>
          <input
            type="tel"
            placeholder="(555) 123-4567"
            className="form-input"
          />
          <p className="field-hint">This will be your main business line managed by the AI receptionist</p>
        </div>

        <div className="form-group">
          <label>Choose AI Voice</label>
          <select className="form-select">
            <option value="samantha">Samantha - Professional Female</option>
            <option value="james">James - Professional Male</option>
            <option value="sarah">Sarah - Warm Female</option>
            <option value="michael">Michael - Confident Male</option>
          </select>
          <button className="btn-secondary">▶️ Preview Voice</button>
        </div>

        <div className="routing-rules">
          <h3>Call Routing Rules</h3>
          <div className="rule-card">
            <h4>Leads → Production Partner</h4>
            <p>New inquiries will be routed to your production partner</p>
            <select className="form-select">
              <option value="">Select team member</option>
              {formData.members.map((member, index) => (
                <option key={index} value={member.email}>
                  {member.firstName} {member.lastName}
                </option>
              ))}
            </select>
          </div>

          <div className="rule-card">
            <h4>Active Loans → Processing Assistant</h4>
            <p>Existing loan inquiries go to processing team</p>
            <select className="form-select">
              <option value="">Select team member</option>
              {formData.members.map((member, index) => (
                <option key={index} value={member.email}>
                  {member.firstName} {member.lastName}
                </option>
              ))}
            </select>
          </div>

          <div className="rule-card">
            <h4>MUM Clients → Schedule on LO Calendar</h4>
            <p>Closed clients get scheduled on loan officer calendar</p>
            <select className="form-select">
              <option value="">Select loan officer</option>
              {formData.members.map((member, index) => (
                <option key={index} value={member.email}>
                  {member.firstName} {member.lastName}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>
    </div>
  );
};

export default AISetupStep;

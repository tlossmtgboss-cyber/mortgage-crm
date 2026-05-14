import React from 'react';

const TeamSetupStep = ({ formData, setFormData }) => {
  const handleAddMember = () => {
    setFormData(prevData => ({
      ...prevData,
      members: [...prevData.members, { firstName: '', lastName: '', email: '', phone: '', role: '', permissions: 'Standard' }]
    }));
  };

  const handleRemoveMember = (index) => {
    setFormData(prevData => ({
      ...prevData,
      members: prevData.members.filter((_, i) => i !== index)
    }));
  };

  const handleMemberChange = (index, field, value) => {
    setFormData(prevData => {
      const updatedMembers = [...prevData.members];
      updatedMembers[index] = { ...updatedMembers[index], [field]: value };
      localStorage.setItem('onboarding_team_setup', JSON.stringify({ members: updatedMembers }));
      return { ...prevData, members: updatedMembers };
    });
  };

  const handleCSVUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (event) => {
        const text = event.target.result;
        const lines = text.split('\n');

        const newMembers = lines.slice(1)
          .filter(line => line.trim())
          .map(line => {
            const values = line.split(',').map(v => v.trim());
            return {
              firstName: values[0] || '',
              lastName: values[1] || '',
              email: values[2] || '',
              phone: values[3] || '',
              role: values[4] || '',
              permissions: values[5] || 'Standard'
            };
          });

        setFormData(prevData => ({
          ...prevData,
          members: newMembers
        }));
        localStorage.setItem('onboarding_team_setup', JSON.stringify({ members: newMembers }));
      };
      reader.readAsText(file);
    }
  };

  const downloadCSVTemplate = () => {
    const csvContent = 'First Name,Last Name,Email,Phone,Role,Permissions\nJohn,Doe,john.doe@example.com,(555) 123-4567,Loan Officer,Standard\n';
    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'team_members_template.csv';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(url);
  };

  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">👥</div>
        <h2>Team Setup</h2>
        <p className="step-description">
          Add your team members and assign their permissions. You can add them individually or upload a CSV file.
        </p>
      </div>

      <div className="team-setup-container">
        <div className="upload-options">
          <div className="csv-upload-section">
            <h3>Quick Upload</h3>
            <p>Upload a CSV file with all your team members at once</p>
            <div className="csv-buttons">
              <button className="btn-secondary" onClick={downloadCSVTemplate}>
                📥 Download CSV Template
              </button>
              <label className="btn-primary file-upload-btn">
                📤 Upload CSV File
                <input
                  type="file"
                  accept=".csv,.xlsx"
                  onChange={handleCSVUpload}
                  style={{ display: 'none' }}
                />
              </label>
            </div>
          </div>

          <div className="divider">
            <span>OR</span>
          </div>

          <div className="manual-entry-section">
            <h3>Add Manually</h3>
            <p>Enter team members one by one</p>
          </div>
        </div>

        <div className="team-members-list">
          {formData.members.map((member, index) => (
            <div key={index} className="team-member-card">
              <div className="member-header">
                <h4>Team Member {index + 1}</h4>
                {formData.members.length > 1 && (
                  <button
                    className="btn-remove"
                    onClick={() => handleRemoveMember(index)}
                    title="Remove member"
                  >
                    ✕
                  </button>
                )}
              </div>

              <div className="member-fields">
                <div className="form-row">
                  <div className="form-group">
                    <label>First Name *</label>
                    <input
                      type="text"
                      placeholder="First name"
                      value={member.firstName}
                      onChange={(e) => handleMemberChange(index, 'firstName', e.target.value)}
                      className="form-input"
                    />
                  </div>

                  <div className="form-group">
                    <label>Last Name *</label>
                    <input
                      type="text"
                      placeholder="Last name"
                      value={member.lastName}
                      onChange={(e) => handleMemberChange(index, 'lastName', e.target.value)}
                      className="form-input"
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Email *</label>
                    <input
                      type="email"
                      placeholder="email@company.com"
                      value={member.email}
                      onChange={(e) => handleMemberChange(index, 'email', e.target.value)}
                      className="form-input"
                    />
                  </div>

                  <div className="form-group">
                    <label>Phone</label>
                    <input
                      type="tel"
                      placeholder="(555) 123-4567"
                      value={member.phone}
                      onChange={(e) => handleMemberChange(index, 'phone', e.target.value)}
                      className="form-input"
                    />
                  </div>
                </div>

                <div className="form-row">
                  <div className="form-group">
                    <label>Role</label>
                    <input
                      type="text"
                      placeholder="e.g., Loan Processor"
                      value={member.role}
                      onChange={(e) => handleMemberChange(index, 'role', e.target.value)}
                      className="form-input"
                    />
                  </div>

                  <div className="form-group">
                    <label>Permissions *</label>
                    <select
                      value={member.permissions || 'Standard'}
                      onChange={(e) => handleMemberChange(index, 'permissions', e.target.value)}
                      className="form-select"
                    >
                      <option value="Admin">Admin - Full Access</option>
                      <option value="Manager">Manager - Team Oversight</option>
                      <option value="Standard">Standard - Basic Access</option>
                      <option value="View Only">View Only - Read Access</option>
                    </select>
                  </div>
                </div>
              </div>
            </div>
          ))}
        </div>

        <button className="btn-add-member" onClick={handleAddMember}>
          + Add Another Team Member
        </button>

        <div className="form-info">
          <span className="info-icon">ℹ️</span>
          <p>Team members will receive invitation emails once onboarding is complete.</p>
        </div>
      </div>
    </div>
  );
};

export default TeamSetupStep;

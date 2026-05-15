import React from 'react';
import { formatPhoneNumber } from '../../utils/phoneUtils';

/**
 * Profile Info, Account Settings, Security, and Work Hours sections.
 * Receives all user profile state + handlers as props from the parent orchestrator.
 */

export const ProfileInfoSection = ({
  userProfile, setUserProfile, profileMessage, loadingProfile,
  savingProfile, saveUserProfile
}) => (
  <div className="profile-section">
    <h2>Profile Information</h2>
    <p className="section-description">Manage your personal information and contact details</p>

    {profileMessage.text && (
      <div className={`profile-message ${profileMessage.type}`}>{profileMessage.text}</div>
    )}

    {loadingProfile ? (
      <div className="loading-state">Loading profile...</div>
    ) : (
      <div className="profile-form">
        <div className="form-group">
          <label>First Name</label>
          <input type="text" value={userProfile.first_name} onChange={(e) => setUserProfile({ ...userProfile, first_name: e.target.value })} placeholder="Enter your first name" />
        </div>
        <div className="form-group">
          <label>Last Name</label>
          <input type="text" value={userProfile.last_name} onChange={(e) => setUserProfile({ ...userProfile, last_name: e.target.value })} placeholder="Enter your last name" />
        </div>
        <div className="form-group">
          <label>Email</label>
          <input type="email" value={userProfile.email} disabled className="disabled-input" />
          <small className="form-hint">Email cannot be changed here. Contact administrator.</small>
        </div>
        <div className="form-group">
          <label>Phone</label>
          <input type="tel" value={userProfile.phone} onChange={(e) => setUserProfile({ ...userProfile, phone: formatPhoneNumber(e.target.value) })} placeholder="Enter your phone number" />
        </div>
        <div className="form-group">
          <label>Job Title</label>
          <input type="text" value={userProfile.job_title} onChange={(e) => setUserProfile({ ...userProfile, job_title: e.target.value })} placeholder="Enter your job title" />
        </div>
        <div className="form-group">
          <label>NMLS Number</label>
          <input type="text" value={userProfile.nmls_number} onChange={(e) => setUserProfile({ ...userProfile, nmls_number: e.target.value })} placeholder="Enter your NMLS number" />
        </div>
        <button className="btn-primary" onClick={saveUserProfile} disabled={savingProfile} style={{ marginTop: '24px' }}>
          {savingProfile ? 'Saving...' : 'Save Profile'}
        </button>
      </div>
    )}
  </div>
);

export const AccountSettingsSection = ({ userProfile }) => (
  <div className="profile-section">
    <h2>Account Settings</h2>
    <p className="section-description">Manage your account preferences and settings</p>
    <div className="account-info-card">
      <h3>Account Information</h3>
      <div className="info-row">
        <span className="info-label">Email:</span>
        <span className="info-value">{userProfile.email}</span>
      </div>
      <div className="info-row">
        <span className="info-label">Account Status:</span>
        <span className="info-value status-active">Active</span>
      </div>
    </div>
    <div className="account-actions">
      <h3>Account Actions</h3>
      <p className="section-description">Need to change your email? Contact your system administrator.</p>
    </div>
  </div>
);

export const SecuritySection = ({
  profileMessage, passwordData, setPasswordData,
  changingPassword, changePassword
}) => (
  <div className="profile-section">
    <h2>Security</h2>
    <p className="section-description">Manage your password and security settings</p>

    {profileMessage.text && (
      <div className={`profile-message ${profileMessage.type}`}>{profileMessage.text}</div>
    )}

    <div className="password-change-form">
      <h3>Change Password</h3>
      <div className="form-group">
        <label>Current Password</label>
        <input type="password" value={passwordData.current_password} onChange={(e) => setPasswordData({ ...passwordData, current_password: e.target.value })} placeholder="Enter current password" />
      </div>
      <div className="form-group">
        <label>New Password</label>
        <input type="password" value={passwordData.new_password} onChange={(e) => setPasswordData({ ...passwordData, new_password: e.target.value })} placeholder="Enter new password" />
      </div>
      <div className="form-group">
        <label>Confirm New Password</label>
        <input type="password" value={passwordData.confirm_password} onChange={(e) => setPasswordData({ ...passwordData, confirm_password: e.target.value })} placeholder="Confirm new password" />
      </div>
      <button className="btn-primary" onClick={changePassword} disabled={changingPassword || !passwordData.current_password || !passwordData.new_password || !passwordData.confirm_password}>
        {changingPassword ? 'Changing...' : 'Change Password'}
      </button>
    </div>
  </div>
);

export const WorkHoursSection = ({
  userProfile, setUserProfile, profileMessage,
  loadingProfile, savingProfile, saveUserProfile
}) => {
  const TimeSelector = ({ value, onChange }) => (
    <select value={value} onChange={onChange} style={{ padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px', background: 'white' }}>
      {Array.from({ length: 48 }, (_, i) => {
        const h = Math.floor(i / 2);
        const m = i % 2 === 0 ? '00' : '30';
        const val = `${h.toString().padStart(2, '0')}:${m}`;
        const display = h === 0 ? `12:${m} AM` : h < 12 ? `${h}:${m} AM` : h === 12 ? `12:${m} PM` : `${h - 12}:${m} PM`;
        return <option key={val} value={val}>{display}</option>;
      })}
    </select>
  );

  return (
    <div className="profile-section">
      <h2>Work Hours</h2>
      <p className="section-description">Set your available hours for scheduling appointments. All calendars will use these hours to determine your availability.</p>

      {profileMessage.text && (
        <div className={`profile-message ${profileMessage.type}`}>{profileMessage.text}</div>
      )}

      {loadingProfile ? (
        <div className="loading-state">Loading work hours...</div>
      ) : (
        <div className="work-hours-form">
          <div className="work-hours-card" style={{ background: '#f9fafb', borderRadius: '12px', padding: '24px', marginBottom: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '8px', color: '#1a1a1a' }}>Daily Schedule</h3>
            <p style={{ fontSize: '14px', color: '#666', marginBottom: '20px' }}>Set different hours for each day</p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              {['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'].map(day => {
                const isEnabled = (userProfile.work_days || []).includes(day);
                const dayHours = (userProfile.daily_hours || {})[day] || {};
                const dayStart = dayHours.start || userProfile.work_hours_start || '09:00';
                const dayEnd = dayHours.end || userProfile.work_hours_end || '17:00';

                return (
                  <div key={day} style={{
                    display: 'grid', gridTemplateColumns: '120px 44px 1fr 1fr', alignItems: 'center', gap: '12px',
                    padding: '10px 14px', background: isEnabled ? 'white' : '#f3f4f6', borderRadius: '8px',
                    border: '1px solid', borderColor: isEnabled ? '#d1d5db' : '#e5e7eb', transition: 'all 0.15s ease'
                  }}>
                    <span style={{ fontSize: '14px', fontWeight: isEnabled ? '600' : '400', color: isEnabled ? '#1a1a1a' : '#9ca3af', textTransform: 'capitalize' }}>{day}</span>
                    <label style={{ position: 'relative', display: 'inline-block', width: '36px', height: '20px', cursor: 'pointer' }}>
                      <input type="checkbox" checked={isEnabled} onChange={() => {
                        const workDays = userProfile.work_days || [];
                        if (workDays.includes(day)) {
                          setUserProfile({ ...userProfile, work_days: workDays.filter(d => d !== day) });
                        } else {
                          setUserProfile({ ...userProfile, work_days: [...workDays, day] });
                        }
                      }} style={{ opacity: 0, width: 0, height: 0 }} />
                      <span style={{ position: 'absolute', cursor: 'pointer', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: isEnabled ? '#1F3D2E' : '#d1d5db', borderRadius: '20px', transition: 'background-color 0.2s' }}>
                        <span style={{ position: 'absolute', height: '16px', width: '16px', left: isEnabled ? '18px' : '2px', bottom: '2px', backgroundColor: 'white', borderRadius: '50%', transition: 'left 0.2s' }} />
                      </span>
                    </label>
                    {isEnabled ? (
                      <>
                        <TimeSelector value={dayStart} onChange={(e) => {
                          const newDailyHours = { ...(userProfile.daily_hours || {}) };
                          newDailyHours[day] = { ...(newDailyHours[day] || {}), start: e.target.value, end: dayEnd };
                          setUserProfile({ ...userProfile, daily_hours: newDailyHours });
                        }} />
                        <TimeSelector value={dayEnd} onChange={(e) => {
                          const newDailyHours = { ...(userProfile.daily_hours || {}) };
                          newDailyHours[day] = { ...(newDailyHours[day] || {}), start: dayStart, end: e.target.value };
                          setUserProfile({ ...userProfile, daily_hours: newDailyHours });
                        }} />
                      </>
                    ) : (
                      <span style={{ gridColumn: 'span 2', fontSize: '13px', color: '#9ca3af', fontStyle: 'italic' }}>Day off</span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>

          <div className="work-hours-card" style={{ background: '#f9fafb', borderRadius: '12px', padding: '24px', marginBottom: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: '600', marginBottom: '8px', color: '#1a1a1a' }}>Blocked Time Slots</h3>
            <p style={{ fontSize: '14px', color: '#666', marginBottom: '20px' }}>Protect specific times from being scheduled (e.g., lunch, meetings)</p>

            {(userProfile.blocked_times || []).length > 0 && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '16px' }}>
                {(userProfile.blocked_times || []).map((block, idx) => (
                  <div key={block.id || idx} style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 120px 120px 36px', alignItems: 'center', gap: '10px', padding: '10px 14px', background: 'white', borderRadius: '8px', border: '1px solid #d1d5db' }}>
                    <input type="text" value={block.label || ''} placeholder="Label (e.g., Lunch)" onChange={(e) => {
                      const updated = [...(userProfile.blocked_times || [])];
                      updated[idx] = { ...updated[idx], label: e.target.value };
                      setUserProfile({ ...userProfile, blocked_times: updated });
                    }} style={{ padding: '8px 10px', border: '1px solid #d1d5db', borderRadius: '6px', fontSize: '13px' }} />
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                      {['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].map((d, di) => {
                        const fullDay = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'][di];
                        const isSelected = (block.days || []).includes(fullDay);
                        return (
                          <button key={d} type="button" onClick={() => {
                            const updated = [...(userProfile.blocked_times || [])];
                            const blockDays = updated[idx].days || [];
                            updated[idx] = { ...updated[idx], days: isSelected ? blockDays.filter(x => x !== fullDay) : [...blockDays, fullDay] };
                            setUserProfile({ ...userProfile, blocked_times: updated });
                          }} style={{ padding: '2px 6px', fontSize: '11px', borderRadius: '4px', cursor: 'pointer', border: '1px solid', transition: 'all 0.1s', borderColor: isSelected ? '#1F3D2E' : '#d1d5db', background: isSelected ? 'rgba(33, 127, 141, 0.1)' : 'white', color: isSelected ? '#1F3D2E' : '#999', fontWeight: isSelected ? '600' : '400' }}>{d}</button>
                        );
                      })}
                    </div>
                    <TimeSelector value={block.start || '12:00'} onChange={(e) => {
                      const updated = [...(userProfile.blocked_times || [])];
                      updated[idx] = { ...updated[idx], start: e.target.value };
                      setUserProfile({ ...userProfile, blocked_times: updated });
                    }} />
                    <TimeSelector value={block.end || '13:00'} onChange={(e) => {
                      const updated = [...(userProfile.blocked_times || [])];
                      updated[idx] = { ...updated[idx], end: e.target.value };
                      setUserProfile({ ...userProfile, blocked_times: updated });
                    }} />
                    <button type="button" onClick={() => {
                      const updated = (userProfile.blocked_times || []).filter((_, i) => i !== idx);
                      setUserProfile({ ...userProfile, blocked_times: updated });
                    }} style={{ padding: '6px', background: 'none', border: '1px solid #e5e7eb', borderRadius: '6px', cursor: 'pointer', color: '#ef4444', fontSize: '14px', display: 'flex', alignItems: 'center', justifyContent: 'center' }} title="Remove">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M3 6h18"/><path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
                    </button>
                  </div>
                ))}
              </div>
            )}

            <button type="button" onClick={() => {
              const newBlock = { id: Math.random().toString(36).substr(2, 8), label: '', days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'], start: '12:00', end: '13:00' };
              setUserProfile({ ...userProfile, blocked_times: [...(userProfile.blocked_times || []), newBlock] });
            }} style={{ padding: '10px 18px', background: 'white', border: '2px dashed #d1d5db', borderRadius: '8px', cursor: 'pointer', fontSize: '14px', color: '#1F3D2E', fontWeight: '500', transition: 'all 0.15s', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M12 5v14M5 12h14"/></svg>
              Add Time Block
            </button>
          </div>

          <div style={{ background: '#e8f4f6', borderRadius: '8px', padding: '16px', marginBottom: '24px', display: 'flex', alignItems: 'flex-start', gap: '12px' }}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#1F3D2E" strokeWidth="2" style={{ flexShrink: 0, marginTop: '2px' }}>
              <circle cx="12" cy="12" r="10" /><path d="M12 16v-4" /><path d="M12 8h.01" />
            </svg>
            <div>
              <p style={{ fontSize: '14px', color: '#1a1a1a', fontWeight: '500', marginBottom: '4px' }}>How this affects scheduling</p>
              <p style={{ fontSize: '13px', color: '#666', margin: 0 }}>
                When clients or team members schedule appointments with you, they'll only see available time slots within your work hours and on your selected work days. Blocked time slots are excluded from availability.
              </p>
            </div>
          </div>

          <button className="btn-primary" onClick={saveUserProfile} disabled={savingProfile} style={{ padding: '12px 24px' }}>
            {savingProfile ? 'Saving...' : 'Save Work Hours'}
          </button>
        </div>
      )}
    </div>
  );
};

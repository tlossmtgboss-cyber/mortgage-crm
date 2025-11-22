import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import api from '../services/api';
import './MorningCheckin.css';

const MorningCheckin = () => {
  const navigate = useNavigate();
  const [phase, setPhase] = useState('welcome'); // welcome, leads, hours, partners, complete
  const [checkin, setCheckin] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Lead form state
  const [leadForm, setLeadForm] = useState({
    name: '',
    phone: '',
    email: '',
    partner_name: '',
    loan_type: '',
    loan_amount: '',
    notes: ''
  });

  // Hours state
  const [hoursWorked, setHoursWorked] = useState('');

  // Partner interaction state
  const [partnerInteraction, setPartnerInteraction] = useState({
    partner_name: '',
    interaction_type: 'call',
    duration_minutes: 30,
    notes: ''
  });

  const [addedLeads, setAddedLeads] = useState([]);
  const [loggedInteractions, setLoggedInteractions] = useState([]);

  useEffect(() => {
    startCheckin();
  }, []);

  const startCheckin = async () => {
    try {
      setLoading(true);
      const response = await api.post('/api/v1/checkin/start', {});
      setCheckin(response.data);
      if (response.data.completed) {
        setPhase('complete');
      }
    } catch (err) {
      setError('Failed to start check-in');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleAddLead = async (e) => {
    e.preventDefault();
    try {
      setLoading(true);
      const response = await api.post('/api/v1/checkin/add-lead', {
        ...leadForm,
        loan_amount: leadForm.loan_amount ? parseFloat(leadForm.loan_amount) : null
      });
      setAddedLeads([...addedLeads, response.data]);
      setLeadForm({
        name: '',
        phone: '',
        email: '',
        partner_name: '',
        loan_type: '',
        loan_amount: '',
        notes: ''
      });
      setError('');
    } catch (err) {
      setError('Failed to add lead');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleLogHours = async () => {
    if (!hoursWorked) {
      setPhase('partners');
      return;
    }
    try {
      setLoading(true);
      await api.post('/api/v1/checkin/log-hours', {
        hours_worked: parseFloat(hoursWorked)
      });
      setPhase('partners');
    } catch (err) {
      setError('Failed to log hours');
    } finally {
      setLoading(false);
    }
  };

  const handleLogInteraction = async (e) => {
    e.preventDefault();
    if (!partnerInteraction.partner_name) return;

    try {
      setLoading(true);
      const response = await api.post('/api/v1/checkin/log-partner-interaction', partnerInteraction);
      setLoggedInteractions([...loggedInteractions, {
        ...partnerInteraction,
        id: response.data.partner_id
      }]);
      setPartnerInteraction({
        partner_name: '',
        interaction_type: 'call',
        duration_minutes: 30,
        notes: ''
      });
    } catch (err) {
      setError('Failed to log interaction');
    } finally {
      setLoading(false);
    }
  };

  const handleComplete = async () => {
    try {
      setLoading(true);
      if (!api || typeof api.post !== 'function') {
        console.error('API not properly initialized:', api);
        setError('API service not available. Please refresh the page.');
        return;
      }
      const response = await api.post('/api/v1/checkin/complete');
      console.log('Check-in completed:', response);
      setPhase('complete');
    } catch (err) {
      console.error('Error completing check-in:', err);
      setError('Failed to complete check-in: ' + (err.response?.data?.detail || err.message));
    } finally {
      setLoading(false);
    }
  };

  const renderWelcome = () => (
    <div className="checkin-phase welcome-phase">
      <div className="phase-icon">☀️</div>
      <h2>Good Morning!</h2>
      <p>Let's capture your business activity and track your partner ROI.</p>
      <p className="checkin-date">Check-in for: {checkin?.date || new Date().toLocaleDateString()}</p>

      <div className="phase-summary">
        <div className="summary-item">
          <span className="summary-label">Leads to add?</span>
          <span className="summary-value">Let's capture them</span>
        </div>
        <div className="summary-item">
          <span className="summary-label">Partner conversations?</span>
          <span className="summary-value">Track your time investment</span>
        </div>
      </div>

      <button className="primary-btn" onClick={() => setPhase('leads')}>
        Start Check-in →
      </button>
    </div>
  );

  const renderLeadsPhase = () => (
    <div className="checkin-phase leads-phase">
      <div className="phase-header">
        <h2>📋 New Leads</h2>
        <p>Any new leads to add from yesterday or this morning?</p>
      </div>

      {addedLeads.length > 0 && (
        <div className="added-items">
          <h4>Added Leads ({addedLeads.length})</h4>
          {addedLeads.map((lead, i) => (
            <div key={i} className="added-item">
              ✓ {lead.lead_name}
              {lead.partner_id && <span className="partner-tag">from partner</span>}
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleAddLead} className="checkin-form">
        <div className="form-row">
          <input
            type="text"
            placeholder="Lead Name *"
            value={leadForm.name}
            onChange={(e) => setLeadForm({...leadForm, name: e.target.value})}
            required
          />
          <input
            type="tel"
            placeholder="Phone"
            value={leadForm.phone}
            onChange={(e) => setLeadForm({...leadForm, phone: e.target.value})}
          />
        </div>

        <div className="form-row">
          <input
            type="email"
            placeholder="Email"
            value={leadForm.email}
            onChange={(e) => setLeadForm({...leadForm, email: e.target.value})}
          />
          <input
            type="text"
            placeholder="Referral Partner Name"
            value={leadForm.partner_name}
            onChange={(e) => setLeadForm({...leadForm, partner_name: e.target.value})}
          />
        </div>

        <div className="form-row">
          <select
            value={leadForm.loan_type}
            onChange={(e) => setLeadForm({...leadForm, loan_type: e.target.value})}
          >
            <option value="">Loan Type</option>
            <option value="Conventional">Conventional</option>
            <option value="FHA">FHA</option>
            <option value="VA">VA</option>
            <option value="USDA">USDA</option>
            <option value="Jumbo">Jumbo</option>
            <option value="Other">Other</option>
          </select>
          <input
            type="number"
            placeholder="Loan Amount"
            value={leadForm.loan_amount}
            onChange={(e) => setLeadForm({...leadForm, loan_amount: e.target.value})}
          />
        </div>

        <textarea
          placeholder="Notes"
          value={leadForm.notes}
          onChange={(e) => setLeadForm({...leadForm, notes: e.target.value})}
        />

        <div className="form-actions">
          <button type="submit" className="secondary-btn" disabled={!leadForm.name || loading}>
            + Add Lead
          </button>
        </div>
      </form>

      <div className="phase-navigation">
        <button className="skip-btn" onClick={() => setPhase('hours')}>
          {addedLeads.length > 0 ? 'Continue →' : 'No leads to add →'}
        </button>
      </div>
    </div>
  );

  const renderHoursPhase = () => (
    <div className="checkin-phase hours-phase">
      <div className="phase-header">
        <h2>⏱️ Hours Worked</h2>
        <p>How many hours did you work yesterday?</p>
      </div>

      <div className="hours-input-container">
        <input
          type="number"
          step="0.5"
          min="0"
          max="24"
          placeholder="0"
          value={hoursWorked}
          onChange={(e) => setHoursWorked(e.target.value)}
          className="hours-input"
        />
        <span className="hours-label">hours</span>
      </div>

      <div className="quick-hours">
        {[6, 8, 10, 12].map(h => (
          <button
            key={h}
            className={`quick-hour-btn ${hoursWorked === String(h) ? 'selected' : ''}`}
            onClick={() => setHoursWorked(String(h))}
          >
            {h}h
          </button>
        ))}
      </div>

      <div className="phase-navigation">
        <button className="primary-btn" onClick={handleLogHours} disabled={loading}>
          Continue →
        </button>
      </div>
    </div>
  );

  const renderPartnersPhase = () => (
    <div className="checkin-phase partners-phase">
      <div className="phase-header">
        <h2>🤝 Partner Conversations</h2>
        <p>Log any conversations with referral partners</p>
      </div>

      {loggedInteractions.length > 0 && (
        <div className="added-items">
          <h4>Logged Interactions ({loggedInteractions.length})</h4>
          {loggedInteractions.map((int, i) => (
            <div key={i} className="added-item">
              ✓ {int.partner_name} - {int.interaction_type} ({int.duration_minutes}min)
            </div>
          ))}
        </div>
      )}

      <form onSubmit={handleLogInteraction} className="checkin-form">
        <input
          type="text"
          placeholder="Partner Name *"
          value={partnerInteraction.partner_name}
          onChange={(e) => setPartnerInteraction({...partnerInteraction, partner_name: e.target.value})}
        />

        <div className="form-row">
          <select
            value={partnerInteraction.interaction_type}
            onChange={(e) => setPartnerInteraction({...partnerInteraction, interaction_type: e.target.value})}
          >
            <option value="call">Phone Call</option>
            <option value="meeting">In-Person Meeting</option>
            <option value="lunch">Lunch/Coffee</option>
            <option value="event">Event/Networking</option>
            <option value="email">Email</option>
            <option value="text">Text Message</option>
          </select>
          <input
            type="number"
            placeholder="Duration (min)"
            value={partnerInteraction.duration_minutes}
            onChange={(e) => setPartnerInteraction({...partnerInteraction, duration_minutes: parseInt(e.target.value)})}
          />
        </div>

        <textarea
          placeholder="Notes"
          value={partnerInteraction.notes}
          onChange={(e) => setPartnerInteraction({...partnerInteraction, notes: e.target.value})}
        />

        <div className="form-actions">
          <button type="submit" className="secondary-btn" disabled={!partnerInteraction.partner_name || loading}>
            + Log Interaction
          </button>
        </div>
      </form>

      <div className="phase-navigation">
        <button className="primary-btn" onClick={handleComplete} disabled={loading}>
          Complete Check-in ✓
        </button>
      </div>
    </div>
  );

  const renderComplete = () => (
    <div className="checkin-phase complete-phase">
      <div className="phase-icon">🎉</div>
      <h2>Check-in Complete!</h2>

      <div className="completion-summary">
        <div className="summary-stat">
          <span className="stat-value">{addedLeads.length}</span>
          <span className="stat-label">Leads Added</span>
        </div>
        <div className="summary-stat">
          <span className="stat-value">{hoursWorked || '—'}</span>
          <span className="stat-label">Hours Logged</span>
        </div>
        <div className="summary-stat">
          <span className="stat-value">{loggedInteractions.length}</span>
          <span className="stat-label">Partner Interactions</span>
        </div>
      </div>

      <div className="completion-actions">
        <button className="primary-btn" onClick={() => navigate('/partner-roi')}>
          View Partner ROI →
        </button>
        <button className="secondary-btn" onClick={() => navigate('/dashboard')}>
          Go to Dashboard
        </button>
      </div>
    </div>
  );

  if (loading && !checkin) {
    return (
      <div className="morning-checkin">
        <div className="checkin-loading">Loading...</div>
      </div>
    );
  }

  return (
    <div className="morning-checkin">
      <div className="checkin-container">
        {error && (
          <div className="checkin-error">
            {error}
            <button onClick={() => setError('')}>×</button>
          </div>
        )}

        <div className="checkin-progress">
          <div className={`progress-step ${phase === 'welcome' ? 'active' : phase !== 'welcome' ? 'completed' : ''}`}>
            Start
          </div>
          <div className={`progress-step ${phase === 'leads' ? 'active' : ['hours', 'partners', 'complete'].includes(phase) ? 'completed' : ''}`}>
            Leads
          </div>
          <div className={`progress-step ${phase === 'hours' ? 'active' : ['partners', 'complete'].includes(phase) ? 'completed' : ''}`}>
            Hours
          </div>
          <div className={`progress-step ${phase === 'partners' ? 'active' : phase === 'complete' ? 'completed' : ''}`}>
            Partners
          </div>
          <div className={`progress-step ${phase === 'complete' ? 'active completed' : ''}`}>
            Done
          </div>
        </div>

        {phase === 'welcome' && renderWelcome()}
        {phase === 'leads' && renderLeadsPhase()}
        {phase === 'hours' && renderHoursPhase()}
        {phase === 'partners' && renderPartnersPhase()}
        {phase === 'complete' && renderComplete()}
      </div>
    </div>
  );
};

export default MorningCheckin;

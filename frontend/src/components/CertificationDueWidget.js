import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './CertificationDueWidget.css';
import { getToken } from '../utils/tokenStore';

const CertificationDueWidget = () => {
  const [certifications, setCertifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const navigate = useNavigate();

  useEffect(() => {
    loadCertifications();
  }, []);

  const loadCertifications = async () => {
    try {
      setLoading(true);
      const token = getToken();
      const response = await fetch('https://api.perenniaai.com/api/v1/certifications/due', {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        setCertifications(data.certifications || []);
      }
    } catch (err) {
      console.error('Error loading certifications:', err);
    } finally {
      setLoading(false);
    }
  };

  const getStatusColor = (status) => {
    return status === 'overdue' ? 'red' : 'orange';
  };

  const getDaysUntilDueText = (days) => {
    if (days < 0) return `${Math.abs(days)} days overdue`;
    if (days === 0) return 'Due today';
    return `Due in ${days} days`;
  };

  if (loading) {
    return (
      <div className="certification-widget">
        <h3>Access Certifications</h3>
        <div className="loading">Loading...</div>
      </div>
    );
  }

  if (certifications.length === 0) {
    return (
      <div className="certification-widget">
        <h3>Access Certifications</h3>
        <div className="empty-state">
          <p>✓ No certifications due</p>
        </div>
      </div>
    );
  }

  return (
    <div className="certification-widget">
      <div className="widget-header">
        <h3>Access Certifications Due</h3>
        <span className="count-badge">{certifications.length}</span>
      </div>

      <div className="certifications-list">
        {certifications.map(cert => (
          <div key={cert.id} className={`cert-card ${cert.status}`}>
            <div className="cert-header">
              <strong>{cert.employee_name}</strong>
              <span className={`status-badge ${getStatusColor(cert.status)}`}>
                {getDaysUntilDueText(cert.days_until_due)}
              </span>
            </div>
            <div className="cert-body">
              <p>Period: {cert.certification_period}</p>
              <p>Permissions: {cert.permissions_count}</p>
            </div>
            <div className="cert-actions">
              <button
                onClick={() => navigate(`/team-members/${cert.employee_id}?tab=permissions&cert=${cert.id}`)}
                className="review-btn"
              >
                Review & Certify →
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default CertificationDueWidget;

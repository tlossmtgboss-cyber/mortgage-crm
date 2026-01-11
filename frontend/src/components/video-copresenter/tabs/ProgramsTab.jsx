/**
 * Programs Tab
 * Display eligible loan programs with recommendations
 */
import React, { useState, useEffect } from 'react';

const API_BASE_URL = typeof window !== 'undefined' &&
  (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
  ? 'https://api.perenniaai.com'
  : 'http://localhost:8000';

const ProgramsTab = ({ clientId, callSessionId, userRole }) => {
  const [programs, setPrograms] = useState([]);
  const [recommendedId, setRecommendedId] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedProgram, setSelectedProgram] = useState(null);

  useEffect(() => {
    fetchPrograms();
  }, [callSessionId]);

  const fetchPrograms = async () => {
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(
        `${API_BASE_URL}/api/v1/voice-copresenter/calls/${callSessionId}/tabs/programs`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setPrograms(data.eligible_programs || []);
        setRecommendedId(data.recommended_program_id);
      }
    } catch (err) {
      console.error('Error fetching programs:', err);
    } finally {
      // Set demo programs if fetch failed
      if (programs.length === 0) {
        setPrograms([
          {
            id: 'conv-30',
            family: 'AGENCY',
            name: '30 Year Fixed',
            term: '30Y',
            min_credit_score: 620,
            min_down_payment_pct: 3,
            max_dti: 50,
            allows_gift_funds: true,
            requires_pmi: true,
            badges: ['Popular', 'Low Down Payment']
          },
          {
            id: 'conv-15',
            family: 'AGENCY',
            name: '15 Year Fixed',
            term: '15Y',
            min_credit_score: 620,
            min_down_payment_pct: 3,
            max_dti: 50,
            allows_gift_funds: true,
            requires_pmi: true,
            badges: ['Lowest Rate']
          },
          {
            id: 'fha-30',
            family: 'GOV',
            name: 'FHA 30 Year',
            term: '30Y',
            min_credit_score: 580,
            min_down_payment_pct: 3.5,
            max_dti: 57,
            allows_gift_funds: true,
            requires_pmi: true,
            badges: ['First-Time Buyer', 'Low Credit OK']
          },
          {
            id: 'va-30',
            family: 'GOV',
            name: 'VA 30 Year',
            term: '30Y',
            min_credit_score: 580,
            min_down_payment_pct: 0,
            max_dti: 60,
            allows_gift_funds: true,
            requires_pmi: false,
            badges: ['No Down Payment', 'No PMI', 'Veterans']
          }
        ]);
        setRecommendedId('conv-30');
      }
      setLoading(false);
    }
  };

  const getFamilyColor = (family) => {
    switch (family) {
      case 'AGENCY':
        return { bg: '#dbeafe', text: '#1e40af', border: '#93c5fd' };
      case 'GOV':
        return { bg: '#dcfce7', text: '#166534', border: '#86efac' };
      case 'JUMBO':
        return { bg: '#fae8ff', text: '#86198f', border: '#e879f9' };
      default:
        return { bg: '#f3f4f6', text: '#374151', border: '#d1d5db' };
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: '48px' }}>
        <div style={{
          width: '32px',
          height: '32px',
          margin: '0 auto 16px',
          border: '3px solid #e5e7eb',
          borderTopColor: '#2563eb',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite'
        }} />
        <p style={{ color: '#6b7280' }}>Loading loan programs...</p>
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ padding: '16px' }}>
      <h2 style={{ margin: '0 0 8px', fontSize: '24px', fontWeight: '700', color: '#111827' }}>
        Loan Programs
      </h2>
      <p style={{ margin: '0 0 24px', fontSize: '14px', color: '#6b7280' }}>
        Based on your profile, here are the programs you qualify for
      </p>

      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: '16px'
      }}>
        {programs.map((program) => {
          const colors = getFamilyColor(program.family);
          const isRecommended = program.id === recommendedId;

          return (
            <div
              key={program.id}
              onClick={() => setSelectedProgram(program)}
              style={{
                backgroundColor: '#fff',
                border: isRecommended ? '2px solid #2563eb' : '1px solid #e5e7eb',
                borderRadius: '12px',
                padding: '20px',
                cursor: 'pointer',
                transition: 'all 0.2s ease',
                boxShadow: isRecommended ? '0 4px 6px rgba(37, 99, 235, 0.1)' : 'none'
              }}
            >
              {/* Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '12px' }}>
                <div>
                  <span style={{
                    display: 'inline-block',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '10px',
                    fontWeight: '600',
                    backgroundColor: colors.bg,
                    color: colors.text,
                    marginBottom: '4px'
                  }}>
                    {program.family}
                  </span>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: '600', color: '#111827' }}>
                    {program.name}
                  </h3>
                </div>
                {isRecommended && (
                  <span style={{
                    padding: '4px 8px',
                    borderRadius: '9999px',
                    fontSize: '10px',
                    fontWeight: '600',
                    backgroundColor: '#2563eb',
                    color: '#fff'
                  }}>
                    Recommended
                  </span>
                )}
              </div>

              {/* Details */}
              <div style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '4px' }}>
                  <span style={{ color: '#6b7280' }}>Min. Down Payment</span>
                  <span style={{ fontWeight: '500', color: '#111827' }}>{program.min_down_payment_pct}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '4px' }}>
                  <span style={{ color: '#6b7280' }}>Min. Credit Score</span>
                  <span style={{ fontWeight: '500', color: '#111827' }}>{program.min_credit_score}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px', marginBottom: '4px' }}>
                  <span style={{ color: '#6b7280' }}>Max DTI</span>
                  <span style={{ fontWeight: '500', color: '#111827' }}>{program.max_dti}%</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '13px' }}>
                  <span style={{ color: '#6b7280' }}>PMI Required</span>
                  <span style={{ fontWeight: '500', color: program.requires_pmi ? '#f59e0b' : '#10b981' }}>
                    {program.requires_pmi ? 'Yes' : 'No'}
                  </span>
                </div>
              </div>

              {/* Badges */}
              {program.badges && program.badges.length > 0 && (
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                  {program.badges.map((badge, i) => (
                    <span
                      key={i}
                      style={{
                        padding: '2px 8px',
                        borderRadius: '9999px',
                        fontSize: '10px',
                        backgroundColor: '#f3f4f6',
                        color: '#6b7280'
                      }}
                    >
                      {badge}
                    </span>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Program Detail Modal */}
      {selectedProgram && (
        <div
          onClick={() => setSelectedProgram(null)}
          style={{
            position: 'fixed',
            inset: 0,
            backgroundColor: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000
          }}
        >
          <div
            onClick={e => e.stopPropagation()}
            style={{
              backgroundColor: '#fff',
              borderRadius: '12px',
              padding: '24px',
              maxWidth: '500px',
              width: '100%',
              margin: '16px'
            }}
          >
            <h3 style={{ margin: '0 0 16px', fontSize: '20px', fontWeight: '600' }}>
              {selectedProgram.name}
            </h3>

            <div style={{ marginBottom: '16px' }}>
              <h4 style={{ margin: '0 0 8px', fontSize: '14px', fontWeight: '600', color: '#6b7280' }}>
                Key Features
              </h4>
              <ul style={{ margin: 0, paddingLeft: '20px', color: '#374151' }}>
                <li>Minimum {selectedProgram.min_down_payment_pct}% down payment required</li>
                <li>Minimum credit score of {selectedProgram.min_credit_score}</li>
                <li>Maximum debt-to-income ratio of {selectedProgram.max_dti}%</li>
                {selectedProgram.allows_gift_funds && <li>Gift funds allowed for down payment</li>}
                {!selectedProgram.requires_pmi && <li>No PMI required</li>}
              </ul>
            </div>

            <button
              onClick={() => setSelectedProgram(null)}
              style={{
                width: '100%',
                padding: '12px',
                backgroundColor: '#2563eb',
                color: '#fff',
                border: 'none',
                borderRadius: '8px',
                fontSize: '14px',
                fontWeight: '500',
                cursor: 'pointer'
              }}
            >
              Close
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default ProgramsTab;
export { ProgramsTab };

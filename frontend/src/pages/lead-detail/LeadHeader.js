import React from 'react';
import SalesforceConnectionBadge from '../../components/SalesforceConnectionBadge';
import { statusOptions, getStatusColor } from './shared/constants';

export default function LeadHeader({
  id, navigate, formData, lead, editing, setEditing,
  handleSave, handleCancel, handleViewNextLead, leadsList,
  showStatusDropdown, setShowStatusDropdown, statusSaving,
  handleStatusChange,
}) {
  return (
    <>
      {/* Header */}
      <div className="detail-header">
        <div className="nav-buttons">
          <button className="btn-back" onClick={() => navigate('/leads')}>
            &larr; Back to Leads
          </button>
          <button className="btn-next" onClick={handleViewNextLead} disabled={leadsList.length === 0}>
            View Next Lead &rarr;
          </button>

          {/* Status Dropdown */}
          <div className="status-dropdown-container">
            <button
              className="btn-status"
              onClick={() => setShowStatusDropdown(!showStatusDropdown)}
              disabled={statusSaving}
              style={{
                backgroundColor: getStatusColor(formData.stage || lead?.stage || 'New'),
                color: 'white',
                border: 'none',
                padding: '10px 20px',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: '500',
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                minWidth: '150px',
                justifyContent: 'space-between'
              }}
            >
              {statusSaving ? 'Saving...' : (formData.stage || lead?.stage || 'New')}
              <span style={{ fontSize: '10px' }}>{'\u25BC'}</span>
            </button>

            {showStatusDropdown && (
              <>
                <div
                  className="status-dropdown-overlay"
                  onClick={() => setShowStatusDropdown(false)}
                  style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 999 }}
                />
                <div
                  className="status-dropdown-menu"
                  style={{
                    position: 'absolute', top: '100%', left: 0,
                    backgroundColor: 'white', borderRadius: '8px',
                    boxShadow: '0 4px 20px rgba(0,0,0,0.15)', zIndex: 1000,
                    minWidth: '200px', marginTop: '4px', maxHeight: '400px', overflowY: 'auto'
                  }}
                >
                  {statusOptions.map((status, idx) => (
                    status.isHeader ? (
                      <div
                        key={status.label}
                        style={{
                          padding: '8px 16px', fontSize: '11px', fontWeight: 600,
                          textTransform: 'uppercase', color: '#6b7280',
                          borderTop: idx > 0 ? '1px solid #e5e7eb' : 'none',
                          marginTop: idx > 0 ? '4px' : 0, letterSpacing: '0.05em', background: '#fafafa',
                        }}
                      >
                        {status.label}
                      </div>
                    ) : (
                      <button
                        key={status}
                        onClick={() => handleStatusChange(status)}
                        style={{
                          display: 'block', width: '100%', padding: '12px 16px', border: 'none',
                          background: (formData.stage || lead?.stage) === status ? '#f0f0f0' : 'white',
                          cursor: 'pointer', textAlign: 'left', fontSize: '14px',
                          borderLeft: `4px solid ${getStatusColor(status)}`, transition: 'background 0.2s'
                        }}
                        onMouseEnter={(e) => e.target.style.background = '#f5f5f5'}
                        onMouseLeave={(e) => e.target.style.background = (formData.stage || lead?.stage) === status ? '#f0f0f0' : 'white'}
                      >
                        {status}
                      </button>
                    )
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
        <div className="header-actions">
          {editing ? (
            <>
              <button className="btn-save" onClick={handleSave}>Save</button>
              <button className="btn-cancel" onClick={handleCancel}>Cancel</button>
            </>
          ) : (
            <button className="btn-edit-header" onClick={() => setEditing(true)}>
              &#x270F;&#xFE0F; Edit
            </button>
          )}
        </div>
      </div>

      {/* Client Name Banner */}
      <div className="client-name-banner" style={{
        padding: '12px 24px', backgroundColor: '#f8fafc',
        borderBottom: '1px solid #e2e8f0', display: 'flex',
        alignItems: 'center', justifyContent: 'space-between'
      }}>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: '600', color: '#1a1a2e' }}>
          {formData.first_name || formData.last_name
            ? `${formData.first_name || ''} ${formData.last_name || ''}`.trim()
            : lead?.first_name || lead?.last_name
              ? `${lead?.first_name || ''} ${lead?.last_name || ''}`.trim()
              : 'Unknown Client'}
        </h2>
        <SalesforceConnectionBadge
          entityType="lead"
          entityId={id}
          salesforceId={lead?.salesforce_id}
          lastSyncedAt={lead?.salesforce_last_synced_at}
        />
      </div>
    </>
  );
}

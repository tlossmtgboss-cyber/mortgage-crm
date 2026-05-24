import React from 'react';
import { ALL_STAGES } from './constants';
import { formatFieldName } from './helpers';

/**
 * StatusCorrectionModal - Shown when a pre-approval check detects a status mismatch.
 * Allows the user to update the entity status, keep current status, or cancel.
 */
export default function StatusCorrectionModal({
  statusCorrectionData,
  selectedNewStatus,
  setSelectedNewStatus,
  onConfirm,
  onSkip,
  onCancel,
}) {
  return (
    <div className="dialog-overlay" style={{ zIndex: 2100 }}>
      <div className="dialog-content" style={{ maxWidth: '550px' }}>
        <div className="dialog-header" style={{ background: '#fef3c7', borderBottom: '2px solid #f59e0b' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: 0 }}>
            Status Mismatch Detected
          </h3>
          <button className="dialog-close" onClick={onCancel}>&times;</button>
        </div>
        <div className="dialog-body" style={{ padding: '24px' }}>
          <p style={{ fontSize: '15px', color: '#374151', marginBottom: '20px' }}>
            <strong>{statusCorrectionData.entity_name}</strong> is currently in{' '}
            <span style={{
              background: '#e5e7eb',
              padding: '2px 8px',
              borderRadius: '4px',
              fontWeight: '600'
            }}>
              {statusCorrectionData.current_status_label}
            </span>{' '}
            status, but the data suggests they should be further along in the process.
          </p>

          <div style={{
            background: '#fef9c3',
            border: '1px solid #facc15',
            borderRadius: '8px',
            padding: '16px',
            marginBottom: '20px'
          }}>
            <p style={{ margin: 0, fontWeight: '500', color: '#854d0e' }}>
              {statusCorrectionData.reason}
            </p>
          </div>

          <div style={{ marginBottom: '20px' }}>
            <label style={{ display: 'block', fontWeight: '600', marginBottom: '8px' }}>
              Update status to:
            </label>
            <select
              value={selectedNewStatus || ''}
              onChange={(e) => setSelectedNewStatus(e.target.value)}
              style={{
                width: '100%',
                padding: '12px',
                border: '2px solid #3b82f6',
                borderRadius: '8px',
                fontSize: '15px',
                background: '#eff6ff'
              }}
            >
              <optgroup label="Lead Stages">
                {ALL_STAGES.filter(s => s.category === 'Lead').map(stage => (
                  <option key={stage.value} value={stage.value}>{stage.label}</option>
                ))}
              </optgroup>
              <optgroup label="Active Loan Stages">
                {ALL_STAGES.filter(s => s.category === 'Active Loan').map(stage => (
                  <option key={stage.value} value={stage.value}>{stage.label}</option>
                ))}
              </optgroup>
            </select>
          </div>

          {statusCorrectionData.fields_to_apply && statusCorrectionData.fields_to_apply.length > 0 && (
            <div style={{
              background: '#f0fdf4',
              border: '1px solid #86efac',
              borderRadius: '8px',
              padding: '16px',
              marginBottom: '20px'
            }}>
              <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#166534' }}>
                Data to be applied ({statusCorrectionData.fields_to_apply.length} fields):
              </h4>
              <ul style={{ margin: 0, paddingLeft: '20px', fontSize: '13px', color: '#15803d' }}>
                {statusCorrectionData.fields_to_apply.slice(0, 8).map((field, idx) => (
                  <li key={idx} style={{ marginBottom: '4px' }}>
                    <strong>{formatFieldName(field.field)}:</strong> {String(field.value).substring(0, 50)}
                  </li>
                ))}
                {statusCorrectionData.fields_to_apply.length > 8 && (
                  <li style={{ fontStyle: 'italic' }}>
                    ...and {statusCorrectionData.fields_to_apply.length - 8} more fields
                  </li>
                )}
              </ul>
            </div>
          )}
        </div>
        <div className="dialog-footer" style={{
          padding: '16px 24px',
          borderTop: '1px solid #e5e7eb',
          display: 'flex',
          justifyContent: 'space-between',
          gap: '12px',
          background: '#f9fafb'
        }}>
          <button
            onClick={onCancel}
            style={{
              padding: '10px 20px',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              background: 'white',
              color: '#374151',
              cursor: 'pointer'
            }}
          >
            Cancel
          </button>
          <div style={{ display: 'flex', gap: '12px' }}>
            <button
              onClick={onSkip}
              style={{
                padding: '10px 20px',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                background: 'white',
                color: '#6b7280',
                cursor: 'pointer'
              }}
            >
              Keep Current Status
            </button>
            <button
              onClick={onConfirm}
              style={{
                padding: '10px 24px',
                border: 'none',
                borderRadius: '6px',
                background: '#2D7A52',
                color: 'white',
                cursor: 'pointer',
                fontWeight: '600'
              }}
            >
              Update Status & Apply Data
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

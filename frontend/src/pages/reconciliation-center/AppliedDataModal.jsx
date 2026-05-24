import React from 'react';
import { formatFieldName } from './helpers';

/**
 * AppliedDataModal - Success confirmation shown after data is applied to a borrower profile.
 * Shows which fields were updated and provides a link to view the profile.
 */
export default function AppliedDataModal({
  appliedDataSummary,
  onClose,
  onViewProfile,
}) {
  return (
    <div className="dialog-overlay" style={{ zIndex: 2100 }}>
      <div className="dialog-content" style={{ maxWidth: '500px' }}>
        <div className="dialog-header" style={{ background: '#d1fae5', borderBottom: '2px solid #2D7A52' }}>
          <h3 style={{ display: 'flex', alignItems: 'center', gap: '10px', margin: 0, color: '#065f46' }}>
            <span style={{ fontSize: '24px' }}>&#10003;</span>
            {appliedDataSummary.isNewBorrower ? 'Borrower Added Successfully' : 'Data Applied Successfully'}
          </h3>
          <button
            className="dialog-close"
            onClick={onClose}
            style={{ color: '#065f46' }}
          >
            &times;
          </button>
        </div>
        <div className="dialog-body" style={{ padding: '24px' }}>
          <p style={{ fontSize: '15px', color: '#374151', marginBottom: '20px' }}>
            {appliedDataSummary.isNewBorrower
              ? <><strong>{appliedDataSummary.entityName}</strong> has been added to the CRM.</>
              : <>The following data has been added to <strong>{appliedDataSummary.entityName}</strong>'s profile:</>
            }
          </p>

          {appliedDataSummary.statusUpdated && (
            <div style={{
              background: '#fef3c7',
              border: '1px solid #f59e0b',
              borderRadius: '8px',
              padding: '12px 16px',
              marginBottom: '20px',
              display: 'flex',
              alignItems: 'center',
              gap: '10px'
            }}>
              <span style={{ fontSize: '20px' }}>&#128202;</span>
              <div>
                <strong style={{ color: '#92400e' }}>Status Updated:</strong>
                <span style={{ marginLeft: '8px', color: '#78350f' }}>
                  {appliedDataSummary.oldStatus} &rarr; {appliedDataSummary.newStatus}
                </span>
              </div>
            </div>
          )}

          {appliedDataSummary.appliedFields && appliedDataSummary.appliedFields.length > 0 ? (
            <div style={{
              background: '#f0fdf4',
              border: '1px solid #86efac',
              borderRadius: '8px',
              padding: '16px'
            }}>
              <h4 style={{ margin: '0 0 12px 0', fontSize: '14px', color: '#166534' }}>
                Fields Updated ({appliedDataSummary.appliedFields.length}):
              </h4>
              <div style={{
                maxHeight: '250px',
                overflowY: 'auto',
                fontSize: '13px'
              }}>
                <table style={{ width: '100%', borderCollapse: 'collapse' }}>
                  <tbody>
                    {appliedDataSummary.appliedFields.map((field, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid #dcfce7' }}>
                        <td style={{
                          padding: '8px 12px',
                          fontWeight: '500',
                          color: '#166534',
                          width: '40%'
                        }}>
                          {formatFieldName(field.field)}
                        </td>
                        <td style={{
                          padding: '8px 12px',
                          color: '#15803d'
                        }}>
                          {String(field.value).substring(0, 60)}
                          {String(field.value).length > 60 && '...'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <p style={{ color: '#6b7280', fontStyle: 'italic' }}>
              No additional fields were applied.
            </p>
          )}
        </div>
        <div className="dialog-footer" style={{
          padding: '16px 24px',
          borderTop: '1px solid #e5e7eb',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          background: '#f9fafb'
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 24px',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              background: 'white',
              color: '#374151',
              cursor: 'pointer',
              fontWeight: '500'
            }}
          >
            Close
          </button>
          {appliedDataSummary.entityId && appliedDataSummary.entityType && (
            <button
              onClick={onViewProfile}
              style={{
                padding: '10px 24px',
                border: 'none',
                borderRadius: '6px',
                background: '#2D7A52',
                color: 'white',
                cursor: 'pointer',
                fontWeight: '600',
                display: 'flex',
                alignItems: 'center',
                gap: '8px'
              }}
            >
              View {appliedDataSummary.entityName}'s Profile
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Document Requests Component
 *
 * Displays document requests and intake field updates from call analysis.
 */

import React from 'react';

const DocumentRequests = ({ requests, intakeFields, onApprove }) => {
  const hasContent = (requests && requests.length > 0) || (intakeFields && intakeFields.length > 0);

  if (!hasContent) {
    return (
      <div className="document-requests">
        <p style={{ color: '#6b7280', textAlign: 'center', padding: '40px' }}>
          No document requests or field updates from this call.
        </p>
      </div>
    );
  }

  const pendingDocs = requests?.filter(r => r.approval_status === 'pending') || [];
  const approvedDocs = requests?.filter(r => r.approval_status === 'approved' || r.approval_status === 'auto_approved') || [];
  const pendingFields = intakeFields?.filter(f => f.approval_status === 'pending') || [];

  return (
    <div className="document-requests">
      {/* Document Requests Section */}
      {requests && requests.length > 0 && (
        <>
          <h4 style={{ margin: '0 0 12px', fontSize: '0.875rem', color: '#374151', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            Document Requests ({requests.length})
          </h4>

          {pendingDocs.length > 0 && (
            <div style={{ marginBottom: '20px' }}>
              <div style={{ fontSize: '0.75rem', color: '#f59e0b', marginBottom: '8px', fontWeight: '500' }}>
                Pending Approval ({pendingDocs.length})
              </div>
              {pendingDocs.map((doc) => (
                <div key={doc.id} className="doc-request-card" style={{ marginBottom: '8px', borderLeft: '3px solid #f59e0b' }}>
                  <div className="doc-header">
                    <span className="doc-title">
                      {doc.title || doc.structured_data?.document_name}
                    </span>
                    <button
                      onClick={() => onApprove([doc.id])}
                      style={{
                        padding: '4px 12px',
                        background: '#2D7A52',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        cursor: 'pointer',
                      }}
                    >
                      Request
                    </button>
                  </div>
                  <div className="doc-reason">
                    {doc.content || doc.structured_data?.reason}
                  </div>
                  {doc.evidence && (
                    <div style={{ marginTop: '8px', fontSize: '0.75rem', color: '#6b7280', fontStyle: 'italic' }}>
                      Evidence: "{doc.evidence}"
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}

          {approvedDocs.length > 0 && (
            <div>
              <div style={{ fontSize: '0.75rem', color: '#2D7A52', marginBottom: '8px', fontWeight: '500' }}>
                Approved ({approvedDocs.length})
              </div>
              {approvedDocs.map((doc) => (
                <div key={doc.id} className="doc-request-card" style={{ marginBottom: '8px', borderLeft: '3px solid #2D7A52' }}>
                  <div className="doc-header">
                    <span className="doc-title">
                      {doc.title || doc.structured_data?.document_name}
                    </span>
                    {doc.execution_status === 'executed' && (
                      <span style={{
                        fontSize: '0.7rem',
                        padding: '2px 8px',
                        background: '#dcfce7',
                        color: '#166534',
                        borderRadius: '4px',
                      }}>
                        Sent to Smart Docs
                      </span>
                    )}
                  </div>
                  <div className="doc-reason">
                    {doc.content || doc.structured_data?.reason}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* Intake Field Updates Section */}
      {intakeFields && intakeFields.length > 0 && (
        <div style={{ marginTop: '24px' }}>
          <h4 style={{ margin: '0 0 12px', fontSize: '0.875rem', color: '#374151', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
            1003 Field Updates ({intakeFields.length})
          </h4>

          <p style={{ fontSize: '0.8rem', color: '#6b7280', marginBottom: '12px' }}>
            These values were mentioned during the call and can be used to update the application.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {intakeFields.map((field) => (
              <div
                key={field.id}
                style={{
                  background: '#f9fafb',
                  padding: '12px',
                  borderRadius: '8px',
                  borderLeft: field.approval_status === 'pending' ? '3px solid #f59e0b' : '3px solid #2D7A52',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: '500', fontSize: '0.875rem', color: '#111827' }}>
                    {field.title || field.structured_data?.field_name}
                  </span>
                  {field.approval_status === 'pending' && (
                    <button
                      onClick={() => onApprove([field.id])}
                      style={{
                        padding: '4px 10px',
                        background: '#3b82f6',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        fontSize: '0.7rem',
                        cursor: 'pointer',
                      }}
                    >
                      Apply
                    </button>
                  )}
                </div>

                <div style={{ display: 'flex', gap: '16px', marginTop: '8px', fontSize: '0.8rem' }}>
                  <div>
                    <span style={{ color: '#6b7280' }}>Value: </span>
                    <span style={{ color: '#3b82f6', fontWeight: '500' }}>
                      {field.content || field.structured_data?.proposed_value}
                    </span>
                  </div>
                  {field.confidence && (
                    <div>
                      <span style={{ color: '#6b7280' }}>Confidence: </span>
                      <span style={{
                        color: field.confidence > 0.8 ? '#2D7A52' : field.confidence > 0.6 ? '#f59e0b' : '#6b7280'
                      }}>
                        {Math.round(field.confidence * 100)}%
                      </span>
                    </div>
                  )}
                </div>

                {field.evidence && (
                  <div style={{ marginTop: '8px', fontSize: '0.75rem', color: '#6b7280', fontStyle: 'italic' }}>
                    "{field.evidence}"
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default DocumentRequests;

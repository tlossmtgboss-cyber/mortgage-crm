import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './PortalSelectorModal.css';

/**
 * Portal Selector Modal
 * Shows options for Client Portal, Buyer's Agent Portal, and Listing Agent Portal
 * Allows opening existing portals or creating new ones
 */
const PortalSelectorModal = ({ isOpen, onClose, loan }) => {
  const [portalStatus, setPortalStatus] = useState({
    client: { exists: false, loading: true, url: null },
    buyersAgent: { exists: false, loading: true, url: null, partyId: null },
    listingAgent: { exists: false, loading: true, url: null, transactionId: null },
  });
  const [creating, setCreating] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (isOpen && loan) {
      checkPortalStatus();
    }
  }, [isOpen, loan]);

  const getAuthHeaders = () => {
    const token = localStorage.getItem('token');
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  };

  const checkPortalStatus = async () => {
    if (!loan) return;

    // Check client portal (PURL workspace) via API
    // Try by loan_id first, then by lead_id if available
    const checkClientPortal = async () => {
      // Try looking up by loan ID
      let response = await fetch(
        `${API_BASE_URL}/api/v1/purl-admin/workspaces/by-loan/${loan.id}`,
        { headers: getAuthHeaders() }
      );

      // If not found and lead_id exists, try by lead_id
      if (!response.ok && loan.lead_id && loan.lead_id !== loan.id) {
        response = await fetch(
          `${API_BASE_URL}/api/v1/purl-admin/workspaces/by-lead/${loan.lead_id}`,
          { headers: getAuthHeaders() }
        );
      }

      return response;
    };

    try {
      const response = await checkClientPortal();
      if (response.ok) {
        const data = await response.json();
        const workspace = data.workspace;
        setPortalStatus(prev => ({
          ...prev,
          client: {
            exists: true,
            loading: false,
            url: workspace?.slug ? `/portal/${workspace.slug}` : null,
            workspaceId: workspace?.workspace_id,
          },
        }));
      } else {
        // No workspace found - check if loan has workspace_slug as fallback
        const clientExists = !!loan.workspace_slug;
        setPortalStatus(prev => ({
          ...prev,
          client: {
            exists: clientExists,
            loading: false,
            url: clientExists ? `/portal/${loan.workspace_slug}` : null,
          },
        }));
      }
    } catch (err) {
      console.error('Failed to check client portal:', err);
      // Fallback to loan.workspace_slug
      const clientExists = !!loan.workspace_slug;
      setPortalStatus(prev => ({
        ...prev,
        client: {
          exists: clientExists,
          loading: false,
          url: clientExists ? `/portal/${loan.workspace_slug}` : null,
        },
      }));
    }

    // Check buyer's agent portal (realtor portal)
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/realtor-portal/clients/${loan.lead_id || loan.id}/status`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        setPortalStatus(prev => ({
          ...prev,
          buyersAgent: {
            exists: data.data?.has_portal || false,
            loading: false,
            url: data.data?.portal_url || null,
            partyId: data.data?.partner_id || null,
          },
        }));
      } else {
        setPortalStatus(prev => ({
          ...prev,
          buyersAgent: { exists: false, loading: false, url: null },
        }));
      }
    } catch (err) {
      console.error('Failed to check buyer agent portal:', err);
      setPortalStatus(prev => ({
        ...prev,
        buyersAgent: { exists: false, loading: false, url: null },
      }));
    }

    // Check listing agent portal
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/listing-portal/transactions?loan_id=${loan.id}`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        // Use loose equality to handle string/number type differences
        const transaction = data.data?.transactions?.find(t => String(t.loan_id) === String(loan.id));
        setPortalStatus(prev => ({
          ...prev,
          listingAgent: {
            exists: !!transaction,
            loading: false,
            url: transaction ? `/listing-portal/transactions/${transaction.id}` : null,
            transactionId: transaction?.id || null,
          },
        }));
      } else {
        setPortalStatus(prev => ({
          ...prev,
          listingAgent: { exists: false, loading: false, url: null },
        }));
      }
    } catch (err) {
      console.error('Failed to check listing agent portal:', err);
      setPortalStatus(prev => ({
        ...prev,
        listingAgent: { exists: false, loading: false, url: null },
      }));
    }
  };

  const handleOpenPortal = (type) => {
    const urls = {
      client: portalStatus.client.url,
      buyersAgent: portalStatus.buyersAgent.url,
      listingAgent: portalStatus.listingAgent.url,
    };

    if (urls[type]) {
      window.open(`${window.location.origin}${urls[type]}`, '_blank');
    }
  };

  const handleCreatePortal = async (type) => {
    setCreating(type);
    setError(null);

    try {
      switch (type) {
        case 'client': {
          // Create PURL workspace for client portal
          const response = await fetch(`${API_BASE_URL}/api/v1/purl-admin/workspaces`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
              lead_id: loan.lead_id || null,
              loan_id: loan.id,
              slug: `loan-${loan.id}-${Date.now()}`,
            }),
          });

          if (response.ok) {
            const data = await response.json();
            setPortalStatus(prev => ({
              ...prev,
              client: {
                exists: true,
                loading: false,
                url: `/portal/${data.data?.slug || data.slug}`,
              },
            }));
          } else {
            throw new Error('Failed to create client portal');
          }
          break;
        }

        case 'buyersAgent': {
          // Navigate to realtor portal setup for this loan
          window.location.href = `/referral-partners?setup_portal=true&loan_id=${loan.id}`;
          return;
        }

        case 'listingAgent': {
          // Create listing agent transaction
          const response = await fetch(`${API_BASE_URL}/api/v1/listing-portal/transactions`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
              loan_id: loan.id,
              property_address: loan.property_address || 'Property Address TBD',
              property_city: loan.property_city || null,
              property_state: loan.property_state || null,
              property_zip: loan.property_zip || null,
              purchase_price: loan.purchase_price || loan.loan_amount || null,
              target_close_date: loan.closing_date || loan.expected_close_date || null,
            }),
          });

          if (response.ok) {
            const data = await response.json();
            const transactionId = data.data?.id;
            setPortalStatus(prev => ({
              ...prev,
              listingAgent: {
                exists: true,
                loading: false,
                url: `/listing-portal/transactions/${transactionId}`,
                transactionId,
              },
            }));
          } else {
            const errorData = await response.json().catch(() => ({}));
            console.error('Listing portal creation error:', response.status, errorData);
            throw new Error(errorData.detail || errorData.error || 'Failed to create listing agent portal');
          }
          break;
        }

        default:
          break;
      }
    } catch (err) {
      console.error(`Failed to create ${type} portal:`, err);
      setError(err.message || `Failed to create portal. Please try again.`);
    } finally {
      setCreating(null);
    }
  };

  if (!isOpen) return null;

  const portalTypes = [
    {
      key: 'client',
      title: 'Client Portal',
      description: 'Borrower access to application status, documents, and communication',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
        </svg>
      ),
      color: '#3b82f6',
    },
    {
      key: 'buyersAgent',
      title: "Buyer's Agent Portal",
      description: "Real estate agent access to transaction updates and client status",
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
        </svg>
      ),
      color: '#10b981',
    },
    {
      key: 'listingAgent',
      title: 'Listing Agent Portal',
      description: 'Listing agent access to transaction milestones and communication',
      icon: (
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
          <path d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      ),
      color: '#8b5cf6',
    },
  ];

  return (
    <div className="portal-selector-overlay" onClick={onClose}>
      <div className="portal-selector-modal" onClick={(e) => e.stopPropagation()}>
        <div className="portal-selector-header">
          <h2>Portal Access</h2>
          <p className="property-context">
            {loan.property_address || loan.borrower_name || `Loan #${loan.id}`}
          </p>
          <button className="close-btn" onClick={onClose}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {error && (
          <div className="portal-error">
            <span>{error}</span>
            <button onClick={() => setError(null)}>&times;</button>
          </div>
        )}

        <div className="portal-options">
          {portalTypes.map((portal) => {
            const status = portalStatus[portal.key];
            const isCreating = creating === portal.key;

            return (
              <div key={portal.key} className="portal-option">
                <div className="portal-icon" style={{ backgroundColor: `${portal.color}15`, color: portal.color }}>
                  {portal.icon}
                </div>

                <div className="portal-info">
                  <h3>{portal.title}</h3>
                  <p>{portal.description}</p>
                </div>

                <div className="portal-action">
                  {status.loading ? (
                    <div className="loading-spinner small" />
                  ) : status.exists ? (
                    <button
                      className="btn-open"
                      onClick={() => handleOpenPortal(portal.key)}
                      style={{ backgroundColor: portal.color }}
                    >
                      <svg viewBox="0 0 20 20" fill="currentColor">
                        <path d="M11 3a1 1 0 100 2h2.586l-6.293 6.293a1 1 0 101.414 1.414L15 6.414V9a1 1 0 102 0V4a1 1 0 00-1-1h-5z" />
                        <path d="M5 5a2 2 0 00-2 2v8a2 2 0 002 2h8a2 2 0 002-2v-3a1 1 0 10-2 0v3H5V7h3a1 1 0 000-2H5z" />
                      </svg>
                      Open Portal
                    </button>
                  ) : (
                    <button
                      className="btn-create"
                      onClick={() => handleCreatePortal(portal.key)}
                      disabled={isCreating}
                    >
                      {isCreating ? (
                        <>
                          <div className="loading-spinner small white" />
                          Creating...
                        </>
                      ) : (
                        <>
                          <svg viewBox="0 0 20 20" fill="currentColor">
                            <path fillRule="evenodd" d="M10 3a1 1 0 011 1v5h5a1 1 0 110 2h-5v5a1 1 0 11-2 0v-5H4a1 1 0 110-2h5V4a1 1 0 011-1z" clipRule="evenodd" />
                          </svg>
                          Build Portal
                        </>
                      )}
                    </button>
                  )}
                </div>

                {status.exists && (
                  <div className="portal-status active">
                    <span className="status-dot" style={{ backgroundColor: portal.color }} />
                    Active
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="portal-selector-footer">
          <button className="btn-close" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

export default PortalSelectorModal;

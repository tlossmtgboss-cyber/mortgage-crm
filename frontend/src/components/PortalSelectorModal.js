import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import './PortalSelectorModal.css';
import { getToken } from '../utils/tokenStore';

/**
 * Portal Selector Modal
 * Shows options for Client Portal, Buyer's Agent Portal, and Listing Agent Portal
 * Allows opening existing portals or creating new ones
 */
const PortalSelectorModal = ({ isOpen, onClose, loan }) => {
  const [portalStatus, setPortalStatus] = useState({
    client: { exists: false, loading: true, url: null },
    buyersAgent: { exists: false, loading: true, url: null, partnerId: null },
    listingAgent: { exists: false, loading: true, url: null, transactionId: null },
  });
  const [creating, setCreating] = useState(null);
  const [error, setError] = useState(null);

  // Referral partner selection state
  const [showPartnerSelect, setShowPartnerSelect] = useState(false);
  const [partnerSearch, setPartnerSearch] = useState('');
  const [partnerResults, setPartnerResults] = useState([]);
  const [searchingPartners, setSearchingPartners] = useState(false);
  const [selectedPartner, setSelectedPartner] = useState(null);

  const getAuthHeaders = useCallback(() => {
    const token = getToken();
    return {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json',
    };
  }, []);

  const checkPortalStatus = useCallback(async () => {
    if (!loan) return;

    // Reset to loading state
    setPortalStatus({
      client: { exists: false, loading: true, url: null },
      buyersAgent: { exists: false, loading: true, url: null, partnerId: null },
      listingAgent: { exists: false, loading: true, url: null, transactionId: null },
    });

    // Check client portal (PURL workspace)
    try {
      let response = await fetch(
        `${API_BASE_URL}/api/v1/purl-admin/workspaces/by-loan/${loan.id}`,
        { headers: getAuthHeaders() }
      );

      if (!response.ok && loan.lead_id && loan.lead_id !== loan.id) {
        response = await fetch(
          `${API_BASE_URL}/api/v1/purl-admin/workspaces/by-lead/${loan.lead_id}`,
          { headers: getAuthHeaders() }
        );
      }

      if (response.ok) {
        const data = await response.json();
        const workspace = data.workspace || data.data?.workspace;
        setPortalStatus(prev => ({
          ...prev,
          client: {
            exists: true,
            loading: false,
            url: workspace?.slug ? `/portal/${workspace.slug}` : null,
            workspaceId: workspace?.id || workspace?.workspace_id,
          },
        }));
      } else {
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
        const hasPortal = data.data?.has_portal || data.has_portal || false;
        const partnerId = data.data?.partner_id || data.partner_id || null;
        setPortalStatus(prev => ({
          ...prev,
          buyersAgent: {
            exists: hasPortal,
            loading: false,
            url: hasPortal && partnerId ? `/partner-portal/${partnerId}/client/${loan.lead_id || loan.id}` : null,
            partnerId: partnerId,
          },
        }));
      } else {
        setPortalStatus(prev => ({
          ...prev,
          buyersAgent: { exists: false, loading: false, url: null, partnerId: null },
        }));
      }
    } catch (err) {
      console.error('Failed to check buyer agent portal:', err);
      setPortalStatus(prev => ({
        ...prev,
        buyersAgent: { exists: false, loading: false, url: null, partnerId: null },
      }));
    }

    // Check listing agent portal
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/listing-portal/transactions`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        const transactions = data.data?.transactions || data.transactions || [];
        const transaction = transactions.find(t => String(t.loan_id) === String(loan.id));
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
          listingAgent: { exists: false, loading: false, url: null, transactionId: null },
        }));
      }
    } catch (err) {
      console.error('Failed to check listing agent portal:', err);
      setPortalStatus(prev => ({
        ...prev,
        listingAgent: { exists: false, loading: false, url: null, transactionId: null },
      }));
    }
  }, [loan, getAuthHeaders]);

  useEffect(() => {
    if (isOpen && loan) {
      checkPortalStatus();
    }
  }, [isOpen, loan, checkPortalStatus]);

  // Search for referral partners
  const searchPartners = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setPartnerResults([]);
      return;
    }

    setSearchingPartners(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/referral-partners?search=${encodeURIComponent(query)}&limit=20`,
        { headers: getAuthHeaders() }
      );
      if (response.ok) {
        const data = await response.json();
        // API returns array directly, not wrapped in data/partners
        setPartnerResults(Array.isArray(data) ? data : (data.data?.partners || data.partners || []));
      }
    } catch (err) {
      console.error('Failed to search partners:', err);
    } finally {
      setSearchingPartners(false);
    }
  }, [getAuthHeaders]);

  useEffect(() => {
    const timeoutId = setTimeout(() => {
      searchPartners(partnerSearch);
    }, 300);
    return () => clearTimeout(timeoutId);
  }, [partnerSearch, searchPartners]);

  const handleOpenPortal = (type) => {
    const urls = {
      client: portalStatus.client.url,
      buyersAgent: portalStatus.buyersAgent.url,
      listingAgent: portalStatus.listingAgent.url,
    };

    const url = urls[type];
    if (url) {
      const fullUrl = `${window.location.origin}${url}`;
      window.open(fullUrl, '_blank');
    } else {
      setError(`No URL found for ${type} portal. Please try creating the portal first.`);
    }
  };

  const handleCreatePortal = async (type) => {
    setError(null);

    if (type === 'buyersAgent') {
      // Show partner selection modal instead of creating directly
      setShowPartnerSelect(true);
      setPartnerSearch('');
      setPartnerResults([]);
      setSelectedPartner(null);
      return;
    }

    setCreating(type);

    try {
      switch (type) {
        case 'client': {
          // Build borrower name from loan data
          const borrowerFirstName = loan.borrower_first_name || loan.first_name || (loan.borrower_name?.split(' ')[0]) || '';
          const borrowerLastName = loan.borrower_last_name || loan.last_name || (loan.borrower_name?.split(' ').slice(1).join(' ')) || '';
          const borrowerName = loan.borrower_name || `${borrowerFirstName} ${borrowerLastName}`.trim() || 'Borrower';

          const response = await fetch(`${API_BASE_URL}/api/v1/purl-admin/workspaces`, {
            method: 'POST',
            headers: getAuthHeaders(),
            body: JSON.stringify({
              lead_id: loan.lead_id || null,
              loan_id: loan.id,
              borrower_name: borrowerName,
              first_name: borrowerFirstName || null,
              last_name: borrowerLastName || null,
              email: loan.borrower_email || loan.email || null,
              phone: loan.borrower_phone || loan.phone || null,
              custom_slug: null,  // Let backend generate slug from borrower name
            }),
          });

          if (response.ok) {
            const data = await response.json();
            const slug = data.workspace?.slug || data.data?.slug || data.slug;
            setPortalStatus(prev => ({
              ...prev,
              client: {
                exists: true,
                loading: false,
                url: `/portal/${slug}`,
              },
            }));
          } else {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || errorData.error || 'Failed to create client portal');
          }
          break;
        }

        case 'listingAgent': {
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
            const transactionId = data.data?.id || data.id;
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

  const handleCreateBuyersAgentPortal = async () => {
    if (!selectedPartner) {
      setError('Please select a referral partner');
      return;
    }

    setCreating('buyersAgent');
    setError(null);

    try {
      // Assign the partner to this client/loan
      const response = await fetch(
        `${API_BASE_URL}/api/v1/realtor-portal/clients/${loan.lead_id || loan.id}/assign-partner`,
        {
          method: 'POST',
          headers: getAuthHeaders(),
          body: JSON.stringify({
            partner_id: selectedPartner.id,
          }),
        }
      );

      if (response.ok) {
        const partnerId = selectedPartner.id;
        const clientId = loan.lead_id || loan.id;

        setPortalStatus(prev => ({
          ...prev,
          buyersAgent: {
            exists: true,
            loading: false,
            url: `/partner-portal/${partnerId}/client/${clientId}`,
            partnerId: partnerId,
          },
        }));

        // Close the partner select and open the portal
        setShowPartnerSelect(false);

        // Navigate to the partner portal client page
        window.open(`${window.location.origin}/partner-portal/${partnerId}/client/${clientId}`, '_blank');
      } else {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || errorData.error || 'Failed to assign partner');
      }
    } catch (err) {
      console.error('Failed to create buyer agent portal:', err);
      setError(err.message || 'Failed to create buyer agent portal. Please try again.');
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

  // Partner Selection Modal
  if (showPartnerSelect) {
    return (
      <div className="portal-selector-overlay" onClick={() => setShowPartnerSelect(false)}>
        <div className="portal-selector-modal partner-select-modal" onClick={(e) => e.stopPropagation()}>
          <div className="portal-selector-header">
            <h2>Select Referral Partner</h2>
            <p className="property-context">
              Choose a buyer's agent for {loan.borrower_name || `Loan #${loan.id}`}
            </p>
            <button className="close-btn" onClick={() => setShowPartnerSelect(false)}>
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

          <div className="partner-search-container">
            <label>Search for Partner</label>
            <input
              type="text"
              placeholder="Type partner name..."
              value={partnerSearch}
              onChange={(e) => setPartnerSearch(e.target.value)}
              className="partner-search-input"
              autoFocus
            />

            {searchingPartners && (
              <div className="search-loading">Searching...</div>
            )}

            {partnerResults.length > 0 && (
              <div className="partner-results">
                {partnerResults.map((partner) => (
                  <div
                    key={partner.id}
                    className={`partner-result-item ${selectedPartner?.id === partner.id ? 'selected' : ''}`}
                    onClick={() => setSelectedPartner(partner)}
                  >
                    <div className="partner-avatar">
                      {partner.first_name?.[0]}{partner.last_name?.[0]}
                    </div>
                    <div className="partner-details">
                      <div className="partner-name">
                        {partner.first_name} {partner.last_name}
                      </div>
                      <div className="partner-company">
                        {partner.company_name || partner.email}
                      </div>
                    </div>
                    {selectedPartner?.id === partner.id && (
                      <span className="check-mark">✓</span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {partnerSearch.length >= 2 && !searchingPartners && partnerResults.length === 0 && (
              <div className="no-results">No partners found matching "{partnerSearch}"</div>
            )}
          </div>

          <div className="portal-selector-footer">
            <button className="btn-close" onClick={() => setShowPartnerSelect(false)}>
              Cancel
            </button>
            <button
              className="btn-create-partner"
              onClick={handleCreateBuyersAgentPortal}
              disabled={!selectedPartner || creating === 'buyersAgent'}
            >
              {creating === 'buyersAgent' ? (
                <>
                  <div className="loading-spinner small white" />
                  Creating...
                </>
              ) : (
                'Create Portal'
              )}
            </button>
          </div>
        </div>
      </div>
    );
  }

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

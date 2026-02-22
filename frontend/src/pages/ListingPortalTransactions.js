import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import {
import { toast } from '../utils/toast';
  listTransactions,
  createTransaction,
  formatCurrency,
  formatDate,
  getStatusInfo,
} from '../services/listingPortalApi';
import { API_BASE_URL } from '../services/api';
import './ListingPortalTransactions.css';

const ListingPortalTransactions = () => {
  const navigate = useNavigate();
  const [transactions, setTransactions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [loans, setLoans] = useState([]);
  const [loansLoading, setLoansLoading] = useState(false);
  const [createForm, setCreateForm] = useState({
    loan_id: '',
    property_address: '',
    property_city: '',
    property_state: '',
    property_zip: '',
    purchase_price: '',
    contract_date: '',
    target_close_date: '',
  });
  const [creating, setCreating] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const fetchTransactions = useCallback(async () => {
    try {
      setLoading(true);
      const response = await listTransactions();
      setTransactions(response.data?.transactions || []);
      setError(null);
    } catch (err) {
      console.error('Failed to fetch transactions:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  const fetchLoans = async () => {
    try {
      setLoansLoading(true);
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/loans/?limit=100`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });
      if (response.ok) {
        const data = await response.json();
        setLoans(data.loans || data.data?.loans || []);
      }
    } catch (err) {
      console.error('Failed to fetch loans:', err);
    } finally {
      setLoansLoading(false);
    }
  };

  const handleOpenCreateModal = () => {
    fetchLoans();
    setShowCreateModal(true);
  };

  const handleLoanSelect = (e) => {
    const loanId = e.target.value;
    setCreateForm((prev) => ({ ...prev, loan_id: loanId }));

    // Auto-fill from loan if possible
    const selectedLoan = loans.find((l) => String(l.id) === String(loanId));
    if (selectedLoan) {
      setCreateForm((prev) => ({
        ...prev,
        loan_id: loanId,
        property_address: selectedLoan.property_address || prev.property_address,
        property_city: selectedLoan.property_city || prev.property_city,
        property_state: selectedLoan.property_state || prev.property_state,
        property_zip: selectedLoan.property_zip || prev.property_zip,
        purchase_price: selectedLoan.purchase_price || selectedLoan.loan_amount || prev.purchase_price,
        target_close_date: selectedLoan.closing_date || selectedLoan.expected_close_date || prev.target_close_date,
      }));
    }
  };

  const handleCreateTransaction = async (e) => {
    e.preventDefault();
    if (!createForm.loan_id || !createForm.property_address) {
      toast.error('Please select a loan and enter a property address');
      return;
    }

    try {
      setCreating(true);
      await createTransaction({
        ...createForm,
        loan_id: parseInt(createForm.loan_id, 10),
        purchase_price: createForm.purchase_price ? parseFloat(createForm.purchase_price) : null,
      });
      setShowCreateModal(false);
      setCreateForm({
        loan_id: '',
        property_address: '',
        property_city: '',
        property_state: '',
        property_zip: '',
        purchase_price: '',
        contract_date: '',
        target_close_date: '',
      });
      fetchTransactions();
    } catch (err) {
      console.error('Failed to create transaction:', err);
      toast.error('Failed to create transaction: ' + err.message);
    } finally {
      setCreating(false);
    }
  };

  const filteredTransactions = transactions.filter((t) => {
    const matchesSearch =
      !searchTerm ||
      t.property_address?.toLowerCase().includes(searchTerm.toLowerCase()) ||
      t.property_city?.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || t.current_status === statusFilter;
    return matchesSearch && matchesStatus;
  });

  const statuses = ['all', 'active', 'pending', 'closing', 'closed', 'cancelled', 'on_hold'];

  if (loading && transactions.length === 0) {
    return (
      <div className="listing-portal-transactions">
        <div className="loading-state">
          <div className="spinner"></div>
          <p>Loading transactions...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="listing-portal-transactions">
      <header className="page-header">
        <div className="header-content">
          <h1>Listing Agent Portal</h1>
          <p className="subtitle">
            Manage transaction visibility for listing agents and other parties
          </p>
        </div>
        <button className="btn-primary" onClick={handleOpenCreateModal}>
          + New Transaction
        </button>
      </header>

      {error && (
        <div className="error-banner">
          <span>{error}</span>
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      <div className="filters-bar">
        <div className="search-box">
          <svg className="search-icon" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M8 4a4 4 0 100 8 4 4 0 000-8zM2 8a6 6 0 1110.89 3.476l4.817 4.817a1 1 0 01-1.414 1.414l-4.816-4.816A6 6 0 012 8z"
              clipRule="evenodd"
            />
          </svg>
          <input
            type="text"
            placeholder="Search by address or city..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
          />
        </div>

        <div className="status-filters">
          {statuses.map((status) => (
            <button
              key={status}
              className={`status-filter ${statusFilter === status ? 'active' : ''}`}
              onClick={() => setStatusFilter(status)}
            >
              {status === 'all' ? 'All' : getStatusInfo(status).label}
            </button>
          ))}
        </div>
      </div>

      <div className="stats-row">
        <div className="stat-card">
          <div className="stat-value">{transactions.length}</div>
          <div className="stat-label">Total Transactions</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {transactions.filter((t) => t.current_status === 'active').length}
          </div>
          <div className="stat-label">Active</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {transactions.filter((t) => t.current_status === 'closing').length}
          </div>
          <div className="stat-label">Closing</div>
        </div>
        <div className="stat-card">
          <div className="stat-value">
            {transactions.reduce((sum, t) => sum + (t.party_count || 0), 0)}
          </div>
          <div className="stat-label">Total Parties</div>
        </div>
      </div>

      {filteredTransactions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <path d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
            </svg>
          </div>
          <h3>No transactions found</h3>
          <p>
            {searchTerm || statusFilter !== 'all'
              ? 'Try adjusting your filters'
              : 'Create your first transaction to get started'}
          </p>
          {!searchTerm && statusFilter === 'all' && (
            <button className="btn-primary" onClick={handleOpenCreateModal}>
              Create Transaction
            </button>
          )}
        </div>
      ) : (
        <div className="transactions-grid">
          {filteredTransactions.map((transaction) => {
            const statusInfo = getStatusInfo(transaction.current_status);
            return (
              <div
                key={transaction.id}
                className="transaction-card"
                onClick={() => navigate(`/listing-portal/transactions/${transaction.id}`)}
              >
                <div className="card-header">
                  <span
                    className="status-badge"
                    style={{ backgroundColor: statusInfo.bg, color: statusInfo.color }}
                  >
                    {statusInfo.label}
                  </span>
                  <span className="party-count">{transaction.party_count || 0} parties</span>
                </div>

                <div className="card-body">
                  <h3 className="property-address">{transaction.property_address}</h3>
                  <p className="property-location">
                    {[transaction.property_city, transaction.property_state]
                      .filter(Boolean)
                      .join(', ')}
                  </p>

                  <div className="card-details">
                    {transaction.purchase_price && (
                      <div className="detail-item">
                        <span className="detail-label">Purchase Price</span>
                        <span className="detail-value">
                          {formatCurrency(transaction.purchase_price)}
                        </span>
                      </div>
                    )}
                    {transaction.target_close_date && (
                      <div className="detail-item">
                        <span className="detail-label">Target Close</span>
                        <span className="detail-value">
                          {formatDate(transaction.target_close_date)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="card-footer">
                  <span className="created-date">
                    Created {formatDate(transaction.created_at)}
                  </span>
                  <span className="view-link">View Details &rarr;</span>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Transaction Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create Transaction</h2>
              <button className="close-btn" onClick={() => setShowCreateModal(false)}>
                &times;
              </button>
            </div>

            <form onSubmit={handleCreateTransaction}>
              <div className="form-group">
                <label>Link to Loan *</label>
                <select
                  value={createForm.loan_id}
                  onChange={handleLoanSelect}
                  required
                  disabled={loansLoading}
                >
                  <option value="">
                    {loansLoading ? 'Loading loans...' : 'Select a loan'}
                  </option>
                  {loans.map((loan) => (
                    <option key={loan.id} value={loan.id}>
                      {loan.borrower_name || loan.primary_borrower_name || 'Unknown'} -{' '}
                      {loan.property_address || 'No address'}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Property Address *</label>
                <input
                  type="text"
                  value={createForm.property_address}
                  onChange={(e) =>
                    setCreateForm((prev) => ({ ...prev, property_address: e.target.value }))
                  }
                  required
                  placeholder="123 Main St"
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>City</label>
                  <input
                    type="text"
                    value={createForm.property_city}
                    onChange={(e) =>
                      setCreateForm((prev) => ({ ...prev, property_city: e.target.value }))
                    }
                    placeholder="City"
                  />
                </div>
                <div className="form-group">
                  <label>State</label>
                  <input
                    type="text"
                    value={createForm.property_state}
                    onChange={(e) =>
                      setCreateForm((prev) => ({ ...prev, property_state: e.target.value }))
                    }
                    placeholder="CA"
                    maxLength={2}
                  />
                </div>
                <div className="form-group">
                  <label>ZIP</label>
                  <input
                    type="text"
                    value={createForm.property_zip}
                    onChange={(e) =>
                      setCreateForm((prev) => ({ ...prev, property_zip: e.target.value }))
                    }
                    placeholder="90210"
                    maxLength={10}
                  />
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Purchase Price</label>
                  <input
                    type="number"
                    value={createForm.purchase_price}
                    onChange={(e) =>
                      setCreateForm((prev) => ({ ...prev, purchase_price: e.target.value }))
                    }
                    placeholder="500000"
                  />
                </div>
                <div className="form-group">
                  <label>Target Close Date</label>
                  <input
                    type="date"
                    value={createForm.target_close_date}
                    onChange={(e) =>
                      setCreateForm((prev) => ({ ...prev, target_close_date: e.target.value }))
                    }
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Contract Date</label>
                <input
                  type="date"
                  value={createForm.contract_date}
                  onChange={(e) =>
                    setCreateForm((prev) => ({ ...prev, contract_date: e.target.value }))
                  }
                />
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={creating}>
                  {creating ? 'Creating...' : 'Create Transaction'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default ListingPortalTransactions;

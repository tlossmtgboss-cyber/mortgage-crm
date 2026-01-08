import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { portfolioAPI, mumAPI } from '../services/api';
import './ClosedLoans.css';

/**
 * ClosedLoans - Simple list view of closed/funded loans
 * This page is shown to non-Loan Officer users (processors, underwriters, closers, etc.)
 * Loan Officers see the full MUM Dashboard at /portfolio instead
 */
function ClosedLoans() {
  const navigate = useNavigate();
  const [closedLoans, setClosedLoans] = useState([]);
  const [loading, setLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [sortBy, setSortBy] = useState('close_date');
  const [sortOrder, setSortOrder] = useState('desc');

  useEffect(() => {
    loadClosedLoans();
  }, []);

  const loadClosedLoans = async () => {
    try {
      setLoading(true);
      // Load both portfolio loans and MUM clients for complete closed loans list
      const [loans, mumClients] = await Promise.all([
        portfolioAPI.getAll(),
        mumAPI.getAll()
      ]);

      // Combine and deduplicate loans
      const combinedLoans = [];
      const seenIds = new Set();

      // Add portfolio loans
      if (Array.isArray(loans)) {
        loans.forEach(loan => {
          if (!seenIds.has(loan.id)) {
            seenIds.add(loan.id);
            combinedLoans.push({
              id: loan.id,
              type: 'loan',
              borrower_name: loan.client_name || loan.borrower_name || 'Unknown',
              loan_number: loan.loan_number || 'N/A',
              loan_amount: loan.loan_amount || 0,
              loan_type: loan.loan_type || 'N/A',
              status: loan.status || 'Closed',
              close_date: loan.close_date || loan.funded_at || loan.created_at,
              interest_rate: loan.interest_rate || 0,
              property_address: loan.property_address || 'N/A'
            });
          }
        });
      }

      // Add MUM clients that aren't already in the list
      if (Array.isArray(mumClients)) {
        mumClients.forEach(client => {
          const mumId = `mum_${client.id}`;
          if (!seenIds.has(mumId) && !seenIds.has(client.loan_number)) {
            seenIds.add(mumId);
            combinedLoans.push({
              id: client.id,
              type: 'mum',
              borrower_name: client.client_name || client.name || 'Unknown',
              loan_number: client.servicing_loan_number || client.loan_number || 'N/A',
              loan_amount: client.current_loan_amount || client.loan_balance || 0,
              loan_type: client.loan_type || 'N/A',
              status: 'Closed',
              close_date: client.closing_date || client.original_close_date,
              interest_rate: client.interest_rate || client.current_rate || 0,
              property_address: client.property_address || 'N/A'
            });
          }
        });
      }

      setClosedLoans(combinedLoans);
    } catch (error) {
      console.error('Failed to load closed loans:', error);
      setClosedLoans([]);
    } finally {
      setLoading(false);
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    try {
      return new Date(dateStr).toLocaleDateString();
    } catch {
      return 'N/A';
    }
  };

  // Filter loans by search query
  const filteredLoans = closedLoans.filter(loan => {
    if (!searchQuery.trim()) return true;
    const query = searchQuery.toLowerCase();
    return (
      loan.borrower_name?.toLowerCase().includes(query) ||
      loan.loan_number?.toLowerCase().includes(query) ||
      loan.property_address?.toLowerCase().includes(query) ||
      loan.loan_type?.toLowerCase().includes(query)
    );
  });

  // Sort loans
  const sortedLoans = [...filteredLoans].sort((a, b) => {
    let aVal = a[sortBy];
    let bVal = b[sortBy];

    // Handle date sorting
    if (sortBy === 'close_date') {
      aVal = aVal ? new Date(aVal).getTime() : 0;
      bVal = bVal ? new Date(bVal).getTime() : 0;
    }

    // Handle numeric sorting
    if (sortBy === 'loan_amount' || sortBy === 'interest_rate') {
      aVal = parseFloat(aVal) || 0;
      bVal = parseFloat(bVal) || 0;
    }

    // Handle string sorting
    if (typeof aVal === 'string') {
      aVal = aVal.toLowerCase();
      bVal = bVal?.toLowerCase() || '';
    }

    if (sortOrder === 'asc') {
      return aVal > bVal ? 1 : -1;
    } else {
      return aVal < bVal ? 1 : -1;
    }
  });

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === 'asc' ? 'desc' : 'asc');
    } else {
      setSortBy(column);
      setSortOrder('desc');
    }
  };

  const handleRowClick = (loan) => {
    if (loan.type === 'mum') {
      navigate(`/portfolio/${loan.id}`);
    } else {
      navigate(`/loans/${loan.id}`);
    }
  };

  const getSortIcon = (column) => {
    if (sortBy !== column) return '↕';
    return sortOrder === 'asc' ? '↑' : '↓';
  };

  // Calculate totals
  const totalVolume = sortedLoans.reduce((sum, loan) => sum + (loan.loan_amount || 0), 0);

  if (loading) {
    return (
      <div className="closed-loans-container">
        <div className="loading">Loading closed loans...</div>
      </div>
    );
  }

  return (
    <div className="closed-loans-container">
      <div className="closed-loans-header">
        <h1 className="closed-loans-title">Closed Loans</h1>
        <div className="header-stats">
          <span className="stat-item">
            <strong>{sortedLoans.length}</strong> loans
          </span>
          <span className="stat-divider">•</span>
          <span className="stat-item">
            <strong>{formatCurrency(totalVolume)}</strong> total volume
          </span>
        </div>
      </div>

      <div className="search-bar-container">
        <input
          type="text"
          className="search-bar"
          placeholder="Search by borrower name, loan number, property address..."
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
        />
        {searchQuery && (
          <button className="clear-search" onClick={() => setSearchQuery('')}>
            ×
          </button>
        )}
      </div>

      <div className="closed-loans-table-container">
        <table className="closed-loans-table">
          <thead>
            <tr>
              <th onClick={() => handleSort('borrower_name')} className="sortable">
                Borrower Name {getSortIcon('borrower_name')}
              </th>
              <th onClick={() => handleSort('loan_number')} className="sortable">
                Loan Number {getSortIcon('loan_number')}
              </th>
              <th onClick={() => handleSort('loan_type')} className="sortable">
                Loan Type {getSortIcon('loan_type')}
              </th>
              <th onClick={() => handleSort('loan_amount')} className="sortable">
                Loan Amount {getSortIcon('loan_amount')}
              </th>
              <th onClick={() => handleSort('interest_rate')} className="sortable">
                Rate {getSortIcon('interest_rate')}
              </th>
              <th onClick={() => handleSort('close_date')} className="sortable">
                Close Date {getSortIcon('close_date')}
              </th>
              <th>Property Address</th>
            </tr>
          </thead>
          <tbody>
            {sortedLoans.map((loan) => (
              <tr
                key={`${loan.type}_${loan.id}`}
                onClick={() => handleRowClick(loan)}
                className="loan-row"
              >
                <td>
                  <strong>{loan.borrower_name}</strong>
                </td>
                <td>{loan.loan_number}</td>
                <td>
                  <span className="loan-type-badge">{loan.loan_type}</span>
                </td>
                <td>{formatCurrency(loan.loan_amount)}</td>
                <td>{loan.interest_rate ? `${loan.interest_rate}%` : 'N/A'}</td>
                <td>{formatDate(loan.close_date)}</td>
                <td className="property-address">{loan.property_address}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {sortedLoans.length === 0 && (
          <div className="empty-state">
            {searchQuery ? (
              <>No closed loans match your search criteria.</>
            ) : (
              <>No closed loans found in the system.</>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export default ClosedLoans;

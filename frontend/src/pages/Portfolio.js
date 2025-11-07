import React, { useState, useEffect } from 'react';
import { portfolioAPI } from '../services/api';
import './Portfolio.css';

function Portfolio() {
  const [portfolioData, setPortfolioData] = useState({
    totalLoans: 0,
    totalVolume: 0,
    activeLoans: 0,
    closedLoans: 0,
    loans: []
  });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPortfolio();
  }, []);

  const loadPortfolio = async () => {
    try {
      setLoading(true);
      const [stats, loans] = await Promise.all([
        portfolioAPI.getStats(),
        portfolioAPI.getAll()
      ]);

      setPortfolioData({
        totalLoans: stats.total_loans || 0,
        totalVolume: stats.total_volume || 0,
        activeLoans: stats.active_loans || 0,
        closedLoans: stats.closed_loans || 0,
        loans: loans.map(loan => ({
          id: loan.id,
          borrower: loan.client_name || loan.borrower_name || 'Unknown',
          loanAmount: loan.loan_amount || 0,
          loanType: loan.loan_type || 'N/A',
          status: loan.status || 'Unknown',
          closeDate: loan.close_date || loan.created_at,
          rate: loan.interest_rate || 0
        }))
      });
    } catch (error) {
      console.error('Failed to load portfolio:', error);
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

  if (loading) {
    return (
      <div className="portfolio-container">
        <div className="loading">Loading portfolio...</div>
      </div>
    );
  }

  return (
    <div className="portfolio-container">
      <h1 className="portfolio-title">Portfolio</h1>

      <div className="portfolio-stats">
        <div className="stat-card">
          <div className="stat-icon">💼</div>
          <div className="stat-info">
            <div className="stat-value">{portfolioData.totalLoans}</div>
            <div className="stat-label">Total Loans</div>
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-icon">💰</div>
          <div className="stat-info">
            <div className="stat-value">{formatCurrency(portfolioData.totalVolume)}</div>
            <div className="stat-label">Total Volume</div>
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-icon">🔄</div>
          <div className="stat-info">
            <div className="stat-value">{portfolioData.activeLoans}</div>
            <div className="stat-label">Active Loans</div>
          </div>
        </div>
        
        <div className="stat-card">
          <div className="stat-icon">✅</div>
          <div className="stat-info">
            <div className="stat-value">{portfolioData.closedLoans}</div>
            <div className="stat-label">Closed Loans</div>
          </div>
        </div>
      </div>

      <div className="loans-table-container">
        <h2>Loan History</h2>
        <table className="loans-table">
          <thead>
            <tr>
              <th>Borrower</th>
              <th>Loan Amount</th>
              <th>Type</th>
              <th>Rate</th>
              <th>Status</th>
              <th>Close Date</th>
            </tr>
          </thead>
          <tbody>
            {portfolioData.loans.map((loan) => (
              <tr key={loan.id}>
                <td>{loan.borrower}</td>
                <td>{formatCurrency(loan.loanAmount)}</td>
                <td>{loan.loanType}</td>
                <td>{loan.rate}%</td>
                <td>
                  <span className={`status-badge status-${loan.status.toLowerCase()}`}>
                    {loan.status}
                  </span>
                </td>
                <td>{new Date(loan.closeDate).toLocaleDateString()}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default Portfolio;

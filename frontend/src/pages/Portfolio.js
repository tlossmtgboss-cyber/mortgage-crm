import React, { useState, useEffect } from 'react';
import './Portfolio.css';

function Portfolio() {
  const [portfolioData, setPortfolioData] = useState({
    totalLoans: 0,
    totalVolume: 0,
    activeLoans: 0,
    closedLoans: 0,
    loans: []
  });

  useEffect(() => {
    // Mock data - replace with API call
    const mockData = {
      totalLoans: 47,
      totalVolume: 23500000,
      activeLoans: 12,
      closedLoans: 35,
      loans: [
        {
          id: 1,
          borrower: 'Robert Brown',
          loanAmount: 550000,
          loanType: 'Conventional',
          status: 'Closed',
          closeDate: '2024-10-15',
          rate: 6.5
        },
        {
          id: 2,
          borrower: 'Emily Davis',
          loanAmount: 400000,
          loanType: 'FHA',
          status: 'Active',
          closeDate: '2024-11-30',
          rate: 6.25
        },
        {
          id: 3,
          borrower: 'Michael Chen',
          loanAmount: 725000,
          loanType: 'Jumbo',
          status: 'Closed',
          closeDate: '2024-09-20',
          rate: 6.75
        }
      ]
    };
    setPortfolioData(mockData);
  }, []);

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0
    }).format(amount);
  };

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

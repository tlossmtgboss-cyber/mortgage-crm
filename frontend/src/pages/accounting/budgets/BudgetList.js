import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../../services/accountingApi';
import { usePermissions } from '../../../contexts/PermissionContext';
import '../AccountingShared.css';
import { toast } from '../../../utils/toast';

function BudgetList() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [budgets, setBudgets] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [showModal, setShowModal] = useState(false);
  const [editingBudget, setEditingBudget] = useState(null);
  const [activeTab, setActiveTab] = useState('overview'); // overview, monthly

  // Filters
  const [yearFilter, setYearFilter] = useState(new Date().getFullYear());
  const [statusFilter, setStatusFilter] = useState('');

  // Form state
  const [formData, setFormData] = useState({
    name: '',
    fiscal_year: new Date().getFullYear(),
    description: '',
    status: 'draft',
    items: [],
  });

  // Monthly breakdown for editing
  const [monthlyData, setMonthlyData] = useState({});

  // Fetch budgets
  const fetchBudgets = useCallback(async () => {
    try {
      setLoading(true);
      const params = { fiscal_year: yearFilter };
      if (statusFilter) params.status = statusFilter;

      const data = await accountingAPI.getBudgets(params);
      setBudgets(data?.budgets || []);
      setLoading(false);
    } catch (err) {
      console.error('Error fetching budgets:', err);
      setLoading(false);
    }
  }, [yearFilter, statusFilter]);

  // Fetch accounts for budget items
  const fetchAccounts = useCallback(async () => {
    try {
      const data = await accountingAPI.getChartOfAccounts();
      // Filter for expense and revenue accounts typically used in budgets
      const budgetAccounts = (data?.accounts || []).filter(
        a => ['expense', 'revenue'].includes(a.account_type)
      );
      setAccounts(budgetAccounts);
    } catch (err) {
      console.error('Error fetching accounts:', err);
    }
  }, []);

  useEffect(() => {
    fetchBudgets();
  }, [fetchBudgets]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount || 0);
  };

  // Get month names
  const months = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'
  ];

  const fullMonths = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  // Initialize monthly data for an account
  const initializeMonthlyData = (items = []) => {
    const data = {};
    items.forEach(item => {
      data[item.account_id] = {
        account_id: item.account_id,
        account_name: item.account_name,
        annual_amount: item.annual_amount || 0,
        monthly: item.monthly || months.reduce((acc, _, i) => {
          acc[i] = item.annual_amount ? item.annual_amount / 12 : 0;
          return acc;
        }, {}),
      };
    });
    return data;
  };

  // Open modal
  const openModal = (budget = null) => {
    if (budget) {
      setEditingBudget(budget);
      setFormData({
        name: budget.name || '',
        fiscal_year: budget.fiscal_year || new Date().getFullYear(),
        description: budget.description || '',
        status: budget.status || 'draft',
        items: budget.items || [],
      });
      setMonthlyData(initializeMonthlyData(budget.items));
    } else {
      setEditingBudget(null);
      setFormData({
        name: '',
        fiscal_year: new Date().getFullYear(),
        description: '',
        status: 'draft',
        items: [],
      });
      setMonthlyData({});
    }
    setActiveTab('overview');
    setShowModal(true);
  };

  // Close modal
  const closeModal = () => {
    setShowModal(false);
    setEditingBudget(null);
  };

  // Add account to budget
  const addAccountToBudget = (accountId) => {
    if (monthlyData[accountId]) return; // Already added

    const account = accounts.find(a => a.id === accountId);
    if (!account) return;

    setMonthlyData(prev => ({
      ...prev,
      [accountId]: {
        account_id: accountId,
        account_name: account.name,
        account_number: account.account_number,
        account_type: account.account_type,
        annual_amount: 0,
        monthly: months.reduce((acc, _, i) => {
          acc[i] = 0;
          return acc;
        }, {}),
      },
    }));
  };

  // Remove account from budget
  const removeAccountFromBudget = (accountId) => {
    setMonthlyData(prev => {
      const newData = { ...prev };
      delete newData[accountId];
      return newData;
    });
  };

  // Update annual amount (distribute evenly)
  const updateAnnualAmount = (accountId, amount) => {
    const monthlyAmount = amount / 12;
    setMonthlyData(prev => ({
      ...prev,
      [accountId]: {
        ...prev[accountId],
        annual_amount: amount,
        monthly: months.reduce((acc, _, i) => {
          acc[i] = monthlyAmount;
          return acc;
        }, {}),
      },
    }));
  };

  // Update monthly amount
  const updateMonthlyAmount = (accountId, monthIndex, amount) => {
    setMonthlyData(prev => {
      const newMonthly = { ...prev[accountId].monthly, [monthIndex]: parseFloat(amount) || 0 };
      const annualAmount = Object.values(newMonthly).reduce((sum, val) => sum + val, 0);
      return {
        ...prev,
        [accountId]: {
          ...prev[accountId],
          monthly: newMonthly,
          annual_amount: annualAmount,
        },
      };
    });
  };

  // Calculate totals
  const calculateTotals = () => {
    const totals = {
      annual: 0,
      monthly: months.reduce((acc, _, i) => { acc[i] = 0; return acc; }, {}),
      byType: { revenue: 0, expense: 0 },
    };

    Object.values(monthlyData).forEach(item => {
      totals.annual += item.annual_amount;
      if (item.account_type === 'revenue') {
        totals.byType.revenue += item.annual_amount;
      } else {
        totals.byType.expense += item.annual_amount;
      }
      Object.entries(item.monthly).forEach(([month, amount]) => {
        totals.monthly[month] += amount;
      });
    });

    return totals;
  };

  // Handle save
  const handleSave = async (status = formData.status) => {
    try {
      const items = Object.values(monthlyData).map(item => ({
        account_id: item.account_id,
        annual_amount: item.annual_amount,
        monthly: item.monthly,
      }));

      const payload = {
        ...formData,
        status,
        items,
      };

      if (editingBudget) {
        await accountingAPI.updateBudget(editingBudget.id, payload);
      } else {
        await accountingAPI.createBudget(payload);
      }

      closeModal();
      fetchBudgets();
    } catch (err) {
      console.error('Error saving budget:', err);
      toast.error('Failed to save budget');
    }
  };

  // Handle approve
  const handleApprove = async (budget) => {
    if (!window.confirm('Are you sure you want to approve this budget?')) return;
    try {
      await accountingAPI.approveBudget(budget.id);
      fetchBudgets();
    } catch (err) {
      console.error('Error approving budget:', err);
      toast.error('Failed to approve budget');
    }
  };

  // Handle delete
  const handleDelete = async (budget) => {
    if (!window.confirm('Are you sure you want to delete this budget?')) return;
    try {
      await accountingAPI.deleteBudget(budget.id);
      fetchBudgets();
    } catch (err) {
      console.error('Error deleting budget:', err);
      toast.error('Failed to delete budget');
    }
  };

  // Copy budget to new year
  const handleCopyBudget = async (budget) => {
    const newYear = prompt('Enter the fiscal year for the new budget:', new Date().getFullYear() + 1);
    if (!newYear) return;

    try {
      await accountingAPI.copyBudget(budget.id, { fiscal_year: parseInt(newYear) });
      setYearFilter(parseInt(newYear));
      fetchBudgets();
    } catch (err) {
      console.error('Error copying budget:', err);
      toast.error('Failed to copy budget');
    }
  };

  // Get status badge
  const getStatusBadge = (status) => {
    const badges = {
      draft: 'badge-draft',
      pending_approval: 'badge-warning',
      approved: 'badge-success',
      closed: 'badge-default',
    };
    return badges[status] || 'badge-default';
  };

  // Generate year options
  const yearOptions = [];
  const currentYear = new Date().getFullYear();
  for (let y = currentYear - 2; y <= currentYear + 2; y++) {
    yearOptions.push(y);
  }

  const totals = calculateTotals();

  if (loading) {
    return (
      <div className="accounting-page loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Budgets...</p>
        </div>
      </div>
    );
  }

  if (!canAccessAccounting) {
    return (
      <div className="accounting-page budget-list">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Budgets.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="accounting-page budget-list">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-calculator"></i> Budgets</h1>
            <p className="subtitle">Create and manage annual budgets</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-secondary" onClick={() => navigate('/accounting/budgets/variance')}>
            <i className="fas fa-chart-bar"></i> Variance Report
          </button>
          <button className="btn-primary" onClick={() => openModal()}>
            <i className="fas fa-plus"></i> New Budget
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar">
        <div className="toolbar-left">
          <select
            value={yearFilter}
            onChange={(e) => setYearFilter(parseInt(e.target.value))}
            className="filter-select"
          >
            {yearOptions.map(year => (
              <option key={year} value={year}>{year}</option>
            ))}
          </select>

          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="filter-select"
          >
            <option value="">All Statuses</option>
            <option value="draft">Draft</option>
            <option value="pending_approval">Pending Approval</option>
            <option value="approved">Approved</option>
            <option value="closed">Closed</option>
          </select>
        </div>

        <div className="toolbar-right">
          <button className="toolbar-btn" onClick={fetchBudgets} title="Refresh">
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>

      {/* Budgets Grid */}
      <div className="budgets-grid">
        {budgets.length > 0 ? (
          budgets.map(budget => (
            <div key={budget.id} className="budget-card">
              <div className="card-header">
                <div className="budget-info">
                  <h3>{budget.name}</h3>
                  <span className="fiscal-year">FY {budget.fiscal_year}</span>
                </div>
                <span className={`status-badge ${getStatusBadge(budget.status)}`}>
                  {budget.status?.replace('_', ' ')}
                </span>
              </div>

              <div className="card-body">
                {budget.description && (
                  <p className="budget-description">{budget.description}</p>
                )}

                <div className="budget-summary">
                  <div className="summary-row">
                    <span className="label">Revenue Budget</span>
                    <span className="value positive">{formatCurrency(budget.total_revenue)}</span>
                  </div>
                  <div className="summary-row">
                    <span className="label">Expense Budget</span>
                    <span className="value negative">{formatCurrency(budget.total_expenses)}</span>
                  </div>
                  <div className="summary-row net">
                    <span className="label">Net Budget</span>
                    <span className={`value ${(budget.total_revenue - budget.total_expenses) >= 0 ? 'positive' : 'negative'}`}>
                      {formatCurrency(budget.total_revenue - budget.total_expenses)}
                    </span>
                  </div>
                </div>

                <div className="budget-meta">
                  <span><i className="fas fa-list"></i> {budget.item_count || 0} line items</span>
                  <span><i className="fas fa-calendar"></i> Updated {new Date(budget.updated_at).toLocaleDateString()}</span>
                </div>
              </div>

              <div className="card-actions">
                <button
                  className="action-btn"
                  onClick={() => openModal(budget)}
                  title="Edit"
                  disabled={budget.status === 'closed'}
                >
                  <i className="fas fa-edit"></i>
                </button>
                <button
                  className="action-btn"
                  onClick={() => navigate(`/accounting/budgets/variance?budget=${budget.id}`)}
                  title="View Variance"
                >
                  <i className="fas fa-chart-bar"></i>
                </button>
                <button
                  className="action-btn"
                  onClick={() => handleCopyBudget(budget)}
                  title="Copy to New Year"
                >
                  <i className="fas fa-copy"></i>
                </button>
                {budget.status === 'pending_approval' && (
                  <button
                    className="action-btn success"
                    onClick={() => handleApprove(budget)}
                    title="Approve"
                  >
                    <i className="fas fa-check"></i>
                  </button>
                )}
                {budget.status === 'draft' && (
                  <button
                    className="action-btn danger"
                    onClick={() => handleDelete(budget)}
                    title="Delete"
                  >
                    <i className="fas fa-trash"></i>
                  </button>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="empty-state full-width">
            <i className="fas fa-calculator"></i>
            <h3>No Budgets Found</h3>
            <p>Create your first budget to start planning.</p>
            <button className="btn-primary" onClick={() => openModal()}>
              <i className="fas fa-plus"></i> Create Budget
            </button>
          </div>
        )}
      </div>

      {/* Budget Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={closeModal}>
          <div className="modal-content xlarge" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>{editingBudget ? 'Edit Budget' : 'New Budget'}</h2>
              <button className="close-btn" onClick={closeModal}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              {/* Budget Info */}
              <div className="form-row">
                <div className="form-group">
                  <label>Budget Name *</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData(prev => ({ ...prev, name: e.target.value }))}
                    placeholder="e.g., Operating Budget 2024"
                    required
                  />
                </div>
                <div className="form-group">
                  <label>Fiscal Year *</label>
                  <select
                    value={formData.fiscal_year}
                    onChange={(e) => setFormData(prev => ({ ...prev, fiscal_year: parseInt(e.target.value) }))}
                  >
                    {yearOptions.map(year => (
                      <option key={year} value={year}>{year}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData(prev => ({ ...prev, description: e.target.value }))}
                  placeholder="Budget notes and assumptions..."
                  rows="2"
                />
              </div>

              {/* Tabs */}
              <div className="budget-tabs">
                <button
                  className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
                  onClick={() => setActiveTab('overview')}
                >
                  <i className="fas fa-list"></i> Line Items
                </button>
                <button
                  className={`tab-btn ${activeTab === 'monthly' ? 'active' : ''}`}
                  onClick={() => setActiveTab('monthly')}
                >
                  <i className="fas fa-calendar"></i> Monthly Breakdown
                </button>
              </div>

              {activeTab === 'overview' && (
                <div className="budget-items-section">
                  {/* Add Account Dropdown */}
                  <div className="add-account-row">
                    <select
                      onChange={(e) => {
                        if (e.target.value) {
                          addAccountToBudget(e.target.value);
                          e.target.value = '';
                        }
                      }}
                      className="filter-select"
                    >
                      <option value="">+ Add Account to Budget</option>
                      <optgroup label="Revenue">
                        {accounts.filter(a => a.account_type === 'revenue').map(a => (
                          <option key={a.id} value={a.id} disabled={!!monthlyData[a.id]}>
                            {a.account_number} - {a.name}
                          </option>
                        ))}
                      </optgroup>
                      <optgroup label="Expenses">
                        {accounts.filter(a => a.account_type === 'expense').map(a => (
                          <option key={a.id} value={a.id} disabled={!!monthlyData[a.id]}>
                            {a.account_number} - {a.name}
                          </option>
                        ))}
                      </optgroup>
                    </select>
                  </div>

                  {/* Budget Items Table */}
                  <div className="budget-items-table">
                    <div className="table-header">
                      <div className="header-cell account">Account</div>
                      <div className="header-cell amount">Annual Budget</div>
                      <div className="header-cell amount">Monthly Avg</div>
                      <div className="header-cell actions"></div>
                    </div>

                    <div className="table-body">
                      {/* Revenue Items */}
                      {Object.values(monthlyData).filter(item => item.account_type === 'revenue').length > 0 && (
                        <>
                          <div className="section-header-row">
                            <span>Revenue</span>
                          </div>
                          {Object.values(monthlyData)
                            .filter(item => item.account_type === 'revenue')
                            .map(item => (
                              <div key={item.account_id} className="table-row">
                                <div className="cell account">
                                  <span className="account-number">{item.account_number}</span>
                                  <span className="account-name">{item.account_name}</span>
                                </div>
                                <div className="cell amount">
                                  <input
                                    type="number"
                                    value={item.annual_amount}
                                    onChange={(e) => updateAnnualAmount(item.account_id, parseFloat(e.target.value) || 0)}
                                    step="100"
                                  />
                                </div>
                                <div className="cell amount monthly-avg">
                                  {formatCurrency(item.annual_amount / 12)}
                                </div>
                                <div className="cell actions">
                                  <button
                                    className="remove-btn"
                                    onClick={() => removeAccountFromBudget(item.account_id)}
                                  >
                                    <i className="fas fa-times"></i>
                                  </button>
                                </div>
                              </div>
                            ))}
                          <div className="subtotal-row">
                            <div className="cell account">Total Revenue</div>
                            <div className="cell amount">{formatCurrency(totals.byType.revenue)}</div>
                            <div className="cell amount">{formatCurrency(totals.byType.revenue / 12)}</div>
                            <div className="cell actions"></div>
                          </div>
                        </>
                      )}

                      {/* Expense Items */}
                      {Object.values(monthlyData).filter(item => item.account_type === 'expense').length > 0 && (
                        <>
                          <div className="section-header-row">
                            <span>Expenses</span>
                          </div>
                          {Object.values(monthlyData)
                            .filter(item => item.account_type === 'expense')
                            .map(item => (
                              <div key={item.account_id} className="table-row">
                                <div className="cell account">
                                  <span className="account-number">{item.account_number}</span>
                                  <span className="account-name">{item.account_name}</span>
                                </div>
                                <div className="cell amount">
                                  <input
                                    type="number"
                                    value={item.annual_amount}
                                    onChange={(e) => updateAnnualAmount(item.account_id, parseFloat(e.target.value) || 0)}
                                    step="100"
                                  />
                                </div>
                                <div className="cell amount monthly-avg">
                                  {formatCurrency(item.annual_amount / 12)}
                                </div>
                                <div className="cell actions">
                                  <button
                                    className="remove-btn"
                                    onClick={() => removeAccountFromBudget(item.account_id)}
                                  >
                                    <i className="fas fa-times"></i>
                                  </button>
                                </div>
                              </div>
                            ))}
                          <div className="subtotal-row">
                            <div className="cell account">Total Expenses</div>
                            <div className="cell amount">{formatCurrency(totals.byType.expense)}</div>
                            <div className="cell amount">{formatCurrency(totals.byType.expense / 12)}</div>
                            <div className="cell actions"></div>
                          </div>
                        </>
                      )}

                      {Object.keys(monthlyData).length === 0 && (
                        <div className="empty-row">
                          <p>No accounts added. Use the dropdown above to add accounts to this budget.</p>
                        </div>
                      )}
                    </div>

                    {/* Net Total */}
                    {Object.keys(monthlyData).length > 0 && (
                      <div className="net-total-row">
                        <div className="cell account">Net Budget (Revenue - Expenses)</div>
                        <div className={`cell amount ${(totals.byType.revenue - totals.byType.expense) >= 0 ? 'positive' : 'negative'}`}>
                          {formatCurrency(totals.byType.revenue - totals.byType.expense)}
                        </div>
                        <div className={`cell amount ${(totals.byType.revenue - totals.byType.expense) >= 0 ? 'positive' : 'negative'}`}>
                          {formatCurrency((totals.byType.revenue - totals.byType.expense) / 12)}
                        </div>
                        <div className="cell actions"></div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {activeTab === 'monthly' && (
                <div className="monthly-breakdown-section">
                  <div className="monthly-table-wrapper">
                    <table className="monthly-table">
                      <thead>
                        <tr>
                          <th className="account-col">Account</th>
                          {months.map((month, i) => (
                            <th key={i} className="month-col">{month}</th>
                          ))}
                          <th className="total-col">Total</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.values(monthlyData).map(item => (
                          <tr key={item.account_id}>
                            <td className="account-col">
                              <span className="account-name">{item.account_name}</span>
                            </td>
                            {months.map((_, monthIndex) => (
                              <td key={monthIndex} className="month-col">
                                <input
                                  type="number"
                                  value={item.monthly[monthIndex] || 0}
                                  onChange={(e) => updateMonthlyAmount(item.account_id, monthIndex, e.target.value)}
                                  step="100"
                                />
                              </td>
                            ))}
                            <td className="total-col">
                              {formatCurrency(item.annual_amount)}
                            </td>
                          </tr>
                        ))}
                        {Object.keys(monthlyData).length > 0 && (
                          <tr className="totals-row">
                            <td className="account-col"><strong>Monthly Totals</strong></td>
                            {months.map((_, monthIndex) => (
                              <td key={monthIndex} className="month-col">
                                <strong>{formatCurrency(totals.monthly[monthIndex])}</strong>
                              </td>
                            ))}
                            <td className="total-col">
                              <strong>{formatCurrency(totals.annual)}</strong>
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>

                  {Object.keys(monthlyData).length === 0 && (
                    <div className="empty-state small">
                      <p>Add accounts in the Line Items tab first.</p>
                    </div>
                  )}
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={closeModal}>
                Cancel
              </button>
              <button className="btn-secondary" onClick={() => handleSave('draft')}>
                Save as Draft
              </button>
              <button className="btn-primary" onClick={() => handleSave('pending_approval')}>
                Submit for Approval
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default BudgetList;

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../services/accountingApi';
import { usePermissions } from '../../contexts/PermissionContext';
import './ChartOfAccounts.css';
import { toast } from '../../utils/toast';

function ChartOfAccounts() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [accounts, setAccounts] = useState([]);
  const [accountTree, setAccountTree] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterType, setFilterType] = useState('all');
  const [expandedAccounts, setExpandedAccounts] = useState(new Set());
  const [showInactive, setShowInactive] = useState(false);

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [modalMode, setModalMode] = useState('create'); // 'create' or 'edit'
  const [selectedAccount, setSelectedAccount] = useState(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    account_number: '',
    name: '',
    description: '',
    account_type: 'asset',
    account_subtype: '',
    parent_account_id: '',
    normal_balance: 'debit',
    is_bank_account: false,
    currency: 'USD',
    is_active: true,
    tax_code: '',
  });

  const accountTypes = [
    { value: 'asset', label: 'Asset', icon: 'fa-building', color: '#3b82f6' },
    { value: 'liability', label: 'Liability', icon: 'fa-credit-card', color: '#ef4444' },
    { value: 'equity', label: 'Equity', icon: 'fa-landmark', color: '#8b5cf6' },
    { value: 'revenue', label: 'Revenue', icon: 'fa-arrow-trend-up', color: '#22c55e' },
    { value: 'expense', label: 'Expense', icon: 'fa-arrow-trend-down', color: '#f97316' },
  ];

  const accountSubtypes = {
    asset: [
      { value: 'current_asset', label: 'Current Asset' },
      { value: 'fixed_asset', label: 'Fixed Asset' },
      { value: 'other_asset', label: 'Other Asset' },
    ],
    liability: [
      { value: 'current_liability', label: 'Current Liability' },
      { value: 'long_term_liability', label: 'Long-Term Liability' },
    ],
    equity: [
      { value: 'equity', label: 'Equity' },
      { value: 'retained_earnings', label: 'Retained Earnings' },
    ],
    revenue: [
      { value: 'operating_revenue', label: 'Operating Revenue' },
      { value: 'other_revenue', label: 'Other Revenue' },
    ],
    expense: [
      { value: 'cost_of_goods', label: 'Cost of Goods Sold' },
      { value: 'operating_expense', label: 'Operating Expense' },
      { value: 'other_expense', label: 'Other Expense' },
    ],
  };

  // Fetch accounts
  const fetchAccounts = useCallback(async () => {
    try {
      setError(null);
      const [accountsData, treeData] = await Promise.all([
        accountingAPI.getAccounts({ include_inactive: showInactive }),
        accountingAPI.getAccountsTree(),
      ]);
      setAccounts(accountsData?.accounts || []);
      setAccountTree(treeData?.tree || []);

      // Expand top-level accounts by default
      const topLevelIds = new Set((treeData?.tree || []).map(a => a.id));
      setExpandedAccounts(topLevelIds);

      setLoading(false);
    } catch (err) {
      console.error('Error fetching accounts:', err);
      setError('Failed to load chart of accounts. Please try again.');
      setLoading(false);
    }
  }, [showInactive]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  // Build tree structure from flat accounts if tree API fails
  const buildTreeFromAccounts = (accounts) => {
    const accountMap = new Map();
    const roots = [];

    // First pass: create map
    accounts.forEach(account => {
      accountMap.set(account.id, { ...account, children: [] });
    });

    // Second pass: build tree
    accounts.forEach(account => {
      const node = accountMap.get(account.id);
      if (account.parent_account_id && accountMap.has(account.parent_account_id)) {
        accountMap.get(account.parent_account_id).children.push(node);
      } else {
        roots.push(node);
      }
    });

    // Sort by display_order or account_number
    const sortFn = (a, b) => {
      if (a.display_order !== b.display_order) {
        return (a.display_order || 0) - (b.display_order || 0);
      }
      return a.account_number.localeCompare(b.account_number);
    };

    const sortTree = (nodes) => {
      nodes.sort(sortFn);
      nodes.forEach(node => {
        if (node.children.length > 0) {
          sortTree(node.children);
        }
      });
    };

    sortTree(roots);
    return roots;
  };

  // Get effective tree (from API or built from accounts)
  const getEffectiveTree = () => {
    if (accountTree.length > 0) {
      return accountTree;
    }
    return buildTreeFromAccounts(accounts);
  };

  // Filter accounts
  const filterAccounts = (tree) => {
    const filterNode = (node) => {
      // Check type filter
      if (filterType !== 'all' && node.account_type !== filterType) {
        // But still include if children match
        const filteredChildren = node.children?.filter(child => filterNode(child)) || [];
        if (filteredChildren.length === 0) {
          return false;
        }
      }

      // Check active filter
      if (!showInactive && !node.is_active) {
        return false;
      }

      // Check search term
      if (searchTerm) {
        const term = searchTerm.toLowerCase();
        const matches =
          node.account_number.toLowerCase().includes(term) ||
          node.name.toLowerCase().includes(term) ||
          (node.description || '').toLowerCase().includes(term);

        if (!matches) {
          // Check if any children match
          const hasMatchingChild = node.children?.some(child => filterNode(child)) || false;
          if (!hasMatchingChild) {
            return false;
          }
        }
      }

      return true;
    };

    return tree.filter(node => filterNode(node));
  };

  // Toggle account expansion
  const toggleExpand = (accountId) => {
    const newExpanded = new Set(expandedAccounts);
    if (newExpanded.has(accountId)) {
      newExpanded.delete(accountId);
    } else {
      newExpanded.add(accountId);
    }
    setExpandedAccounts(newExpanded);
  };

  // Expand all
  const expandAll = () => {
    const allIds = new Set();
    const addIds = (nodes) => {
      nodes.forEach(node => {
        allIds.add(node.id);
        if (node.children?.length > 0) {
          addIds(node.children);
        }
      });
    };
    addIds(getEffectiveTree());
    setExpandedAccounts(allIds);
  };

  // Collapse all
  const collapseAll = () => {
    setExpandedAccounts(new Set());
  };

  // Open create modal
  const openCreateModal = (parentAccount = null) => {
    setModalMode('create');
    setSelectedAccount(null);
    setFormData({
      account_number: '',
      name: '',
      description: '',
      account_type: parentAccount?.account_type || 'asset',
      account_subtype: parentAccount?.account_subtype || '',
      parent_account_id: parentAccount?.id || '',
      normal_balance: parentAccount?.normal_balance || 'debit',
      is_bank_account: false,
      currency: 'USD',
      is_active: true,
      tax_code: '',
    });
    setShowModal(true);
  };

  // Open edit modal
  const openEditModal = (account) => {
    setModalMode('edit');
    setSelectedAccount(account);
    setFormData({
      account_number: account.account_number || '',
      name: account.name || '',
      description: account.description || '',
      account_type: account.account_type || 'asset',
      account_subtype: account.account_subtype || '',
      parent_account_id: account.parent_account_id || '',
      normal_balance: account.normal_balance || 'debit',
      is_bank_account: account.is_bank_account || false,
      currency: account.currency || 'USD',
      is_active: account.is_active !== false,
      tax_code: account.tax_code || '',
    });
    setShowModal(true);
  };

  // Handle form change
  const handleFormChange = (field, value) => {
    setFormData(prev => {
      const updated = { ...prev, [field]: value };

      // Auto-set normal balance based on account type
      if (field === 'account_type') {
        if (['asset', 'expense'].includes(value)) {
          updated.normal_balance = 'debit';
        } else {
          updated.normal_balance = 'credit';
        }
        // Clear subtype when type changes
        updated.account_subtype = '';
      }

      return updated;
    });
  };

  // Save account
  const handleSave = async () => {
    try {
      setSaving(true);

      const data = {
        ...formData,
        parent_account_id: formData.parent_account_id || null,
      };

      if (modalMode === 'create') {
        await accountingAPI.createAccount(data);
      } else {
        await accountingAPI.updateAccount(selectedAccount.id, data);
      }

      setShowModal(false);
      fetchAccounts();
    } catch (err) {
      console.error('Error saving account:', err);
      toast.error(err.response?.data?.detail || 'Failed to save account. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(amount || 0);
  };

  // Get account type info
  const getAccountTypeInfo = (type) => {
    return accountTypes.find(t => t.value === type) || accountTypes[0];
  };

  // Render account row
  const renderAccountRow = (account, level = 0) => {
    const hasChildren = account.children?.length > 0;
    const isExpanded = expandedAccounts.has(account.id);
    const typeInfo = getAccountTypeInfo(account.account_type);

    return (
      <div key={account.id} className="account-node">
        <div
          className={`account-row ${!account.is_active ? 'inactive' : ''} ${account.is_system_account ? 'system' : ''}`}
          style={{ paddingLeft: `${20 + level * 24}px` }}
        >
          <div className="account-expand">
            {hasChildren ? (
              <button
                className="expand-btn"
                onClick={() => toggleExpand(account.id)}
              >
                <i className={`fas fa-chevron-${isExpanded ? 'down' : 'right'}`}></i>
              </button>
            ) : (
              <span className="expand-placeholder"></span>
            )}
          </div>

          <div className="account-number">{account.account_number}</div>

          <div className="account-name">
            <span className="name-text">{account.name}</span>
            {account.is_bank_account && (
              <span className="badge bank">
                <i className="fas fa-university"></i>
              </span>
            )}
            {account.is_system_account && (
              <span className="badge system">System</span>
            )}
            {!account.is_active && (
              <span className="badge inactive">Inactive</span>
            )}
          </div>

          <div className="account-type">
            <span
              className="type-badge"
              style={{ backgroundColor: `${typeInfo.color}15`, color: typeInfo.color }}
            >
              <i className={`fas ${typeInfo.icon}`}></i>
              {typeInfo.label}
            </span>
          </div>

          <div className="account-balance">
            {account.balance !== undefined ? formatCurrency(account.balance) : '-'}
          </div>

          <div className="account-actions">
            <button
              className="action-btn"
              onClick={() => navigate(`/accounting/accounts/${account.id}`)}
              title="View Details"
            >
              <i className="fas fa-eye"></i>
            </button>
            <button
              className="action-btn"
              onClick={() => openEditModal(account)}
              title="Edit Account"
              disabled={account.is_system_account}
            >
              <i className="fas fa-edit"></i>
            </button>
            <button
              className="action-btn"
              onClick={() => openCreateModal(account)}
              title="Add Sub-Account"
            >
              <i className="fas fa-plus"></i>
            </button>
          </div>
        </div>

        {hasChildren && isExpanded && (
          <div className="account-children">
            {account.children.map(child => renderAccountRow(child, level + 1))}
          </div>
        )}
      </div>
    );
  };

  if (loading) {
    return (
      <div className="chart-of-accounts loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Chart of Accounts...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="chart-of-accounts">
        <div className="page-header">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i> Back
          </button>
          <h1><i className="fas fa-sitemap"></i> Chart of Accounts</h1>
        </div>
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h3>Unable to Load Data</h3>
          <p>{error}</p>
          <button className="retry-btn" onClick={fetchAccounts}>
            <i className="fas fa-redo"></i> Retry
          </button>
        </div>
      </div>
    );
  }

  const effectiveTree = getEffectiveTree();
  const filteredTree = filterAccounts(effectiveTree);

  if (!canAccessAccounting) {
    return (
      <div className="chart-of-accounts">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Chart of Accounts.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="chart-of-accounts">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-sitemap"></i> Chart of Accounts</h1>
            <p className="subtitle">{accounts.length} accounts</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-primary" onClick={() => openCreateModal()}>
            <i className="fas fa-plus"></i> New Account
          </button>
        </div>
      </div>

      {/* Toolbar */}
      <div className="toolbar">
        <div className="toolbar-left">
          <div className="search-box">
            <i className="fas fa-search"></i>
            <input
              type="text"
              placeholder="Search accounts..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
            />
            {searchTerm && (
              <button className="clear-btn" onClick={() => setSearchTerm('')}>
                <i className="fas fa-times"></i>
              </button>
            )}
          </div>

          <div className="filter-group">
            <select
              value={filterType}
              onChange={(e) => setFilterType(e.target.value)}
              className="filter-select"
            >
              <option value="all">All Types</option>
              {accountTypes.map(type => (
                <option key={type.value} value={type.value}>{type.label}</option>
              ))}
            </select>
          </div>

          <label className="checkbox-label">
            <input
              type="checkbox"
              checked={showInactive}
              onChange={(e) => setShowInactive(e.target.checked)}
            />
            Show Inactive
          </label>
        </div>

        <div className="toolbar-right">
          <button className="toolbar-btn" onClick={expandAll} title="Expand All">
            <i className="fas fa-expand-alt"></i>
          </button>
          <button className="toolbar-btn" onClick={collapseAll} title="Collapse All">
            <i className="fas fa-compress-alt"></i>
          </button>
        </div>
      </div>

      {/* Account Type Summary */}
      <div className="type-summary">
        {accountTypes.map(type => {
          const typeAccounts = accounts.filter(a => a.account_type === type.value);
          const total = typeAccounts.reduce((sum, a) => sum + (a.balance || 0), 0);
          return (
            <div
              key={type.value}
              className={`type-card ${filterType === type.value ? 'active' : ''}`}
              onClick={() => setFilterType(filterType === type.value ? 'all' : type.value)}
            >
              <div className="type-icon" style={{ backgroundColor: `${type.color}15`, color: type.color }}>
                <i className={`fas ${type.icon}`}></i>
              </div>
              <div className="type-info">
                <span className="type-label">{type.label}</span>
                <span className="type-count">{typeAccounts.length} accounts</span>
              </div>
              <div className="type-total">{formatCurrency(total)}</div>
            </div>
          );
        })}
      </div>

      {/* Accounts Table */}
      <div className="accounts-table">
        <div className="table-header">
          <div className="header-cell expand"></div>
          <div className="header-cell number">Account #</div>
          <div className="header-cell name">Account Name</div>
          <div className="header-cell type">Type</div>
          <div className="header-cell balance">Balance</div>
          <div className="header-cell actions">Actions</div>
        </div>

        <div className="table-body">
          {filteredTree.length > 0 ? (
            filteredTree.map(account => renderAccountRow(account))
          ) : (
            <div className="empty-state">
              <i className="fas fa-folder-open"></i>
              <h3>No Accounts Found</h3>
              <p>
                {searchTerm || filterType !== 'all'
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Get started by creating your first account.'}
              </p>
              {!searchTerm && filterType === 'all' && (
                <button className="btn-primary" onClick={() => openCreateModal()}>
                  <i className="fas fa-plus"></i> Create Account
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Account Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                <i className={`fas fa-${modalMode === 'create' ? 'plus' : 'edit'}`}></i>
                {modalMode === 'create' ? 'New Account' : 'Edit Account'}
              </h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              <div className="form-row">
                <div className="form-group">
                  <label>Account Number <span className="required">*</span></label>
                  <input
                    type="text"
                    value={formData.account_number}
                    onChange={(e) => handleFormChange('account_number', e.target.value)}
                    placeholder="e.g., 1100"
                  />
                </div>
                <div className="form-group">
                  <label>Account Name <span className="required">*</span></label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => handleFormChange('name', e.target.value)}
                    placeholder="e.g., Cash"
                  />
                </div>
              </div>

              <div className="form-group">
                <label>Description</label>
                <textarea
                  value={formData.description}
                  onChange={(e) => handleFormChange('description', e.target.value)}
                  placeholder="Optional description..."
                  rows={2}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Account Type <span className="required">*</span></label>
                  <select
                    value={formData.account_type}
                    onChange={(e) => handleFormChange('account_type', e.target.value)}
                  >
                    {accountTypes.map(type => (
                      <option key={type.value} value={type.value}>{type.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Subtype</label>
                  <select
                    value={formData.account_subtype}
                    onChange={(e) => handleFormChange('account_subtype', e.target.value)}
                  >
                    <option value="">Select Subtype</option>
                    {(accountSubtypes[formData.account_type] || []).map(sub => (
                      <option key={sub.value} value={sub.value}>{sub.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Parent Account</label>
                  <select
                    value={formData.parent_account_id}
                    onChange={(e) => handleFormChange('parent_account_id', e.target.value)}
                  >
                    <option value="">No Parent (Top Level)</option>
                    {accounts
                      .filter(a => a.account_type === formData.account_type && a.id !== selectedAccount?.id)
                      .map(a => (
                        <option key={a.id} value={a.id}>
                          {a.account_number} - {a.name}
                        </option>
                      ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Normal Balance</label>
                  <select
                    value={formData.normal_balance}
                    onChange={(e) => handleFormChange('normal_balance', e.target.value)}
                  >
                    <option value="debit">Debit</option>
                    <option value="credit">Credit</option>
                  </select>
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label>Currency</label>
                  <select
                    value={formData.currency}
                    onChange={(e) => handleFormChange('currency', e.target.value)}
                  >
                    <option value="USD">USD - US Dollar</option>
                    <option value="EUR">EUR - Euro</option>
                    <option value="GBP">GBP - British Pound</option>
                    <option value="CAD">CAD - Canadian Dollar</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Tax Code</label>
                  <input
                    type="text"
                    value={formData.tax_code}
                    onChange={(e) => handleFormChange('tax_code', e.target.value)}
                    placeholder="Optional"
                  />
                </div>
              </div>

              <div className="form-row checkboxes">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={formData.is_bank_account}
                    onChange={(e) => handleFormChange('is_bank_account', e.target.checked)}
                  />
                  This is a bank account
                </label>
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => handleFormChange('is_active', e.target.checked)}
                  />
                  Active
                </label>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary"
                onClick={handleSave}
                disabled={saving || !formData.account_number || !formData.name}
              >
                {saving ? (
                  <>
                    <i className="fas fa-spinner fa-spin"></i> Saving...
                  </>
                ) : (
                  <>
                    <i className="fas fa-check"></i> {modalMode === 'create' ? 'Create Account' : 'Save Changes'}
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default ChartOfAccounts;

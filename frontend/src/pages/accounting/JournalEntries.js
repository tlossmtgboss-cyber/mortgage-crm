import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { accountingAPI } from '../../services/accountingApi';
import { usePermissions } from '../../contexts/PermissionContext';
import './JournalEntries.css';
import { toast } from '../../utils/toast';

function JournalEntries() {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin } = usePermissions();
  const canAccessAccounting = isAdmin || hasAnyPermission(['accounting.view', 'accounting.manage', 'finance.view', 'admin.manage']) || userRole === 'admin' || userRole === 'management';
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [entries, setEntries] = useState([]);
  const [accounts, setAccounts] = useState([]);
  const [pagination, setPagination] = useState({ page: 1, limit: 25, total: 0 });

  // Filters
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateRange, setDateRange] = useState({
    start: new Date(new Date().getFullYear(), new Date().getMonth(), 1).toISOString().split('T')[0],
    end: new Date().toISOString().split('T')[0],
  });

  // Modal state
  const [showModal, setShowModal] = useState(false);
  const [modalMode, setModalMode] = useState('create'); // 'create', 'edit', 'view'
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [saving, setSaving] = useState(false);

  // Form state
  const [formData, setFormData] = useState({
    entry_date: new Date().toISOString().split('T')[0],
    reference_number: '',
    description: '',
    memo: '',
    lines: [
      { account_id: '', description: '', debit: '', credit: '' },
      { account_id: '', description: '', debit: '', credit: '' },
    ],
  });

  const statusOptions = [
    { value: 'all', label: 'All Status' },
    { value: 'draft', label: 'Draft', color: '#6b7280' },
    { value: 'posted', label: 'Posted', color: '#22c55e' },
    { value: 'voided', label: 'Voided', color: '#ef4444' },
    { value: 'reversed', label: 'Reversed', color: '#f97316' },
  ];

  // Fetch journal entries
  const fetchEntries = useCallback(async () => {
    try {
      setError(null);
      const params = {
        page: pagination.page,
        limit: pagination.limit,
        start_date: dateRange.start,
        end_date: dateRange.end,
      };
      if (statusFilter !== 'all') {
        params.status = statusFilter;
      }
      if (searchTerm) {
        params.search = searchTerm;
      }

      const data = await accountingAPI.getJournalEntries(params);
      setEntries(data?.entries || []);
      setPagination(prev => ({
        ...prev,
        total: data?.total || 0,
      }));
      setLoading(false);
    } catch (err) {
      console.error('Error fetching journal entries:', err);
      setError('Failed to load journal entries. Please try again.');
      setLoading(false);
    }
  }, [pagination.page, pagination.limit, statusFilter, dateRange, searchTerm]);

  // Fetch accounts for dropdown
  const fetchAccounts = useCallback(async () => {
    try {
      const data = await accountingAPI.getAccounts({ is_active: true });
      setAccounts(data?.accounts || []);
    } catch (err) {
      console.error('Error fetching accounts:', err);
    }
  }, []);

  useEffect(() => {
    fetchEntries();
  }, [fetchEntries]);

  useEffect(() => {
    fetchAccounts();
  }, [fetchAccounts]);

  // Format currency
  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 2,
    }).format(amount || 0);
  };

  // Format date
  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  // Calculate totals
  const calculateTotals = (lines) => {
    let totalDebit = 0;
    let totalCredit = 0;
    lines.forEach(line => {
      totalDebit += parseFloat(line.debit) || 0;
      totalCredit += parseFloat(line.credit) || 0;
    });
    return { totalDebit, totalCredit, isBalanced: Math.abs(totalDebit - totalCredit) < 0.01 };
  };

  // Open create modal
  const openCreateModal = () => {
    setModalMode('create');
    setSelectedEntry(null);
    setFormData({
      entry_date: new Date().toISOString().split('T')[0],
      reference_number: '',
      description: '',
      memo: '',
      lines: [
        { account_id: '', description: '', debit: '', credit: '' },
        { account_id: '', description: '', debit: '', credit: '' },
      ],
    });
    setShowModal(true);
  };

  // Open view modal
  const openViewModal = async (entry) => {
    setModalMode('view');
    setSelectedEntry(entry);

    // Fetch full entry details with lines
    try {
      const fullEntry = await accountingAPI.getJournalEntry(entry.id);
      setFormData({
        entry_date: fullEntry.entry_date?.split('T')[0] || '',
        reference_number: fullEntry.reference_number || '',
        description: fullEntry.description || '',
        memo: fullEntry.memo || '',
        lines: fullEntry.lines?.map(line => ({
          account_id: line.account_id,
          account_name: line.account_name,
          account_number: line.account_number,
          description: line.description || '',
          debit: line.debit_amount || '',
          credit: line.credit_amount || '',
        })) || [],
      });
      setShowModal(true);
    } catch (err) {
      console.error('Error fetching entry details:', err);
      toast.error('Failed to load entry details');
    }
  };

  // Open edit modal
  const openEditModal = async (entry) => {
    if (entry.status !== 'draft') {
      toast.error('Only draft entries can be edited.');
      return;
    }
    setModalMode('edit');
    setSelectedEntry(entry);

    try {
      const fullEntry = await accountingAPI.getJournalEntry(entry.id);
      setFormData({
        entry_date: fullEntry.entry_date?.split('T')[0] || '',
        reference_number: fullEntry.reference_number || '',
        description: fullEntry.description || '',
        memo: fullEntry.memo || '',
        lines: fullEntry.lines?.map(line => ({
          id: line.id,
          account_id: line.account_id,
          description: line.description || '',
          debit: line.debit_amount || '',
          credit: line.credit_amount || '',
        })) || [],
      });
      setShowModal(true);
    } catch (err) {
      console.error('Error fetching entry details:', err);
      toast.error('Failed to load entry details');
    }
  };

  // Handle form change
  const handleFormChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Handle line change
  const handleLineChange = (index, field, value) => {
    setFormData(prev => {
      const newLines = [...prev.lines];
      newLines[index] = { ...newLines[index], [field]: value };

      // Auto-clear the opposite field if entering debit/credit
      if (field === 'debit' && value) {
        newLines[index].credit = '';
      } else if (field === 'credit' && value) {
        newLines[index].debit = '';
      }

      return { ...prev, lines: newLines };
    });
  };

  // Add line
  const addLine = () => {
    setFormData(prev => ({
      ...prev,
      lines: [...prev.lines, { account_id: '', description: '', debit: '', credit: '' }],
    }));
  };

  // Remove line
  const removeLine = (index) => {
    if (formData.lines.length <= 2) {
      toast.error('Journal entry must have at least 2 lines.');
      return;
    }
    setFormData(prev => ({
      ...prev,
      lines: prev.lines.filter((_, i) => i !== index),
    }));
  };

  // Save entry
  const handleSave = async (asDraft = true) => {
    const { totalDebit, totalCredit, isBalanced } = calculateTotals(formData.lines);

    if (!isBalanced) {
      toast.error(`Entry is not balanced. Debits: ${formatCurrency(totalDebit)}, Credits: ${formatCurrency(totalCredit)}`);
      return;
    }

    if (!formData.description) {
      toast.error('Please enter a description for the journal entry.');
      return;
    }

    const validLines = formData.lines.filter(line =>
      line.account_id && (parseFloat(line.debit) > 0 || parseFloat(line.credit) > 0)
    );

    if (validLines.length < 2) {
      toast.error('Journal entry must have at least 2 valid lines.');
      return;
    }

    try {
      setSaving(true);

      const data = {
        entry_date: formData.entry_date,
        reference_number: formData.reference_number || null,
        description: formData.description,
        memo: formData.memo || null,
        status: asDraft ? 'draft' : 'posted',
        lines: validLines.map(line => ({
          account_id: line.account_id,
          description: line.description || null,
          debit_amount: parseFloat(line.debit) || 0,
          credit_amount: parseFloat(line.credit) || 0,
        })),
      };

      if (modalMode === 'create') {
        await accountingAPI.createJournalEntry(data);
      } else {
        await accountingAPI.updateJournalEntry(selectedEntry.id, data);
      }

      setShowModal(false);
      fetchEntries();
    } catch (err) {
      console.error('Error saving entry:', err);
      toast.error(err.response?.data?.detail || 'Failed to save journal entry. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  // Post entry
  const handlePost = async (entry) => {
    if (entry.status !== 'draft') {
      toast.error('Only draft entries can be posted.');
      return;
    }

    if (!window.confirm('Are you sure you want to post this entry? Posted entries cannot be edited.')) {
      return;
    }

    try {
      await accountingAPI.postJournalEntry(entry.id);
      fetchEntries();
    } catch (err) {
      console.error('Error posting entry:', err);
      toast.error(err.response?.data?.detail || 'Failed to post entry.');
    }
  };

  // Void entry
  const handleVoid = async (entry) => {
    if (entry.status !== 'posted') {
      toast.error('Only posted entries can be voided.');
      return;
    }

    const reason = window.prompt('Please enter a reason for voiding this entry:');
    if (!reason) return;

    try {
      await accountingAPI.voidJournalEntry(entry.id, { reason });
      fetchEntries();
    } catch (err) {
      console.error('Error voiding entry:', err);
      toast.error(err.response?.data?.detail || 'Failed to void entry.');
    }
  };

  // Reverse entry
  const handleReverse = async (entry) => {
    if (entry.status !== 'posted') {
      toast.error('Only posted entries can be reversed.');
      return;
    }

    if (!window.confirm('Are you sure you want to create a reversing entry? This will create a new entry with opposite debits/credits.')) {
      return;
    }

    try {
      await accountingAPI.reverseJournalEntry(entry.id);
      fetchEntries();
    } catch (err) {
      console.error('Error reversing entry:', err);
      toast.error(err.response?.data?.detail || 'Failed to reverse entry.');
    }
  };

  // Delete draft entry
  const handleDelete = async (entry) => {
    if (entry.status !== 'draft') {
      toast.success('Only draft entries can be deleted.');
      return;
    }

    if (!window.confirm('Are you sure you want to delete this draft entry?')) {
      return;
    }

    try {
      await accountingAPI.deleteJournalEntry(entry.id);
      fetchEntries();
    } catch (err) {
      console.error('Error deleting entry:', err);
      toast.error(err.response?.data?.detail || 'Failed to delete entry.');
    }
  };

  // Get status badge
  const getStatusBadge = (status) => {
    const statusInfo = statusOptions.find(s => s.value === status) || statusOptions[1];
    return (
      <span
        className="status-badge"
        style={{ backgroundColor: `${statusInfo.color}15`, color: statusInfo.color }}
      >
        {statusInfo.label}
      </span>
    );
  };

  // Pagination
  const totalPages = Math.ceil(pagination.total / pagination.limit);

  const handlePageChange = (newPage) => {
    setPagination(prev => ({ ...prev, page: newPage }));
  };

  if (loading) {
    return (
      <div className="journal-entries loading">
        <div className="loading-spinner">
          <i className="fas fa-spinner fa-spin"></i>
          <p>Loading Journal Entries...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="journal-entries">
        <div className="page-header">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i> Back
          </button>
          <h1><i className="fas fa-book"></i> Journal Entries</h1>
        </div>
        <div className="error-state">
          <i className="fas fa-exclamation-triangle"></i>
          <h3>Unable to Load Data</h3>
          <p>{error}</p>
          <button className="retry-btn" onClick={fetchEntries}>
            <i className="fas fa-redo"></i> Retry
          </button>
        </div>
      </div>
    );
  }

  const { totalDebit, totalCredit, isBalanced } = calculateTotals(formData.lines);

  if (!canAccessAccounting) {
    return (
      <div className="journal-entries">
        <div className="access-denied" style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to access Journal Entries.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="journal-entries">
      {/* Header */}
      <div className="page-header">
        <div className="header-left">
          <button className="back-btn" onClick={() => navigate('/accounting')}>
            <i className="fas fa-arrow-left"></i>
          </button>
          <div className="header-title">
            <h1><i className="fas fa-book"></i> Journal Entries</h1>
            <p className="subtitle">{pagination.total} entries</p>
          </div>
        </div>
        <div className="header-right">
          <button className="btn-primary" onClick={openCreateModal}>
            <i className="fas fa-plus"></i> New Entry
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
              placeholder="Search entries..."
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
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="filter-select"
            >
              {statusOptions.map(status => (
                <option key={status.value} value={status.value}>{status.label}</option>
              ))}
            </select>
          </div>

          <div className="date-range">
            <input
              type="date"
              value={dateRange.start}
              onChange={(e) => setDateRange(prev => ({ ...prev, start: e.target.value }))}
              className="date-input"
            />
            <span className="date-separator">to</span>
            <input
              type="date"
              value={dateRange.end}
              onChange={(e) => setDateRange(prev => ({ ...prev, end: e.target.value }))}
              className="date-input"
            />
          </div>
        </div>

        <div className="toolbar-right">
          <button
            className="toolbar-btn"
            onClick={fetchEntries}
            title="Refresh"
          >
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      </div>

      {/* Summary Cards */}
      <div className="summary-cards">
        <div className="summary-card">
          <div className="summary-icon draft">
            <i className="fas fa-edit"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {entries.filter(e => e.status === 'draft').length}
            </span>
            <span className="summary-label">Draft</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon posted">
            <i className="fas fa-check-circle"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {entries.filter(e => e.status === 'posted').length}
            </span>
            <span className="summary-label">Posted</span>
          </div>
        </div>
        <div className="summary-card">
          <div className="summary-icon total">
            <i className="fas fa-calculator"></i>
          </div>
          <div className="summary-info">
            <span className="summary-value">
              {formatCurrency(entries.reduce((sum, e) => sum + (e.total_amount || 0), 0))}
            </span>
            <span className="summary-label">Total Amount</span>
          </div>
        </div>
      </div>

      {/* Entries Table */}
      <div className="entries-table">
        <div className="table-header">
          <div className="header-cell date">Date</div>
          <div className="header-cell reference">Reference</div>
          <div className="header-cell description">Description</div>
          <div className="header-cell amount">Debit</div>
          <div className="header-cell amount">Credit</div>
          <div className="header-cell status">Status</div>
          <div className="header-cell actions">Actions</div>
        </div>

        <div className="table-body">
          {entries.length > 0 ? (
            entries.map(entry => (
              <div key={entry.id} className={`entry-row ${entry.status}`}>
                <div className="cell date">{formatDate(entry.entry_date)}</div>
                <div className="cell reference">
                  <span className="entry-number">{entry.entry_number || '-'}</span>
                  {entry.reference_number && (
                    <span className="ref-number">{entry.reference_number}</span>
                  )}
                </div>
                <div className="cell description">
                  <span className="desc-text">{entry.description}</span>
                  {entry.memo && (
                    <span className="memo-text">{entry.memo}</span>
                  )}
                </div>
                <div className="cell amount">{formatCurrency(entry.total_debit)}</div>
                <div className="cell amount">{formatCurrency(entry.total_credit)}</div>
                <div className="cell status">{getStatusBadge(entry.status)}</div>
                <div className="cell actions">
                  <button
                    className="action-btn"
                    onClick={() => openViewModal(entry)}
                    title="View Details"
                  >
                    <i className="fas fa-eye"></i>
                  </button>
                  {entry.status === 'draft' && (
                    <>
                      <button
                        className="action-btn"
                        onClick={() => openEditModal(entry)}
                        title="Edit"
                      >
                        <i className="fas fa-edit"></i>
                      </button>
                      <button
                        className="action-btn post"
                        onClick={() => handlePost(entry)}
                        title="Post Entry"
                      >
                        <i className="fas fa-check"></i>
                      </button>
                      <button
                        className="action-btn delete"
                        onClick={() => handleDelete(entry)}
                        title="Delete"
                      >
                        <i className="fas fa-trash"></i>
                      </button>
                    </>
                  )}
                  {entry.status === 'posted' && (
                    <>
                      <button
                        className="action-btn void"
                        onClick={() => handleVoid(entry)}
                        title="Void Entry"
                      >
                        <i className="fas fa-ban"></i>
                      </button>
                      <button
                        className="action-btn reverse"
                        onClick={() => handleReverse(entry)}
                        title="Reverse Entry"
                      >
                        <i className="fas fa-undo"></i>
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="empty-state">
              <i className="fas fa-book-open"></i>
              <h3>No Journal Entries Found</h3>
              <p>
                {searchTerm || statusFilter !== 'all'
                  ? 'Try adjusting your search or filter criteria.'
                  : 'Get started by creating your first journal entry.'}
              </p>
              {!searchTerm && statusFilter === 'all' && (
                <button className="btn-primary" onClick={openCreateModal}>
                  <i className="fas fa-plus"></i> Create Entry
                </button>
              )}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="pagination">
            <button
              className="page-btn"
              onClick={() => handlePageChange(pagination.page - 1)}
              disabled={pagination.page === 1}
            >
              <i className="fas fa-chevron-left"></i>
            </button>
            <span className="page-info">
              Page {pagination.page} of {totalPages}
            </span>
            <button
              className="page-btn"
              onClick={() => handlePageChange(pagination.page + 1)}
              disabled={pagination.page >= totalPages}
            >
              <i className="fas fa-chevron-right"></i>
            </button>
          </div>
        )}
      </div>

      {/* Entry Modal */}
      {showModal && (
        <div className="modal-overlay" onClick={() => setShowModal(false)}>
          <div className="modal-content large" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>
                <i className={`fas fa-${modalMode === 'create' ? 'plus' : modalMode === 'edit' ? 'edit' : 'eye'}`}></i>
                {modalMode === 'create' ? 'New Journal Entry' :
                 modalMode === 'edit' ? 'Edit Journal Entry' : 'Journal Entry Details'}
              </h2>
              <button className="close-btn" onClick={() => setShowModal(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>

            <div className="modal-body">
              {/* Entry Header */}
              <div className="entry-header-form">
                <div className="form-row">
                  <div className="form-group">
                    <label>Entry Date <span className="required">*</span></label>
                    <input
                      type="date"
                      value={formData.entry_date}
                      onChange={(e) => handleFormChange('entry_date', e.target.value)}
                      disabled={modalMode === 'view'}
                    />
                  </div>
                  <div className="form-group">
                    <label>Reference Number</label>
                    <input
                      type="text"
                      value={formData.reference_number}
                      onChange={(e) => handleFormChange('reference_number', e.target.value)}
                      placeholder="Optional"
                      disabled={modalMode === 'view'}
                    />
                  </div>
                </div>

                <div className="form-group">
                  <label>Description <span className="required">*</span></label>
                  <input
                    type="text"
                    value={formData.description}
                    onChange={(e) => handleFormChange('description', e.target.value)}
                    placeholder="Enter description..."
                    disabled={modalMode === 'view'}
                  />
                </div>

                <div className="form-group">
                  <label>Memo</label>
                  <textarea
                    value={formData.memo}
                    onChange={(e) => handleFormChange('memo', e.target.value)}
                    placeholder="Additional notes..."
                    rows={2}
                    disabled={modalMode === 'view'}
                  />
                </div>
              </div>

              {/* Entry Lines */}
              <div className="entry-lines">
                <div className="lines-header">
                  <h3>Entry Lines</h3>
                  {modalMode !== 'view' && (
                    <button className="add-line-btn" onClick={addLine}>
                      <i className="fas fa-plus"></i> Add Line
                    </button>
                  )}
                </div>

                <div className="lines-table">
                  <div className="lines-header-row">
                    <div className="line-cell account">Account</div>
                    <div className="line-cell desc">Description</div>
                    <div className="line-cell amount">Debit</div>
                    <div className="line-cell amount">Credit</div>
                    {modalMode !== 'view' && <div className="line-cell action"></div>}
                  </div>

                  {formData.lines.map((line, index) => (
                    <div key={index} className="line-row">
                      <div className="line-cell account">
                        {modalMode === 'view' ? (
                          <span className="account-display">
                            {line.account_number} - {line.account_name}
                          </span>
                        ) : (
                          <select
                            value={line.account_id}
                            onChange={(e) => handleLineChange(index, 'account_id', e.target.value)}
                          >
                            <option value="">Select Account</option>
                            {accounts.map(account => (
                              <option key={account.id} value={account.id}>
                                {account.account_number} - {account.name}
                              </option>
                            ))}
                          </select>
                        )}
                      </div>
                      <div className="line-cell desc">
                        {modalMode === 'view' ? (
                          <span>{line.description || '-'}</span>
                        ) : (
                          <input
                            type="text"
                            value={line.description}
                            onChange={(e) => handleLineChange(index, 'description', e.target.value)}
                            placeholder="Line description"
                          />
                        )}
                      </div>
                      <div className="line-cell amount">
                        {modalMode === 'view' ? (
                          <span className="amount-value">
                            {line.debit ? formatCurrency(line.debit) : '-'}
                          </span>
                        ) : (
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={line.debit}
                            onChange={(e) => handleLineChange(index, 'debit', e.target.value)}
                            placeholder="0.00"
                            className={line.debit ? 'has-value' : ''}
                          />
                        )}
                      </div>
                      <div className="line-cell amount">
                        {modalMode === 'view' ? (
                          <span className="amount-value">
                            {line.credit ? formatCurrency(line.credit) : '-'}
                          </span>
                        ) : (
                          <input
                            type="number"
                            step="0.01"
                            min="0"
                            value={line.credit}
                            onChange={(e) => handleLineChange(index, 'credit', e.target.value)}
                            placeholder="0.00"
                            className={line.credit ? 'has-value' : ''}
                          />
                        )}
                      </div>
                      {modalMode !== 'view' && (
                        <div className="line-cell action">
                          <button
                            className="remove-line-btn"
                            onClick={() => removeLine(index)}
                            disabled={formData.lines.length <= 2}
                            title="Remove Line"
                          >
                            <i className="fas fa-times"></i>
                          </button>
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Totals Row */}
                  <div className="totals-row">
                    <div className="line-cell account">
                      <strong>Totals</strong>
                    </div>
                    <div className="line-cell desc"></div>
                    <div className="line-cell amount">
                      <strong>{formatCurrency(totalDebit)}</strong>
                    </div>
                    <div className="line-cell amount">
                      <strong>{formatCurrency(totalCredit)}</strong>
                    </div>
                    {modalMode !== 'view' && <div className="line-cell action"></div>}
                  </div>

                  {/* Balance Status */}
                  <div className={`balance-status ${isBalanced ? 'balanced' : 'unbalanced'}`}>
                    {isBalanced ? (
                      <>
                        <i className="fas fa-check-circle"></i>
                        <span>Entry is balanced</span>
                      </>
                    ) : (
                      <>
                        <i className="fas fa-exclamation-triangle"></i>
                        <span>
                          Entry is not balanced (Difference: {formatCurrency(Math.abs(totalDebit - totalCredit))})
                        </span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>
                {modalMode === 'view' ? 'Close' : 'Cancel'}
              </button>
              {modalMode !== 'view' && (
                <>
                  <button
                    className="btn-secondary"
                    onClick={() => handleSave(true)}
                    disabled={saving || !isBalanced}
                  >
                    {saving ? (
                      <><i className="fas fa-spinner fa-spin"></i> Saving...</>
                    ) : (
                      <><i className="fas fa-save"></i> Save as Draft</>
                    )}
                  </button>
                  <button
                    className="btn-primary"
                    onClick={() => handleSave(false)}
                    disabled={saving || !isBalanced}
                  >
                    {saving ? (
                      <><i className="fas fa-spinner fa-spin"></i> Posting...</>
                    ) : (
                      <><i className="fas fa-check"></i> Save &amp; Post</>
                    )}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default JournalEntries;

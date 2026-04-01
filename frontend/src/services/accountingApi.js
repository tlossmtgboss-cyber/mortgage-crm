/**
 * Accounting System API Service
 * Handles all API calls for the full double-entry accounting system
 */

// Use shared api instance for CSRF, auth, and impersonation support
import api from './api';

/**
 * Accounting System API
 */
export const accountingAPI = {
  // ==========================================================================
  // DASHBOARD & REPORTS
  // ==========================================================================

  /**
   * Get profit & loss statement
   */
  getProfitLoss: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/reports/profit-loss', { params });
    return response.data;
  },

  /**
   * Get balance sheet
   */
  getBalanceSheet: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/reports/balance-sheet', { params });
    return response.data;
  },

  /**
   * Get cash flow statement
   */
  getCashFlow: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/reports/cash-flow', { params });
    return response.data;
  },

  /**
   * Get financial ratios
   */
  getFinancialRatios: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/reports/financial-ratios', { params });
    return response.data;
  },

  /**
   * Get budget variance
   */
  getBudgetVariance: async (budgetId, params = {}) => {
    const response = await api.get(`/api/v1/accounting/reports/budget-variance/${budgetId}`, { params });
    return response.data;
  },

  /**
   * Get general ledger
   */
  getGeneralLedger: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/reports/general-ledger', { params });
    return response.data;
  },

  // ==========================================================================
  // CHART OF ACCOUNTS
  // ==========================================================================

  /**
   * Get all accounts
   */
  getAccounts: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/accounts', { params });
    return response.data;
  },

  /**
   * Get accounts as tree
   */
  getAccountsTree: async () => {
    const response = await api.get('/api/v1/accounting/accounts/tree');
    return response.data;
  },

  /**
   * Get single account
   */
  getAccount: async (accountId) => {
    const response = await api.get(`/api/v1/accounting/accounts/${accountId}`);
    return response.data;
  },

  /**
   * Create account
   */
  createAccount: async (data) => {
    const response = await api.post('/api/v1/accounting/accounts', data);
    return response.data;
  },

  /**
   * Update account
   */
  updateAccount: async (accountId, data) => {
    const response = await api.put(`/api/v1/accounting/accounts/${accountId}`, data);
    return response.data;
  },

  /**
   * Get account balance
   */
  getAccountBalance: async (accountId, params = {}) => {
    const response = await api.get(`/api/v1/accounting/accounts/${accountId}/balance`, { params });
    return response.data;
  },

  // ==========================================================================
  // JOURNAL ENTRIES
  // ==========================================================================

  /**
   * Get journal entries
   */
  getJournalEntries: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/journal-entries', { params });
    return response.data;
  },

  /**
   * Get single journal entry
   */
  getJournalEntry: async (entryId) => {
    const response = await api.get(`/api/v1/accounting/journal-entries/${entryId}`);
    return response.data;
  },

  /**
   * Create journal entry
   */
  createJournalEntry: async (data) => {
    const response = await api.post('/api/v1/accounting/journal-entries', data);
    return response.data;
  },

  /**
   * Post journal entry
   */
  postJournalEntry: async (entryId) => {
    const response = await api.post(`/api/v1/accounting/journal-entries/${entryId}/post`);
    return response.data;
  },

  /**
   * Void journal entry
   */
  voidJournalEntry: async (entryId, reason) => {
    const response = await api.post(`/api/v1/accounting/journal-entries/${entryId}/void`, { reason });
    return response.data;
  },

  /**
   * Reverse journal entry
   */
  reverseJournalEntry: async (entryId, data = {}) => {
    const response = await api.post(`/api/v1/accounting/journal-entries/${entryId}/reverse`, data);
    return response.data;
  },

  // ==========================================================================
  // ACCOUNTS RECEIVABLE
  // ==========================================================================

  /**
   * Get AR customers
   */
  getCustomers: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ar/customers', { params });
    return response.data;
  },

  /**
   * Create customer
   */
  createCustomer: async (data) => {
    const response = await api.post('/api/v1/accounting/ar/customers', data);
    return response.data;
  },

  /**
   * Get invoices
   */
  getInvoices: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ar/invoices', { params });
    return response.data;
  },

  /**
   * Create invoice
   */
  createInvoice: async (data) => {
    const response = await api.post('/api/v1/accounting/ar/invoices', data);
    return response.data;
  },

  /**
   * Send invoice
   */
  sendInvoice: async (invoiceId) => {
    const response = await api.post(`/api/v1/accounting/ar/invoices/${invoiceId}/send`);
    return response.data;
  },

  /**
   * Get AR payments
   */
  getARPayments: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ar/payments', { params });
    return response.data;
  },

  /**
   * Create AR payment
   */
  createARPayment: async (data) => {
    const response = await api.post('/api/v1/accounting/ar/payments', data);
    return response.data;
  },

  /**
   * Get AR aging report
   */
  getARAgingReport: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ar/aging', { params });
    return response.data;
  },

  // ==========================================================================
  // ACCOUNTS PAYABLE
  // ==========================================================================

  /**
   * Get AP vendors
   */
  getVendors: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ap/vendors', { params });
    return response.data;
  },

  /**
   * Create vendor
   */
  createVendor: async (data) => {
    const response = await api.post('/api/v1/accounting/ap/vendors', data);
    return response.data;
  },

  /**
   * Get bills
   */
  getBills: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ap/bills', { params });
    return response.data;
  },

  /**
   * Create bill
   */
  createBill: async (data) => {
    const response = await api.post('/api/v1/accounting/ap/bills', data);
    return response.data;
  },

  /**
   * Approve bill
   */
  approveBill: async (billId) => {
    const response = await api.post(`/api/v1/accounting/ap/bills/${billId}/approve`);
    return response.data;
  },

  /**
   * Get AP payments
   */
  getAPPayments: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ap/payments', { params });
    return response.data;
  },

  /**
   * Create AP payment
   */
  createAPPayment: async (data) => {
    const response = await api.post('/api/v1/accounting/ap/payments', data);
    return response.data;
  },

  /**
   * Get AP aging report
   */
  getAPAgingReport: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ap/aging', { params });
    return response.data;
  },

  /**
   * Get 1099 report
   */
  get1099Report: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/ap/1099-report', { params });
    return response.data;
  },

  // ==========================================================================
  // BANKING
  // ==========================================================================

  /**
   * Get bank accounts
   */
  getBankAccounts: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/banking/accounts', { params });
    return response.data;
  },

  /**
   * Create bank account
   */
  createBankAccount: async (data) => {
    const response = await api.post('/api/v1/accounting/banking/accounts', data);
    return response.data;
  },

  /**
   * Get bank transactions
   */
  getBankTransactions: async (accountId, params = {}) => {
    const response = await api.get(`/api/v1/accounting/banking/accounts/${accountId}/transactions`, { params });
    return response.data;
  },

  /**
   * Match bank transaction
   */
  matchBankTransaction: async (transactionId, data) => {
    const response = await api.post(`/api/v1/accounting/banking/transactions/${transactionId}/match`, data);
    return response.data;
  },

  /**
   * Get Plaid link token
   */
  getPlaidLinkToken: async () => {
    const response = await api.post('/api/v1/accounting/banking/plaid/link-token');
    return response.data;
  },

  /**
   * Exchange Plaid public token
   */
  exchangePlaidToken: async (publicToken, institutionId) => {
    const response = await api.post('/api/v1/accounting/banking/plaid/exchange-token', {
      public_token: publicToken,
      institution_id: institutionId,
    });
    return response.data;
  },

  /**
   * Sync Plaid transactions
   */
  syncPlaidTransactions: async (accountId) => {
    const response = await api.post(`/api/v1/accounting/banking/accounts/${accountId}/sync`);
    return response.data;
  },

  /**
   * Get categorization rules
   */
  getCategorizationRules: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/banking/rules', { params });
    return response.data;
  },

  /**
   * Create categorization rule
   */
  createCategorizationRule: async (data) => {
    const response = await api.post('/api/v1/accounting/banking/rules', data);
    return response.data;
  },

  // ==========================================================================
  // BUDGETS
  // ==========================================================================

  /**
   * Get budgets
   */
  getBudgets: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/budgets', { params });
    return response.data;
  },

  /**
   * Get single budget
   */
  getBudget: async (budgetId) => {
    const response = await api.get(`/api/v1/accounting/budgets/${budgetId}`);
    return response.data;
  },

  /**
   * Create budget
   */
  createBudget: async (data) => {
    const response = await api.post('/api/v1/accounting/budgets', data);
    return response.data;
  },

  /**
   * Update budget
   */
  updateBudget: async (budgetId, data) => {
    const response = await api.put(`/api/v1/accounting/budgets/${budgetId}`, data);
    return response.data;
  },

  /**
   * Activate budget
   */
  activateBudget: async (budgetId) => {
    const response = await api.post(`/api/v1/accounting/budgets/${budgetId}/activate`);
    return response.data;
  },

  // ==========================================================================
  // ACCOUNTING PERIODS
  // ==========================================================================

  /**
   * Get accounting periods
   */
  getPeriods: async (params = {}) => {
    const response = await api.get('/api/v1/accounting/periods', { params });
    return response.data;
  },

  /**
   * Get current period
   */
  getCurrentPeriod: async () => {
    const response = await api.get('/api/v1/accounting/periods/current');
    return response.data;
  },

  /**
   * Close period
   */
  closePeriod: async (periodId) => {
    const response = await api.post(`/api/v1/accounting/periods/${periodId}/close`);
    return response.data;
  },
};

export default accountingAPI;

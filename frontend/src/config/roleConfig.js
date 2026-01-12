/**
 * Role Configuration - Central source of truth for role-based navigation and dashboards
 *
 * This file defines:
 * 1. Navigation items available in the system
 * 2. Which navigation items each role can see
 * 3. Which dashboard containers each role can see
 * 4. Role detection logic
 */

// =============================================================================
// NAVIGATION ITEMS - Master list of all navigation items
// =============================================================================

export const NAVIGATION_ITEMS = {
  dashboard: {
    path: '/dashboard',
    label: 'Dashboard',
    icon: null,
    module: 'base'  // Base package - always available
  },
  leads: {
    path: '/leads',
    label: 'Leads',
    badgeKey: 'leads',
    module: 'base'
  },
  activeLoans: {
    path: '/loans',
    label: 'Active Loans',
    badgeKey: 'loans',
    module: 'base'
  },
  portfolio: {
    path: '/portfolio',
    label: 'MUM Clients',  // Mortgages Under Management - for Loan Officers only
    module: 'base'
  },
  closedClients: {
    path: '/closed-loans',
    label: 'Closed Loans',  // Simple closed loans list for Production Assistants
    module: 'base'
  },
  closedLoans: {
    path: '/closed-loans',
    label: 'Closed Loans',  // Simple closed loans list for ops roles
    module: 'base'
  },
  tasks: {
    path: '/tasks',
    label: 'Tasks',
    badgeKey: 'urgentTasks',
    badgeClass: 'urgent',
    module: 'base'
  },
  reconciliation: {
    path: '/reconciliation',
    label: 'Reconciliation',
    badgeKey: 'reconciliation',
    module: 'base'
  },
  smartDocs: {
    path: '/smart-docs',
    label: 'Smart Docs',
    matchPaths: ['/smart-docs/', '/smart-docs'],
    module: 'base'
  },
  marketing: {
    path: '/marketing',
    label: 'Marketing',
    matchPaths: ['/marketing'],
    module: 'base'
  },
  calendar: {
    path: '/calendar',
    label: 'Calendar',
    module: 'base'
  },
  scorecard: {
    path: '/scorecard',
    label: 'Scorecard',
    module: 'base'
  },
  partners: {
    path: '/referral-partners',
    label: 'Partners',
    badgeKey: 'partners',
    module: 'partner_portals'  // Premium: Partner Portals module
  },
  aiUnderwriter: {
    path: '/ai-underwriter',
    label: 'AI Underwriter',
    module: 'ai_assistant'  // Premium: AI Assistant module
  },
  market: {
    path: '/market',
    label: 'Market',
    module: 'advanced_analytics'  // Premium: Advanced Analytics module
  },
  profitability: {
    path: '/profitability',
    label: 'Profitability',
    module: 'advanced_analytics'  // Premium: Advanced Analytics module
  },
  usageIntelligence: {
    path: '/usage-intelligence',
    label: 'Usage Intelligence',
    module: 'base',
    adminOnly: true  // Owner-only: Cost tracking and pricing recommendations
  },
  capacity: {
    path: '/master-manager',
    label: 'Capacity',
    module: 'recruiting_suite'  // Premium: Recruiting Suite module
  },
  recruiting: {
    path: '/master-manager/recruiting',
    label: 'Recruiting',
    matchPaths: ['/master-manager/recruiting', '/master-manager'],
    module: 'recruiting_suite'  // Premium: Recruiting Suite module
  },
  partnerRecruiting: {
    path: '/partner-recruiting',
    label: 'Partner Recruiting',
    matchPaths: ['/partner-recruiting/'],
    module: 'recruiting_suite'  // Premium: Recruiting Suite module
  },
  conversationIntelligence: {
    path: '/conversation-intelligence',
    label: 'Call Intelligence',
    matchPaths: ['/conversation-intelligence'],
    module: 'conversation_intelligence'  // Premium: Conversation Intelligence module
  },
  videoOs: {
    path: '/video-os',
    label: 'Video OS',
    matchPaths: ['/video-os'],
    module: 'video_os'  // Premium: Video OS module
  },
  integrations: {
    path: '/integrations',
    label: 'Integrations',
    matchPaths: ['/integrations'],
    module: 'integrations'  // Premium: Integrations module
  },
  liveCallWhisper: {
    path: '/live-call-whisper',
    label: 'Live Call Whisper',
    matchPaths: ['/live-call-whisper'],
    module: 'conversation_intelligence'  // Premium: Conversation Intelligence module
  },
  productionPredictor: {
    path: '/production-predictor',
    label: 'Production Predictor',
    matchPaths: ['/production-predictor'],
    module: 'advanced_analytics'  // Premium: Advanced Analytics module
  },
  dealAlerts: {
    path: '/deal-alerts',
    label: 'Deal Alerts',
    matchPaths: ['/deal-alerts'],
    module: 'advanced_analytics'  // Premium: Advanced Analytics module
  },
  voiceAgents: {
    path: '/voice/agents',
    label: 'Voice Agents',
    matchPaths: ['/voice/agents', '/voice/agents/new'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  voiceLive: {
    path: '/voice/live',
    label: 'Live Calls',
    matchPaths: ['/voice/live'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  callQueues: {
    path: '/voice/queues',
    label: 'Call Queues',
    matchPaths: ['/voice/queues'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  conferenceRooms: {
    path: '/voice/conferences',
    label: 'Conference Rooms',
    matchPaths: ['/voice/conferences'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  ivrMenus: {
    path: '/voice/ivr',
    label: 'IVR Menus',
    matchPaths: ['/voice/ivr'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  holdMusic: {
    path: '/voice/hold-music',
    label: 'Hold Music',
    matchPaths: ['/voice/hold-music'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  talkToAgent: {
    path: '/voice/talk',
    label: 'Talk to Agent',
    matchPaths: ['/voice/talk'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  powerDialer: {
    path: '/dialer',
    label: 'Power Dialer',
    matchPaths: ['/dialer'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  callAnalytics: {
    path: '/voice/analytics',
    label: 'Call Analytics',
    matchPaths: ['/voice/analytics'],
    module: 'voice_os'  // Premium: Voice OS module
  },
  // Accounting System - with submenu structure
  accounting: {
    path: '/accounting',
    label: 'Accounting',
    matchPaths: ['/accounting'],
    module: 'base',  // Base module - available to appropriate roles
    children: [
      { path: '/accounting', label: 'Dashboard', icon: 'fa-tachometer-alt' },
      { path: '/accounting/accounts', label: 'Chart of Accounts', icon: 'fa-sitemap' },
      { path: '/accounting/journal-entries', label: 'Journal Entries', icon: 'fa-book' },
      {
        label: 'Receivables',
        icon: 'fa-hand-holding-usd',
        children: [
          { path: '/accounting/ar/customers', label: 'Customers' },
          { path: '/accounting/ar/invoices', label: 'Invoices' },
          { path: '/accounting/ar/payments', label: 'Payments' },
          { path: '/accounting/ar/aging', label: 'AR Aging Report' },
        ]
      },
      {
        label: 'Payables',
        icon: 'fa-file-invoice-dollar',
        children: [
          { path: '/accounting/ap/vendors', label: 'Vendors' },
          { path: '/accounting/ap/bills', label: 'Bills' },
          { path: '/accounting/ap/payments', label: 'Pay Bills' },
          { path: '/accounting/ap/aging', label: 'AP Aging Report' },
        ]
      },
      {
        label: 'Banking',
        icon: 'fa-university',
        children: [
          { path: '/accounting/banking/accounts', label: 'Bank Accounts' },
          { path: '/accounting/banking/connect', label: 'Connect Bank' },
          { path: '/accounting/banking/transactions', label: 'Transactions' },
          { path: '/accounting/banking/reconciliation', label: 'Reconciliation' },
        ]
      },
      {
        label: 'Reports',
        icon: 'fa-chart-line',
        children: [
          { path: '/accounting/reports/profit-loss', label: 'Profit & Loss' },
          { path: '/accounting/reports/balance-sheet', label: 'Balance Sheet' },
          { path: '/accounting/reports/cash-flow', label: 'Cash Flow' },
          { path: '/accounting/reports/trial-balance', label: 'Trial Balance' },
        ]
      },
      {
        label: 'Budgets',
        icon: 'fa-calculator',
        children: [
          { path: '/accounting/budgets', label: 'Budget List' },
          { path: '/accounting/budgets/variance', label: 'Variance Report' },
        ]
      },
    ]
  },
  // Admin-only navigation items
  adminPanel: {
    path: '/admin',
    label: 'Admin Panel',
    matchPaths: ['/admin'],
    module: 'base',
    adminOnly: true  // Flag for admin-only items
  }
};

// =============================================================================
// ROLE NAVIGATION - Which nav items each role sees (in display order)
// =============================================================================

export const ROLE_NAVIGATION = {
  // Admin - Full access to everything, Admin Panel first
  admin: [
    'adminPanel',           // Admin Panel link - admin only
    'dashboard',
    'leads',
    'activeLoans',
    'portfolio',
    'tasks',
    'reconciliation',
    'smartDocs',
    'marketing',
    'calendar',
    'partners',
    'aiUnderwriter',
    'market',
    'profitability',
    'usageIntelligence',    // Owner-only: Usage costs & pricing
    'accounting',           // Accounting System
    'capacity',
    'recruiting',
    'partnerRecruiting',
    'conversationIntelligence',
    'liveCallWhisper',
    'voiceAgents',
    'voiceLive',
    'callQueues',
    'conferenceRooms',
    'ivrMenus',
    'holdMusic',
    'talkToAgent',
    'powerDialer',
    'callAnalytics',
    'productionPredictor',
    'dealAlerts'
  ],

  // Loan Officer - Full sales navigation
  // Note: Production Predictor, Deal Alerts are on dashboard instead of nav
  // Note: Live Call Whisper, Call Intelligence are accessed via Marketing
  loan_officer: [
    'dashboard',
    'leads',
    'activeLoans',
    'portfolio',
    'tasks',
    'reconciliation',
    'smartDocs',
    'marketing',
    'calendar',
    'partners',
    'aiUnderwriter',
    'market',
    'profitability',
    'partnerRecruiting',
    'powerDialer',
    'callAnalytics'
  ],

  // Production Assistant - Support role navigation
  production_assistant: [
    'dashboard',
    'leads',
    'activeLoans',
    'closedClients',  // Portfolio with "Closed Clients" label
    'tasks',
    'reconciliation',
    'smartDocs',
    'calendar',
    'aiUnderwriter'
  ],

  // Concierge - Same permissions as Production Assistant
  concierge: [
    'dashboard',
    'leads',
    'activeLoans',
    'closedClients',  // Portfolio with "Closed Clients" label
    'tasks',
    'reconciliation',
    'smartDocs',
    'calendar',
    'aiUnderwriter'
  ],

  // Processor - Operations role, NO dashboard
  processor: [
    'activeLoans',
    'closedLoans',  // Portfolio with "Closed Loans" label
    'tasks',
    'reconciliation',
    'smartDocs',
    'calendar',
    'aiUnderwriter'
  ],

  // Underwriter - Operations role, NO dashboard
  underwriter: [
    'activeLoans',
    'closedLoans',
    'tasks',
    'reconciliation',
    'smartDocs',
    'calendar',
    'aiUnderwriter'
  ],

  // Closer - Operations role, NO dashboard
  closer: [
    'activeLoans',
    'closedLoans',
    'tasks',
    'reconciliation',
    'smartDocs',
    'calendar',
    'aiUnderwriter'
  ],

  // Manager - Management navigation
  manager: [
    'dashboard',
    'leads',
    'activeLoans',
    'closedLoans',
    'tasks',
    'reconciliation',
    'smartDocs',
    'marketing',
    'calendar',
    'aiUnderwriter',
    'market',
    'accounting',       // Accounting System
    'recruiting'
  ],

  // Executive - Minimal high-level navigation
  executive: [
    'dashboard',
    'tasks',
    'reconciliation',
    'calendar',
    'accounting',       // Accounting System
    'recruiting'
  ]
};

// =============================================================================
// DASHBOARD CONTAINERS - Which containers each role sees on their dashboard
// These IDs must match the container IDs in Dashboard.js renderDraggableContainer()
// =============================================================================

export const ROLE_DASHBOARD_CONTAINERS = {
  // Admin Dashboard - Full access to all containers
  admin: [
    'ai-alerts',           // AI Alerts (lead alerts, follow-ups)
    'production-tracker',  // Monthly Production Tracker
    'profitability',       // Profitability Intelligence
    'efficiency',          // Pipeline Efficiency Monitor
    'workflow-scorecards', // Workflow Scorecards
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline',           // Live Loan Pipeline
    'referrals',          // Referral Scoreboard
    'team'                // Team Performance
  ],

  // Loan Officer Dashboard - Full view with all sales-related containers
  loan_officer: [
    'ai-alerts',           // AI Alerts (lead alerts, follow-ups)
    'production-tracker',  // Monthly Production Tracker
    'production-predictor', // Production Predictor (moved from nav)
    'deal-alerts',         // Deal Alerts (moved from nav)
    'profitability',       // Profitability Intelligence (LO view)
    'efficiency',          // Pipeline Efficiency Monitor
    'workflow-scorecards', // Workflow Scorecards (acts as scorecard)
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline',           // Live Loan Pipeline
    'referrals'           // Referral Scoreboard
  ],

  // Production Assistant Dashboard - Support role view
  production_assistant: [
    'efficiency',          // Pipeline Efficiency
    'ai-alerts',           // AI Alerts (lead status alerts)
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline'            // Live Loan Pipeline (shows active loans)
  ],

  // Concierge Dashboard - Same as Production Assistant
  concierge: [
    'efficiency',          // Pipeline Efficiency
    'ai-alerts',           // AI Alerts (lead status alerts)
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline'            // Live Loan Pipeline (shows active loans)
  ],

  // Processor Dashboard - Operations view, NO dashboard access but if they land here
  processor: [
    'efficiency',          // Pipeline Efficiency
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline'            // Live Loan Pipeline (In Processing, In UW, Funded)
  ],

  // Underwriter Dashboard - Same as processor
  underwriter: [
    'efficiency',
    'ai-tasks',
    'pipeline'
  ],

  // Closer Dashboard - Same as processor
  closer: [
    'efficiency',
    'ai-tasks',
    'pipeline'
  ],

  // Manager Dashboard - Management view with team oversight
  manager: [
    'efficiency',          // Pipeline Efficiency (team view)
    'production-tracker',  // Production Tracker
    'profitability',       // Profitability (Manager/team view)
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline',           // Live Loan Pipeline
    'team'                // Team Performance
  ],

  // Executive Dashboard - High-level company view
  executive: [
    'efficiency',          // Pipeline Efficiency (company view)
    'profitability',       // Profitability (Company view)
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline',           // Live Loan Pipeline
    'team'                // Team Performance
  ]
};

// =============================================================================
// DEFAULT ROUTES - Where each role lands after login
// =============================================================================

export const ROLE_DEFAULT_ROUTES = {
  admin: '/admin',
  loan_officer: '/dashboard',
  production_assistant: '/dashboard',
  concierge: '/dashboard',  // Same as Production Assistant
  processor: '/loans',      // No dashboard, land on Active Loans
  underwriter: '/loans',
  closer: '/loans',
  manager: '/dashboard',
  executive: '/dashboard'
};

// =============================================================================
// ROLE DETECTION - Determine effective role from user data
// =============================================================================

/**
 * Determines the effective UI role based on user's permission_role and legacy role
 * @param {string} permissionRole - The user's permission_role from backend (admin, leadership, management, sales, processing, operations)
 * @param {string} legacyRole - The user's legacy role field (loan_officer, processor, underwriter, closer, manager, production_assistant)
 * @returns {string} The effective role for UI purposes
 */
export const getUserEffectiveRole = (permissionRole, legacyRole) => {
  // Check legacy role first for more specific role identification
  if (legacyRole) {
    const normalizedLegacy = legacyRole.toLowerCase().replace(/\s+/g, '_');

    // Operations roles
    if (['processor', 'loan_processor'].includes(normalizedLegacy)) {
      return 'processor';
    }
    if (normalizedLegacy === 'underwriter') {
      return 'underwriter';
    }
    if (['closer', 'funder'].includes(normalizedLegacy)) {
      return 'closer';
    }

    // Production assistant
    if (normalizedLegacy.includes('production_assistant') || normalizedLegacy === 'production_asst') {
      return 'production_assistant';
    }

    // Concierge - same permissions as production_assistant
    if (normalizedLegacy === 'concierge') {
      return 'concierge';
    }

    // Loan officer
    if (['loan_officer', 'senior_loan_officer', 'jr_lo', 'junior_loan_officer'].includes(normalizedLegacy)) {
      return 'loan_officer';
    }

    // Manager
    if (['manager', 'branch_manager', 'team_lead'].includes(normalizedLegacy)) {
      return 'manager';
    }

    // Executive
    if (['executive', 'ceo', 'cfo', 'coo', 'owner'].includes(normalizedLegacy)) {
      return 'executive';
    }
  }

  // Fall back to permission_role mapping
  if (permissionRole) {
    const normalizedPermission = permissionRole.toLowerCase();

    switch (normalizedPermission) {
      case 'admin':
        return 'admin';       // Admin gets full access
      case 'leadership':
        return 'executive';
      case 'management':
        return 'manager';
      case 'sales':
        return 'loan_officer';
      case 'processing':
        return 'processor';
      case 'operations':
        return 'production_assistant';
      default:
        break;
    }
  }

  // Default to loan officer
  return 'loan_officer';
};

/**
 * Check if a role has access to the dashboard page
 * @param {string} effectiveRole - The effective role
 * @returns {boolean} True if role has dashboard access
 */
export const roleHasDashboard = (effectiveRole) => {
  const rolesWithoutDashboard = ['processor', 'underwriter', 'closer'];
  return !rolesWithoutDashboard.includes(effectiveRole);
};

/**
 * Get navigation items for a specific role
 * @param {string} effectiveRole - The effective role
 * @returns {Array} Array of navigation item objects
 */
export const getNavigationForRole = (effectiveRole) => {
  const navKeys = ROLE_NAVIGATION[effectiveRole] || ROLE_NAVIGATION.loan_officer;
  return navKeys.map(key => ({
    ...NAVIGATION_ITEMS[key],
    key
  }));
};

/**
 * Get dashboard containers for a specific role
 * @param {string} effectiveRole - The effective role
 * @returns {Array} Array of container IDs
 */
export const getDashboardContainersForRole = (effectiveRole) => {
  return ROLE_DASHBOARD_CONTAINERS[effectiveRole] || ROLE_DASHBOARD_CONTAINERS.loan_officer;
};

/**
 * Get the default route for a role after login
 * @param {string} effectiveRole - The effective role
 * @returns {string} The default route path
 */
export const getDefaultRouteForRole = (effectiveRole) => {
  return ROLE_DEFAULT_ROUTES[effectiveRole] || '/dashboard';
};

// =============================================================================
// PROFITABILITY VIEW TYPES - Different views based on role
// =============================================================================

export const PROFITABILITY_VIEW_TYPES = {
  admin: 'company',              // Admin sees company-wide profitability
  loan_officer: 'personal',      // LO sees their own profitability
  manager: 'team',               // Manager sees team profitability
  executive: 'company'           // Executive sees company-wide profitability
};

/**
 * Get the profitability view type for a role
 * @param {string} effectiveRole - The effective role
 * @returns {string} The profitability view type
 */
export const getProfitabilityViewType = (effectiveRole) => {
  return PROFITABILITY_VIEW_TYPES[effectiveRole] || 'personal';
};

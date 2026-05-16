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
    label: 'Portfolio',  // Mortgages Under Management - for Loan Officers only
    module: 'base'
  },
  rateMonitor: {
    path: '/rate-monitor',
    label: 'Rate Monitor',
    matchPaths: ['/rate-monitor'],
    module: 'base'  // Available to roles with portfolio access
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
    badgeKey: 'totalTasks',
    badgeClass: 'urgent',
    module: 'base'
  },
  smartDocs: {
    path: '/smart-docs',
    label: 'Smart Docs',
    matchPaths: ['/smart-docs/', '/smart-docs'],
    badgeKey: 'smartDocs',
    badgeClass: 'urgent',
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
  briefing: {
    path: '/briefing',
    label: 'Morning Briefing',
    module: 'base'
  },
  scorecard: {
    path: '/scorecard',
    label: 'Scorecard',
    module: 'base'
  },
  goalTracker: {
    path: '/goal-tracker',
    label: 'Goal Tracker',
    matchPaths: ['/goal-tracker'],
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
  opsManager: {
    path: '/ops-manager',
    label: 'Ops Manager',
    module: 'base',
    adminOnly: true  // Admin/Site Admin only: Pipeline health & impediment detection
  },
  capacity: {
    path: '/master-manager',
    label: 'Capacity',
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
  // Voice & Calls - dropdown with all voice/call center items
  voiceCalls: {
    path: '/voice',
    label: 'Voice & Calls',
    matchPaths: ['/voice', '/dialer', '/conversation-intelligence', '/live-call-whisper'],
    module: 'voice_os',
    children: [
      { path: '/voice/studio', label: 'Agent Studio', icon: 'fa-robot' },
      { path: '/voice/agents', label: 'Voice Agents', icon: 'fa-user-headset' },
      { path: '/dialer', label: 'Power Dialer', icon: 'fa-phone-volume' },
      { path: '/voice/calls', label: 'Live Calls', icon: 'fa-broadcast-tower' },
      { path: '/voice/analytics', label: 'Call Analytics', icon: 'fa-chart-bar' },
      { path: '/conversation-intelligence', label: 'Call Intelligence', icon: 'fa-brain' },
      { path: '/live-call-whisper', label: 'Live Whisper', icon: 'fa-comment-dots' },
      { path: '/voice/queues', label: 'Call Queues', icon: 'fa-users' },
      { path: '/voice/conferences', label: 'Conference Rooms', icon: 'fa-users-class' },
      { path: '/voice/ivr', label: 'IVR Menus', icon: 'fa-sitemap' },
      { path: '/voice/hold-music', label: 'Hold Music', icon: 'fa-music' },
      { path: '/voice/talk', label: 'Talk to Agent', icon: 'fa-microphone' },
    ]
  },
  // Admin-only navigation items
  adminPanel: {
    path: '/admin',
    label: 'Admin Panel',
    matchPaths: ['/admin'],
    module: 'base',
    adminOnly: true  // Flag for admin-only items
  },
  enterpriseDocs: {
    path: '/enterprise-docs',
    label: 'Enterprise Docs',
    matchPaths: ['/enterprise-docs'],
    module: 'base',
    adminOnly: true  // Enterprise documentation portal for admins
  }
};

// =============================================================================
// ROLE NAVIGATION - Which nav items each role sees (in display order)
// =============================================================================

export const ROLE_NAVIGATION = {
  // Admin - Platform developer with full access to everything across all orgs
  // Includes ALL features for full visibility and testing
  admin: [
    'dashboard',
    'leads',
    'activeLoans',
    'portfolio',
    'rateMonitor',          // Rate Monitor for refinance opportunities
    'closedLoans',          // Closed loans access
    'tasks',
    'smartDocs',
    'marketing',            // Marketing page (includes Voice & Call Center, Video OS)
    'calendar',
    'briefing',             // Morning Briefing page
    'scorecard',            // Scorecard
    'goalTracker',          // Goal Tracker for production goals
    'partners',
    'aiUnderwriter',
    'market',
    'profitability',
    'usageIntelligence',    // Owner-only: Usage costs & pricing
    'opsManager',           // Ops Manager: Pipeline health & impediments
    'capacity',
    'productionPredictor',
    'dealAlerts'
  ],

  // Site Administrator - Licensee who manages their organization's users
  // Has access to admin panel (org-scoped) + LO features, but NOT platform-level features
  site_admin: [
    'dashboard',
    'leads',
    'activeLoans',
    'portfolio',
    'rateMonitor',          // Rate Monitor for refinance opportunities
    'tasks',
    'smartDocs',
    'marketing',            // Marketing page (includes Voice & Call Center, Video OS)
    'calendar',
    'briefing',             // Morning Briefing page
    'scorecard',
    'goalTracker',          // Goal Tracker for production goals
    'partners',
    'aiUnderwriter',
    'market',
    'profitability',
    'opsManager'            // Ops Manager: Pipeline health & impediments
  ],

  // Loan Officer - Full sales navigation
  // Note: Production Predictor, Deal Alerts are on dashboard instead of nav
  // Note: Voice/Call tools are accessed via Marketing page
  loan_officer: [
    'dashboard',
    'leads',
    'activeLoans',
    'portfolio',
    'rateMonitor',          // Rate Monitor for refinance opportunities
    'tasks',
    'smartDocs',
    'marketing',            // Marketing page includes Voice & Call Center tools
    'calendar',
    'briefing',             // Morning Briefing page
    'scorecard',            // Scorecard for performance tracking
    'goalTracker',          // Goal Tracker for production goals
    'partners',
    'aiUnderwriter',
    'market',
    'profitability',
  ],

  // Production Assistant - Support role navigation
  production_assistant: [
    'dashboard',
    'leads',
    'activeLoans',
    'closedClients',  // Portfolio with "Closed Clients" label
    'tasks',
    'smartDocs',
    'calendar',
    'briefing',       // Morning Briefing page
    'aiUnderwriter'
  ],

  // Concierge - Same permissions as Production Assistant
  concierge: [
    'dashboard',
    'leads',
    'activeLoans',
    'closedClients',  // Portfolio with "Closed Clients" label
    'tasks',
    'smartDocs',
    'calendar',
    'briefing',       // Morning Briefing page
    'aiUnderwriter'
  ],

  // Processor - Operations role, NO dashboard
  processor: [
    'activeLoans',
    'closedLoans',  // Portfolio with "Closed Loans" label
    'tasks',
    'smartDocs',
    'calendar',
    'briefing',     // Morning Briefing page
    'aiUnderwriter'
  ],

  // Underwriter - Operations role, NO dashboard
  underwriter: [
    'activeLoans',
    'closedLoans',
    'tasks',
    'smartDocs',
    'calendar',
    'briefing',     // Morning Briefing page
    'aiUnderwriter'
  ],

  // Closer - Operations role, NO dashboard
  closer: [
    'activeLoans',
    'closedLoans',
    'tasks',
    'smartDocs',
    'calendar',
    'briefing',     // Morning Briefing page
    'aiUnderwriter'
  ],

  // Manager - Management navigation
  manager: [
    'dashboard',
    'leads',
    'activeLoans',
    'closedLoans',
    'tasks',
    'smartDocs',
    'marketing',
    'calendar',
    'briefing',         // Morning Briefing page
    'scorecard',        // Scorecard for performance tracking
    'goalTracker',      // Goal Tracker for production goals
    'aiUnderwriter',
    'market',
  ],

  // Executive - Minimal high-level navigation
  executive: [
    'dashboard',
    'tasks',
    'calendar',
    'briefing',         // Morning Briefing page
  ]
};

// =============================================================================
// DASHBOARD CONTAINERS - Which containers each role sees on their dashboard
// These IDs must match the container IDs in Dashboard.js renderDraggableContainer()
// =============================================================================

export const ROLE_DASHBOARD_CONTAINERS = {
  // Admin Dashboard - Platform developer, full access to ALL containers
  admin: [
    'ai-alerts',           // AI Alerts (lead alerts, follow-ups)
    'production-tracker',  // Monthly Production Tracker
    'production-predictor', // Production Predictor
    'deal-alerts',         // Deal Alerts
    'profitability',       // Profitability Intelligence
    'efficiency',          // Pipeline Efficiency Monitor
    'workflow-scorecards', // Workflow Scorecards
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline',           // Live Loan Pipeline
    'referrals',          // Referral Scoreboard
    'mum',                // Mortgages Under Management
    'team',               // Team Performance
    'it-tickets'          // IT Support Tickets KPIs
  ],

  // Site Admin Dashboard - Licensee/org owner, same dashboard access as admin
  site_admin: [
    'ai-alerts',           // AI Alerts (lead alerts, follow-ups)
    'production-tracker',  // Monthly Production Tracker
    'production-predictor', // Production Predictor
    'deal-alerts',         // Deal Alerts
    'profitability',       // Profitability Intelligence (org view)
    'efficiency',          // Pipeline Efficiency Monitor
    'workflow-scorecards', // Workflow Scorecards
    'ai-tasks',           // AI Prioritized Tasks
    'pipeline',           // Live Loan Pipeline
    'referrals',          // Referral Scoreboard
    'mum',                // Mortgages Under Management
    'team',               // Team Performance
    'it-tickets'          // IT Support Tickets KPIs
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
    'referrals',          // Referral Scoreboard
    'mum'                 // Mortgages Under Management
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
  admin: '/dashboard',
  site_admin: '/dashboard',
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
        return 'admin';       // Platform Admin (developer) - full access across all orgs
      case 'site_admin':
        return 'site_admin';  // Site Administrator (licensee) - manages their org
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
 * Maps onboarding_roles table role names to effectiveRole keys used in the UI
 * This is used by the multi-role system to convert database role names to UI role keys
 * @param {string} roleName - The role name from onboarding_roles table (e.g., "Site Administrator", "Loan Officer")
 * @returns {string} The effective role key for UI purposes (e.g., "admin", "loan_officer")
 */
export const mapRoleNameToEffective = (roleName) => {
  if (!roleName) return 'loan_officer';

  const normalized = roleName.toLowerCase().replace(/\s+/g, '_');

  // Map onboarding role names to effective role keys
  const roleMapping = {
    // Platform Administrator roles (full access)
    'administrator': 'admin',
    'admin': 'admin',
    'platform_admin': 'admin',

    // Site Administrator roles (org-level access, NOT full admin)
    'site_administrator': 'site_admin',
    'site_admin': 'site_admin',

    // Management roles
    'manager': 'manager',
    'branch_manager': 'manager',
    'sales_manager': 'manager',
    'team_lead': 'manager',
    'team_manager': 'manager',

    // Executive roles
    'executive': 'executive',
    'owner': 'executive',
    'ceo': 'executive',
    'coo': 'executive',
    'cfo': 'executive',

    // Sales roles
    'loan_officer': 'loan_officer',
    'lo': 'loan_officer',
    'senior_loan_officer': 'loan_officer',
    'sr_loan_officer': 'loan_officer',
    'junior_loan_officer': 'loan_officer',
    'jr_loan_officer': 'loan_officer',
    'jr_lo': 'loan_officer',
    'mortgage_loan_originator': 'loan_officer',
    'mlo': 'loan_officer',

    // Support roles
    'production_assistant': 'production_assistant',
    'production_assistant_1': 'production_assistant',
    'production_assistant_2': 'production_assistant',
    'concierge': 'production_assistant',
    'loan_coordinator': 'production_assistant',

    // Operations roles
    'processor': 'processor',
    'loan_processor': 'processor',
    'underwriter': 'underwriter',
    'closer': 'closer',
    'funder': 'closer',
    'post_closer': 'closer',
    'post-closer': 'closer'
  };

  // Check direct mapping first
  if (roleMapping[normalized]) {
    return roleMapping[normalized];
  }

  // Check for partial matches
  if (normalized.includes('admin')) return 'admin';
  if (normalized.includes('manager')) return 'manager';
  if (normalized.includes('executive') || normalized.includes('owner')) return 'executive';
  if (normalized.includes('production_assistant') || normalized.includes('concierge')) return 'production_assistant';
  if (normalized.includes('processor')) return 'processor';
  if (normalized.includes('underwriter')) return 'underwriter';
  if (normalized.includes('closer') || normalized.includes('funder')) return 'closer';
  if (normalized.includes('loan_officer') || normalized.includes('_lo')) return 'loan_officer';

  // Default to loan_officer
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
// MASTER ADMIN NAVIGATION - Consolidated dropdown structure for admin@perenniaai.com
// =============================================================================

export const MASTER_ADMIN_EMAIL = 'admin@perenniaai.com';

/**
 * Check if user is the master admin (admin@perenniaai.com)
 * @param {string} email - The user's email
 * @returns {boolean} True if user is master admin
 */
export const isMasterAdmin = (email) => {
  return email?.toLowerCase() === MASTER_ADMIN_EMAIL;
};

/**
 * Master Admin Navigation Structure
 * Consolidated into 4 main dropdown categories + standalone items (Tasks, Reconciliation)
 * Tasks and Reconciliation remain as standalone nav items for quick access
 */
export const MASTER_ADMIN_NAVIGATION = [
  // Standalone items for quick access (with badges)
  {
    key: 'dashboard',
    label: 'Dashboard',
    path: '/admin',  // Admin Panel is the admin's dashboard
    matchPaths: ['/admin'],
    isStandalone: true
  },
  {
    key: 'tasks',
    label: 'Tasks',
    path: '/tasks',
    badgeKey: 'totalTasks',
    badgeClass: 'urgent',
    isStandalone: true
  },
  {
    key: 'itTickets',
    label: 'IT Tickets',
    path: '/support',
    isStandalone: true
  },
  {
    key: 'calendar',
    label: 'Calendar',
    path: '/calendar',
    isStandalone: true
  },
  // Dropdown categories
  {
    key: 'sales',
    label: 'Sales',
    path: '/leads',
    matchPaths: ['/leads', '/loans', '/portfolio', '/referral-partners', '/marketing', '/rate-monitor'],
    children: [
      { path: '/leads', label: 'Leads', icon: 'fa-user-plus', badgeKey: 'leads' },
      { path: '/loans', label: 'Active Loans', icon: 'fa-file-contract', badgeKey: 'loans' },
      { path: '/portfolio', label: 'Portfolio', icon: 'fa-users' },
      { path: '/rate-monitor', label: 'Rate Monitor', icon: 'fa-chart-line' },
      { path: '/referral-partners', label: 'Partners', icon: 'fa-handshake' },
      { path: '/marketing', label: 'Marketing', icon: 'fa-bullhorn' },
    ]
  },
  {
    key: 'operations',
    label: 'Operations',
    path: '/smart-docs',
    matchPaths: ['/smart-docs', '/closed-loans', '/ai-underwriter', '/ops-manager'],
    children: [
      { path: '/smart-docs', label: 'Smart Docs', icon: 'fa-file-alt', badgeKey: 'smartDocs', badgeClass: 'urgent' },
      { path: '/closed-loans', label: 'Closed Loans', icon: 'fa-check-circle' },
      { path: '/ai-underwriter', label: 'AI Underwriter', icon: 'fa-robot' },
      { path: '/ops-manager', label: 'Ops Manager', icon: 'fa-clipboard-check' },
    ]
  },
  {
    key: 'management',
    label: 'Management',
    path: '/accounting',
    matchPaths: ['/master-manager', '/usage-intelligence', '/voice', '/dialer', '/conversation-intelligence'],
    children: [
      { path: '/master-manager', label: 'Capacity', icon: 'fa-chart-pie' },
      { path: '/usage-intelligence', label: 'Usage Intelligence', icon: 'fa-chart-bar' },
      {
        label: 'Voice & Calls',
        icon: 'fa-phone-volume',
        children: [
          { path: '/voice/studio', label: 'Agent Studio' },
          { path: '/voice/agents', label: 'Voice Agents' },
          { path: '/dialer', label: 'Power Dialer' },
          { path: '/voice/calls', label: 'Live Calls' },
          { path: '/voice/analytics', label: 'Call Analytics' },
          { path: '/conversation-intelligence', label: 'Call Intelligence' },
        ]
      },
    ]
  },
  {
    key: 'leadership',
    label: 'Leadership',
    path: '/market',
    matchPaths: ['/market', '/profitability', '/production-predictor', '/deal-alerts', '/scorecard'],
    children: [
      { path: '/market', label: 'Market', icon: 'fa-globe' },
      { path: '/profitability', label: 'Profitability', icon: 'fa-dollar-sign' },
      { path: '/production-predictor', label: 'Production Predictor', icon: 'fa-crystal-ball' },
      { path: '/deal-alerts', label: 'Deal Alerts', icon: 'fa-bell' },
      { path: '/scorecard', label: 'Scorecard', icon: 'fa-clipboard-list' },
    ]
  }
];

/**
 * Get master admin navigation items
 * @returns {Array} Array of navigation item objects for master admin
 */
export const getMasterAdminNavigation = () => {
  return MASTER_ADMIN_NAVIGATION;
};

// =============================================================================
// PROFITABILITY VIEW TYPES - Different views based on role
// =============================================================================

export const PROFITABILITY_VIEW_TYPES = {
  admin: 'company',              // Platform Admin sees company-wide profitability (all orgs)
  site_admin: 'company',         // Site Admin sees their organization's profitability
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

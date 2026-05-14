// Re-export all dashboard components for backward compatibility
import '../RoleDashboards.css';

import { LoanOfficerDashboard } from './LoanOfficerDashboard';
import { ProcessorDashboard } from './ProcessorDashboard';
import { UnderwriterDashboard } from './UnderwriterDashboard';
import { CloserDashboard } from './CloserDashboard';
import { SiteAdminDashboard } from './SiteAdminDashboard';
import { ManagerDashboard } from './ManagerDashboard';
import { AdminDashboard } from './AdminDashboard';
import { ProductionAssistant1Dashboard, ProductionAssistant2Dashboard } from './ProductionAssistantDashboard';
import { RoleDashboardSwitcher } from './RoleDashboardSwitcher';

// Named re-exports
export {
  LoanOfficerDashboard,
  ProcessorDashboard,
  UnderwriterDashboard,
  CloserDashboard,
  SiteAdminDashboard,
  ManagerDashboard,
  AdminDashboard,
  ProductionAssistant1Dashboard,
  ProductionAssistant2Dashboard,
  RoleDashboardSwitcher
};

// Resolve which dashboard component to render based on role ID
export const getDashboardByRole = (roleId) => {
  switch (roleId) {
    case 'site_admin':
      return SiteAdminDashboard;
    case 'loan_officer':
    case 'sales':
      return LoanOfficerDashboard;
    case 'production_assistant_1':
    case 'pa1':
      return ProductionAssistant1Dashboard;
    case 'production_assistant_2':
    case 'pa2':
      return ProductionAssistant2Dashboard;
    case 'concierge':
      return ProductionAssistant1Dashboard;
    case 'processor':
      return ProcessorDashboard;
    case 'underwriter':
      return UnderwriterDashboard;
    case 'closer':
      return CloserDashboard;
    case 'manager':
    case 'management':
      return ManagerDashboard;
    case 'executive':
    case 'admin':
      return AdminDashboard;
    default:
      return null;
  }
};

// Default export for backward compatibility
const RoleDashboards = {
  LoanOfficerDashboard,
  ProductionAssistant1Dashboard,
  ProductionAssistant2Dashboard,
  ProcessorDashboard,
  UnderwriterDashboard,
  CloserDashboard,
  ManagerDashboard,
  SiteAdminDashboard,
  AdminDashboard,
  RoleDashboardSwitcher,
  getDashboardByRole
};

export default RoleDashboards;

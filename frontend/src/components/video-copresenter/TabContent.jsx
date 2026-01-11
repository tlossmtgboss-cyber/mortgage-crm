/**
 * Tab Content Router
 * Routes to the appropriate tab component based on active tab
 */
import React from 'react';
import { ProcessTab } from './tabs/ProcessTab';
import { ProgramsTab } from './tabs/ProgramsTab';
import { RatesTab } from './tabs/RatesTab';
import { ComparisonTab } from './tabs/ComparisonTab';
import { ClosingCostsTab } from './tabs/ClosingCostsTab';

const TabContent = ({
  tab,
  state,
  clientId,
  callSessionId,
  userRole
}) => {
  const commonProps = { clientId, callSessionId, userRole, state };

  switch (tab) {
    case 'process':
      return <ProcessTab {...commonProps} />;
    case 'programs':
      return <ProgramsTab {...commonProps} />;
    case 'rates':
      return <RatesTab {...commonProps} />;
    case 'comparison':
      return <ComparisonTab {...commonProps} />;
    case 'closing_costs':
      return <ClosingCostsTab {...commonProps} />;
    default:
      return (
        <div style={{ textAlign: 'center', padding: '48px', color: '#6b7280' }}>
          <p>Select a tab to view content</p>
        </div>
      );
  }
};

export default TabContent;
export { TabContent };

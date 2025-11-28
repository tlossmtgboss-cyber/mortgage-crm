import React from 'react';
import './PermissionsStep.css';

/**
 * PermissionsStep - Placeholder component for user permissions configuration
 * TODO: Implement full permissions UI
 */
function PermissionsStep({
  selectedResponsibilities = [],
  onResponsibilitiesChange = () => {},
  selectedStages = [],
  onStagesChange = () => {},
  enabledFeatures = {},
  onFeaturesChange = () => {}
}) {
  return (
    <div className="permissions-step">
      <div className="permissions-header">
        <h2>Configure Permissions</h2>
        <p>Set up user responsibilities and access levels</p>
      </div>

      <div className="permissions-content">
        <div className="permissions-section">
          <h3>Responsibilities</h3>
          <p className="section-description">
            Permissions will be configured based on the user's role and team assignment.
          </p>
        </div>
      </div>
    </div>
  );
}

export default PermissionsStep;

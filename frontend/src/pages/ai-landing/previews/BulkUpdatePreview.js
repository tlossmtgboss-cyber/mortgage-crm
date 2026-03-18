import React from 'react';

function BulkUpdatePreview({ preview, onExecute, onEdit }) {
  return (
    <div className="ai-message-content-new ai-special-content">
      I found 14 deals in underwriting that need the new appraisal waiver guidelines added.

      <div className="ai-action-preview">
        <h3>Bulk Deal Update</h3>
        <div className="ai-preview-content">
          Found 14 deals currently in underwriting status:<br/><br/>
          Will Update:<br/>
          • LN-2024-8901 - Lisa Anderson - Conventional<br/>
          • LN-2024-8834 - Robert Taylor - Refinance<br/>
          • LN-2024-8756 - James Wilson - FHA<br/>
          • LN-2024-9012 - Patricia White - Conventional<br/>
          • LN-2024-9088 - John Davis - VA<br/>
          ... and 9 more<br/><br/>
          Update Details:<br/>
          Field: Guidelines Notes<br/>
          Adding: "NEW: Appraisal waiver available for LTV ≤ 80% on conv. loans per Fannie Mae 11/2025 updates. Eligible borrowers can save $500-700 and 1-2 weeks processing time."<br/><br/>
          This will be added to each deal's notes section and trigger a notification to assigned processors.
        </div>
        <div className="ai-action-buttons">
          <button className="ai-btn ai-btn-edit" onClick={onEdit}>Modify Update</button>
          <button className="ai-btn ai-btn-approve" onClick={onExecute}>Update 14 Deals</button>
        </div>
      </div>
    </div>
  );
}

export default BulkUpdatePreview;

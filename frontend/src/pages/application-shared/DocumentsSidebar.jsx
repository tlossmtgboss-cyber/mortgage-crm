import React from 'react';
import Icon from './Icon';

/**
 * Documents sidebar showing dynamically generated document requirements.
 * Used by both Purchase and Refinance applications.
 *
 * @param {Object} props
 * @param {Array} props.enabledStages - All enabled application stages
 * @param {string} props.currentStage - Current stage ID
 * @param {Function} props.getRequiredDocuments - Function returning document requirements
 * @param {Object} props.declarations - Current declaration answers
 * @param {Object} props.assetData - Current asset data (optional, pass {} for refinance)
 * @param {Object} props.profileData - Current profile data
 * @param {Object} props.incomeData - Current income data
 * @param {Object} props.coBorrowerData - Co-borrower profile data
 * @param {Object} props.coBorrowerIncomeData - Co-borrower income data
 * @param {Object} props.categoryUnlockStage - Map of category to stage that unlocks it
 */
const DocumentsSidebar = ({
  enabledStages,
  currentStage,
  getRequiredDocuments,
  declarations,
  assetData = {},
  profileData = {},
  incomeData = {},
  coBorrowerData = {},
  coBorrowerIncomeData = {},
  categoryUnlockStage = {
    identity: 'declarations',
    income: 'income',
    assets: 'assets',
    property: 'property',
  },
}) => {
  const currentIndex = enabledStages.findIndex(s => s.id === currentStage);
  const requiredDocs = getRequiredDocuments(
    declarations,
    assetData,
    profileData,
    incomeData,
    coBorrowerData,
    coBorrowerIncomeData
  );

  const categoryLabels = {
    identity: 'Identity Verification',
    income: 'Income Documents',
    assets: 'Asset Documents',
    property: 'Property Documents',
  };

  // Filter categories to only show those that have been unlocked AND have documents
  const visibleCategories = ['identity', 'income', 'assets', 'property'].filter(category => {
    const unlockStage = categoryUnlockStage[category];
    const unlockIndex = enabledStages.findIndex(s => s.id === unlockStage);
    const categoryDocs = requiredDocs.filter(d => d.category === category);
    return currentIndex >= unlockIndex && categoryDocs.length > 0;
  });

  return (
    <aside className="documents-sidebar">
      <div className="sidebar-header">
        <Icon name="document" size={20} />
        <h3>Documents Needed</h3>
      </div>
      <p className="sidebar-subtitle">Gather these documents to speed up your application</p>

      <div className="documents-list">
        {visibleCategories.map(category => {
          const categoryDocs = requiredDocs.filter(d => d.category === category);
          const isCurrent = categoryDocs.some(d => d.stage === currentStage);

          return (
            <div key={category} className={`doc-category ${isCurrent ? 'current' : ''}`}>
              <h4 className="doc-category-title">{categoryLabels[category]}</h4>
              <ul className="doc-items">
                {categoryDocs.map(doc => (
                  <li key={doc.id} className="doc-item">
                    <span className="doc-checkbox">
                      <Icon name="document" size={14} />
                    </span>
                    <div className="doc-info">
                      <span className="doc-name">{doc.name}</span>
                      <span className="doc-desc">{doc.description}</span>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          );
        })}
      </div>

      <div className="sidebar-tip">
        <Icon name="info" size={16} />
        <span>You can upload documents after submitting your application</span>
      </div>
    </aside>
  );
};

export default DocumentsSidebar;

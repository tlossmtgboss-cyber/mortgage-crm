import React, { useState, useEffect, useRef, useCallback } from 'react';
import './DocumentsNeeded.css';

/**
 * DocumentsNeeded - Dynamic document tracking component
 * Displays required documents that populate as application questions are answered
 * Integrates with backend lead_conditions table
 *
 * Field names must match the snake_case IDs from purchaseQuestions.js / refinanceQuestions.js
 */

const API_URL = process.env.REACT_APP_API_URL || 'https://api.perenniaai.com';

const DocumentsNeeded = ({ applicationData, workspaceId }) => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);
  const prevDocsRef = useRef(null);

  // Document rules based on application answers (snake_case field names)
  const evaluateDocumentRequirements = useCallback((data) => {
    if (!data || typeof data !== 'object') return [];

    const requiredDocs = [];

    // --- Income documents ---
    // employment_status: 'employed', 'self_employed', '1099_contractor', 'retired', 'not_employed'
    const empStatus = data.employment_status;

    if (empStatus === 'employed') {
      requiredDocs.push({
        name: 'Recent Pay Stubs',
        description: 'Most recent 30 days of pay stubs',
        category: 'income',
        priority: 'required'
      });
      requiredDocs.push({
        name: 'W-2 Forms',
        description: 'Last 2 years of W-2 forms',
        category: 'income',
        priority: 'required'
      });
    }

    if (empStatus === 'self_employed' || empStatus === '1099_contractor') {
      requiredDocs.push({
        name: 'Tax Returns',
        description: 'Personal and business tax returns for last 2 years',
        category: 'income',
        priority: 'required'
      });
      requiredDocs.push({
        name: 'Profit & Loss Statement',
        description: 'Year-to-date P&L statement',
        category: 'income',
        priority: 'required'
      });
      requiredDocs.push({
        name: 'Business Bank Statements',
        description: 'Last 2 months of business bank statements',
        category: 'income',
        priority: 'required'
      });
    }

    // --- Asset documents ---
    // down_payment_source: 'checking_savings', 'sale_of_home', 'gift', 'retirement', 'investment', 'other'
    const dpSource = data.down_payment_source;
    const hasAssets = parseFloat(data.checking_balance) > 0
      || parseFloat(data.savings_balance) > 0
      || parseFloat(data.investment_balance) > 0;

    if (dpSource === 'checking_savings' || dpSource === 'investment' || hasAssets) {
      requiredDocs.push({
        name: 'Bank Statements',
        description: 'Last 2 months of all bank account statements',
        category: 'assets',
        priority: 'required'
      });
    }

    if (dpSource === 'gift') {
      requiredDocs.push({
        name: 'Gift Letter',
        description: 'Signed gift letter from donor',
        category: 'assets',
        priority: 'required'
      });
      requiredDocs.push({
        name: 'Donor Bank Statements',
        description: 'Proof of funds from gift donor',
        category: 'assets',
        priority: 'required'
      });
    }

    // retirement_balance is a currency field
    if (parseFloat(data.retirement_balance) > 0) {
      requiredDocs.push({
        name: 'Retirement Account Statements',
        description: 'Most recent 401k, IRA, or other retirement account statements',
        category: 'assets',
        priority: 'optional'
      });
    }

    // --- Property documents ---
    // found_property is a boolean, property_address is a string
    if (data.property_address || data.found_property === true) {
      requiredDocs.push({
        name: 'Purchase Agreement',
        description: 'Fully executed purchase contract',
        category: 'property',
        priority: 'required'
      });
    }

    // property_type: 'single_family', 'condo', 'townhouse', 'multi_family', 'manufactured'
    if (data.property_type === 'condo') {
      requiredDocs.push({
        name: 'HOA Documents',
        description: 'Homeowners association documents and budget',
        category: 'property',
        priority: 'required'
      });
    }

    // --- Additional income ---
    // has_additional_income is a boolean
    if (data.has_additional_income === true) {
      requiredDocs.push({
        name: 'Additional Income Documentation',
        description: 'Documentation for rental, alimony, or other income',
        category: 'income',
        priority: 'required'
      });
    }

    // owns_other_property is a boolean
    if (data.owns_other_property === true) {
      requiredDocs.push({
        name: 'Rental Property Documentation',
        description: 'Lease agreements and rental income verification',
        category: 'income',
        priority: 'required'
      });
    }

    // --- Credit and debt documents ---
    // has_delinquent_debt is a boolean (covers student loans, tax liens, etc.)
    if (data.has_delinquent_debt === true) {
      requiredDocs.push({
        name: 'Delinquent Debt Statement',
        description: 'Current statements for student loans, tax liens, or other delinquent debts',
        category: 'liabilities',
        priority: 'required'
      });
    }

    // has_bankruptcy and has_foreclosure are booleans
    if (data.has_bankruptcy === true || data.has_foreclosure === true) {
      requiredDocs.push({
        name: 'Bankruptcy/Foreclosure Documentation',
        description: 'Discharge papers and explanation letter',
        category: 'credit',
        priority: 'required'
      });
    }

    // --- Identity documents (always required once user has started) ---
    if (Object.keys(data).length > 0) {
      requiredDocs.push({
        name: 'Government-Issued ID',
        description: 'Driver\'s license or passport',
        category: 'identity',
        priority: 'required'
      });
    }

    return requiredDocs;
  }, []);

  // Update documents when application data changes
  useEffect(() => {
    if (applicationData && Object.keys(applicationData).length > 0) {
      const newDocs = evaluateDocumentRequirements(applicationData);

      // Only update state if documents actually changed (prevent infinite loop)
      const newDocsKey = JSON.stringify(newDocs);
      if (newDocsKey !== prevDocsRef.current) {
        prevDocsRef.current = newDocsKey;
        setDocuments(newDocs);
      }
    }
  }, [applicationData, evaluateDocumentRequirements]);

  // Sync with backend when documents change (debounced, with auth)
  useEffect(() => {
    if (documents.length === 0 || !workspaceId) return;

    const timer = setTimeout(() => {
      syncDocumentsWithBackend();
    }, 1000);

    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documents, workspaceId]);

  const syncDocumentsWithBackend = async () => {
    try {
      setLoading(true);
      const token = localStorage.getItem('token');

      await fetch(`${API_URL}/api/workspaces/${workspaceId}/documents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token && { 'Authorization': `Bearer ${token}` }),
        },
        body: JSON.stringify({ documents }),
      });
    } catch (error) {
      console.error('Error syncing documents:', error);
    } finally {
      setLoading(false);
    }
  };

  const getCategoryIcon = (category) => {
    const icons = {
      income: '💵',
      assets: '💰',
      property: '🏠',
      liabilities: '💳',
      credit: '📊',
      identity: '🆔',
    };
    return icons[category] || '📄';
  };

  const getCategoryLabel = (category) => {
    const labels = {
      income: 'Income',
      assets: 'Assets',
      property: 'Property',
      liabilities: 'Liabilities',
      credit: 'Credit',
      identity: 'Identity',
    };
    return labels[category] || category;
  };

  if (documents.length === 0) {
    return (
      <div className="documents-needed-empty">
        <p>Answer questions to see required documents</p>
      </div>
    );
  }

  // Group documents by category
  const groupedDocs = documents.reduce((acc, doc) => {
    if (!acc[doc.category]) {
      acc[doc.category] = [];
    }
    acc[doc.category].push(doc);
    return acc;
  }, {});

  return (
    <div className="documents-needed">
      <div className="documents-needed-header">
        <h3>Documents Needed</h3>
        <span className="document-count">{documents.length} {documents.length === 1 ? 'item' : 'items'}</span>
      </div>

      {loading && <div className="loading-indicator">Syncing...</div>}

      <div className="documents-list">
        {Object.entries(groupedDocs).map(([category, docs]) => (
          <div key={category} className="document-category">
            <div className="category-header">
              <span className="category-icon">{getCategoryIcon(category)}</span>
              <span className="category-name">{getCategoryLabel(category)}</span>
              <span className="category-count">({docs.length})</span>
            </div>

            <div className="category-documents">
              {docs.map((doc, index) => (
                <div key={`${category}-${index}`} className="document-item">
                  <div className="document-header">
                    <span className="document-name">{doc.name}</span>
                    {doc.priority === 'required' && (
                      <span className="badge-required">Required</span>
                    )}
                    {doc.priority === 'optional' && (
                      <span className="badge-optional">Optional</span>
                    )}
                  </div>
                  <p className="document-description">{doc.description}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="documents-needed-footer">
        <p className="footer-note">
          These documents will be requested in your client portal after submission.
        </p>
      </div>
    </div>
  );
};

export default DocumentsNeeded;

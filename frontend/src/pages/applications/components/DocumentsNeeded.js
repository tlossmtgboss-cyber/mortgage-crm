import React, { useState, useEffect } from 'react';
import './DocumentsNeeded.css';

/**
 * DocumentsNeeded - Dynamic document tracking component
 * Displays required documents that populate as application questions are answered
 * Integrates with backend lead_conditions table
 */
const DocumentsNeeded = ({ applicationData, workspaceId }) => {
  const [documents, setDocuments] = useState([]);
  const [loading, setLoading] = useState(false);

  // Document rules based on application answers
  const evaluateDocumentRequirements = (data) => {
    const requiredDocs = [];

    // Income documents
    if (data.employmentStatus === 'employed' || data.employmentType === 'W2') {
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

    if (data.employmentStatus === 'self-employed' || data.employmentType === 'self-employed') {
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

    // Asset documents
    if (data.downPaymentSource === 'savings' || data.assetsAmount > 0) {
      requiredDocs.push({
        name: 'Bank Statements',
        description: 'Last 2 months of all bank account statements',
        category: 'assets',
        priority: 'required'
      });
    }

    if (data.downPaymentSource === 'gift') {
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

    if (data.hasRetirementAccounts === 'yes' || data.retirementAccountsAmount > 0) {
      requiredDocs.push({
        name: 'Retirement Account Statements',
        description: 'Most recent 401k, IRA, or other retirement account statements',
        category: 'assets',
        priority: 'optional'
      });
    }

    // Property documents
    if (data.propertyAddress || data.hasContract === 'yes') {
      requiredDocs.push({
        name: 'Purchase Agreement',
        description: 'Fully executed purchase contract',
        category: 'property',
        priority: 'required'
      });
    }

    if (data.propertyType === 'condo') {
      requiredDocs.push({
        name: 'HOA Documents',
        description: 'Homeowners association documents and budget',
        category: 'property',
        priority: 'required'
      });
    }

    // Additional income sources
    if (data.hasAdditionalIncome === 'yes' || data.rentalIncome > 0) {
      requiredDocs.push({
        name: 'Additional Income Documentation',
        description: 'Documentation for rental, alimony, or other income',
        category: 'income',
        priority: 'required'
      });
    }

    if (data.hasRentalProperty === 'yes') {
      requiredDocs.push({
        name: 'Rental Property Documentation',
        description: 'Lease agreements and rental income verification',
        category: 'income',
        priority: 'required'
      });
    }

    // Credit and debt documents
    if (data.hasStudentLoans === 'yes' || data.studentLoanBalance > 0) {
      requiredDocs.push({
        name: 'Student Loan Statement',
        description: 'Current student loan statement showing balance and payment',
        category: 'liabilities',
        priority: 'required'
      });
    }

    if (data.hasBankruptcy === 'yes' || data.hasForeclosure === 'yes') {
      requiredDocs.push({
        name: 'Bankruptcy/Foreclosure Documentation',
        description: 'Discharge papers and explanation letter',
        category: 'credit',
        priority: 'required'
      });
    }

    // Identity documents (always required)
    if (Object.keys(data).length > 0) {
      requiredDocs.push({
        name: 'Government-Issued ID',
        description: 'Driver\'s license or passport',
        category: 'identity',
        priority: 'required'
      });
    }

    return requiredDocs;
  };

  // Update documents when application data changes
  useEffect(() => {
    if (applicationData && Object.keys(applicationData).length > 0) {
      const newDocs = evaluateDocumentRequirements(applicationData);
      setDocuments(newDocs);
    }
  }, [applicationData]);

  // Sync with backend when documents change
  useEffect(() => {
    if (documents.length > 0 && workspaceId) {
      syncDocumentsWithBackend();
    }
  }, [documents, workspaceId]);

  const syncDocumentsWithBackend = async () => {
    try {
      setLoading(true);
      const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';
      
      // Send documents to backend to create lead_conditions
      await fetch(`${API_URL}/api/workspaces/${workspaceId}/documents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
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
        <p>📋 Answer questions to see required documents</p>
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
        <h3>📋 Documents Needed</h3>
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

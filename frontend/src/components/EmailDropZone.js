import React, { useState, useCallback } from 'react';
import EmailReconciliationModal from './EmailReconciliationModal';
import DocumentDropModal from './DocumentDropModal';
import { emailDropAPI, documentDropAPI } from '../services/api';
import './EmailDropZone.css';

/**
 * EmailDropZone - Drag and drop component for email and document files
 * Wraps children and provides drag-drop overlay
 * When email is dropped, prompts user to:
 * 1. Add to borrower's document tab
 * 2. Add/reconcile data to CRM
 * When document is dropped, classifies and uploads it
 */
function EmailDropZone({ children }) {
  const [isDragging, setIsDragging] = useState(false);
  const [showChoiceModal, setShowChoiceModal] = useState(false);
  const [showReconciliationModal, setShowReconciliationModal] = useState(false);
  const [showDocumentModal, setShowDocumentModal] = useState(false);
  const [emailData, setEmailData] = useState(null);
  const [documentFile, setDocumentFile] = useState(null);
  const [parsing, setParsing] = useState(false);
  const [aiParseResult, setAiParseResult] = useState(null);

  // Determine if file is an email or document
  const isEmailFile = (file) => {
    return (
      file.name.endsWith('.eml') ||
      file.name.endsWith('.msg') ||
      file.type === 'message/rfc822'
    );
  };

  const isDocumentFile = (file) => {
    const docExtensions = ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.png', '.jpg', '.jpeg', '.gif', '.tiff'];
    return docExtensions.some(ext => file.name.toLowerCase().endsWith(ext));
  };

  // Parse email file content
  const parseEmailFile = async (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target.result;

        // Parse .eml or .msg file format
        const emailData = parseEmailContent(content, file.name);
        resolve(emailData);
      };
      reader.onerror = reject;
      reader.readAsText(file);
    });
  };

  // Parse email content from raw text
  const parseEmailContent = (content, filename) => {
    // Extract headers
    const fromMatch = content.match(/^From:\s*(.+)$/mi);
    const toMatch = content.match(/^To:\s*(.+)$/mi);
    const subjectMatch = content.match(/^Subject:\s*(.+)$/mi);
    const dateMatch = content.match(/^Date:\s*(.+)$/mi);

    // Find email body (after headers)
    const bodyStart = content.indexOf('\n\n');
    let body = bodyStart > -1 ? content.substring(bodyStart + 2) : content;

    // Clean up body - remove HTML if present
    if (body.includes('<html') || body.includes('<HTML')) {
      // Extract text from HTML
      body = body.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    }

    // Try to extract borrower name from content
    const borrowerPatterns = [
      /(?:borrower|client|customer):\s*([A-Z][a-z]+\s+[A-Z][a-z]+)/i,
      /(?:Dear|Hi|Hello)\s+([A-Z][a-z]+)/i,
      /(?:regarding|re:)\s+([A-Z][a-z]+\s+[A-Z][a-z]+)/i,
    ];

    let matchedBorrower = null;
    for (const pattern of borrowerPatterns) {
      const match = content.match(pattern);
      if (match) {
        matchedBorrower = match[1];
        break;
      }
    }

    // Try to extract loan number
    const loanMatch = content.match(/(?:loan\s*#?|loan\s*number|file\s*#?)[\s:]*([A-Z0-9-]+)/i);

    // Determine confidence based on what we found
    let confidence = 45; // Base confidence
    if (fromMatch) confidence += 10;
    if (subjectMatch) confidence += 10;
    if (matchedBorrower) confidence += 15;
    if (loanMatch) confidence += 20;

    return {
      id: Date.now(),
      filename,
      from: fromMatch ? fromMatch[1].trim() : 'Unknown Sender',
      to: toMatch ? toMatch[1].trim() : '',
      subject: subjectMatch ? subjectMatch[1].trim() : 'No Subject',
      date: dateMatch ? dateMatch[1].trim() : new Date().toLocaleString(),
      body: body.substring(0, 2000), // Limit body size
      rawContent: content,
      matchedBorrower,
      matchedLoanNumber: loanMatch ? loanMatch[1] : null,
      confidence: Math.min(confidence, 95),
    };
  };

  const handleDragEnter = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();

    // Check if dragging files
    if (e.dataTransfer.types.includes('Files')) {
      setIsDragging(true);
    }
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();

    // Only hide if leaving the drop zone entirely
    if (e.currentTarget === e.target) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
  }, []);

  const handleDrop = useCallback(async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    if (files.length === 0) return;

    const file = files[0];

    // Check if it's an email file
    if (isEmailFile(file)) {
      setParsing(true);
      try {
        const parsed = await parseEmailFile(file);
        setEmailData(parsed);

        // Try to get AI parsing in background
        try {
          const aiResult = await emailDropAPI.parse(parsed);
          setAiParseResult(aiResult);
          // Update confidence based on AI result
          if (aiResult.success) {
            parsed.aiExtractedFields = aiResult.extracted_fields;
            parsed.aiConfidenceScores = aiResult.confidence_scores;
            parsed.aiSuggestedAction = aiResult.suggested_action;
            parsed.aiQuestions = aiResult.questions;
            parsed.aiSummary = aiResult.ai_summary;
            parsed.matchedEntities = aiResult.matched_entities;
          }
        } catch (aiError) {
          console.warn('AI parsing failed, using basic parsing:', aiError);
        }

        setShowChoiceModal(true);
      } catch (error) {
        console.error('Failed to parse email:', error);
        alert('Failed to parse email file. Please try again.');
      }
      setParsing(false);
      return;
    }

    // Check if it's a document file
    if (isDocumentFile(file)) {
      setDocumentFile(file);
      setShowDocumentModal(true);
      return;
    }

    // Try to parse as text email anyway
    setParsing(true);
    try {
      const parsed = await parseEmailFile(file);
      setEmailData(parsed);
      setShowChoiceModal(true);
    } catch (error) {
      console.error('Failed to parse file:', error);
      alert('Could not parse this file. Supported formats: .eml, .msg, .pdf, .doc, .docx, .xls, .xlsx, images');
    }
    setParsing(false);
  }, []);

  const handleChoiceDocument = () => {
    setShowChoiceModal(false);
    setShowReconciliationModal(true);
  };

  const handleChoiceLead = () => {
    setShowChoiceModal(false);
    // Set the action type for the reconciliation modal
    if (emailData) {
      emailData.preferredAction = 'lead';
    }
    setShowReconciliationModal(true);
  };

  const handleChoiceLoan = () => {
    setShowChoiceModal(false);
    if (emailData) {
      emailData.preferredAction = 'loan';
    }
    setShowReconciliationModal(true);
  };

  const handleReconciliationClose = () => {
    setShowReconciliationModal(false);
    setEmailData(null);
    setAiParseResult(null);
  };

  const handleReconciliationComplete = async (action, data) => {
    console.log('Reconciliation complete:', action, data);

    try {
      // Call the backend API to process the email
      const result = await emailDropAPI.process(
        action,
        emailData,
        data.extractedFields || emailData.aiExtractedFields || {},
        data.matchedEntity?.data?.id?.toString(),
        data.matchedEntity?.type,
        !data.matchedEntity, // create_new if no matched entity
        data.userAnswers || {}
      );

      if (result.success) {
        alert(`Success! ${result.message}`);
      } else {
        alert(`Warning: ${result.message}`);
      }
    } catch (error) {
      console.error('Failed to process email:', error);
      alert('Failed to process email. Please try again.');
    }

    setShowReconciliationModal(false);
    setEmailData(null);
    setAiParseResult(null);
  };

  const handleDocumentModalClose = () => {
    setShowDocumentModal(false);
    setDocumentFile(null);
  };

  const handleDocumentUploadComplete = (result) => {
    console.log('Document upload complete:', result);
    setShowDocumentModal(false);
    setDocumentFile(null);
    alert(`Document uploaded successfully!`);
  };

  return (
    <div
      className="email-drop-zone-wrapper"
      onDragEnter={handleDragEnter}
      onDragLeave={handleDragLeave}
      onDragOver={handleDragOver}
      onDrop={handleDrop}
    >
      {children}

      {/* Drag Overlay */}
      {isDragging && (
        <div className="email-drop-overlay">
          <div className="email-drop-content">
            <div className="email-drop-icon">📧📄</div>
            <h2>Drop File Here</h2>
            <p>Drop emails (.eml, .msg) or documents (.pdf, .doc, images) to import</p>
          </div>
        </div>
      )}

      {/* Parsing Indicator */}
      {parsing && (
        <div className="email-parsing-overlay">
          <div className="email-parsing-content">
            <div className="parsing-spinner"></div>
            <p>Analyzing file with AI...</p>
          </div>
        </div>
      )}

      {/* Choice Modal */}
      {showChoiceModal && emailData && (
        <div className="email-choice-modal-overlay" onClick={() => setShowChoiceModal(false)}>
          <div className="email-choice-modal" onClick={e => e.stopPropagation()}>
            <div className="email-choice-header">
              <h2>Email Imported</h2>
              <button className="close-btn" onClick={() => setShowChoiceModal(false)}>×</button>
            </div>

            <div className="email-preview">
              <div className="email-preview-row">
                <span className="label">From:</span>
                <span className="value">{emailData.from}</span>
              </div>
              <div className="email-preview-row">
                <span className="label">Subject:</span>
                <span className="value">{emailData.subject}</span>
              </div>
              <div className="email-preview-row">
                <span className="label">Date:</span>
                <span className="value">{emailData.date}</span>
              </div>
              {emailData.aiSummary && (
                <div className="email-preview-row ai-summary">
                  <span className="label">AI Summary:</span>
                  <span className="value">{emailData.aiSummary}</span>
                </div>
              )}
              {emailData.aiSuggestedAction && (
                <div className="email-preview-row ai-suggestion">
                  <span className="label">AI Suggests:</span>
                  <span className="value suggested-action">{emailData.aiSuggestedAction.replace(/_/g, ' ')}</span>
                </div>
              )}
            </div>

            <div className="email-choice-question">
              <h3>Where should this email go?</h3>
            </div>

            <div className="email-choice-options">
              <button className="choice-btn document" onClick={handleChoiceDocument}>
                <span className="choice-icon">📁</span>
                <span className="choice-title">Archive Email</span>
                <span className="choice-desc">Add to borrower's document tab</span>
              </button>

              <button
                className={`choice-btn lead ${emailData.aiSuggestedAction === 'create_lead' || emailData.aiSuggestedAction === 'update_lead' ? 'suggested' : ''}`}
                onClick={handleChoiceLead}
              >
                <span className="choice-icon">👤</span>
                <span className="choice-title">Lead</span>
                <span className="choice-desc">Create or update a lead</span>
                {(emailData.aiSuggestedAction === 'create_lead' || emailData.aiSuggestedAction === 'update_lead') && (
                  <span className="ai-badge">AI Suggested</span>
                )}
              </button>

              <button
                className={`choice-btn crm ${emailData.aiSuggestedAction === 'create_loan' || emailData.aiSuggestedAction === 'update_loan' ? 'suggested' : ''}`}
                onClick={handleChoiceLoan}
              >
                <span className="choice-icon">➕</span>
                <span className="choice-title">Create/Open Loan</span>
                <span className="choice-desc">Add data to the CRM</span>
                {(emailData.aiSuggestedAction === 'create_loan' || emailData.aiSuggestedAction === 'update_loan') && (
                  <span className="ai-badge">AI Suggested</span>
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reconciliation Modal */}
      {showReconciliationModal && emailData && (
        <EmailReconciliationModal
          emailData={emailData}
          aiParseResult={aiParseResult}
          onClose={handleReconciliationClose}
          onComplete={handleReconciliationComplete}
        />
      )}

      {/* Document Upload Modal */}
      {showDocumentModal && documentFile && (
        <DocumentDropModal
          file={documentFile}
          onClose={handleDocumentModalClose}
          onComplete={handleDocumentUploadComplete}
        />
      )}
    </div>
  );
}

export default EmailDropZone;

import React, { useState, useCallback } from 'react';
import EmailReconciliationModal from './EmailReconciliationModal';
import './EmailDropZone.css';

/**
 * EmailDropZone - Drag and drop component for email files
 * Wraps children and provides drag-drop overlay
 * When email is dropped, prompts user to:
 * 1. Add to borrower's document tab
 * 2. Add/reconcile data to CRM
 */
function EmailDropZone({ children }) {
  const [isDragging, setIsDragging] = useState(false);
  const [showChoiceModal, setShowChoiceModal] = useState(false);
  const [showReconciliationModal, setShowReconciliationModal] = useState(false);
  const [emailData, setEmailData] = useState(null);
  const [parsing, setParsing] = useState(false);

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

    // Filter for email files (.eml, .msg, .txt)
    const emailFiles = files.filter(file =>
      file.name.endsWith('.eml') ||
      file.name.endsWith('.msg') ||
      file.name.endsWith('.txt') ||
      file.type === 'message/rfc822'
    );

    if (emailFiles.length === 0) {
      // Check if it's any file - could still be an email export
      if (files.length > 0) {
        // Try to parse anyway
        setParsing(true);
        try {
          const parsed = await parseEmailFile(files[0]);
          setEmailData(parsed);
          setShowChoiceModal(true);
        } catch (error) {
          console.error('Failed to parse file:', error);
          alert('Could not parse this file as an email. Please use .eml, .msg, or .txt format.');
        }
        setParsing(false);
      }
      return;
    }

    // Parse the first email file
    setParsing(true);
    try {
      const parsed = await parseEmailFile(emailFiles[0]);
      setEmailData(parsed);
      setShowChoiceModal(true);
    } catch (error) {
      console.error('Failed to parse email:', error);
      alert('Failed to parse email file. Please try again.');
    }
    setParsing(false);
  }, []);

  const handleChoiceDocument = () => {
    setShowChoiceModal(false);
    // TODO: Open borrower search/select modal to add to documents
    alert('Document upload feature coming soon. Select a borrower to attach this email to their documents.');
  };

  const handleChoiceCRM = () => {
    setShowChoiceModal(false);
    setShowReconciliationModal(true);
  };

  const handleReconciliationClose = () => {
    setShowReconciliationModal(false);
    setEmailData(null);
  };

  const handleReconciliationComplete = (action, data) => {
    console.log('Reconciliation complete:', action, data);
    setShowReconciliationModal(false);
    setEmailData(null);
    // TODO: Call API to save the data
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
            <div className="email-drop-icon">📧</div>
            <h2>Drop Email Here</h2>
            <p>Release to import email into CRM</p>
          </div>
        </div>
      )}

      {/* Parsing Indicator */}
      {parsing && (
        <div className="email-parsing-overlay">
          <div className="email-parsing-content">
            <div className="parsing-spinner"></div>
            <p>Parsing email...</p>
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

              <button className="choice-btn lead" onClick={handleChoiceCRM}>
                <span className="choice-icon">👤</span>
                <span className="choice-title">Lead</span>
                <span className="choice-desc">Create or update a lead</span>
              </button>

              <button className="choice-btn crm" onClick={handleChoiceCRM}>
                <span className="choice-icon">➕</span>
                <span className="choice-title">Create/Open Loan</span>
                <span className="choice-desc">Add data to the CRM</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reconciliation Modal */}
      {showReconciliationModal && emailData && (
        <EmailReconciliationModal
          emailData={emailData}
          onClose={handleReconciliationClose}
          onComplete={handleReconciliationComplete}
        />
      )}
    </div>
  );
}

export default EmailDropZone;

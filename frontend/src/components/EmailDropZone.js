import React, { useState, useCallback, useEffect, useRef } from 'react';
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
  const dragCounterRef = useRef(0);
  const dropZoneRef = useRef(null);

  // Reference to the main handleDrop callback for use in global handler
  const handleDropRef = useRef(null);

  // Global document-level drag handlers for better capture
  useEffect(() => {
    let dragCounter = 0;

    const handleWindowDragEnter = (e) => {
      e.preventDefault();
      dragCounter++;

      // Check if it's a valid drag (files, emails, etc.)
      const types = Array.from(e.dataTransfer?.types || []);
      console.log('Window DragEnter - types:', types, 'counter:', dragCounter);

      // Files type is present when dragging files from desktop/finder
      const hasFiles = types.includes('Files');
      const hasText = types.includes('text/html') || types.includes('text/plain') || types.includes('text/uri-list');

      if (hasFiles || hasText) {
        setIsDragging(true);
      }
    };

    const handleWindowDragLeave = (e) => {
      e.preventDefault();
      dragCounter--;
      console.log('Window DragLeave - counter:', dragCounter);

      // Only hide when all drag events have left
      if (dragCounter <= 0) {
        dragCounter = 0;
        setIsDragging(false);
      }
    };

    const handleWindowDragOver = (e) => {
      // CRITICAL: Must prevent default to allow drop
      e.preventDefault();
      // Set the drop effect to show it's droppable
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleWindowDrop = (e) => {
      // MUST prevent default to stop browser from opening file
      e.preventDefault();
      console.log('Window Drop detected - types:', Array.from(e.dataTransfer?.types || []), 'files:', e.dataTransfer?.files?.length);
      dragCounter = 0;

      // Directly call the drop handler
      if (handleDropRef.current) {
        handleDropRef.current(e);
      } else {
        setIsDragging(false);
      }
    };

    // Add document-level listeners with capture phase for priority
    document.addEventListener('dragenter', handleWindowDragEnter, true);
    document.addEventListener('dragleave', handleWindowDragLeave, true);
    document.addEventListener('dragover', handleWindowDragOver, true);
    document.addEventListener('drop', handleWindowDrop, true);

    return () => {
      document.removeEventListener('dragenter', handleWindowDragEnter, true);
      document.removeEventListener('dragleave', handleWindowDragLeave, true);
      document.removeEventListener('dragover', handleWindowDragOver, true);
      document.removeEventListener('drop', handleWindowDrop, true);
    };
  }, []);

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

  // Parse email content from dragged HTML/text (from Outlook, Gmail, etc.)
  const parseEmailFromDragContent = (content, contentType) => {
    let textContent = content;
    let fromAddress = '';
    let toAddress = '';
    let subject = '';
    let dateStr = '';
    let body = '';

    if (contentType === 'html') {
      // Extract text from HTML
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = content;

      // Try to find email headers in the HTML
      const allText = tempDiv.textContent || tempDiv.innerText;
      textContent = allText;

      // Look for common email header patterns in HTML
      const fromMatch = content.match(/From:?\s*<?([^<>\n\r]+@[^<>\n\r]+)>?/i) ||
                       content.match(/from[:\s]+([^\n<]+)/i);
      const toMatch = content.match(/To:?\s*<?([^<>\n\r]+@[^<>\n\r]+)>?/i);
      const subjectMatch = content.match(/Subject:?\s*([^\n\r<]+)/i) ||
                          content.match(/<title>([^<]+)<\/title>/i);
      const dateMatch = content.match(/Date:?\s*([^\n\r<]+)/i) ||
                       content.match(/Sent:?\s*([^\n\r<]+)/i);

      fromAddress = fromMatch ? fromMatch[1].trim() : '';
      toAddress = toMatch ? toMatch[1].trim() : '';
      subject = subjectMatch ? subjectMatch[1].trim() : '';
      dateStr = dateMatch ? dateMatch[1].trim() : '';
      body = allText.substring(0, 3000);
    } else {
      // Plain text - parse as standard email format
      const fromMatch = textContent.match(/From:\s*(.+)/i);
      const toMatch = textContent.match(/To:\s*(.+)/i);
      const subjectMatch = textContent.match(/Subject:\s*(.+)/i);
      const dateMatch = textContent.match(/Date:\s*(.+)/i) ||
                       textContent.match(/Sent:\s*(.+)/i);

      fromAddress = fromMatch ? fromMatch[1].trim() : '';
      toAddress = toMatch ? toMatch[1].trim() : '';
      subject = subjectMatch ? subjectMatch[1].trim() : '';
      dateStr = dateMatch ? dateMatch[1].trim() : '';

      // Body is everything after headers
      const bodyStart = textContent.search(/\n\n|\r\n\r\n/);
      body = bodyStart > -1 ? textContent.substring(bodyStart + 2, bodyStart + 3000) : textContent.substring(0, 3000);
    }

    // Try to extract email from the from field if it contains a name
    const emailMatch = fromAddress.match(/[\w\.-]+@[\w\.-]+\.\w+/);
    if (emailMatch) {
      fromAddress = emailMatch[0];
    }

    // Try to extract borrower name from content
    const borrowerPatterns = [
      /(?:borrower|client|customer):\s*([A-Z][a-z]+\s+[A-Z][a-z]+)/i,
      /(?:Dear|Hi|Hello)\s+([A-Z][a-z]+)/i,
      /(?:my name is|I am|I'm)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/i,
    ];

    let matchedBorrower = null;
    for (const pattern of borrowerPatterns) {
      const match = textContent.match(pattern);
      if (match) {
        matchedBorrower = match[1];
        break;
      }
    }

    // Try to extract loan number
    const loanMatch = textContent.match(/(?:loan\s*#?|loan\s*number|file\s*#?)[\s:]*([A-Z0-9-]+)/i);

    // Calculate confidence
    let confidence = 40;
    if (fromAddress) confidence += 15;
    if (subject) confidence += 10;
    if (matchedBorrower) confidence += 15;
    if (loanMatch) confidence += 20;

    return {
      id: Date.now(),
      filename: `dragged_email_${Date.now()}.txt`,
      from: fromAddress || 'Unknown Sender',
      to: toAddress || '',
      subject: subject || 'Dragged Email Content',
      date: dateStr || new Date().toLocaleString(),
      body: body,
      rawContent: textContent,
      matchedBorrower,
      matchedLoanNumber: loanMatch ? loanMatch[1] : null,
      confidence: Math.min(confidence, 95),
    };
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

  // Check if the drag contains valid droppable content
  const isValidDrag = useCallback((e) => {
    const types = Array.from(e.dataTransfer.types);
    return types.includes('Files') ||
           types.includes('text/html') ||
           types.includes('text/plain') ||
           types.includes('text/uri-list');
  }, []);

  const handleDragEnter = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();

    // Increment counter for nested elements
    dragCounterRef.current++;

    // Check if dragging files OR email content (text/html from email clients)
    const types = Array.from(e.dataTransfer.types);
    console.log('DragEnter - types:', types, 'counter:', dragCounterRef.current);

    if (isValidDrag(e)) {
      setIsDragging(true);
    }
  }, [isValidDrag]);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();

    // Decrement counter
    dragCounterRef.current--;
    console.log('DragLeave - counter:', dragCounterRef.current);

    // Only hide when we've left all nested elements
    if (dragCounterRef.current === 0) {
      setIsDragging(false);
    }
  }, []);

  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    // Set dropEffect to show it's droppable
    e.dataTransfer.dropEffect = 'copy';
  }, []);

  const handleDrop = useCallback(async (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    dragCounterRef.current = 0; // Reset counter

    // Log what we received for debugging
    console.log('Drop event - types:', e.dataTransfer.types);
    console.log('Drop event - files:', e.dataTransfer.files.length);

    const files = Array.from(e.dataTransfer.files);

    // First, check for dragged email content (from Outlook, Gmail, etc.)
    // This happens when dragging directly from email client
    if (files.length === 0) {
      // Try to get text/html or text/plain content
      let content = '';
      let contentType = '';

      if (e.dataTransfer.types.includes('text/html')) {
        content = e.dataTransfer.getData('text/html');
        contentType = 'html';
      } else if (e.dataTransfer.types.includes('text/plain')) {
        content = e.dataTransfer.getData('text/plain');
        contentType = 'text';
      } else if (e.dataTransfer.types.includes('text/uri-list')) {
        content = e.dataTransfer.getData('text/uri-list');
        contentType = 'uri';
      }

      console.log('Drag content type:', contentType, 'Content length:', content?.length);

      if (content && content.length > 20) {
        setParsing(true);
        try {
          // Parse the dragged content as email
          const parsed = parseEmailFromDragContent(content, contentType);
          setEmailData(parsed);

          // Try AI parsing
          try {
            const aiResult = await emailDropAPI.parse(parsed);
            setAiParseResult(aiResult);
            if (aiResult.success) {
              parsed.aiExtractedFields = aiResult.extracted_fields;
              parsed.aiConfidenceScores = aiResult.confidence_scores;
              parsed.aiSuggestedAction = aiResult.suggested_action;
              parsed.aiQuestions = aiResult.questions;
              parsed.aiSummary = aiResult.ai_summary;
              parsed.matchedEntities = aiResult.matched_entities;
            }
          } catch (aiError) {
            console.warn('AI parsing failed:', aiError);
          }

          setShowChoiceModal(true);
        } catch (error) {
          console.error('Failed to parse dragged content:', error);
          alert('Could not parse this email. Try saving it as a .eml file first and then drag that file.');
        }
        setParsing(false);
        return;
      }

      // No valid content found
      alert('No valid file or email content detected. Try:\n1. Save the email as .eml file and drag that\n2. Or copy/paste the email content');
      return;
    }

    const file = files[0];
    console.log('File dropped:', file.name, file.type, file.size);

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

    // Try to parse as text email anyway (for .txt or unknown files)
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

  // Keep the ref updated for the global drop handler
  useEffect(() => {
    handleDropRef.current = handleDrop;
  }, [handleDrop]);

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

      {/* Drag Overlay - captures drop events when visible */}
      {isDragging && (
        <div
          className="email-drop-overlay"
          onDragOver={handleDragOver}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
        >
          <div className="email-drop-content">
            <div className="email-drop-icon">📧📄</div>
            <h2>Drop Here</h2>
            <p>Drag emails from Outlook/Gmail, .eml files, or documents to import</p>
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

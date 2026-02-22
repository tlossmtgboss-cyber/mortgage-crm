import React, { useState, useCallback, useEffect, useRef } from 'react';
import EmailReconciliationModal from './EmailReconciliationModal';
import DocumentDropModal from './DocumentDropModal';
import { emailDropAPI, documentDropAPI } from '../services/api';
import './EmailDropZone.css';
import { toast } from '../utils/toast';

/**
 * EmailDropZone - Drag and drop component for email and document files
 * Wraps children and provides drag-drop overlay
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

  // Ref to track drag counter persistently
  const dragCounterRef = useRef(0);

  // Ref to store the current processDropEvent function
  const processDropEventRef = useRef(null);

  // Set up global drag listeners on mount - ONLY ONCE
  useEffect(() => {
    // Check if the target or any of its parents has a local drop handler
    const hasLocalDropZone = (element) => {
      while (element) {
        if (element.classList?.contains('upload-zone') ||
            element.classList?.contains('local-drop-zone') ||
            element.dataset?.localDrop === 'true') {
          return true;
        }
        element = element.parentElement;
      }
      return false;
    };

    const handleDragEnter = (e) => {
      // Check if this is an internal drag (element being dragged within the page)
      // Internal drags typically have 'text/html' without 'Files'
      const types = e.dataTransfer?.types ? Array.from(e.dataTransfer.types) : [];

      // Only show overlay for external file drops, not internal drag-and-drop
      // External drops have 'Files' type, internal drags have text/html or text/plain
      const hasFiles = types.includes('Files');
      const isInternalDrag = !hasFiles && (types.includes('text/html') || types.includes('text/plain'));

      // If it's an internal drag (like reordering rows), don't intercept
      if (isInternalDrag) {
        console.log('[EmailDropZone] Ignoring internal drag - types:', types);
        return;
      }

      // Don't intercept if target has its own drop handler (like estimate upload zones)
      if (hasLocalDropZone(e.target)) {
        console.log('[EmailDropZone] Ignoring - target has local drop zone');
        return;
      }

      e.preventDefault();
      e.stopPropagation();
      dragCounterRef.current++;

      console.log('[EmailDropZone] DragEnter - counter:', dragCounterRef.current, 'types:', types);

      // Show overlay on first drag enter
      if (dragCounterRef.current === 1) {
        console.log('[EmailDropZone] Showing overlay');
        setIsDragging(true);
      }
    };

    const handleDragLeave = (e) => {
      // Only handle if we're tracking this drag (counter > 0)
      if (dragCounterRef.current === 0) {
        return; // This was an internal drag we're not tracking
      }

      e.preventDefault();
      e.stopPropagation();
      dragCounterRef.current--;

      console.log('[EmailDropZone] DragLeave - counter:', dragCounterRef.current);

      // Hide when fully left
      if (dragCounterRef.current <= 0) {
        dragCounterRef.current = 0;
        console.log('[EmailDropZone] Hiding overlay');
        setIsDragging(false);
      }
    };

    const handleDragOver = (e) => {
      // Only intercept if we're tracking a drag (counter > 0)
      if (dragCounterRef.current === 0) {
        return; // This is an internal drag we're not handling
      }

      // MUST prevent default to allow drop
      e.preventDefault();
      e.stopPropagation();

      // Set drop effect
      if (e.dataTransfer) {
        e.dataTransfer.dropEffect = 'copy';
      }
    };

    const handleDrop = (e) => {
      // Don't intercept if target has its own drop handler
      if (hasLocalDropZone(e.target)) {
        console.log('[EmailDropZone] Drop ignored - target has local drop zone');
        dragCounterRef.current = 0;
        setIsDragging(false);
        return; // Let the local handler process it
      }

      // Only handle if we're tracking this drag (counter > 0)
      if (dragCounterRef.current === 0) {
        return; // This was an internal drag we didn't intercept
      }

      e.preventDefault();
      e.stopPropagation();

      const files = e.dataTransfer?.files;
      const types = e.dataTransfer?.types ? Array.from(e.dataTransfer.types) : [];
      console.log('[EmailDropZone] Drop - files:', files?.length, 'types:', types);

      // Reset state
      dragCounterRef.current = 0;
      setIsDragging(false);

      // Process the drop using the ref to get the latest function
      if (processDropEventRef.current) {
        processDropEventRef.current(e);
      }
    };

    // Also prevent default on window to stop browser from opening file
    const handleWindowDragOver = (e) => {
      e.preventDefault();
    };

    const handleWindowDrop = (e) => {
      // Only prevent if not handled by document handler
      if (dragCounterRef.current === 0) {
        e.preventDefault();
      }
    };

    // Add listeners to document
    document.addEventListener('dragenter', handleDragEnter, true);
    document.addEventListener('dragleave', handleDragLeave, true);
    document.addEventListener('dragover', handleDragOver, true);
    document.addEventListener('drop', handleDrop, true);

    // Also add to window for extra coverage
    window.addEventListener('dragover', handleWindowDragOver, false);
    window.addEventListener('drop', handleWindowDrop, false);

    console.log('[EmailDropZone] *** Drag listeners ATTACHED ***');

    return () => {
      document.removeEventListener('dragenter', handleDragEnter, true);
      document.removeEventListener('dragleave', handleDragLeave, true);
      document.removeEventListener('dragover', handleDragOver, true);
      document.removeEventListener('drop', handleDrop, true);
      window.removeEventListener('dragover', handleWindowDragOver, false);
      window.removeEventListener('drop', handleWindowDrop, false);
      console.log('[EmailDropZone] Drag listeners removed');
    };
  }, []); // Empty dependency array - only run once on mount

  // Process the drop event
  const processDropEvent = useCallback(async (e) => {
    const files = Array.from(e.dataTransfer?.files || []);

    // First check for files
    if (files.length > 0) {
      const file = files[0];
      console.log('[Drop] Processing file:', file.name, file.type, file.size);

      // Check if it's an email file
      if (isEmailFile(file)) {
        await handleEmailFile(file);
        return;
      }

      // Check if it's a document file
      if (isDocumentFile(file)) {
        setDocumentFile(file);
        setShowDocumentModal(true);
        return;
      }

      // Try to parse as text anyway
      await handleEmailFile(file);
      return;
    }

    // No files - check for dragged text/html content
    const types = Array.from(e.dataTransfer?.types || []);
    let content = '';
    let contentType = '';

    if (types.includes('text/html')) {
      content = e.dataTransfer.getData('text/html');
      contentType = 'html';
    } else if (types.includes('text/plain')) {
      content = e.dataTransfer.getData('text/plain');
      contentType = 'text';
    }

    console.log('[Drop] Content type:', contentType, 'length:', content?.length);

    if (content && content.length > 20) {
      await handleDraggedContent(content, contentType);
    } else {
      toast.error('No valid file or email content detected. Try:\n1. Save the email as .eml file and drag that\n2. Or copy/paste the email content');
    }
  }, []);

  // Keep the ref updated with the latest processDropEvent function
  useEffect(() => {
    processDropEventRef.current = processDropEvent;
  }, [processDropEvent]);

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

  // Handle email file
  const handleEmailFile = async (file) => {
    setParsing(true);
    try {
      const content = await readFileAsText(file);
      const parsed = parseEmailContent(content, file.name);
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
      console.error('Failed to parse email:', error);
      toast.error('Failed to parse email file. Please try again.');
    }
    setParsing(false);
  };

  // Handle dragged content (from Outlook/Gmail)
  const handleDraggedContent = async (content, contentType) => {
    setParsing(true);
    try {
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
      toast.error('Could not parse this email. Try saving it as a .eml file first.');
    }
    setParsing(false);
  };

  // Read file as text
  const readFileAsText = (file) => {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = (e) => resolve(e.target.result);
      reader.onerror = reject;
      reader.readAsText(file);
    });
  };

  // Parse email content from raw text
  const parseEmailContent = (content, filename) => {
    const fromMatch = content.match(/^From:\s*(.+)$/mi);
    const toMatch = content.match(/^To:\s*(.+)$/mi);
    const subjectMatch = content.match(/^Subject:\s*(.+)$/mi);
    const dateMatch = content.match(/^Date:\s*(.+)$/mi);

    const bodyStart = content.indexOf('\n\n');
    let body = bodyStart > -1 ? content.substring(bodyStart + 2) : content;

    if (body.includes('<html') || body.includes('<HTML')) {
      body = body.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
    }

    const borrowerPatterns = [
      /(?:borrower|client|customer):\s*([A-Z][a-z]+\s+[A-Z][a-z]+)/i,
      /(?:Dear|Hi|Hello)\s+([A-Z][a-z]+)/i,
    ];

    let matchedBorrower = null;
    for (const pattern of borrowerPatterns) {
      const match = content.match(pattern);
      if (match) {
        matchedBorrower = match[1];
        break;
      }
    }

    const loanMatch = content.match(/(?:loan\s*#?|loan\s*number)[\s:]*([A-Z0-9-]+)/i);

    let confidence = 45;
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
      body: body.substring(0, 2000),
      rawContent: content,
      matchedBorrower,
      matchedLoanNumber: loanMatch ? loanMatch[1] : null,
      confidence: Math.min(confidence, 95),
    };
  };

  // Parse email from dragged HTML/text content
  const parseEmailFromDragContent = (content, contentType) => {
    let textContent = content;
    let fromAddress = '';
    let toAddress = '';
    let subject = '';
    let dateStr = '';
    let body = '';

    if (contentType === 'html') {
      const tempDiv = document.createElement('div');
      tempDiv.innerHTML = content;
      const allText = tempDiv.textContent || tempDiv.innerText;
      textContent = allText;

      const fromMatch = content.match(/From:?\s*<?([^<>\n\r]+@[^<>\n\r]+)>?/i);
      const toMatch = content.match(/To:?\s*<?([^<>\n\r]+@[^<>\n\r]+)>?/i);
      const subjectMatch = content.match(/Subject:?\s*([^\n\r<]+)/i);
      const dateMatch = content.match(/Date:?\s*([^\n\r<]+)/i);

      fromAddress = fromMatch ? fromMatch[1].trim() : '';
      toAddress = toMatch ? toMatch[1].trim() : '';
      subject = subjectMatch ? subjectMatch[1].trim() : '';
      dateStr = dateMatch ? dateMatch[1].trim() : '';
      body = allText.substring(0, 3000);
    } else {
      const fromMatch = textContent.match(/From:\s*(.+)/i);
      const toMatch = textContent.match(/To:\s*(.+)/i);
      const subjectMatch = textContent.match(/Subject:\s*(.+)/i);
      const dateMatch = textContent.match(/Date:\s*(.+)/i);

      fromAddress = fromMatch ? fromMatch[1].trim() : '';
      toAddress = toMatch ? toMatch[1].trim() : '';
      subject = subjectMatch ? subjectMatch[1].trim() : '';
      dateStr = dateMatch ? dateMatch[1].trim() : '';

      const bodyStart = textContent.search(/\n\n|\r\n\r\n/);
      body = bodyStart > -1 ? textContent.substring(bodyStart + 2, bodyStart + 3000) : textContent.substring(0, 3000);
    }

    const emailMatch = fromAddress.match(/[\w\.-]+@[\w\.-]+\.\w+/);
    if (emailMatch) {
      fromAddress = emailMatch[0];
    }

    const borrowerPatterns = [
      /(?:borrower|client|customer):\s*([A-Z][a-z]+\s+[A-Z][a-z]+)/i,
      /(?:Dear|Hi|Hello)\s+([A-Z][a-z]+)/i,
    ];

    let matchedBorrower = null;
    for (const pattern of borrowerPatterns) {
      const match = textContent.match(pattern);
      if (match) {
        matchedBorrower = match[1];
        break;
      }
    }

    const loanMatch = textContent.match(/(?:loan\s*#?|loan\s*number)[\s:]*([A-Z0-9-]+)/i);

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

  // Choice handlers
  const handleChoiceDocument = () => {
    setShowChoiceModal(false);
    setShowReconciliationModal(true);
  };

  const handleChoiceLead = () => {
    setShowChoiceModal(false);
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
      const result = await emailDropAPI.process(
        action,
        emailData,
        data.extractedFields || emailData.aiExtractedFields || {},
        data.matchedEntity?.data?.id?.toString(),
        data.matchedEntity?.type,
        !data.matchedEntity,
        data.userAnswers || {}
      );
      if (result.success) {
        toast.success(`Success! ${result.message}`);
      } else {
        toast.warning(`Warning: ${result.message}`);
      }
    } catch (error) {
      console.error('Failed to process email:', error);
      toast.error('Failed to process email. Please try again.');
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
    toast.success(`Document uploaded successfully!`);
  };

  return (
    <div className="email-drop-zone-wrapper">
      {children}

      {/* Drag Overlay */}
      {isDragging && (
        <div className="email-drop-overlay">
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
          <div className="email-choice-modal email-choice-modal-expanded" onClick={e => e.stopPropagation()}>
            <div className="email-choice-header">
              <h2>Email Imported</h2>
              <button className="close-btn" onClick={() => setShowChoiceModal(false)}>×</button>
            </div>

            <div className="email-choice-content">
              {/* Left Column - Email Details */}
              <div className="email-details-column">
                <div className="email-preview">
                  <div className="email-preview-row">
                    <span className="label">From:</span>
                    <span className="value">{emailData.from}</span>
                  </div>
                  {emailData.to && (
                    <div className="email-preview-row">
                      <span className="label">To:</span>
                      <span className="value">{emailData.to}</span>
                    </div>
                  )}
                  <div className="email-preview-row">
                    <span className="label">Subject:</span>
                    <span className="value">{emailData.subject}</span>
                  </div>
                  <div className="email-preview-row">
                    <span className="label">Date:</span>
                    <span className="value">{emailData.date}</span>
                  </div>
                </div>

                {/* AI Analysis Section */}
                <div className="ai-analysis-section">
                  {emailData.aiSummary && (
                    <div className="ai-analysis-row">
                      <span className="ai-label">AI Summary:</span>
                      <span className="ai-value">{emailData.aiSummary}</span>
                    </div>
                  )}
                  {emailData.aiSuggestedAction && (
                    <div className="ai-analysis-row suggestion">
                      <span className="ai-label">AI Suggests:</span>
                      <span className="ai-value suggested-action">{emailData.aiSuggestedAction.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}</span>
                    </div>
                  )}
                  {emailData.matchedBorrower && (
                    <div className="ai-analysis-row">
                      <span className="ai-label">Matched Borrower:</span>
                      <span className="ai-value">{emailData.matchedBorrower}</span>
                    </div>
                  )}
                  {emailData.matchedLoanNumber && (
                    <div className="ai-analysis-row">
                      <span className="ai-label">Loan Number:</span>
                      <span className="ai-value">{emailData.matchedLoanNumber}</span>
                    </div>
                  )}
                  {emailData.aiExtractedFields && Object.keys(emailData.aiExtractedFields).length > 0 && (
                    <div className="ai-extracted-fields">
                      <span className="ai-label">Extracted Fields:</span>
                      <div className="extracted-fields-list">
                        {Object.entries(emailData.aiExtractedFields).map(([key, value]) => (
                          value && (
                            <div key={key} className="extracted-field">
                              <span className="field-key">{key.replace(/_/g, ' ')}:</span>
                              <span className="field-value">{String(value)}</span>
                            </div>
                          )
                        ))}
                      </div>
                    </div>
                  )}
                  <div className="ai-analysis-row confidence">
                    <span className="ai-label">Confidence:</span>
                    <span className={`confidence-badge ${emailData.confidence > 70 ? 'high' : emailData.confidence > 40 ? 'medium' : 'low'}`}>
                      {emailData.confidence}%
                    </span>
                  </div>
                </div>

                {/* Email Body Preview */}
                <div className="email-body-section">
                  <span className="section-label">Email Body:</span>
                  <div className="email-body-preview">
                    <pre>{emailData.body || '(No body content)'}</pre>
                  </div>
                </div>
              </div>

              {/* Right Column - Actions */}
              <div className="email-actions-column">
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

                {/* AI Auto-Execute Option */}
                <div className="ai-auto-execute-section">
                  <div className="auto-execute-header">
                    <span className="auto-icon">🤖</span>
                    <span className="auto-title">AI Automation</span>
                  </div>
                  <label className="auto-execute-checkbox">
                    <input
                      type="checkbox"
                      checked={emailData.autoExecuteEnabled || false}
                      onChange={(e) => {
                        setEmailData(prev => ({ ...prev, autoExecuteEnabled: e.target.checked }));
                      }}
                    />
                    <span className="checkbox-label">
                      Let AI automatically handle similar emails in the future
                    </span>
                  </label>
                  {emailData.autoExecuteEnabled && (
                    <div className="auto-execute-note">
                      AI will automatically {emailData.aiSuggestedAction?.replace(/_/g, ' ') || 'process'} emails matching this pattern without prompting.
                    </div>
                  )}
                </div>
              </div>
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

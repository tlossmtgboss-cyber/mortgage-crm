/**
 * ApplicantTasks Component
 *
 * Displays tasks for applicants to complete in the portal.
 * Includes lightbox modals for:
 * - 7 Step Process
 * - Bullet Proof Buyer
 * - Documents Needed
 *
 * Features:
 * - Sound notification on new tasks
 * - Task completion tracking via localStorage
 * - Lightbox modals for task content
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './ApplicantTasks.css';

// Sound notification hook
const useTaskNotification = (tasks, hasNewTasks) => {
  const audioRef = useRef(null);
  const hasPlayedRef = useRef(false);

  useEffect(() => {
    // Only play sound once per session when there are incomplete tasks
    if (hasNewTasks && !hasPlayedRef.current && tasks.length > 0) {
      const incompleteTasks = tasks.filter(t => !t.completed);
      if (incompleteTasks.length > 0) {
        try {
          if (!audioRef.current) {
            audioRef.current = new Audio('/sounds/youve-got-mail-sound.mp3');
            audioRef.current.volume = 0.5;
          }
          audioRef.current.play().catch(err => {
            console.log('Audio autoplay blocked:', err);
          });
          hasPlayedRef.current = true;
        } catch (err) {
          console.log('Audio not available:', err);
        }
      }
    }
  }, [tasks, hasNewTasks]);
};

// Lightbox Modal Component
const LightboxModal = ({ isOpen, onClose, title, children }) => {
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  if (!isOpen) return null;

  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <div className="lightbox-content" onClick={e => e.stopPropagation()}>
        <div className="lightbox-header">
          <h2>{title}</h2>
          <button className="lightbox-close" onClick={onClose}>×</button>
        </div>
        <div className="lightbox-body">
          {children}
        </div>
      </div>
    </div>
  );
};

// 7 Step Process Content
const SevenStepProcessContent = () => (
  <div className="seven-step-process">
    <div className="process-hero">
      <h2>How to Borrow Money: The 7 Steps</h2>
      <p className="process-tagline">
        Borrowing money isn't just about getting approved—it's about making sure the money you borrow actually improves your life.
      </p>
    </div>

    <p className="process-intro">
      <strong>How to Borrow Money: The 7 Steps</strong> is the proven framework I use to help clients make smarter borrowing decisions that support cash flow, reduce stress, and build long-term wealth. This goes far beyond what most lenders offer, because it treats your mortgage as a financial strategy—not a transaction.
    </p>

    <div className="process-callout">
      <p><strong>You're not here just to get a loan.</strong></p>
      <p>You're here to make a good decision.</p>
    </div>

    <div className="process-section">
      <h3>Why This Matters for You</h3>
      <p>Most lenders focus almost exclusively on numbers:</p>
      <ul className="simple-list">
        <li>Income</li>
        <li>Assets</li>
        <li>Credit</li>
        <li>Property</li>
      </ul>
      <p>Those details matter—but they don't tell the full story.</p>
      <p>This 7-step process is designed to help you:</p>
      <ul>
        <li>Borrow with confidence</li>
        <li>Protect your liquidity</li>
        <li>Align your mortgage with your long-term goals</li>
        <li>Adjust as your life and opportunities change</li>
      </ul>
      <p className="highlight-text">
        We'll focus deeply on <strong>Steps 1–4</strong> right now to structure your loan correctly. Then we'll map out <strong>Steps 5–7</strong> so this decision keeps working for you long after closing—something most lenders never revisit.
      </p>
    </div>

    <div className="process-section">
      <h3>The 7 Steps to Borrowing Money the Right Way</h3>
      <p>This process is built around thoughtful questions, not pressure, so your mortgage fits your priorities.</p>
    </div>

    <div className="process-steps">
      <div className="process-step primary-step">
        <div className="step-number">1</div>
        <div className="step-content">
          <h3>Safety</h3>
          <p className="step-question">What does financial safety mean to you?</p>
          <p>We start by understanding your comfort level with risk, stability, and monthly obligations—so your loan feels secure, not restrictive.</p>
        </div>
      </div>

      <div className="process-step primary-step">
        <div className="step-number">2</div>
        <div className="step-content">
          <h3>Liquidity</h3>
          <p className="step-question">How important is access to cash?</p>
          <p>We protect your cash flow and flexibility, because borrowing shouldn't trap your money or limit your options.</p>
        </div>
      </div>

      <div className="process-step primary-step">
        <div className="step-number">3</div>
        <div className="step-content">
          <h3>Growth & Return</h3>
          <p className="step-question">What do you want this home to do for you financially?</p>
          <p>Whether this is a lifestyle decision, an investment, or both, we align your borrowing with your bigger financial picture.</p>
        </div>
      </div>

      <div className="process-step primary-step">
        <div className="step-number">4</div>
        <div className="step-content">
          <h3>Optimize the Borrowing</h3>
          <p className="step-question">This is where structure matters most.</p>
          <p>We design the loan around rates, terms, and payment strategy to create the best real-world outcome—not just the lowest headline rate.</p>
        </div>
      </div>
    </div>

    <div className="process-divider">
      <h3>What Most Lenders Never Cover (But We Do)</h3>
      <p>Borrowing doesn't stop at closing—and neither do we.</p>
    </div>

    <div className="process-steps secondary-steps">
      <div className="process-step secondary-step">
        <div className="step-number">5</div>
        <div className="step-content">
          <h3>Repay Smart</h3>
          <p>We create strategies to reduce interest and accelerate payoff, often tied to life events like income growth or retirement.</p>
        </div>
      </div>

      <div className="process-step secondary-step">
        <div className="step-number">6</div>
        <div className="step-content">
          <h3>Protect Wealth</h3>
          <p>Your equity is valuable. We help you think through protection strategies so one unexpected event doesn't undo years of progress.</p>
        </div>
      </div>

      <div className="process-step secondary-step">
        <div className="step-number">7</div>
        <div className="step-content">
          <h3>Review & Adjust</h3>
          <p>Life changes. Markets change. That's why we schedule ongoing reviews to refine your strategy, explore refinance opportunities, and keep your plan optimized over time.</p>
        </div>
      </div>
    </div>

    <div className="process-summary">
      <h3>What This Means for You</h3>
      <div className="summary-table">
        <div className="summary-row header">
          <div className="summary-cell">Your Focus</div>
          <div className="summary-cell">What We Do Now</div>
          <div className="summary-cell">Long-Term Advantage</div>
        </div>
        <div className="summary-row">
          <div className="summary-cell"><strong>Steps 1–4: Borrow Smart</strong></div>
          <div className="summary-cell">Design the right loan today</div>
          <div className="summary-cell">Clarity, confidence, and immediate savings</div>
        </div>
        <div className="summary-row">
          <div className="summary-cell"><strong>Steps 5–7: Repay & Protect</strong></div>
          <div className="summary-cell">Strategic roadmap</div>
          <div className="summary-cell">Ongoing optimization most lenders never offer</div>
        </div>
      </div>
    </div>

    <div className="process-footer">
      <p><strong>This isn't about one loan—it's about borrowing money well, consistently, over your lifetime.</strong></p>
    </div>
  </div>
);

// Bullet Proof Buyer Content
const BulletProofBuyerContent = () => (
  <div className="bullet-proof-buyer">
    <p className="buyer-intro">
      Become a Bullet Proof Buyer and stand out from the competition. Here's how to make your offer irresistible to sellers:
    </p>

    <div className="buyer-sections">
      <div className="buyer-section">
        <div className="section-icon">🎯</div>
        <h3>Get Fully Pre-Approved</h3>
        <p>A pre-qualification is good, but a full pre-approval is better. We'll verify your income, assets, and credit upfront so there are no surprises.</p>
        <ul>
          <li>Submit all required documents early</li>
          <li>Get credit issues resolved before shopping</li>
          <li>Know your exact buying power</li>
        </ul>
      </div>

      <div className="buyer-section">
        <div className="section-icon">📋</div>
        <h3>Be Document-Ready</h3>
        <p>Have your complete financial package ready before making an offer. This shows sellers you mean business.</p>
        <ul>
          <li>2 years of tax returns</li>
          <li>Recent pay stubs (30 days)</li>
          <li>2 months of bank statements</li>
          <li>Valid ID and Social Security</li>
        </ul>
      </div>

      <div className="buyer-section">
        <div className="section-icon">💪</div>
        <h3>Strengthen Your Offer</h3>
        <p>In competitive markets, being bullet proof can make the difference.</p>
        <ul>
          <li>Larger earnest money deposit shows commitment</li>
          <li>Flexible closing date accommodates sellers</li>
          <li>Clean offer with minimal contingencies</li>
          <li>Personal letter can create emotional connection</li>
        </ul>
      </div>

      <div className="buyer-section">
        <div className="section-icon">⚡</div>
        <h3>Stay Responsive</h3>
        <p>Speed matters in real estate. Be ready to act quickly throughout the process.</p>
        <ul>
          <li>Check messages and emails daily</li>
          <li>Respond to document requests within 24 hours</li>
          <li>Keep your schedule flexible for inspections and appraisals</li>
          <li>Have your loan officer on speed dial</li>
        </ul>
      </div>
    </div>

    <div className="buyer-checklist">
      <h4>✅ Bullet Proof Buyer Checklist</h4>
      <div className="checklist-grid">
        <label><input type="checkbox" /> Full pre-approval letter in hand</label>
        <label><input type="checkbox" /> All documents submitted and verified</label>
        <label><input type="checkbox" /> Credit score optimized</label>
        <label><input type="checkbox" /> Down payment funds verified</label>
        <label><input type="checkbox" /> Gift letters prepared (if applicable)</label>
        <label><input type="checkbox" /> Emergency fund established</label>
      </div>
    </div>
  </div>
);

// Documents Needed Content
const DocumentsNeededContent = ({ documentRequirements, conditions, onUpload, uploading }) => {
  // Combine document requirements and conditions
  const allDocs = [];

  // Add document requirements
  if (documentRequirements && documentRequirements.length > 0) {
    documentRequirements.forEach(doc => {
      allDocs.push({
        id: `doc_${doc.id}`,
        name: doc.name || doc.document_type,
        description: doc.description || getDocumentDescription(doc.document_type),
        category: doc.category,
        status: doc.status || 'pending',
        type: 'requirement'
      });
    });
  }

  // Add conditions as documents
  if (conditions && conditions.length > 0) {
    conditions.forEach(cond => {
      if (cond.status === 'pending') {
        allDocs.push({
          id: `cond_${cond.id}`,
          conditionId: cond.id,
          name: cond.name,
          description: cond.description || getConditionDescription(cond.category),
          category: cond.category,
          status: cond.status,
          type: 'condition'
        });
      }
    });
  }

  // Group by category
  const groupedDocs = allDocs.reduce((acc, doc) => {
    const cat = doc.category || 'other';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(doc);
    return acc;
  }, {});

  const categoryLabels = {
    income_verification: 'Income Verification',
    asset_verification: 'Asset Verification',
    employment: 'Employment',
    property: 'Property',
    credit: 'Credit',
    identity: 'Identity',
    other: 'Other Documents'
  };

  return (
    <div className="documents-needed">
      <p className="docs-intro">
        Upload the following documents to keep your loan moving forward.
        Click the upload button next to each document to submit.
      </p>

      {Object.keys(groupedDocs).length === 0 ? (
        <div className="no-docs-needed">
          <div className="no-docs-icon">✓</div>
          <h3>No Documents Currently Needed</h3>
          <p>You're all caught up! We'll notify you if any additional documents are required.</p>
        </div>
      ) : (
        <div className="docs-categories">
          {Object.entries(groupedDocs).map(([category, docs]) => (
            <div key={category} className="docs-category">
              <h3>{categoryLabels[category] || category}</h3>
              <div className="docs-list">
                {docs.map(doc => (
                  <div key={doc.id} className={`doc-item status-${doc.status}`}>
                    <div className="doc-info">
                      <div className="doc-name">{doc.name}</div>
                      <div className="doc-description">{doc.description}</div>
                    </div>
                    <div className="doc-actions">
                      {doc.status === 'pending' ? (
                        <label className="upload-doc-btn">
                          <input
                            type="file"
                            onChange={(e) => onUpload(doc.conditionId || doc.id, e)}
                            disabled={uploading}
                            accept=".pdf,.jpg,.jpeg,.png,.doc,.docx"
                          />
                          {uploading ? 'Uploading...' : '📤 Upload'}
                        </label>
                      ) : doc.status === 'received' ? (
                        <span className="doc-status-badge pending">Under Review</span>
                      ) : doc.status === 'approved' ? (
                        <span className="doc-status-badge approved">✓ Approved</span>
                      ) : (
                        <span className="doc-status-badge">{doc.status}</span>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="docs-tips">
        <h4>📝 Document Tips</h4>
        <ul>
          <li>PDF format is preferred for all documents</li>
          <li>Ensure all pages are legible and complete</li>
          <li>Include all pages of multi-page documents</li>
          <li>Bank statements should show your name, account number, and date</li>
        </ul>
      </div>
    </div>
  );
};

// Helper function to get document descriptions
function getDocumentDescription(docType) {
  const descriptions = {
    paystubs: 'Most recent 30 days of pay stubs showing year-to-date earnings',
    w2: 'W-2 forms from the past 2 years from all employers',
    tax_returns: 'Complete federal tax returns (all pages and schedules) for the past 2 years',
    bank_statements: '2 months of complete bank statements for all accounts',
    '1099': '1099 forms for any additional income sources',
    drivers_license: 'Valid government-issued photo ID (front and back)',
    social_security: 'Social Security card or verification letter',
    default: 'Required document for your loan application'
  };
  return descriptions[docType] || descriptions.default;
}

// Helper function to get condition descriptions
function getConditionDescription(category) {
  const descriptions = {
    income_verification: 'Document needed to verify your income',
    asset_verification: 'Document needed to verify your assets',
    employment: 'Document needed to verify your employment',
    property: 'Document related to the property',
    credit: 'Document related to your credit',
    default: 'Document needed to process your loan'
  };
  return descriptions[category] || descriptions.default;
}

// Main ApplicantTasks Component
export default function ApplicantTasks({
  workspaceId,
  conditions = [],
  documentRequirements = [],
  onUploadForCondition,
  uploading,
  onTaskComplete
}) {
  // State for lightbox modals
  const [showSevenStep, setShowSevenStep] = useState(false);
  const [showBulletProof, setShowBulletProof] = useState(false);
  const [showDocuments, setShowDocuments] = useState(false);

  // State for task completion (persisted to localStorage)
  const storageKey = `applicant_tasks_${workspaceId}`;
  const [completedTasks, setCompletedTasks] = useState(() => {
    try {
      const saved = localStorage.getItem(storageKey);
      return saved ? JSON.parse(saved) : {};
    } catch {
      return {};
    }
  });

  // Check if this is first visit
  const [isFirstVisit, setIsFirstVisit] = useState(() => {
    const visitKey = `portal_visited_${workspaceId}`;
    const visited = localStorage.getItem(visitKey);
    if (!visited) {
      localStorage.setItem(visitKey, 'true');
      return true;
    }
    return false;
  });

  // Define the applicant tasks
  const applicantTasks = [
    {
      id: 'seven_step_process',
      title: 'Read the 7 Step Process',
      description: 'Learn about each step of your mortgage journey',
      icon: '📋',
      onClick: () => setShowSevenStep(true),
      completed: completedTasks['seven_step_process'] || false
    },
    {
      id: 'bullet_proof_buyer',
      title: 'Be a Bullet Proof Buyer',
      description: 'Tips to make your offer stand out',
      icon: '🛡️',
      onClick: () => setShowBulletProof(true),
      completed: completedTasks['bullet_proof_buyer'] || false
    },
    {
      id: 'review_documents',
      title: 'Review Documents Needed',
      description: 'See what documents you need to upload',
      icon: '📁',
      onClick: () => setShowDocuments(true),
      completed: completedTasks['review_documents'] || false
    }
  ];

  // Count incomplete tasks
  const incompleteTasks = applicantTasks.filter(t => !t.completed);
  const hasNewTasks = incompleteTasks.length > 0;

  // Play sound notification on first visit with tasks
  useTaskNotification(applicantTasks, isFirstVisit);

  // Save completed tasks to localStorage
  useEffect(() => {
    try {
      localStorage.setItem(storageKey, JSON.stringify(completedTasks));
    } catch {
      // Ignore storage errors
    }
  }, [completedTasks, storageKey]);

  // Mark task as completed when lightbox is closed
  const handleCloseLightbox = useCallback((taskId, setter) => {
    setter(false);
    if (!completedTasks[taskId]) {
      setCompletedTasks(prev => ({ ...prev, [taskId]: true }));
      onTaskComplete?.(taskId);
    }
  }, [completedTasks, onTaskComplete]);

  // If all tasks are completed, show "all caught up" message
  if (incompleteTasks.length === 0) {
    return (
      <section className="all-caught-up-section">
        <div className="caught-up-icon">✓</div>
        <h2>You're all caught up!</h2>
        <p>Your loan officer is reviewing your application. We'll notify you when there's something new.</p>
      </section>
    );
  }

  return (
    <>
      <section className="applicant-tasks-section">
        <div className="tasks-header">
          <h2>Your Action Items</h2>
          <span className="tasks-count">{incompleteTasks.length} items to complete</span>
        </div>

        <div className="applicant-tasks-list">
          {applicantTasks.map(task => (
            <div
              key={task.id}
              className={`applicant-task-card ${task.completed ? 'completed' : ''}`}
              onClick={task.onClick}
            >
              <div className="task-icon">{task.icon}</div>
              <div className="task-info">
                <div className="task-title">{task.title}</div>
                <div className="task-description">{task.description}</div>
              </div>
              <div className="task-status">
                {task.completed ? (
                  <span className="status-complete">✓ Done</span>
                ) : (
                  <span className="status-action">View →</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 7 Step Process Lightbox */}
      <LightboxModal
        isOpen={showSevenStep}
        onClose={() => handleCloseLightbox('seven_step_process', setShowSevenStep)}
        title="How to Borrow Money: The 7 Steps"
      >
        <SevenStepProcessContent />
      </LightboxModal>

      {/* Bullet Proof Buyer Lightbox */}
      <LightboxModal
        isOpen={showBulletProof}
        onClose={() => handleCloseLightbox('bullet_proof_buyer', setShowBulletProof)}
        title="Be a Bullet Proof Buyer"
      >
        <BulletProofBuyerContent />
      </LightboxModal>

      {/* Documents Needed Lightbox */}
      <LightboxModal
        isOpen={showDocuments}
        onClose={() => handleCloseLightbox('review_documents', setShowDocuments)}
        title="Documents Needed"
      >
        <DocumentsNeededContent
          documentRequirements={documentRequirements}
          conditions={conditions}
          onUpload={onUploadForCondition}
          uploading={uploading}
        />
      </LightboxModal>
    </>
  );
}

// Export lightbox component for toolbar links
export { LightboxModal, SevenStepProcessContent, BulletProofBuyerContent };

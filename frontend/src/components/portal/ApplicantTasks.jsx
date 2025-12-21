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
const LightboxModal = ({ isOpen, onClose, onComplete, title, children, showCompleteButton = false, isCompleted = false }) => {
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

  const handleComplete = () => {
    if (onComplete) {
      onComplete();
    }
    onClose();
  };

  return (
    <div className="lightbox-overlay" onClick={onClose}>
      <div className="lightbox-content" onClick={e => e.stopPropagation()}>
        <div className="lightbox-header">
          <h2>{title}</h2>
          <button className="lightbox-close" onClick={onClose}>×</button>
        </div>
        <div className="lightbox-body">
          {children}
          {showCompleteButton && (
            <div className="lightbox-complete-section">
              {isCompleted ? (
                <div className="task-already-complete">
                  <span className="complete-check">✓</span>
                  <span>You've completed this task</span>
                </div>
              ) : (
                <button className="complete-task-btn" onClick={handleComplete}>
                  ✓ I've Read This — Mark Complete
                </button>
              )}
            </div>
          )}
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
    <div className="buyer-hero">
      <h2>You've Made a Smart Move</h2>
      <p className="buyer-tagline">Welcome to Becoming a Bulletproof Buyer</p>
    </div>

    <p className="buyer-intro">
      Buying a home can feel overwhelming — especially in today's market. Multiple offers, fast timelines, confusing advice, and pressure to make big decisions quickly.
    </p>
    <p className="buyer-intro">
      That's exactly why you're here — and that's a good thing.
    </p>

    <div className="buyer-callout">
      <p><strong>A Bulletproof Buyer isn't someone who rushes or takes risks.</strong></p>
      <p>A Bulletproof Buyer is someone who is prepared, supported, and positioned to move forward with confidence.</p>
      <p className="callout-emphasis">And that's what we're building together.</p>
    </div>

    <div className="buyer-section-block">
      <h3>What Being a Bulletproof Buyer Really Means</h3>
      <p>In simple terms, being a Bulletproof Buyer means your financing is solid, your plan is clear, and there are no surprises waiting around the corner.</p>

      <div className="buyer-checklist-block">
        <p><strong>A Bulletproof Buyer:</strong></p>
        <ul className="check-list">
          <li>✅ Has financing that's truly ready — not just "pre-approved on paper"</li>
          <li>✅ Understands what they can do before they're in a stressful situation</li>
          <li>✅ Can move forward confidently when the right home appears</li>
          <li>✅ Feels calm knowing their loan is structured correctly from the start</li>
        </ul>
      </div>

      <p className="highlight-text">
        This isn't about pressure or perfection.<br/>
        <strong>It's about clarity, preparation, and peace of mind.</strong>
      </p>
      <p>When sellers review offers, they're not just looking at price — they're looking for certainty. And certainty comes from knowing the buyer is backed by a strong, well-prepared loan.</p>
    </div>

    <div className="buyer-section-block">
      <h3>Why Buyers Who Are Prepared Feel More at Ease</h3>

      <div className="ease-item">
        <h4>1. You Understand What's Happening — and Why</h4>
        <p>We take the time to explain how today's market works — pricing trends, demand, timelines, and expectations — so nothing feels confusing or rushed.</p>
        <p className="ease-highlight">When you understand the why, decisions feel lighter. You move forward thoughtfully instead of reactively.</p>
      </div>

      <div className="ease-item">
        <h4>2. You're Not Caught Off Guard by Appraisals</h4>
        <p>In competitive markets, appraisal questions are common — and stressful when no plan exists.</p>
        <p>As a Bulletproof Buyer, you already understand:</p>
        <ul>
          <li>How appraisals work</li>
          <li>What your options are</li>
          <li>What flexibility you may or may not need</li>
        </ul>
        <p className="ease-highlight">That preparation removes anxiety and replaces it with confidence.</p>
      </div>

      <div className="ease-item">
        <h4>3. Your Financing Has Real Strength Behind It</h4>
        <p>Many buyers carry a basic pre-approval. We go a step further by verifying income, assets, and credit early, so your approval isn't fragile.</p>
        <p><strong>That means:</strong></p>
        <ul className="checkmark-list">
          <li>✔ Fewer last-minute surprises</li>
          <li>✔ Clear expectations from day one</li>
          <li>✔ A smoother, more predictable path to closing</li>
        </ul>
        <p className="ease-highlight">This isn't about being aggressive — it's about being secure.</p>
      </div>

      <div className="ease-item">
        <h4>4. You Control the Timeline — Not the Other Way Around</h4>
        <p>Because we prepare your loan upfront, you're not scrambling later.</p>
        <p><strong>You can:</strong></p>
        <ul>
          <li>Move forward when you are ready</li>
          <li>Offer timelines with confidence</li>
          <li>Trust that the process won't unravel at the last minute</li>
        </ul>
        <p className="ease-highlight">Sellers appreciate that — but more importantly, you benefit from the calm that comes with readiness.</p>
      </div>
    </div>

    <div className="buyer-section-block highlight-section">
      <h3>Why You're in the Right Place</h3>
      <p>You didn't just apply for a loan — you chose a process designed to protect you.</p>

      <p><strong>Here's what makes this experience different:</strong></p>

      <div className="difference-item">
        <h4>✔ We Prepare — Not Just Approve</h4>
        <p>Your file is built carefully so it holds up under real-world conditions, not just ideal ones.</p>
      </div>

      <div className="difference-item">
        <h4>✔ You're Guided at Every Step</h4>
        <p>You'll always know what's needed, what's next, and why it matters.</p>
      </div>

      <div className="difference-item">
        <h4>✔ Confidence Replaces Stress</h4>
        <p>Instead of wondering if something will go wrong, you know you're supported by a clear plan.</p>
      </div>
    </div>

    <div className="buyer-summary">
      <h3>Your Bulletproof Advantage (At a Glance)</h3>
      <p>You're gaining:</p>
      <ul className="advantage-list">
        <li>🔹 Clear market guidance</li>
        <li>🔹 Appraisal preparedness</li>
        <li>🔹 Verified underwriting early in the process</li>
        <li>🔹 Strong, reliable approvals</li>
        <li>🔹 Fewer surprises and smoother closings</li>
        <li>🔹 Confidence that your financing is built to last</li>
      </ul>
      <p className="summary-emphasis"><strong>That's what being a Bulletproof Buyer truly means.</strong></p>
    </div>

    <div className="buyer-footer">
      <p><strong>And that's why you're exactly where you should be.</strong></p>
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

  // Mark task as completed (only via button click)
  const markTaskComplete = useCallback((taskId) => {
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
        onClose={() => setShowSevenStep(false)}
        onComplete={() => markTaskComplete('seven_step_process')}
        title="How to Borrow Money: The 7 Steps"
        showCompleteButton={true}
        isCompleted={completedTasks['seven_step_process'] || false}
      >
        <SevenStepProcessContent />
      </LightboxModal>

      {/* Bullet Proof Buyer Lightbox */}
      <LightboxModal
        isOpen={showBulletProof}
        onClose={() => setShowBulletProof(false)}
        onComplete={() => markTaskComplete('bullet_proof_buyer')}
        title="Be a Bullet Proof Buyer"
        showCompleteButton={true}
        isCompleted={completedTasks['bullet_proof_buyer'] || false}
      >
        <BulletProofBuyerContent />
      </LightboxModal>

      {/* Documents Needed Lightbox */}
      <LightboxModal
        isOpen={showDocuments}
        onClose={() => setShowDocuments(false)}
        onComplete={() => markTaskComplete('review_documents')}
        title="Documents Needed"
        showCompleteButton={true}
        isCompleted={completedTasks['review_documents'] || false}
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

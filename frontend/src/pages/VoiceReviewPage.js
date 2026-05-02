/**
 * VoiceReviewPage — Borrower consent & review after voice-completed URLA
 *
 * Accessed via /apply/voice-review/:token (magic link from SMS).
 * Fetches the application summary, wraps ReviewStage with ApplicationContext,
 * and handles final submission.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { ApplicationProvider } from './applications/contexts/ApplicationContext';
import { createInitialState } from './applications/contexts/applicationReducer';
import ReviewStage from './applications/components/stages/ReviewStage';
import ApplicationShell from './applications/components/ApplicationShell';
import { getStages } from './applications/config/stageConfig';
import './VoiceReviewPage.css';
import '../styles/borrower-theme.css';

const DEMO_DATA = {
  credit_auth: { completed: false, timestamp: null },
  e_consent: { completed: false, timestamp: null },
  all_complete: false,
  application_status: 'pending_consent',
  lo_name: 'Sarah Johnson',
  form_data: {
    application_type: 'purchase',
    first_name: 'Timothy',
    last_name: 'Loss',
    email: 'timothy@example.com',
    phone: '8435551234',
    date_of_birth: '1985-06-15',
    ssn: '123456789',
    citizenship_status: 'US Citizen',
    current_address: { street: '123 Main St', city: 'Charleston', state: 'SC', zip: '29401' },
    employment_type: 'W-2 Employee',
    employer_name: 'Perennia AI',
    job_title: 'Senior Loan Officer',
    monthly_income: '12500',
    years_at_job: '4',
    property_type: 'Single Family',
    occupancy_type: 'Primary Residence',
    purchase_price: '425000',
    down_payment: '85000',
    checking_balance: '32000',
    savings_balance: '48000',
    investment_balance: '125000',
    retirement_balance: '210000',
  },
};

export default function VoiceReviewPage() {
  const { token } = useParams();
  const isDemoMode = token === 'demo';
  const [loading, setLoading] = useState(!isDemoMode);
  const [error, setError] = useState(null);
  const [applicationData, setApplicationData] = useState(isDemoMode ? DEMO_DATA : null);
  const [submitted, setSubmitted] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const apiBase = process.env.REACT_APP_API_URL || '';

  useEffect(() => {
    if (isDemoMode) return;
    async function loadApplication() {
      try {
        const res = await fetch(`${apiBase}/api/v1/pos/consent/${token}/status`);
        if (res.status === 410) {
          setError('This review link has expired. Please contact your loan officer for a new link.');
          return;
        }
        if (res.status === 404) {
          setError('Application not found. Please check your link or contact your loan officer.');
          return;
        }
        if (!res.ok) {
          setError('Unable to load your application. Please try again later.');
          return;
        }
        const data = await res.json();

        if (data.application_status === 'submitted') {
          setSubmitted(true);
        }

        setApplicationData(data);
      } catch (err) {
        setError('Unable to load your application. Please try again later.');
      } finally {
        setLoading(false);
      }
    }
    loadApplication();
  }, [token, apiBase, isDemoMode]);

  const handleSubmit = useCallback(async () => {
    if (isDemoMode) {
      setSubmitting(true);
      setTimeout(() => { setSubmitted(true); setSubmitting(false); }, 1500);
      return;
    }
    setSubmitting(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/pos/consent/${token}/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || 'Submission failed');
      }
      setSubmitted(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  }, [token, apiBase, isDemoMode]);

  const initialFormData = applicationData?.form_data || {};
  const appType = initialFormData.application_type || 'purchase';

  const branding = useMemo(() => ({
    loName: applicationData?.lo_name,
    companyName: applicationData?.company_name || 'Perennia',
  }), [applicationData]);

  const initialState = useMemo(() => {
    const base = createInitialState(appType);
    const stages = getStages(appType);
    return {
      ...base,
      currentStage: 'review',
      completedStages: stages.map(s => s.id).filter(id => id !== 'review'),
      formData: {
        ...base.formData,
        ...initialFormData,
        borrowers: base.formData.borrowers,
      },
    };
  }, [initialFormData, appType]);

  if (loading) {
    return (
      <div className="voice-review-page borrower-theme">
        <div className="voice-review-loading">
          <div className="loading-spinner" />
          <p>Loading your application...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="voice-review-page borrower-theme">
        <div className="voice-review-error">
          <h2>Oops</h2>
          <p>{error}</p>
          <p className="voice-review-error-help">
            If you continue to have trouble, please contact your loan officer directly.
          </p>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="voice-review-page borrower-theme">
        <div className="voice-review-submitted">
          <div className="submitted-check">&#10003;</div>
          <h1>Application Submitted!</h1>
          <p>
            Your application has been submitted successfully. Your loan officer
            will be in touch shortly with next steps.
          </p>
          <p className="submitted-note">
            You'll receive an email with instructions for uploading any
            remaining documents.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="voice-review-page borrower-theme">
      <ApplicationProvider
        applicationType={appType}
        initialState={initialState}
      >
        <ApplicationShell
          branding={branding}
          showSaveIndicator={false}
          showDocumentChecklist={false}
          readOnlyBanner="Aria completed this application during your call. Review the details below and sign to submit."
          showAriaChat={true}
        >
          <ReviewStage
            onSubmit={handleSubmit}
            isSubmitting={submitting}
            voiceReviewToken={token}
            showCalendar={true}
            orgSlug={applicationData?.org_slug}
            loSlug={applicationData?.lo_slug}
            loName={applicationData?.lo_name}
          />
        </ApplicationShell>
      </ApplicationProvider>
    </div>
  );
}

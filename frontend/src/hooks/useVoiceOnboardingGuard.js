/**
 * useVoiceOnboardingGuard.js
 * Perennia AI — First-launch voice onboarding gate
 *
 * Checks whether the current user has completed voice enrollment.
 * Used to conditionally show the AriaVoiceOnboarding screen.
 *
 * Usage:
 *   const { isReady, isEnrolled, markEnrollmentComplete, resetEnrollment } = useVoiceOnboardingGuard();
 *
 *   if (!isReady) return <SplashScreen />;
 *   if (!isEnrolled) return <AriaVoiceOnboarding onComplete={markEnrollmentComplete} />;
 */

import { useState, useEffect, useCallback } from 'react';
import { voiceProfileApi } from '../services/voiceProfileService';

const ONBOARDING_KEY = 'perennia_voice_onboarding_complete';

export function useVoiceOnboardingGuard() {
  const [isReady, setIsReady] = useState(false);
  const [isEnrolled, setIsEnrolled] = useState(false);

  useEffect(() => {
    checkEnrollmentStatus();
  }, []);

  async function checkEnrollmentStatus() {
    try {
      // Fast local check first — avoids an API call on every cold start
      const localFlag = localStorage.getItem(ONBOARDING_KEY);
      if (localFlag === 'true') {
        setIsEnrolled(true);
        setIsReady(true);
        return;
      }

      // Verify with backend in case user switched devices or cleared storage
      const status = await voiceProfileApi.getStatus();
      const enrolled = status.status === 'enrolled' && status.embedding_ready;

      if (enrolled) {
        localStorage.setItem(ONBOARDING_KEY, 'true');
      }

      setIsEnrolled(enrolled);
    } catch (err) {
      // If network fails, default to not blocking — user can enroll later
      console.warn('Voice enrollment check failed:', err);
      setIsEnrolled(false);
    } finally {
      setIsReady(true);
    }
  }

  const markEnrollmentComplete = useCallback(() => {
    localStorage.setItem(ONBOARDING_KEY, 'true');
    setIsEnrolled(true);
  }, []);

  const resetEnrollment = useCallback(async () => {
    localStorage.removeItem(ONBOARDING_KEY);
    setIsEnrolled(false);
  }, []);

  return { isReady, isEnrolled, markEnrollmentComplete, resetEnrollment };
}

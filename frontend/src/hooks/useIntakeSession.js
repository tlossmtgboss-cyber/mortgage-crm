/**
 * useIntakeSession Hook
 * Manages intake engine session state and API interactions
 */

import { useState, useCallback, useEffect, useRef } from 'react';
import { intakeApi } from '../services/intakeApi';

/**
 * Custom hook for managing intake session
 * @param {Object} options - Hook options
 * @param {string} options.leadId - Lead ID to create session for
 * @param {string} options.loanId - Loan ID to create session for
 * @param {string} options.sessionId - Existing session ID to resume
 * @param {boolean} options.autoRefreshScores - Auto-refresh scores after answers (default: true)
 */
export function useIntakeSession(options = {}) {
  const {
    leadId,
    loanId,
    sessionId: existingSessionId,
    autoRefreshScores = true
  } = options;

  // Session state
  const [sessionId, setSessionId] = useState(existingSessionId || null);
  const [sessionStatus, setSessionStatus] = useState(null);
  const [currentQuestion, setCurrentQuestion] = useState(null);
  const [isCompleted, setIsCompleted] = useState(false);

  // Scores state
  const [scores, setScores] = useState({
    truth_score: 0,
    truth_band: 'none',
    readiness_score: 0,
    hesitation_score: 0,
    hesitation_band: 'none',
    breakdown: {}
  });
  const [coaching, setCoaching] = useState({ suggestions: [] });
  const [flags, setFlags] = useState({ flags: [] });

  // Loading states
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  // Track mount status to prevent state updates on unmounted component
  const mountedRef = useRef(true);
  const initializedRef = useRef(false);

  /**
   * Refresh all scores from API
   */
  const refreshScores = useCallback(async (sid) => {
    const targetSid = sid || sessionId;
    if (!targetSid) return;

    try {
      const [scoresData, coachingData, flagsData] = await Promise.all([
        intakeApi.getScores(targetSid),
        intakeApi.getCoaching(targetSid),
        intakeApi.getFlags(targetSid)
      ]);

      if (mountedRef.current) {
        setScores(scoresData);
        setCoaching(coachingData);
        setFlags(flagsData);
      }
    } catch (err) {
      console.error('Error refreshing scores:', err);
    }
  }, [sessionId]);

  /**
   * Fetch scores for a session (internal helper)
   */
  const fetchScores = async (sid) => {
    try {
      const [scoresData, coachingData, flagsData] = await Promise.all([
        intakeApi.getScores(sid),
        intakeApi.getCoaching(sid),
        intakeApi.getFlags(sid)
      ]);

      if (mountedRef.current) {
        setScores(scoresData);
        setCoaching(coachingData);
        setFlags(flagsData);
      }
    } catch (err) {
      console.error('Error fetching scores:', err);
    }
  };

  /**
   * Initialize or resume a session
   */
  const initialize = useCallback(async () => {
    // Prevent double initialization
    if (initializedRef.current) return;
    initializedRef.current = true;

    try {
      setLoading(true);
      setError(null);

      let session;

      if (existingSessionId) {
        // Resume existing session
        session = await intakeApi.getSession(existingSessionId);
        if (!session) {
          throw new Error('Session not found');
        }
      } else {
        // Create new session
        session = await intakeApi.createSession({
          lead_id: leadId,
          loan_id: loanId,
          party_type: 'borrower'
        });
      }

      if (!mountedRef.current) return;

      const sid = session.session_id || session.id;
      setSessionId(sid);
      setSessionStatus(session);

      // Check if already completed
      if (session.status === 'completed') {
        setIsCompleted(true);
        await fetchScores(sid);
        return;
      }

      // Fetch next question
      const questionData = await intakeApi.getNextQuestion(sid);

      if (mountedRef.current) {
        if (questionData.completed) {
          setIsCompleted(true);
          setCurrentQuestion(null);
        } else {
          setCurrentQuestion(questionData);
        }
      }

      // Fetch initial scores
      if (autoRefreshScores) {
        await fetchScores(sid);
      }
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message);
      }
    } finally {
      if (mountedRef.current) {
        setLoading(false);
      }
    }
  }, [leadId, loanId, existingSessionId, autoRefreshScores]);

  /**
   * Submit answer and advance to next question
   */
  const submitAnswer = useCallback(async (questionId, answer, metadata = {}) => {
    if (!sessionId) {
      return { success: false, error: 'No active session' };
    }

    try {
      setSubmitting(true);
      setError(null);

      // Submit the answer
      await intakeApi.submitAnswer(sessionId, {
        question_id: questionId,
        answer,
        metadata
      });

      // Refresh session status
      const status = await intakeApi.getSession(sessionId);
      if (mountedRef.current) {
        setSessionStatus(status);
      }

      // Get next question
      const nextData = await intakeApi.getNextQuestion(sessionId);

      if (mountedRef.current) {
        if (nextData.completed) {
          setIsCompleted(true);
          setCurrentQuestion(null);
        } else {
          setCurrentQuestion(nextData);
        }
      }

      // Refresh scores after each answer
      if (autoRefreshScores) {
        await refreshScores();
      }

      return {
        success: true,
        completed: nextData.completed
      };
    } catch (err) {
      if (mountedRef.current) {
        setError(err.message);
      }
      return { success: false, error: err.message };
    } finally {
      if (mountedRef.current) {
        setSubmitting(false);
      }
    }
  }, [sessionId, autoRefreshScores, refreshScores]);

  /**
   * Skip current question (if allowed)
   */
  const skipQuestion = useCallback(async () => {
    if (!currentQuestion) return { success: false };

    // Submit with empty/null answer to skip
    return submitAnswer(currentQuestion.question_id, null, { skipped: true });
  }, [currentQuestion, submitAnswer]);

  /**
   * Go back to previous question (if supported)
   */
  const goBack = useCallback(async () => {
    // TODO: Implement if backend supports going back
    console.warn('Go back not yet implemented');
  }, []);

  // Initialize on mount only
  useEffect(() => {
    mountedRef.current = true;
    initialize();

    return () => {
      mountedRef.current = false;
      initializedRef.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Calculate progress
  const progress = sessionStatus ? {
    currentSection: currentQuestion?.section || sessionStatus.current_section || 'unknown',
    questionsAnswered: sessionStatus.questions_answered || 0,
    totalQuestions: sessionStatus.total_questions || 79,
    percentage: sessionStatus.total_questions
      ? Math.round((sessionStatus.questions_answered / sessionStatus.total_questions) * 100)
      : 0
  } : null;

  return {
    // Session data
    sessionId,
    sessionStatus,
    currentQuestion,
    isCompleted,
    progress,

    // Scores
    scores,
    coaching,
    flags,

    // Loading states
    loading,
    submitting,
    error,

    // Actions
    submitAnswer,
    skipQuestion,
    goBack,
    refreshScores,
    reinitialize: initialize
  };
}

export default useIntakeSession;

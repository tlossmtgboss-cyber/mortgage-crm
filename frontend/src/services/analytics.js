import { getToken } from '../utils/tokenStore';

/**
 * Analytics Service - Track user behavior and feature usage
 * Used for beta program metrics and product improvement
 */

const ANALYTICS_ENDPOINT = '/api/v1/analytics/track';

/**
 * Track a user event
 * @param {string} eventName - Name of the event
 * @param {object} properties - Additional properties
 */
export const trackEvent = async (eventName, properties = {}) => {
  try {
    const token = getToken();

    const eventData = {
      event: eventName,
      properties: {
        ...properties,
        timestamp: new Date().toISOString(),
        url: window.location.pathname,
        userAgent: navigator.userAgent,
        screenWidth: window.innerWidth,
        screenHeight: window.innerHeight,
      }
    };

    // Log in development
    if (process.env.NODE_ENV === 'development') {
      console.log('[Analytics]', eventName, eventData);
    }

    // Send to backend (fire and forget)
    if (token) {
      fetch(ANALYTICS_ENDPOINT, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${token}`
        },
        body: JSON.stringify(eventData)
      }).catch(() => {
        // Silently fail - don't interrupt user experience
      });
    }
  } catch (error) {
    // Never let analytics break the app
    console.warn('Analytics error:', error);
  }
};

/**
 * Track page view
 * @param {string} pageName - Name of the page
 */
export const trackPageView = (pageName) => {
  trackEvent('page_view', { page: pageName });
};

/**
 * Track feature usage
 * @param {string} featureName - Name of the feature
 * @param {string} action - Action taken (e.g., 'opened', 'completed', 'cancelled')
 */
export const trackFeature = (featureName, action, metadata = {}) => {
  trackEvent('feature_usage', {
    feature: featureName,
    action,
    ...metadata
  });
};

// Pre-defined event trackers for common actions

/**
 * Track clip events
 */
export const trackClip = {
  started: () => trackFeature('video_clip', 'recording_started'),
  completed: (duration) => trackFeature('video_clip', 'recording_completed', { duration }),
  cancelled: () => trackFeature('video_clip', 'recording_cancelled'),
  shared: (clipId) => trackFeature('video_clip', 'shared', { clipId }),
  viewed: (clipId, viewDuration) => trackFeature('video_clip', 'viewed', { clipId, viewDuration }),
  templateUsed: (templateId) => trackFeature('video_clip', 'template_used', { templateId }),
};

/**
 * Track meeting/call events
 */
export const trackMeeting = {
  started: () => trackFeature('meeting', 'call_started'),
  ended: (duration) => trackFeature('meeting', 'call_ended', { duration }),
  transcriptViewed: (meetingId) => trackFeature('meeting', 'transcript_viewed', { meetingId }),
  analyticsViewed: (meetingId) => trackFeature('meeting', 'analytics_viewed', { meetingId }),
  actionItemCreated: () => trackFeature('meeting', 'action_item_created'),
};

/**
 * Track AI assistant interactions
 */
export const trackAI = {
  chatOpened: () => trackFeature('ai_assistant', 'opened'),
  messageSent: () => trackFeature('ai_assistant', 'message_sent'),
  suggestionAccepted: (suggestionType) => trackFeature('ai_assistant', 'suggestion_accepted', { suggestionType }),
  coachingViewed: () => trackFeature('ai_assistant', 'coaching_viewed'),
};

/**
 * Track onboarding progress
 */
export const trackOnboarding = {
  started: () => trackFeature('onboarding', 'started'),
  stepCompleted: (stepNumber, stepName) => trackFeature('onboarding', 'step_completed', { stepNumber, stepName }),
  completed: () => trackFeature('onboarding', 'completed'),
  skipped: (atStep) => trackFeature('onboarding', 'skipped', { atStep }),
};

/**
 * Track help usage
 */
export const trackHelp = {
  opened: () => trackFeature('help', 'opened'),
  articleViewed: (articleId, category) => trackFeature('help', 'article_viewed', { articleId, category }),
  searchPerformed: (query) => trackFeature('help', 'search_performed', { query }),
  contactSupport: () => trackFeature('help', 'contact_support_clicked'),
};

/**
 * Track errors (for debugging)
 */
export const trackError = (errorType, errorMessage, context = {}) => {
  trackEvent('error', {
    errorType,
    errorMessage,
    ...context
  });
};

export default {
  trackEvent,
  trackPageView,
  trackFeature,
  trackClip,
  trackMeeting,
  trackAI,
  trackOnboarding,
  trackHelp,
  trackError,
};

/**
 * Calendar Settings - Reducer & Initial State
 *
 * Manages all cross-section state via useReducer.
 * Extracted from CalendarSettings.js for testability and clarity.
 */

import {
  DEFAULT_AVAILABILITY,
  DEFAULT_NOTIFICATIONS,
  DEFAULT_BOOKING_PAGE,
  DEFAULT_CANCELLATION_POLICY,
  DEFAULT_ADVANCED,
  DEFAULT_INTEGRATIONS,
  DEFAULT_INTEGRATION_SETTINGS,
  DEFAULT_WEBHOOK_SETTINGS,
  DEFAULT_MEETING_DEFAULTS,
  DEFAULT_TEAM,
  DEFAULT_EXPANDED_SECTIONS,
} from './calendarSettingsDefaults';

// ============================================================================
// Action types
// ============================================================================

export const SET_TAB = 'SET_TAB';
export const LOAD_SECTION_START = 'LOAD_SECTION_START';
export const LOAD_SECTION_SUCCESS = 'LOAD_SECTION_SUCCESS';
export const LOAD_SECTION_ERROR = 'LOAD_SECTION_ERROR';
export const UPDATE_FIELD = 'UPDATE_FIELD';
export const SAVE_START = 'SAVE_START';
export const SAVE_SUCCESS = 'SAVE_SUCCESS';
export const SAVE_ERROR = 'SAVE_ERROR';
export const RESET_SECTION = 'RESET_SECTION';

// ============================================================================
// Initial state
// ============================================================================

export const initialState = {
  activeSection: 'availability',
  loading: true,
  saving: false,
  hasChanges: false,
  saveStatus: 'saved', // 'saved' | 'saving' | 'unsaved'

  sections: {
    availability: {
      data: DEFAULT_AVAILABILITY,
      seasonalHours: [],
      overrideDays: [],
      expandedSections: DEFAULT_EXPANDED_SECTIONS,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    'appointment-types': {
      data: [],
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    notifications: {
      data: DEFAULT_NOTIFICATIONS,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    'booking-page': {
      data: DEFAULT_BOOKING_PAGE,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    'cancellation-policy': {
      data: DEFAULT_CANCELLATION_POLICY,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    advanced: {
      data: DEFAULT_ADVANCED,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    integrations: {
      data: DEFAULT_INTEGRATIONS,
      integrationSettings: DEFAULT_INTEGRATION_SETTINGS,
      syncErrors: [],
      webhookSettings: DEFAULT_WEBHOOK_SETTINGS,
      meetingDefaults: DEFAULT_MEETING_DEFAULTS,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    team: {
      data: DEFAULT_TEAM,
      isManager: false,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
    'locations-labels': {
      locations: [],
      locationsLoading: false,
      labels: [],
      labelsLoading: false,
      templates: [],
      templatesLoading: false,
      autoAssignLabels: false,
      labelMappings: {},
      defaultLabelId: null,
      loading: false,
      error: null,
      dirty: false,
      lastSaved: null,
    },
  },
};

// ============================================================================
// Reducer
// ============================================================================

export function settingsReducer(state, action) {
  switch (action.type) {
    case SET_TAB:
      return {
        ...state,
        activeSection: action.payload,
        hasChanges: false,
        saveStatus: 'saved',
      };

    case LOAD_SECTION_START:
      return {
        ...state,
        loading: true,
        sections: {
          ...state.sections,
          [action.section]: {
            ...state.sections[action.section],
            loading: true,
            error: null,
          },
        },
      };

    case LOAD_SECTION_SUCCESS: {
      const section = action.section;
      const currentSection = state.sections[section];
      return {
        ...state,
        loading: false,
        hasChanges: false,
        saveStatus: 'saved',
        sections: {
          ...state.sections,
          [section]: {
            ...currentSection,
            ...action.payload,
            loading: false,
            error: null,
            dirty: false,
            lastSaved: action.payload.data || currentSection.data,
          },
        },
      };
    }

    case LOAD_SECTION_ERROR:
      return {
        ...state,
        loading: false,
        hasChanges: false,
        saveStatus: 'saved',
        sections: {
          ...state.sections,
          [action.section]: {
            ...state.sections[action.section],
            loading: false,
            error: action.error,
          },
        },
      };

    case UPDATE_FIELD: {
      const { section, field, value } = action;
      const currentSection = state.sections[section];

      // Support functional updates (same as useState callback pattern)
      const resolvedValue = typeof value === 'function' ? value(currentSection[field]) : value;

      return {
        ...state,
        hasChanges: true,
        saveStatus: 'unsaved',
        sections: {
          ...state.sections,
          [section]: {
            ...currentSection,
            [field]: resolvedValue,
            dirty: true,
          },
        },
      };
    }

    case SAVE_START:
      return {
        ...state,
        saving: true,
        saveStatus: 'saving',
      };

    case SAVE_SUCCESS: {
      const section = action.section;
      const currentSection = state.sections[section];
      return {
        ...state,
        saving: false,
        hasChanges: false,
        saveStatus: 'saved',
        sections: {
          ...state.sections,
          [section]: {
            ...currentSection,
            dirty: false,
            lastSaved: currentSection.data,
          },
        },
      };
    }

    case SAVE_ERROR:
      return {
        ...state,
        saving: false,
        saveStatus: 'unsaved',
      };

    case RESET_SECTION: {
      const section = action.section;
      const currentSection = state.sections[section];
      if (currentSection.lastSaved) {
        return {
          ...state,
          hasChanges: false,
          saveStatus: 'saved',
          sections: {
            ...state.sections,
            [section]: {
              ...currentSection,
              data: currentSection.lastSaved,
              dirty: false,
            },
          },
        };
      }
      return state;
    }

    default:
      return state;
  }
}

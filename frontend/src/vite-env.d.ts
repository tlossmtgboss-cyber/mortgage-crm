/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string;
  readonly VITE_WS_URL: string;
  readonly VITE_MICROSOFT_CLIENT_ID: string;
  readonly VITE_GOOGLE_PLACES_API_KEY: string;
  readonly VITE_GOOGLE_CLIENT_ID: string;
  readonly VITE_FACEBOOK_APP_ID: string;
  readonly VITE_LINKEDIN_CLIENT_ID: string;
  readonly VITE_APPLE_CLIENT_ID: string;
  readonly VITE_ENABLE_AGENT_DASHBOARD: string;
  readonly VITE_ENABLE_AGENT_GYM: string;
  readonly VITE_ENABLE_PURL_PORTAL: string;
  readonly VITE_ENABLE_VIDEO_FEATURE: string;
  readonly VITE_SENTRY_DSN: string;
  readonly VITE_GA_TRACKING_ID: string;
  readonly VITE_MIXPANEL_TOKEN: string;
  readonly VITE_ENVIRONMENT: string;
  readonly VITE_DEBUG: string;
  readonly VITE_PURL_SESSION_TIMEOUT: string;
  readonly VITE_PURL_DEBUG: string;
  readonly DEV: boolean;
  readonly PROD: boolean;
  readonly MODE: string;
  readonly [key: string]: string | boolean | undefined;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

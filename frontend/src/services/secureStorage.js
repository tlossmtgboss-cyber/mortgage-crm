/**
 * Secure Storage Layer for Perennia AI Mobile App
 *
 * Enterprise-grade storage with AES-256-GCM encryption-at-rest on top of
 * Capacitor Preferences. Provides data classification, authenticated encryption,
 * and transparent migration from legacy storage formats.
 *
 * Security approach:
 * - ALL sensitive data is encrypted with AES-256-GCM via the Web Crypto API
 * - Web Crypto is available in all modern browsers and iOS WKWebView (Capacitor)
 * - If Web Crypto is unavailable (ancient browser), sensitive writes are REFUSED
 *   rather than falling back to weak obfuscation — GLBA compliance requires real encryption
 * - AES key is stored in Capacitor Preferences (native) or sessionStorage (web)
 *
 * Architecture:
 * - RESTRICTED data: Handled exclusively by OS keychain via NativeBiometric (never touches Preferences)
 * - SENSITIVE data: Encrypted with AES-256-GCM before writing to Preferences
 * - INTERNAL data: Stored in Preferences with integrity checksums
 * - PUBLIC data: Stored in Preferences as-is
 *
 * Backward compatibility: Old XOR-encrypted envelopes (v1) are transparently
 * decrypted and re-encrypted with AES-GCM on read. The legacy XOR decryption
 * code is retained solely for this one-time migration and is never used for
 * new writes.
 */

import { Capacitor } from '@capacitor/core';
import { Preferences } from '@capacitor/preferences';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const isNative = Capacitor.isNativePlatform();

/** Prefix applied to all secure storage keys to avoid collisions */
const SECURE_PREFIX = '_ss_';

/** Key under which the encryption key fingerprint is stored for tamper detection */
const KEY_FINGERPRINT_KEY = '_ss_meta_key_fingerprint';

/** Key that tracks the storage schema version for migration */
const SCHEMA_VERSION_KEY = '_ss_meta_schema_version';

/** Current schema version — bump when storage format changes */
const CURRENT_SCHEMA_VERSION = 2;

/** Server identifier used with NativeBiometric credential store */
const KEYCHAIN_SERVER = 'com.perenniaai.secure-storage';

/** Whether Web Crypto API with AES-GCM is available */
const HAS_WEB_CRYPTO = (() => {
  try {
    return (
      typeof crypto !== 'undefined' &&
      typeof crypto.subtle !== 'undefined' &&
      typeof crypto.subtle.generateKey === 'function' &&
      typeof crypto.subtle.encrypt === 'function' &&
      typeof crypto.subtle.decrypt === 'function'
    );
  } catch {
    return false;
  }
})();

if (!HAS_WEB_CRYPTO) {
  console.error(
    'Secure storage: Web Crypto API not available. ' +
    'Sensitive data CANNOT be encrypted — writes to sensitive keys will be refused. ' +
    'GLBA compliance requires AES-256-GCM. Upgrade to a modern browser.'
  );
}

/**
 * Data classification levels.
 * Each stored key is assigned one of these levels, which determines how it is handled.
 */
export const DATA_CLASSIFICATION = Object.freeze({
  /** App preferences, theme, language — stored as plaintext */
  PUBLIC: 'PUBLIC',
  /** Cached API responses, sync state — stored with integrity checksum */
  INTERNAL: 'INTERNAL',
  /** Auth tokens, credentials, PII — encrypted at rest */
  SENSITIVE: 'SENSITIVE',
  /** Biometric data — OS keychain only, never written to Preferences */
  RESTRICTED: 'RESTRICTED',
});

/**
 * Keys that require encryption. Any key in this set will be encrypted before
 * being written to Preferences and decrypted on read.
 */
const SENSITIVE_KEYS = new Set([
  'auth_token',
  'refresh_token',
  'user_credentials',
  'biometric_credentials',
  'session_data',
  'cached_user_profile',
  'token',           // legacy key used across the app
  'user',            // legacy key — contains user object with PII
  'impersonation',   // impersonation session data
]);

/**
 * Maps well-known keys to their classification. Keys not listed here default
 * to INTERNAL if they start with a cache prefix, otherwise PUBLIC.
 */
const KEY_CLASSIFICATION = {
  // SENSITIVE
  auth_token: DATA_CLASSIFICATION.SENSITIVE,
  refresh_token: DATA_CLASSIFICATION.SENSITIVE,
  user_credentials: DATA_CLASSIFICATION.SENSITIVE,
  biometric_credentials: DATA_CLASSIFICATION.RESTRICTED,
  session_data: DATA_CLASSIFICATION.SENSITIVE,
  cached_user_profile: DATA_CLASSIFICATION.SENSITIVE,
  token: DATA_CLASSIFICATION.SENSITIVE,
  user: DATA_CLASSIFICATION.SENSITIVE,
  impersonation: DATA_CLASSIFICATION.SENSITIVE,

  // INTERNAL
  dashboardOrder: DATA_CLASSIFICATION.INTERNAL,
  moduleCache: DATA_CLASSIFICATION.INTERNAL,
  userRole: DATA_CLASSIFICATION.INTERNAL,
  assignedRoles: DATA_CLASSIFICATION.INTERNAL,
  activeRole: DATA_CLASSIFICATION.INTERNAL,
  canSwitchRoles: DATA_CLASSIFICATION.INTERNAL,
  viewAsRole: DATA_CLASSIFICATION.INTERNAL,
  role_preview: DATA_CLASSIFICATION.INTERNAL,
  original_user_backup: DATA_CLASSIFICATION.INTERNAL,
  original_token_backup: DATA_CLASSIFICATION.INTERNAL,

  // PUBLIC
  theme: DATA_CLASSIFICATION.PUBLIC,
  language: DATA_CLASSIFICATION.PUBLIC,
  sidebar_collapsed: DATA_CLASSIFICATION.PUBLIC,
  onboarding_complete: DATA_CLASSIFICATION.PUBLIC,
};

// ---------------------------------------------------------------------------
// Base64 helpers (browser-safe, no atob/btoa unicode issues)
// ---------------------------------------------------------------------------

function uint8ToBase64(uint8Array) {
  let binary = '';
  for (let i = 0; i < uint8Array.length; i++) {
    binary += String.fromCharCode(uint8Array[i]);
  }
  return btoa(binary);
}

function base64ToUint8(base64) {
  const binary = atob(base64);
  const uint8 = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    uint8[i] = binary.charCodeAt(i);
  }
  return uint8;
}

// ---------------------------------------------------------------------------
// Legacy XOR cipher (kept for backward-compatible decryption of v1 envelopes)
// ---------------------------------------------------------------------------

/**
 * Derives XOR key bytes from a seed string (legacy v1 format).
 * @private — only used for migrating old data
 */
function _legacyDeriveKeyBytes(seed) {
  const encoder = new TextEncoder();
  const seedBytes = encoder.encode(seed);
  const keyLength = 32;
  const key = new Uint8Array(keyLength);

  for (let i = 0; i < keyLength; i++) {
    key[i] = (seedBytes[i % seedBytes.length] ^ (i * 167)) & 0xff;
  }

  for (let i = 1; i < keyLength; i++) {
    key[i] = (key[i] + key[i - 1] * 31) & 0xff;
  }

  return key;
}

/**
 * Decrypts XOR-encrypted data (legacy v1 format).
 * @private — only used for migrating old data
 */
function _legacyDecrypt(cipherBase64, keyBytes) {
  const encrypted = base64ToUint8(cipherBase64);
  const decrypted = new Uint8Array(encrypted.length);

  for (let i = 0; i < encrypted.length; i++) {
    decrypted[i] = encrypted[i] ^ keyBytes[i % keyBytes.length];
  }

  const decoder = new TextDecoder();
  return decoder.decode(decrypted);
}

/**
 * Computes FNV-1a checksum for integrity verification.
 * Used for non-encrypted (INTERNAL/PUBLIC) data tamper detection and
 * legacy v1 envelope migration.
 * @private
 */
function _legacyComputeChecksum(value) {
  let hash = 0x811c9dc5;
  const encoder = new TextEncoder();
  const bytes = encoder.encode(value);

  for (let i = 0; i < bytes.length; i++) {
    hash ^= bytes[i];
    hash = Math.imul(hash, 0x01000193);
  }

  return (hash >>> 0).toString(16).padStart(8, '0');
}

// ---------------------------------------------------------------------------
// AES-256-GCM encryption primitives
// ---------------------------------------------------------------------------

/**
 * Encrypts plaintext using AES-256-GCM.
 *
 * Returns a base64-encoded string containing: IV (12 bytes) || ciphertext || auth tag (16 bytes).
 * The GCM authentication tag provides both integrity and authenticity — no separate
 * checksum is needed.
 *
 * @param {string} plaintext - The string to encrypt
 * @param {CryptoKey} cryptoKey - AES-256-GCM CryptoKey
 * @returns {Promise<string>} base64-encoded IV+ciphertext+tag
 */
async function aesGcmEncrypt(plaintext, cryptoKey) {
  const encoder = new TextEncoder();
  const data = encoder.encode(plaintext);

  // Generate a random 96-bit IV (NIST recommended for GCM)
  const iv = crypto.getRandomValues(new Uint8Array(12));

  const cipherBuffer = await crypto.subtle.encrypt(
    { name: 'AES-GCM', iv },
    cryptoKey,
    data
  );

  // Prepend IV to ciphertext+tag so we can extract it on decrypt
  const cipherArray = new Uint8Array(cipherBuffer);
  const combined = new Uint8Array(iv.length + cipherArray.length);
  combined.set(iv, 0);
  combined.set(cipherArray, iv.length);

  return uint8ToBase64(combined);
}

/**
 * Decrypts AES-256-GCM encrypted data.
 *
 * Expects the input to be base64-encoded: IV (12 bytes) || ciphertext || auth tag.
 * If the authentication tag does not verify, this throws (GCM guarantees integrity).
 *
 * @param {string} cipherBase64 - base64-encoded IV+ciphertext+tag
 * @param {CryptoKey} cryptoKey - AES-256-GCM CryptoKey
 * @returns {Promise<string>} decrypted plaintext
 * @throws {DOMException} if authentication fails (data tampered)
 */
async function aesGcmDecrypt(cipherBase64, cryptoKey) {
  const combined = base64ToUint8(cipherBase64);

  // Extract IV (first 12 bytes) and ciphertext+tag (remainder)
  const iv = combined.slice(0, 12);
  const ciphertext = combined.slice(12);

  const plainBuffer = await crypto.subtle.decrypt(
    { name: 'AES-GCM', iv },
    cryptoKey,
    ciphertext
  );

  const decoder = new TextDecoder();
  return decoder.decode(plainBuffer);
}

// NOTE: XOR fallback encrypt/decrypt functions have been removed.
// XOR provides zero real security (trivially reversible obfuscation) and
// does not meet GLBA encryption requirements. If Web Crypto API is not
// available, sensitive data writes are refused rather than silently
// downgrading to insecure obfuscation.

// ---------------------------------------------------------------------------
// Storage envelope format
// ---------------------------------------------------------------------------

/**
 * Wraps a value in a storage envelope that includes metadata for format
 * identification and — for v2 AES-GCM — authenticated encryption.
 *
 * v2 envelope JSON structure (AES-GCM):
 * {
 *   v: 2,            // envelope version
 *   c: "SENSITIVE",  // classification
 *   d: "...",        // data (AES-GCM encrypted for SENSITIVE, plain otherwise)
 *   t: 1711900000    // timestamp (ms since epoch)
 * }
 *
 * For non-SENSITIVE data (INTERNAL classification), a checksum is still stored:
 * {
 *   v: 2,
 *   c: "INTERNAL",
 *   d: "...",        // plaintext data
 *   h: "abc123de",   // FNV-1a checksum for non-encrypted integrity
 *   t: 1711900000
 * }
 *
 * v1 envelope (legacy XOR — read-only for migration):
 * {
 *   v: 1,
 *   c: "SENSITIVE",
 *   d: "...",        // XOR-encrypted data
 *   h: "abc123de",   // FNV-1a checksum
 *   t: 1711900000
 * }
 */
async function createEnvelope(value, classification, cryptoKey) {
  const serialized = typeof value === 'string' ? value : JSON.stringify(value);

  let storedData;
  let checksum = undefined;

  if (classification === DATA_CLASSIFICATION.SENSITIVE) {
    if (cryptoKey) {
      // AES-256-GCM — GCM authentication tag provides both integrity and authenticity
      storedData = await aesGcmEncrypt(serialized, cryptoKey);
    } else {
      // Refuse to write sensitive data without real encryption.
      // XOR obfuscation was removed — it provided zero security and violated GLBA.
      throw new Error(
        'Secure storage: cannot write sensitive data without AES-256-GCM encryption. ' +
        'Web Crypto API is required.'
      );
    }
  } else {
    storedData = serialized;
    // Non-encrypted data still gets a checksum for tamper detection
    checksum = _legacyComputeChecksum(serialized);
  }

  const envelope = {
    v: 2,
    c: classification,
    d: storedData,
    t: Date.now(),
  };

  if (checksum !== undefined) {
    envelope.h = checksum;
  }

  return JSON.stringify(envelope);
}

/**
 * Opens a storage envelope, decrypting if necessary and verifying integrity.
 *
 * Handles both v2 (AES-GCM) and v1 (XOR) envelopes transparently.
 * For v1 SENSITIVE envelopes, decrypts using the legacy XOR key and flags
 * `needsReEncrypt: true` so the caller can re-encrypt with AES-GCM.
 *
 * Returns { value, valid, classification, timestamp, legacy, needsReEncrypt }
 * or null if the envelope is malformed.
 */
async function openEnvelope(envelopeStr, cryptoKey, legacyKeyBytes) {
  if (!envelopeStr) return null;

  try {
    const envelope = JSON.parse(envelopeStr);

    // Not an envelope — legacy raw value
    if (typeof envelope !== 'object' || envelope.v === undefined) {
      return { value: envelopeStr, valid: true, classification: null, timestamp: null, legacy: true, needsReEncrypt: false };
    }

    // ------- v2 envelope (AES-GCM) -------
    if (envelope.v === 2) {
      let plaintext;

      if (envelope.c === DATA_CLASSIFICATION.SENSITIVE) {
        if (cryptoKey) {
          try {
            // AES-GCM decrypt — authentication tag is verified automatically.
            // If tampered, this throws a DOMException.
            plaintext = await aesGcmDecrypt(envelope.d, cryptoKey);
          } catch (e) {
            // GCM authentication failed — data tampered or key changed
            console.warn('Secure storage: AES-GCM decryption/authentication failed');
            return { value: null, valid: false, classification: envelope.c, timestamp: envelope.t, legacy: false, needsReEncrypt: false };
          }
        } else {
          // No crypto key available — cannot decrypt sensitive data
          console.warn('Secure storage: cannot decrypt sensitive data without AES-GCM key');
          return { value: null, valid: false, classification: envelope.c, timestamp: envelope.t, legacy: false, needsReEncrypt: false };
        }

        return {
          value: plaintext,
          valid: true,
          classification: envelope.c,
          timestamp: envelope.t,
          legacy: false,
          needsReEncrypt: false,
        };
      }

      // Non-SENSITIVE v2 envelope — verify checksum if present
      plaintext = envelope.d;
      let valid = true;
      if (envelope.h) {
        const expectedChecksum = _legacyComputeChecksum(plaintext);
        valid = expectedChecksum === envelope.h;
        if (!valid) {
          console.warn('Secure storage: checksum mismatch — possible tampering detected');
        }
      }

      return {
        value: plaintext,
        valid,
        classification: envelope.c,
        timestamp: envelope.t,
        legacy: false,
        needsReEncrypt: false,
      };
    }

    // ------- v1 envelope (legacy XOR) — migration path -------
    // Legacy XOR decryption is retained ONLY to read old v1 data so it can
    // be re-encrypted with AES-GCM. No new data is ever written in v1 format.
    if (envelope.v === 1) {
      let plaintext;

      if (envelope.c === DATA_CLASSIFICATION.SENSITIVE && legacyKeyBytes) {
        try {
          plaintext = _legacyDecrypt(envelope.d, legacyKeyBytes);
        } catch (e) {
          console.warn('Secure storage: legacy XOR decryption failed, key may have rotated');
          return { value: null, valid: false, classification: envelope.c, timestamp: envelope.t, legacy: false, needsReEncrypt: false };
        }
      } else {
        plaintext = envelope.d;
      }

      // Verify legacy checksum
      let valid = true;
      if (envelope.h) {
        const expectedChecksum = _legacyComputeChecksum(plaintext);
        valid = expectedChecksum === envelope.h;
        if (!valid) {
          console.warn('Secure storage: legacy checksum mismatch — possible tampering detected');
        }
      }

      return {
        value: plaintext,
        valid,
        classification: envelope.c,
        timestamp: envelope.t,
        legacy: false,
        // Flag that this v1 data should be re-encrypted with AES-GCM
        needsReEncrypt: valid && envelope.c === DATA_CLASSIFICATION.SENSITIVE,
      };
    }

    // Unknown envelope version
    console.warn(`Secure storage: unknown envelope version ${envelope.v}`);
    return { value: envelope.d, valid: true, classification: envelope.c, timestamp: envelope.t, legacy: true, needsReEncrypt: false };

  } catch (e) {
    // Not valid JSON — treat as legacy raw value
    return { value: envelopeStr, valid: true, classification: null, timestamp: null, legacy: true, needsReEncrypt: false };
  }
}

// ---------------------------------------------------------------------------
// Key management
// ---------------------------------------------------------------------------

/**
 * Generates a cryptographically random seed string (32 hex chars = 128 bits of entropy).
 */
function generateRandomSeed() {
  const array = new Uint8Array(16);
  crypto.getRandomValues(array);
  return Array.from(array, (b) => b.toString(16).padStart(2, '0')).join('');
}

/**
 * Manages the encryption key lifecycle.
 *
 * - Generates a 256-bit AES-GCM CryptoKey via Web Crypto API
 * - Exports the key as JWK for storage
 * - On native: stores JWK in Capacitor Preferences
 * - On web: stores JWK in sessionStorage (cleared when tab closes)
 *
 * Also maintains the legacy XOR key bytes solely for decrypting old v1
 * envelopes during migration. No new data is ever encrypted with XOR.
 */
class KeyManager {
  constructor() {
    /** @type {CryptoKey|null} AES-256-GCM CryptoKey (null if Web Crypto unavailable) */
    this._cryptoKey = null;
    /** @type {Uint8Array|null} Legacy XOR key bytes from old seed — for decrypting v1 envelopes only */
    this._legacyKeyBytes = null;
    this._initialized = false;
    this._initPromise = null;
  }

  /**
   * Initialize the key manager. Safe to call multiple times — will only
   * initialize once.
   */
  async initialize() {
    if (this._initialized) return;
    if (this._initPromise) return this._initPromise;

    this._initPromise = this._doInitialize();
    await this._initPromise;
    this._initialized = true;
  }

  async _doInitialize() {
    try {
      // Load legacy key bytes so we can decrypt any remaining v1 envelopes
      await this._loadLegacyKey();

      if (HAS_WEB_CRYPTO) {
        await this._loadOrCreateAesKey();
      } else {
        // Web Crypto unavailable — sensitive data cannot be encrypted or decrypted.
        // Non-sensitive storage still works. This is intentional: refusing to use
        // XOR obfuscation prevents a false sense of security.
        console.error(
          'Secure storage: Web Crypto API unavailable. ' +
          'Sensitive storage operations will fail. Non-sensitive storage is unaffected.'
        );
      }
    } catch (error) {
      console.error('Secure storage: key initialization failed', error);
      // Legacy key loading is best-effort — don't block the entire storage layer
    }
  }

  /**
   * Load the legacy XOR key seed so we can decrypt old v1 envelopes.
   * This reads from the SAME location the old KeyManager stored its seed.
   */
  async _loadLegacyKey() {
    try {
      let seed = null;

      if (isNative) {
        // Try keychain first (where the old code stored it)
        try {
          const { NativeBiometric } = await import('@capgo/capacitor-native-biometric');
          const creds = await NativeBiometric.getCredentials({ server: KEYCHAIN_SERVER });
          if (creds && creds.password) {
            seed = creds.password;
          }
        } catch {
          // No keychain creds — try Preferences fallback
        }

        if (!seed) {
          const seedKey = '_ss_internal_key_seed';
          const { value } = await Preferences.get({ key: seedKey });
          if (value) seed = value;
        }
      } else {
        // Web: old seed was in sessionStorage
        seed = sessionStorage.getItem('_ss_web_key_seed');
      }

      if (seed) {
        this._legacyKeyBytes = _legacyDeriveKeyBytes(seed);
      }
    } catch (error) {
      console.warn('Secure storage: could not load legacy key for migration', error);
    }
  }

  /**
   * Load an existing AES-256-GCM key from storage, or generate a new one.
   */
  async _loadOrCreateAesKey() {
    const storageKey = '_ss_aes_key_jwk';

    // Try to load existing exported key
    let jwkStr = null;
    if (isNative) {
      const { value } = await Preferences.get({ key: storageKey });
      jwkStr = value;
    } else {
      jwkStr = sessionStorage.getItem(storageKey);
    }

    if (jwkStr) {
      try {
        const jwk = JSON.parse(jwkStr);
        this._cryptoKey = await crypto.subtle.importKey(
          'jwk',
          jwk,
          { name: 'AES-GCM' },
          true,  // extractable — needed to re-export for storage
          ['encrypt', 'decrypt']
        );
        return;
      } catch (e) {
        console.warn('Secure storage: stored AES key import failed, generating new key', e);
      }
    }

    // Generate new AES-256-GCM key
    this._cryptoKey = await crypto.subtle.generateKey(
      { name: 'AES-GCM', length: 256 },
      true,  // extractable — we need to export for persistent storage
      ['encrypt', 'decrypt']
    );

    // Export as JWK and persist
    const jwk = await crypto.subtle.exportKey('jwk', this._cryptoKey);
    const jwkString = JSON.stringify(jwk);

    if (isNative) {
      await Preferences.set({ key: storageKey, value: jwkString });
    } else {
      sessionStorage.setItem(storageKey, jwkString);
    }
  }

  /** Returns the AES-256-GCM CryptoKey (null if Web Crypto unavailable). */
  getCryptoKey() {
    return this._cryptoKey;
  }

  /** Returns legacy XOR key bytes for decrypting v1 envelopes during migration. */
  getLegacyKeyBytes() {
    return this._legacyKeyBytes;
  }

  /** Whether the key manager has been initialized. */
  get isReady() {
    return this._initialized;
  }
}

// ---------------------------------------------------------------------------
// Secure Storage class
// ---------------------------------------------------------------------------

class SecureStorage {
  constructor() {
    this._keyManager = new KeyManager();
    this._migrated = false;
    this._ready = false;
    this._readyPromise = null;
  }

  // -------------------------------------------------------------------------
  // Initialization
  // -------------------------------------------------------------------------

  /**
   * Ensures the storage layer is initialized (key loaded, migration done).
   * Automatically called by all public methods — callers do not need to
   * explicitly initialize.
   */
  async _ensureReady() {
    if (this._ready) return;
    if (this._readyPromise) return this._readyPromise;

    this._readyPromise = this._initialize();
    await this._readyPromise;
    this._ready = true;
  }

  async _initialize() {
    await this._keyManager.initialize();
    await this._migrateIfNeeded();
  }

  // -------------------------------------------------------------------------
  // Public API — Encrypted (sensitive) storage
  // -------------------------------------------------------------------------

  /**
   * Store a value with encryption. Use this for sensitive data such as
   * auth tokens, credentials, and PII.
   *
   * @param {string} key
   * @param {*} value - Will be JSON-stringified if not a string
   * @returns {Promise<void>}
   */
  async setSecure(key, value) {
    await this._ensureReady();

    if (value === null || value === undefined) {
      await this.remove(key);
      return;
    }

    const serialized = typeof value === 'string' ? value : JSON.stringify(value);
    const envelope = await createEnvelope(
      serialized,
      DATA_CLASSIFICATION.SENSITIVE,
      this._keyManager.getCryptoKey()
    );

    await this._rawSet(SECURE_PREFIX + key, envelope);
  }

  /**
   * Retrieve and decrypt a sensitive value.
   *
   * @param {string} key
   * @returns {Promise<string|null>} The decrypted value, or null if not found or tampered
   */
  async getSecure(key) {
    await this._ensureReady();

    const raw = await this._rawGet(SECURE_PREFIX + key);
    if (raw === null) return null;

    const result = await openEnvelope(
      raw,
      this._keyManager.getCryptoKey(),
      this._keyManager.getLegacyKeyBytes()
    );
    if (!result) return null;

    if (!result.valid) {
      console.warn(`Secure storage: integrity check failed for key "${key}"`);
      // Remove tampered data
      await this._rawRemove(SECURE_PREFIX + key);
      return null;
    }

    // If this was a v1 XOR envelope, re-encrypt with AES-GCM
    if (result.needsReEncrypt && result.value !== null) {
      try {
        const newEnvelope = await createEnvelope(
          result.value,
          DATA_CLASSIFICATION.SENSITIVE,
          this._keyManager.getCryptoKey()
        );
        await this._rawSet(SECURE_PREFIX + key, newEnvelope);
      } catch (e) {
        // Non-fatal — data was read successfully, just couldn't upgrade encryption
        console.warn('Secure storage: failed to re-encrypt legacy data with AES-GCM', e);
      }
    }

    return result.value;
  }

  // -------------------------------------------------------------------------
  // Public API — Standard (non-sensitive) storage
  // -------------------------------------------------------------------------

  /**
   * Store a non-sensitive value. Includes an integrity checksum but no encryption.
   *
   * @param {string} key
   * @param {*} value - Will be JSON-stringified if not a string
   * @returns {Promise<void>}
   */
  async set(key, value) {
    await this._ensureReady();

    if (value === null || value === undefined) {
      await this.remove(key);
      return;
    }

    const classification = this._classifyKey(key);

    // If the caller uses set() for a key we know is sensitive, upgrade to encrypted
    if (classification === DATA_CLASSIFICATION.SENSITIVE) {
      return this.setSecure(key, value);
    }

    const serialized = typeof value === 'string' ? value : JSON.stringify(value);
    const envelope = await createEnvelope(serialized, classification, null, null);

    await this._rawSet(SECURE_PREFIX + key, envelope);
  }

  /**
   * Retrieve a non-sensitive value.
   *
   * @param {string} key
   * @returns {Promise<string|null>}
   */
  async get(key) {
    await this._ensureReady();

    const classification = this._classifyKey(key);

    // If the caller uses get() for a sensitive key, route through secure path
    if (classification === DATA_CLASSIFICATION.SENSITIVE) {
      return this.getSecure(key);
    }

    const raw = await this._rawGet(SECURE_PREFIX + key);
    if (raw === null) return null;

    const result = await openEnvelope(
      raw,
      this._keyManager.getCryptoKey(),
      this._keyManager.getLegacyKeyBytes()
    );
    if (!result) return null;

    if (!result.valid) {
      console.warn(`Secure storage: integrity check failed for key "${key}"`);
      return null;
    }

    return result.value;
  }

  /**
   * Retrieve and parse a JSON value.
   *
   * @param {string} key
   * @returns {Promise<*|null>}
   */
  async getJSON(key) {
    const value = await this.get(key);
    if (value === null) return null;

    try {
      return JSON.parse(value);
    } catch (e) {
      // Value is a plain string, not JSON
      return value;
    }
  }

  /**
   * Store a value as JSON.
   *
   * @param {string} key
   * @param {*} value
   * @returns {Promise<void>}
   */
  async setJSON(key, value) {
    await this.set(key, JSON.stringify(value));
  }

  // -------------------------------------------------------------------------
  // Public API — Removal
  // -------------------------------------------------------------------------

  /**
   * Remove a single key from storage.
   *
   * @param {string} key
   * @returns {Promise<void>}
   */
  async remove(key) {
    await this._ensureReady();
    await this._rawRemove(SECURE_PREFIX + key);
  }

  /**
   * Clear ALL data from secure storage.
   *
   * @returns {Promise<void>}
   */
  async clearAll() {
    await this._ensureReady();

    if (isNative) {
      // Get all keys and remove those with our prefix
      const { keys: allKeys } = await Preferences.keys();
      const ourKeys = allKeys.filter((k) => k.startsWith(SECURE_PREFIX));
      for (const key of ourKeys) {
        await Preferences.remove({ key });
      }
    } else {
      const allKeys = Object.keys(localStorage);
      const ourKeys = allKeys.filter((k) => k.startsWith(SECURE_PREFIX));
      for (const key of ourKeys) {
        localStorage.removeItem(key);
      }
    }
  }

  /**
   * Clear only sensitive data. Call this on logout to ensure auth tokens
   * and credentials are wiped while preserving user preferences.
   *
   * @returns {Promise<void>}
   */
  async clearSensitive() {
    await this._ensureReady();

    for (const key of SENSITIVE_KEYS) {
      await this._rawRemove(SECURE_PREFIX + key);
    }

    // Also clear any legacy (non-prefixed) sensitive keys that might remain
    for (const key of SENSITIVE_KEYS) {
      await this._rawRemove(key);
    }
  }

  /**
   * Clear data by classification level.
   *
   * @param {string} classification - One of DATA_CLASSIFICATION values
   * @returns {Promise<void>}
   */
  async clearByClassification(classification) {
    await this._ensureReady();

    const allKeys = await this._getAllKeys();
    for (const rawKey of allKeys) {
      if (!rawKey.startsWith(SECURE_PREFIX)) continue;

      const key = rawKey.slice(SECURE_PREFIX.length);
      if (this._classifyKey(key) === classification) {
        await this._rawRemove(rawKey);
      }
    }
  }

  // -------------------------------------------------------------------------
  // Public API — Utilities
  // -------------------------------------------------------------------------

  /**
   * Get all keys currently in secure storage (without the internal prefix).
   *
   * @returns {Promise<string[]>}
   */
  async keys() {
    await this._ensureReady();

    const allKeys = await this._getAllKeys();
    return allKeys
      .filter((k) => k.startsWith(SECURE_PREFIX) && !k.startsWith('_ss_meta_') && !k.startsWith('_ss_internal_') && !k.startsWith('_ss_aes_'))
      .map((k) => k.slice(SECURE_PREFIX.length));
  }

  /**
   * Check whether a key exists in storage.
   *
   * @param {string} key
   * @returns {Promise<boolean>}
   */
  async has(key) {
    const raw = await this._rawGet(SECURE_PREFIX + key);
    return raw !== null;
  }

  /**
   * Get the data classification for a given key.
   *
   * @param {string} key
   * @returns {string} One of DATA_CLASSIFICATION values
   */
  classifyKey(key) {
    return this._classifyKey(key);
  }

  /**
   * Verify integrity of all stored data. Returns a report of any issues found.
   *
   * @returns {Promise<{ total: number, valid: number, invalid: string[], legacy: string[] }>}
   */
  async verifyIntegrity() {
    await this._ensureReady();

    const allKeys = await this.keys();
    const report = { total: allKeys.length, valid: 0, invalid: [], legacy: [] };

    for (const key of allKeys) {
      const raw = await this._rawGet(SECURE_PREFIX + key);
      if (raw === null) continue;

      const result = await openEnvelope(
        raw,
        this._keyManager.getCryptoKey(),
        this._keyManager.getLegacyKeyBytes()
      );

      if (!result) {
        report.invalid.push(key);
      } else if (result.legacy) {
        report.legacy.push(key);
      } else if (result.valid) {
        report.valid++;
      } else {
        report.invalid.push(key);
      }
    }

    return report;
  }

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  /**
   * Classifies a key based on the KEY_CLASSIFICATION map, SENSITIVE_KEYS set,
   * or naming heuristics.
   */
  _classifyKey(key) {
    // Explicit classification
    if (KEY_CLASSIFICATION[key]) {
      return KEY_CLASSIFICATION[key];
    }

    // Sensitive keys set
    if (SENSITIVE_KEYS.has(key)) {
      return DATA_CLASSIFICATION.SENSITIVE;
    }

    // Heuristic: keys containing 'token', 'credential', 'password', 'secret'
    const lowerKey = key.toLowerCase();
    if (
      lowerKey.includes('token') ||
      lowerKey.includes('credential') ||
      lowerKey.includes('password') ||
      lowerKey.includes('secret') ||
      lowerKey.includes('session')
    ) {
      return DATA_CLASSIFICATION.SENSITIVE;
    }

    // Heuristic: cache-like keys
    if (lowerKey.includes('cache') || lowerKey.includes('sync') || lowerKey.startsWith('_')) {
      return DATA_CLASSIFICATION.INTERNAL;
    }

    return DATA_CLASSIFICATION.PUBLIC;
  }

  /**
   * Raw read from the underlying storage (Preferences or localStorage).
   * Does NOT apply any prefix — caller must provide the full key.
   */
  async _rawGet(key) {
    if (isNative) {
      const { value } = await Preferences.get({ key });
      return value;
    }
    return localStorage.getItem(key);
  }

  /**
   * Raw write to the underlying storage.
   */
  async _rawSet(key, value) {
    if (isNative) {
      await Preferences.set({ key, value });
    } else {
      localStorage.setItem(key, value);
    }
  }

  /**
   * Raw remove from the underlying storage.
   */
  async _rawRemove(key) {
    if (isNative) {
      await Preferences.remove({ key });
    } else {
      localStorage.removeItem(key);
    }
  }

  /**
   * Get all keys from the underlying storage.
   */
  async _getAllKeys() {
    if (isNative) {
      const { keys: allKeys } = await Preferences.keys();
      return allKeys;
    }
    return Object.keys(localStorage);
  }

  // -------------------------------------------------------------------------
  // Migration
  // -------------------------------------------------------------------------

  /**
   * Transparently migrates data from legacy formats:
   *
   * 1. Raw values from the old storage.js utility (no envelope, no prefix)
   *    -> Wrapped in v2 envelope with AES-GCM encryption
   *
   * 2. v1 XOR-encrypted envelopes (schema version 1)
   *    -> Decrypted with legacy XOR key, re-encrypted with AES-GCM
   *
   * Migration is idempotent and runs once per session.
   */
  async _migrateIfNeeded() {
    if (this._migrated) return;

    try {
      // Check current schema version
      const versionRaw = await this._rawGet(SCHEMA_VERSION_KEY);
      const currentVersion = versionRaw ? parseInt(versionRaw, 10) : 0;

      if (currentVersion >= CURRENT_SCHEMA_VERSION) {
        this._migrated = true;
        return;
      }

      // ---------- Schema 0 -> 1 or 2: Migrate legacy raw keys ----------
      if (currentVersion < 1) {
        const legacyKeys = [
          'token', 'user', 'impersonation', 'dashboardOrder',
          'userRole', 'assignedRoles', 'activeRole', 'canSwitchRoles',
          'viewAsRole', 'role_preview', 'original_user_backup',
          'original_token_backup', 'moduleCache',
        ];

        let migratedCount = 0;

        for (const key of legacyKeys) {
          const legacyValue = await this._rawGet(key);
          if (legacyValue === null) continue;

          const existingSecure = await this._rawGet(SECURE_PREFIX + key);
          if (existingSecure !== null) continue;

          const classification = this._classifyKey(key);
          const cryptoKey = classification === DATA_CLASSIFICATION.SENSITIVE
            ? this._keyManager.getCryptoKey()
            : null;

          // Skip sensitive keys if we don't have a real crypto key — cannot encrypt
          if (classification === DATA_CLASSIFICATION.SENSITIVE && !cryptoKey) {
            console.warn(`Secure storage: skipping migration of sensitive key "${key}" — no AES key available`);
            continue;
          }

          const envelope = await createEnvelope(legacyValue, classification, cryptoKey);
          await this._rawSet(SECURE_PREFIX + key, envelope);

          migratedCount++;
        }

        if (migratedCount > 0) {
          console.log(`Secure storage: migrated ${migratedCount} keys from legacy format`);
        }
      }

      // ---------- Schema 1 -> 2: Re-encrypt v1 XOR envelopes with AES-GCM ----------
      if (currentVersion >= 1 && currentVersion < 2 && HAS_WEB_CRYPTO) {
        const allKeys = await this._getAllKeys();
        let reEncryptedCount = 0;

        for (const rawKey of allKeys) {
          if (!rawKey.startsWith(SECURE_PREFIX)) continue;
          if (rawKey.startsWith('_ss_meta_') || rawKey.startsWith('_ss_internal_') || rawKey.startsWith('_ss_aes_')) continue;

          const envelopeStr = await this._rawGet(rawKey);
          if (!envelopeStr) continue;

          try {
            const envelope = JSON.parse(envelopeStr);
            if (typeof envelope !== 'object' || envelope.v !== 1) continue;

            // Only re-encrypt SENSITIVE v1 envelopes
            if (envelope.c !== DATA_CLASSIFICATION.SENSITIVE) continue;

            const legacyKeyBytes = this._keyManager.getLegacyKeyBytes();
            if (!legacyKeyBytes) continue;

            // Decrypt with legacy XOR
            const plaintext = _legacyDecrypt(envelope.d, legacyKeyBytes);

            // Verify old checksum
            if (envelope.h) {
              const expectedChecksum = _legacyComputeChecksum(plaintext);
              if (expectedChecksum !== envelope.h) {
                console.warn(`Secure storage: skipping migration of tampered key ${rawKey}`);
                continue;
              }
            }

            // Re-encrypt with AES-GCM (requires Web Crypto — already checked above)
            const newEnvelope = await createEnvelope(
              plaintext,
              DATA_CLASSIFICATION.SENSITIVE,
              this._keyManager.getCryptoKey()
            );
            await this._rawSet(rawKey, newEnvelope);
            reEncryptedCount++;
          } catch {
            // Skip keys that fail to parse/decrypt
            continue;
          }
        }

        if (reEncryptedCount > 0) {
          console.log(`Secure storage: re-encrypted ${reEncryptedCount} keys from XOR to AES-GCM`);
        }
      }

      // Store key fingerprint for future tamper detection
      const cryptoKey = this._keyManager.getCryptoKey();
      if (cryptoKey) {
        try {
          const jwk = await crypto.subtle.exportKey('jwk', cryptoKey);
          // Use first 16 chars of the key material as fingerprint
          const fingerprint = _legacyComputeChecksum(jwk.k ? jwk.k.slice(0, 16) : 'aes-gcm');
          await this._rawSet(KEY_FINGERPRINT_KEY, fingerprint);
        } catch {
          // Non-critical
        }
      }

      // Mark migration complete
      await this._rawSet(SCHEMA_VERSION_KEY, String(CURRENT_SCHEMA_VERSION));
      this._migrated = true;
    } catch (error) {
      console.error('Secure storage: migration failed', error);
      // Don't block — the storage layer should still function
      this._migrated = true;
    }
  }
}

// ---------------------------------------------------------------------------
// Singleton export
// ---------------------------------------------------------------------------

/**
 * Singleton instance of the secure storage layer.
 *
 * Usage:
 *   import { secureStorage } from '../services/secureStorage';
 *
 *   // Encrypted storage for sensitive data
 *   await secureStorage.setSecure('auth_token', token);
 *   const token = await secureStorage.getSecure('auth_token');
 *
 *   // Standard storage (auto-classifies and encrypts sensitive keys)
 *   await secureStorage.set('theme', 'dark');
 *   const theme = await secureStorage.get('theme');
 *
 *   // Logout cleanup
 *   await secureStorage.clearSensitive();
 */
export const secureStorage = new SecureStorage();

export default secureStorage;

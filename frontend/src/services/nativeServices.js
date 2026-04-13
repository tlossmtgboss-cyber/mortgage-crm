/**
 * Native Mobile Services
 *
 * Provides access to native iOS features via Capacitor:
 * - Push Notifications
 * - Biometric Authentication (Face ID / Touch ID)
 * - Camera & Photo Library
 * - Haptic Feedback
 */

import { Capacitor } from '@capacitor/core';
import { PushNotifications } from '@capacitor/push-notifications';
import { Camera, CameraResultType, CameraSource } from '@capacitor/camera';
import { Haptics, ImpactStyle, NotificationType } from '@capacitor/haptics';
import { NativeBiometric, BiometryType } from '@capgo/capacitor-native-biometric';

// Check if running on native platform
export const isNative = Capacitor.isNativePlatform();
export const platform = Capacitor.getPlatform();

// ============================================================================
// PUSH NOTIFICATIONS
// ============================================================================

export const pushNotifications = {
  /**
   * Request permission and register for push notifications
   * Returns the device token on success
   */
  async register() {
    if (!isNative) {
      console.log('Push notifications not available on web');
      return null;
    }

    try {
      // Request permission
      const permission = await PushNotifications.requestPermissions();

      if (permission.receive === 'granted') {
        // Register with APNs
        await PushNotifications.register();

        // Return promise that resolves with token
        return new Promise((resolve, reject) => {
          PushNotifications.addListener('registration', (token) => {
            console.log('Push registration success, token:', token.value);
            resolve(token.value);
          });

          PushNotifications.addListener('registrationError', (error) => {
            console.error('Push registration error:', error);
            reject(error);
          });
        });
      } else {
        console.log('Push notification permission denied');
        return null;
      }
    } catch (error) {
      console.error('Error registering for push notifications:', error);
      throw error;
    }
  },

  /**
   * Add listener for incoming push notifications
   */
  onNotificationReceived(callback) {
    if (!isNative) return () => {};

    const listener = PushNotifications.addListener('pushNotificationReceived', (notification) => {
      console.log('Push notification received:', notification);
      callback(notification);
    });

    return () => listener.remove();
  },

  /**
   * Add listener for notification tap (when user taps notification)
   */
  onNotificationTapped(callback) {
    if (!isNative) return () => {};

    const listener = PushNotifications.addListener('pushNotificationActionPerformed', (action) => {
      console.log('Push notification action:', action);
      callback(action);
    });

    return () => listener.remove();
  },

  /**
   * Get list of delivered notifications
   */
  async getDelivered() {
    if (!isNative) return [];
    return await PushNotifications.getDeliveredNotifications();
  },

  /**
   * Remove all delivered notifications
   */
  async clearAll() {
    if (!isNative) return;
    await PushNotifications.removeAllDeliveredNotifications();
  }
};

// ============================================================================
// BIOMETRIC AUTHENTICATION (Face ID / Touch ID)
// ============================================================================

export const biometrics = {
  /**
   * Check if biometric auth is available on this device
   */
  async isAvailable() {
    if (!isNative) return { available: false, biometryType: 'none' };

    try {
      const result = await NativeBiometric.isAvailable();
      return {
        available: result.isAvailable,
        biometryType: result.biometryType === BiometryType.FACE_ID ? 'faceId'
                    : result.biometryType === BiometryType.TOUCH_ID ? 'touchId'
                    : result.biometryType === BiometryType.FINGERPRINT ? 'fingerprint'
                    : 'none'
      };
    } catch (error) {
      console.error('Error checking biometric availability:', error);
      return { available: false, biometryType: 'none' };
    }
  },

  /**
   * Authenticate user with biometrics
   */
  async authenticate(reason = 'Verify your identity') {
    if (!isNative) {
      console.log('Biometric auth not available on web');
      return false;
    }

    try {
      await NativeBiometric.verifyIdentity({
        reason,
        title: 'Perennia AI',
        subtitle: 'Log in with biometrics',
        description: reason,
      });
      return true;
    } catch (error) {
      console.error('Biometric authentication failed:', error);
      return false;
    }
  },

  /**
   * Store credentials securely with biometric protection
   */
  async storeCredentials(server, username, password) {
    if (!isNative) return false;

    try {
      await NativeBiometric.setCredentials({
        username,
        password,
        server,
      });
      return true;
    } catch (error) {
      console.error('Error storing credentials:', error);
      return false;
    }
  },

  /**
   * Retrieve stored credentials (requires biometric auth)
   */
  async getCredentials(server) {
    if (!isNative) return null;

    try {
      const credentials = await NativeBiometric.getCredentials({ server });
      return credentials;
    } catch (error) {
      console.error('Error retrieving credentials:', error);
      return null;
    }
  },

  /**
   * Delete stored credentials
   */
  async deleteCredentials(server) {
    if (!isNative) return false;

    try {
      await NativeBiometric.deleteCredentials({ server });
      return true;
    } catch (error) {
      console.error('Error deleting credentials:', error);
      return false;
    }
  }
};

// ============================================================================
// CAMERA & PHOTOS
// ============================================================================

export const camera = {
  /**
   * Take a photo with the camera
   */
  async takePhoto(options = {}) {
    try {
      const image = await Camera.getPhoto({
        quality: options.quality || 90,
        allowEditing: options.allowEditing || false,
        resultType: CameraResultType.Base64,
        source: CameraSource.Camera,
        width: options.width,
        height: options.height,
      });

      return {
        base64: image.base64String,
        format: image.format,
        dataUrl: `data:image/${image.format};base64,${image.base64String}`
      };
    } catch (error) {
      console.error('Error taking photo:', error);
      throw error;
    }
  },

  /**
   * Pick a photo from the gallery
   */
  async pickFromGallery(options = {}) {
    try {
      const image = await Camera.getPhoto({
        quality: options.quality || 90,
        allowEditing: options.allowEditing || false,
        resultType: CameraResultType.Base64,
        source: CameraSource.Photos,
        width: options.width,
        height: options.height,
      });

      return {
        base64: image.base64String,
        format: image.format,
        dataUrl: `data:image/${image.format};base64,${image.base64String}`
      };
    } catch (error) {
      console.error('Error picking photo:', error);
      throw error;
    }
  },

  /**
   * Show prompt to choose camera or gallery
   */
  async pickPhoto(options = {}) {
    try {
      const image = await Camera.getPhoto({
        quality: options.quality || 90,
        allowEditing: options.allowEditing || false,
        resultType: CameraResultType.Base64,
        source: CameraSource.Prompt, // Shows action sheet to choose
        promptLabelHeader: 'Select Photo',
        promptLabelCancel: 'Cancel',
        promptLabelPhoto: 'From Gallery',
        promptLabelPicture: 'Take Photo',
        width: options.width,
        height: options.height,
      });

      return {
        base64: image.base64String,
        format: image.format,
        dataUrl: `data:image/${image.format};base64,${image.base64String}`
      };
    } catch (error) {
      if (error.message?.includes('User cancelled')) {
        return null;
      }
      console.error('Error picking photo:', error);
      throw error;
    }
  },

  /**
   * Check camera permissions
   */
  async checkPermissions() {
    try {
      const permissions = await Camera.checkPermissions();
      return permissions;
    } catch (error) {
      console.error('Error checking camera permissions:', error);
      return { camera: 'denied', photos: 'denied' };
    }
  }
};

// ============================================================================
// HAPTIC FEEDBACK
// ============================================================================

export const haptics = {
  /**
   * Light impact feedback (subtle tap)
   */
  async light() {
    if (!isNative) return;
    await Haptics.impact({ style: ImpactStyle.Light });
  },

  /**
   * Medium impact feedback
   */
  async medium() {
    if (!isNative) return;
    await Haptics.impact({ style: ImpactStyle.Medium });
  },

  /**
   * Heavy impact feedback
   */
  async heavy() {
    if (!isNative) return;
    await Haptics.impact({ style: ImpactStyle.Heavy });
  },

  /**
   * Success notification feedback
   */
  async success() {
    if (!isNative) return;
    await Haptics.notification({ type: NotificationType.Success });
  },

  /**
   * Warning notification feedback
   */
  async warning() {
    if (!isNative) return;
    await Haptics.notification({ type: NotificationType.Warning });
  },

  /**
   * Error notification feedback
   */
  async error() {
    if (!isNative) return;
    await Haptics.notification({ type: NotificationType.Error });
  },

  /**
   * Selection changed feedback (very subtle)
   */
  async selection() {
    if (!isNative) return;
    await Haptics.selectionChanged();
  },

  /**
   * Vibrate for specified duration
   */
  async vibrate(duration = 300) {
    if (!isNative) return;
    await Haptics.vibrate({ duration });
  }
};

// ============================================================================
// MICROPHONE
// ============================================================================

export const microphone = {
  /**
   * Check if microphone permission is granted
   * Uses the Permissions API where available, otherwise attempts getUserMedia
   */
  async checkPermission() {
    try {
      if (navigator.permissions) {
        const result = await navigator.permissions.query({ name: 'microphone' });
        return result.state; // 'granted', 'denied', 'prompt'
      }
      // Fallback: try getUserMedia briefly
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop());
      return 'granted';
    } catch (error) {
      if (error.name === 'NotAllowedError') return 'denied';
      return 'prompt';
    }
  },

  /**
   * Request microphone permission by triggering getUserMedia
   * On iOS, this will show the system permission dialog
   */
  async requestPermission() {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(track => track.stop());
      return true;
    } catch (error) {
      console.error('Microphone permission denied:', error);
      return false;
    }
  },
};

// ============================================================================
// EXPORT ALL
// ============================================================================

export default {
  isNative,
  platform,
  pushNotifications,
  biometrics,
  camera,
  haptics,
  microphone,
};

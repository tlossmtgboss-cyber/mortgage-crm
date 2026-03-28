/**
 * usePushNotifications Hook
 *
 * Manages push notification registration and handling for the mobile app.
 * Registers device tokens with the backend and handles incoming notifications.
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { Capacitor } from '@capacitor/core';
import { pushNotifications, isNative } from '../services/nativeServices';
import { API_BASE_URL } from '../services/api';

export function usePushNotifications() {
  const [isRegistered, setIsRegistered] = useState(false);
  const [deviceToken, setDeviceToken] = useState(null);
  const [error, setError] = useState(null);
  const [isLoading, setIsLoading] = useState(false);
  const notificationListeners = useRef([]);

  /**
   * Register for push notifications and send token to backend
   */
  const register = useCallback(async () => {
    if (!isNative) {
      console.log('Push notifications not available on web');
      return null;
    }

    setIsLoading(true);
    setError(null);

    try {
      const token = await pushNotifications.register();

      if (token) {
        setDeviceToken(token);

        // Send token to backend
        const authToken = localStorage.getItem('token');
        if (authToken) {
          const response = await fetch(`${API_BASE_URL}/api/v1/push/register`, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Authorization': `Bearer ${authToken}`,
            },
            body: JSON.stringify({
              device_token: token,
              platform: Capacitor.getPlatform(),
            }),
          });

          if (response.ok) {
            setIsRegistered(true);
            console.log('Push notification token registered with backend');
          } else {
            console.error('Failed to register token with backend');
          }
        }

        return token;
      }
    } catch (err) {
      console.error('Error registering for push notifications:', err);
      setError(err.message);
    } finally {
      setIsLoading(false);
    }

    return null;
  }, []);

  /**
   * Add a listener for incoming notifications
   */
  const onNotification = useCallback((callback) => {
    if (!isNative) return () => {};

    const removeReceived = pushNotifications.onNotificationReceived(callback);
    const removeTapped = pushNotifications.onNotificationTapped((action) => {
      callback(action.notification, { tapped: true, actionId: action.actionId });
    });

    return () => {
      removeReceived();
      removeTapped();
    };
  }, []);

  /**
   * Clear all delivered notifications
   */
  const clearNotifications = useCallback(async () => {
    if (!isNative) return;
    await pushNotifications.clearAll();
  }, []);

  /**
   * Get badge count (delivered notifications)
   */
  const getBadgeCount = useCallback(async () => {
    if (!isNative) return 0;
    const delivered = await pushNotifications.getDelivered();
    return delivered.notifications?.length || 0;
  }, []);

  // Auto-register on mount if user is logged in
  useEffect(() => {
    const token = localStorage.getItem('token');
    if (token && isNative) {
      register();
    }
  }, [register]);

  return {
    // State
    isNative,
    isRegistered,
    deviceToken,
    error,
    isLoading,

    // Actions
    register,
    onNotification,
    clearNotifications,
    getBadgeCount,
  };
}

export default usePushNotifications;

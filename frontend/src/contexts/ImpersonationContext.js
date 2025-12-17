import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { getJSON, setJSON, removeItem, STORAGE_KEYS } from '../utils/storage';

const ImpersonationContext = createContext();

export const useImpersonation = () => {
  const context = useContext(ImpersonationContext);
  if (!context) {
    throw new Error('useImpersonation must be used within ImpersonationProvider');
  }
  return context;
};

export const ImpersonationProvider = ({ children }) => {
  const [impersonationData, setImpersonationData] = useState(null);
  const [isImpersonating, setIsImpersonating] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Load impersonation state from storage on mount
  useEffect(() => {
    const loadImpersonationData = async () => {
      try {
        const data = await getJSON(STORAGE_KEYS.IMPERSONATION);
        if (data) {
          // Check if session is still valid
          const expiresAt = new Date(data.expires_at);
          if (expiresAt > new Date()) {
            setImpersonationData(data);
            setIsImpersonating(true);
          } else {
            // Session expired, clear it
            await removeItem(STORAGE_KEYS.IMPERSONATION);
          }
        }
      } catch (error) {
        console.error('Error loading impersonation data:', error);
        await removeItem(STORAGE_KEYS.IMPERSONATION);
      } finally {
        setIsLoading(false);
      }
    };

    loadImpersonationData();
  }, []);

  const startImpersonation = useCallback(async (sessionData) => {
    setImpersonationData(sessionData);
    setIsImpersonating(true);
    await setJSON(STORAGE_KEYS.IMPERSONATION, sessionData);
  }, []);

  const endImpersonation = useCallback(async () => {
    setImpersonationData(null);
    setIsImpersonating(false);
    await removeItem(STORAGE_KEYS.IMPERSONATION);
  }, []);

  const getSessionToken = useCallback(() => {
    return impersonationData?.session_token || null;
  }, [impersonationData]);

  const getImpersonatedUser = useCallback(() => {
    return impersonationData?.impersonated_user || null;
  }, [impersonationData]);

  const getTimeRemaining = useCallback(() => {
    if (!impersonationData?.expires_at) return 0;
    const expiresAt = new Date(impersonationData.expires_at);
    const now = new Date();
    const remaining = Math.max(0, Math.floor((expiresAt - now) / 1000));
    return remaining;
  }, [impersonationData]);

  const value = {
    isImpersonating,
    isLoading,
    impersonationData,
    startImpersonation,
    endImpersonation,
    getSessionToken,
    getImpersonatedUser,
    getTimeRemaining
  };

  return (
    <ImpersonationContext.Provider value={value}>
      {children}
    </ImpersonationContext.Provider>
  );
};

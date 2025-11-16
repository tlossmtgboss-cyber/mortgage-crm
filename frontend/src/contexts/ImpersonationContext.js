import React, { createContext, useContext, useState, useEffect } from 'react';

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

  // Load impersonation state from localStorage on mount
  useEffect(() => {
    const savedData = localStorage.getItem('impersonation');
    if (savedData) {
      try {
        const data = JSON.parse(savedData);
        // Check if session is still valid
        const expiresAt = new Date(data.expires_at);
        if (expiresAt > new Date()) {
          setImpersonationData(data);
          setIsImpersonating(true);
        } else {
          // Session expired, clear it
          localStorage.removeItem('impersonation');
        }
      } catch (error) {
        console.error('Error loading impersonation data:', error);
        localStorage.removeItem('impersonation');
      }
    }
  }, []);

  const startImpersonation = (sessionData) => {
    setImpersonationData(sessionData);
    setIsImpersonating(true);
    localStorage.setItem('impersonation', JSON.stringify(sessionData));
  };

  const endImpersonation = () => {
    setImpersonationData(null);
    setIsImpersonating(false);
    localStorage.removeItem('impersonation');
  };

  const getSessionToken = () => {
    return impersonationData?.session_token || null;
  };

  const getImpersonatedUser = () => {
    return impersonationData?.impersonated_user || null;
  };

  const getTimeRemaining = () => {
    if (!impersonationData?.expires_at) return 0;
    const expiresAt = new Date(impersonationData.expires_at);
    const now = new Date();
    const remaining = Math.max(0, Math.floor((expiresAt - now) / 1000));
    return remaining;
  };

  const value = {
    isImpersonating,
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

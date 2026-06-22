import React, { createContext, useContext, useState, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';

const RecruitPlatformContext = createContext(null);

function decodeJWT(token) {
  try {
    const base64 = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
    return JSON.parse(atob(base64));
  } catch {
    return null;
  }
}

function isTokenExpired(token) {
  const payload = decodeJWT(token);
  if (!payload || !payload.exp) return true;
  return Date.now() / 1000 > payload.exp - 30; // 30s buffer
}

export function RecruitPlatformProvider({ children }) {
  const [recruitToken, setRecruitToken] = useState(() => localStorage.getItem('recruit_auth_token'));
  const [recruitUser, setRecruitUser] = useState(() => {
    const token = localStorage.getItem('recruit_auth_token');
    return token ? decodeJWT(token) : null;
  });
  const navigate = useNavigate();
  const refreshingRef = useRef(null); // deduplicate concurrent refresh calls

  const _setToken = (token) => {
    localStorage.setItem('recruit_auth_token', token);
    setRecruitToken(token);
    setRecruitUser(decodeJWT(token));
  };

  const logout = useCallback(() => {
    localStorage.removeItem('recruit_auth_token');
    localStorage.removeItem('recruit_refresh_token');
    setRecruitToken(null);
    setRecruitUser(null);
    navigate('/recruit/login');
  }, [navigate]);

  const login = async (email, password) => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ x1: email, x2: password }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      const detail = err.detail;
      const message = Array.isArray(detail)
        ? (detail[0]?.msg || 'Invalid email or password')
        : (typeof detail === 'string' ? detail : 'Invalid email or password');
      throw new Error(message);
    }
    const data = await response.json();
    _setToken(data.access_token);
    if (data.refresh_token) {
      localStorage.setItem('recruit_refresh_token', data.refresh_token);
    }
    return decodeJWT(data.access_token);
  };

  // Returns the new access token, or null if refresh failed (triggers logout).
  const refreshAccessToken = useCallback(async () => {
    if (refreshingRef.current) return refreshingRef.current; // deduplicate
    const refreshToken = localStorage.getItem('recruit_refresh_token');
    if (!refreshToken) { logout(); return null; }

    refreshingRef.current = (async () => {
      try {
        const res = await fetch('/token/refresh', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
        if (!res.ok) { logout(); return null; }
        const data = await res.json();
        _setToken(data.access_token);
        if (data.refresh_token) {
          localStorage.setItem('recruit_refresh_token', data.refresh_token);
        }
        return data.access_token;
      } catch {
        logout();
        return null;
      } finally {
        refreshingRef.current = null;
      }
    })();

    return refreshingRef.current;
  }, [logout]);

  // Fetch wrapper: injects auth header, auto-refreshes on 401, retries once.
  const fetchWithAuth = useCallback(async (url, options = {}) => {
    let token = localStorage.getItem('recruit_auth_token');

    // Proactively refresh if token is near expiry
    if (token && isTokenExpired(token)) {
      token = await refreshAccessToken();
      if (!token) return new Response(null, { status: 401 });
    }

    const makeReq = (t) => fetch(url, {
      ...options,
      headers: {
        ...(options.headers || {}),
        Authorization: `Bearer ${t}`,
        ...(!(options.headers?.['Content-Type']) && !(options.body instanceof FormData)
          ? { 'Content-Type': 'application/json' } : {}),
      },
    });

    let res = await makeReq(token);

    // On 401 try one refresh + retry
    if (res.status === 401) {
      const newToken = await refreshAccessToken();
      if (!newToken) return res;
      res = await makeReq(newToken);
    }

    return res;
  }, [refreshAccessToken]);

  const isAuthenticated = Boolean(recruitToken && recruitUser);
  const isPlatformAdmin = recruitUser?.role === 'platform_admin';

  return (
    <RecruitPlatformContext.Provider value={{
      recruitToken,
      recruitUser,
      login,
      logout,
      isAuthenticated,
      isPlatformAdmin,
      fetchWithAuth,
      refreshAccessToken,
    }}>
      {children}
    </RecruitPlatformContext.Provider>
  );
}

export function useRecruitPlatform() {
  const ctx = useContext(RecruitPlatformContext);
  if (!ctx) throw new Error('useRecruitPlatform must be used inside RecruitPlatformProvider');
  return ctx;
}

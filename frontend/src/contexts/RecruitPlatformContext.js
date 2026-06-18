import React, { createContext, useContext, useState } from 'react';
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

export function RecruitPlatformProvider({ children }) {
  const [recruitToken, setRecruitToken] = useState(() => localStorage.getItem('recruit_auth_token'));
  const [recruitUser, setRecruitUser] = useState(() => {
    const token = localStorage.getItem('recruit_auth_token');
    return token ? decodeJWT(token) : null;
  });
  const navigate = useNavigate();

  const login = async (email, password) => {
    const response = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password }),
    });
    if (!response.ok) {
      const err = await response.json().catch(() => ({}));
      throw new Error(err.detail || 'Invalid email or password');
    }
    const data = await response.json();
    const token = data.access_token;
    const user = decodeJWT(token);
    localStorage.setItem('recruit_auth_token', token);
    setRecruitToken(token);
    setRecruitUser(user);
    return user;
  };

  const logout = () => {
    localStorage.removeItem('recruit_auth_token');
    setRecruitToken(null);
    setRecruitUser(null);
    navigate('/recruit/login');
  };

  const isAuthenticated = Boolean(recruitToken && recruitUser);
  const isPlatformAdmin = recruitUser?.role === 'platform_admin';

  return (
    <RecruitPlatformContext.Provider value={{ recruitToken, recruitUser, login, logout, isAuthenticated, isPlatformAdmin }}>
      {children}
    </RecruitPlatformContext.Provider>
  );
}

export function useRecruitPlatform() {
  const ctx = useContext(RecruitPlatformContext);
  if (!ctx) throw new Error('useRecruitPlatform must be used inside RecruitPlatformProvider');
  return ctx;
}

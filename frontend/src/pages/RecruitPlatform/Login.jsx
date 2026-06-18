import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useRecruitPlatform } from '../../contexts/RecruitPlatformContext';
import './Login.css';

export default function RecruitLogin() {
  const { login, isAuthenticated } = useRecruitPlatform();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (isAuthenticated) {
      navigate('/recruit/dashboard', { replace: true });
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const user = await login(email, password);
      if (user?.role === 'platform_admin') {
        navigate('/recruit/license-manager', { replace: true });
      } else {
        navigate('/recruit/dashboard', { replace: true });
      }
    } catch (err) {
      setError(err.message || 'Invalid email or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="recruit-login-page">
      <div className="recruit-login-left">
        <div className="recruit-login-brand">
          <svg className="recruit-brand-icon" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
            <rect width="48" height="48" rx="12" fill="#3b82f6"/>
            <path d="M14 34V20a2 2 0 012-2h16a2 2 0 012 2v14" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            <path d="M10 34h28" stroke="white" strokeWidth="2.5" strokeLinecap="round"/>
            <path d="M20 18v-4a2 2 0 012-2h4a2 2 0 012 2v4" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"/>
            <rect x="20" y="24" width="8" height="6" rx="1" stroke="white" strokeWidth="2"/>
          </svg>
          <span className="recruit-brand-name">Perennia Recruit</span>
        </div>
        <h1 className="recruit-login-headline">Recruit top talent.<br/>Manage smarter.</h1>
        <p className="recruit-login-subtext">The AI-powered recruiting platform built for mortgage professionals.</p>
      </div>
      <div className="recruit-login-right">
        <div className="recruit-login-card">
          <h2>Sign in to your account</h2>
          {error && <div className="recruit-login-error">{error}</div>}
          <form onSubmit={handleSubmit} className="recruit-login-form">
            <div className="recruit-form-group">
              <label htmlFor="recruit-email">Email address</label>
              <input
                id="recruit-email"
                type="email"
                value={email}
                onChange={e => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="you@example.com"
              />
            </div>
            <div className="recruit-form-group">
              <label htmlFor="recruit-password">Password</label>
              <input
                id="recruit-password"
                type="password"
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="••••••••"
              />
            </div>
            <div className="recruit-login-forgot">
              <a href="mailto:support@perenniaai.com">Forgot password?</a>
            </div>
            <button type="submit" disabled={loading} className="recruit-login-btn">
              {loading ? 'Signing in...' : 'Sign in'}
            </button>
          </form>
          <p className="recruit-login-footer">Powered by Perennia AI</p>
        </div>
      </div>
    </div>
  );
}

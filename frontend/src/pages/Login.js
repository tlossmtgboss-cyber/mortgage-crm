import React, { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { Capacitor } from '@capacitor/core';
import { authAPI, API_BASE_URL } from '../services/api';
import { setAuth, isAuthenticated } from '../utils/auth';
import { getUserEffectiveRole, getDefaultRouteForRole } from '../config/roleConfig';
import { useBiometricLogin } from '../hooks/useBiometricLogin';
import { haptics } from '../services/nativeServices';
import { consumePendingDeepLink } from '../services/deepLinkRouter';
import './Login.css';

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showEnableBiometric, setShowEnableBiometric] = useState(false);
  const [pendingCredentials, setPendingCredentials] = useState(null);
  const [pendingRoute, setPendingRoute] = useState(null);
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const rawRedirect = searchParams.get('redirect') || null;
  const isValidRedirect = (path) => {
    if (!path) return false;
    return path.startsWith('/') && !path.startsWith('//') && !path.includes('://');
  };
  const redirectTo = isValidRedirect(rawRedirect) ? rawRedirect : null;

  const {
    isAvailable: biometricAvailable,
    biometryDisplayName,
    hasStoredCredentials,
    isNative,
    authenticateWithBiometrics,
    enableBiometricLogin,
  } = useBiometricLogin();

  // Try biometric login on mount if available
  useEffect(() => {
    if (biometricAvailable && hasStoredCredentials) {
      handleBiometricLogin();
    }
  }, [biometricAvailable, hasStoredCredentials]);

  // Authenticate only — returns user data, does NOT navigate
  const authenticate = async (loginEmail, loginPassword) => {
    const data = await authAPI.login(loginEmail, loginPassword);

    if (!data.access_token) {
      throw new Error('No token received from server');
    }

    await setAuth(data.access_token, data.user, data.refresh_token);

    const authenticated = await isAuthenticated();
    if (!authenticated) {
      throw new Error('Could not save authentication');
    }

    return data;
  };

  const getPostLoginRoute = (data) => {
    if (redirectTo) return redirectTo;
    // Check for a pending deep link queued before auth (e.g. push notification tap)
    const pendingDeepLink = consumePendingDeepLink();
    if (pendingDeepLink) return pendingDeepLink;
    // Native app and mobile browsers go to dashboard (Aria is accessible via FAB)
    if (Capacitor.isNativePlatform()) return '/dashboard';
    const isMobileBrowser = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if (isMobileBrowser) return '/dashboard';
    const permissionRole = data?.user?.permission_role || 'sales';
    const legacyRole = data?.user?.role || null;
    const effectiveRole = getUserEffectiveRole(permissionRole, legacyRole);
    return getDefaultRouteForRole(effectiveRole);
  };

  const handleBiometricLogin = async () => {
    setError('');
    setLoading(true);

    try {
      const credentials = await authenticateWithBiometrics();

      if (credentials) {
        const data = await authenticate(credentials.username, credentials.password);
        haptics.success();
        navigate(getPostLoginRoute(data));
      }
    } catch (err) {
      console.error('Biometric login error:', err);
      haptics.error();
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const data = await authenticate(email, password);

      // If biometric is available but not set up, offer to enable it
      if (biometricAvailable && !hasStoredCredentials) {
        setPendingCredentials({ email, password });
        setPendingRoute(getPostLoginRoute(data));
        setShowEnableBiometric(true);
        setLoading(false);
        return;
      }

      haptics.success();
      navigate(getPostLoginRoute(data));
    } catch (err) {
      console.error('Login error:', err);
      const errorMessage = err.response?.data?.detail || err.response?.data?.error || err.message || 'Login failed. Please check your credentials and try again.';
      setError(errorMessage);
      haptics.error();
    } finally {
      setLoading(false);
    }
  };

  const handleEnableBiometric = async () => {
    if (pendingCredentials) {
      const enabled = await enableBiometricLogin(pendingCredentials.email, pendingCredentials.password);
      if (enabled) {
        haptics.success();
      }
    }
    setShowEnableBiometric(false);
    navigate(pendingRoute || '/dashboard');
  };

  const handleSkipBiometric = () => {
    setShowEnableBiometric(false);
    navigate(pendingRoute || '/dashboard');
  };

  // Show biometric enable prompt
  if (showEnableBiometric) {
    return (
      <div className="login-container">
        <div className="login-box">
          <div className="login-header">
            <h1>Enable {biometryDisplayName}?</h1>
            <p>Sign in faster next time</p>
          </div>

          <div className="biometric-prompt">
            <div className="biometric-icon">
              {biometryDisplayName === 'Face ID' ? '👤' : '👆'}
            </div>
            <p>Would you like to enable {biometryDisplayName} for quick sign in?</p>

            <button
              className="btn-primary"
              onClick={handleEnableBiometric}
            >
              Enable {biometryDisplayName}
            </button>

            <button
              className="btn-secondary"
              onClick={handleSkipBiometric}
              style={{ marginTop: '12px' }}
            >
              Not Now
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-container">
      <div className="login-box">
        <div className="login-header">
          <h1>Aria</h1>
          <p>AI-Powered Loan Officer OS</p>
        </div>

        {/* Biometric Login Button */}
        {biometricAvailable && hasStoredCredentials && (
          <div className="biometric-login-section">
            <button
              className="btn-biometric"
              onClick={handleBiometricLogin}
              disabled={loading}
            >
              <span className="biometric-icon">
                {biometryDisplayName === 'Face ID' ? '👤' : '👆'}
              </span>
              Sign in with {biometryDisplayName}
            </button>
            <div className="divider">or</div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="login-form">
          <div className="form-group">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Enter your email"
              required
              disabled={loading}
            />
          </div>

          <div className="form-group">
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter your password"
              required
              disabled={loading}
            />
          </div>

          <div className="forgot-password-link">
            <Link to="/forgot-password">Forgot Password?</Link>
          </div>

          {error && <div className="error-message">{error}</div>}

          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Logging in...' : 'Login'}
          </button>
        </form>
      </div>
    </div>
  );
}

export default Login;

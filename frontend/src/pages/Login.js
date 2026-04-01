import React, { useState, useEffect } from 'react';
import { useNavigate, Link, useSearchParams } from 'react-router-dom';
import axios from 'axios';
import { authAPI, API_BASE_URL } from '../services/api';
import { setAuth } from '../utils/auth';
import { getUserEffectiveRole, getDefaultRouteForRole } from '../config/roleConfig';
import { useBiometricLogin } from '../hooks/useBiometricLogin';
import { haptics } from '../services/nativeServices';
import './Login.css';

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [showEnableBiometric, setShowEnableBiometric] = useState(false);
  const [pendingCredentials, setPendingCredentials] = useState(null);
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

  const handleBiometricLogin = async () => {
    setError('');
    setLoading(true);

    try {
      const credentials = await authenticateWithBiometrics();

      if (credentials) {
        // Login with stored credentials
        await performLogin(credentials.username, credentials.password);
        haptics.success();
      }
    } catch (err) {
      console.error('Biometric login error:', err);
      haptics.error();
    } finally {
      setLoading(false);
    }
  };

  const performLogin = async (loginEmail, loginPassword) => {
    const data = await authAPI.login(loginEmail, loginPassword);
    // Login successful

    if (!data.access_token) {
      throw new Error('No token received from server');
    }

    await setAuth(data.access_token, data.user);

    const savedToken = localStorage.getItem('token');
    if (!savedToken) {
      throw new Error('Could not save authentication');
    }

    // Check for redirect parameter first, then use role-based default route
    if (redirectTo) {
      navigate(redirectTo);
      return;
    }

    // Determine role-based default route
    const permissionRole = data.user?.permission_role || 'sales';
    const legacyRole = data.user?.role || null;
    const effectiveRole = getUserEffectiveRole(permissionRole, legacyRole);
    const defaultRoute = getDefaultRouteForRole(effectiveRole);

    navigate(defaultRoute);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    // Attempting login

    try {
      await performLogin(email, password);

      // If biometric is available but not set up, offer to enable it
      if (biometricAvailable && !hasStoredCredentials) {
        setPendingCredentials({ email, password });
        setShowEnableBiometric(true);
        setLoading(false);
        return;
      }

      haptics.success();
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
    // Continue with login regardless
    setShowEnableBiometric(false);
    if (pendingCredentials) {
      navigate(redirectTo || '/dashboard');
    }
  };

  const handleSkipBiometric = () => {
    setShowEnableBiometric(false);
    if (pendingCredentials) {
      navigate(redirectTo || '/dashboard');
    }
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
          <h1>Mortgage CRM</h1>
          <p>Agentic AI Platform</p>
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

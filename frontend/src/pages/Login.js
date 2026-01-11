import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { authAPI, API_BASE_URL } from '../services/api';
import { setAuth } from '../utils/auth';
import { getUserEffectiveRole, getDefaultRouteForRole } from '../config/roleConfig';
import './Login.css';

function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    console.log('Attempting login with:', email);

    try {
      const data = await authAPI.login(email, password);
      console.log('Login successful:', data);
      console.log('Token received:', data.access_token ? 'Yes (length: ' + data.access_token.length + ')' : 'NO TOKEN!');
      console.log('User received:', data.user);

      // Validate token exists before saving
      if (!data.access_token) {
        console.error('Login response missing access_token!', data);
        setError('Login failed: No token received from server');
        return;
      }

      await setAuth(data.access_token, data.user);

      // Verify token was saved
      const savedToken = localStorage.getItem('token');
      console.log('Token saved to localStorage:', savedToken ? 'Yes' : 'NO!');
      if (!savedToken) {
        console.error('Token failed to save to localStorage!');
        setError('Login failed: Could not save authentication');
        return;
      }

      // Determine role-based default route
      const permissionRole = data.user?.permission_role || 'sales';
      const legacyRole = data.user?.role || null;
      const effectiveRole = getUserEffectiveRole(permissionRole, legacyRole);
      const defaultRoute = getDefaultRouteForRole(effectiveRole);
      console.log('Role-based redirect:', { permissionRole, legacyRole, effectiveRole, defaultRoute });
      navigate(defaultRoute);
    } catch (err) {
      console.error('Login error:', err);
      console.error('Error response:', err.response);
      const errorMessage = err.response?.data?.detail || err.message || 'Login failed. Please check your credentials and try again.';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container">
      <div className="login-box">
        <div className="login-header">
          <h1>Mortgage CRM</h1>
          <p>Agentic AI Platform</p>
        </div>

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

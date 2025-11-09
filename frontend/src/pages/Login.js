import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { authAPI } from '../services/api';
import { setAuth } from '../utils/auth';
import './Login.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

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
      setAuth(data.access_token, data.user);
      navigate('/dashboard');
    } catch (err) {
      console.error('Login error:', err);
      console.error('Error response:', err.response);
      const errorMessage = err.response?.data?.detail || err.message || 'Login failed. Please check your credentials and try again.';
      setError(errorMessage);
    } finally {
      setLoading(false);
    }
  };

  const handleQuickTestLogin = async () => {
    setError('');
    setLoading(true);

    try {
      // Login with demo credentials
      const data = await authAPI.login('demo@example.com', 'demo123');
      setAuth(data.access_token, data.user);
      navigate('/dashboard');
    } catch (err) {
      setError('Quick test login failed. Please try again or contact support.');
      console.error('Quick login error:', err);
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

          <div className="divider">OR</div>

          <button
            type="button"
            className="btn-quick-test"
            onClick={handleQuickTestLogin}
            disabled={loading}
          >
            🚀 Quick Test Login (Auto-creates demo account)
          </button>
        </form>

        <div className="login-footer">
          <p>Need an account? <a href="/register">Sign up here</a></p>
          <div className="demo-credentials">
            <p className="note"><strong>Demo Credentials:</strong></p>
            <p className="note">Email: demo@example.com</p>
            <p className="note">Password: demo123</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Login;

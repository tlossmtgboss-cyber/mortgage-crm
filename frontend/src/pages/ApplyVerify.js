import { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';

/**
 * ApplyVerify - Handles magic link verification
 *
 * Redirects to the backend API to verify the magic link token,
 * which then redirects back to the frontend with an auth token.
 */
export default function ApplyVerify() {
  const [searchParams] = useSearchParams();

  useEffect(() => {
    const token = searchParams.get('token');

    if (token) {
      // Redirect to backend API for verification
      window.location.href = `${API_BASE_URL}/api/v1/borrower-auth/email/verify?token=${token}`;
    } else {
      // No token, redirect to login page
      window.location.href = '/apply/login';
    }
  }, [searchParams]);

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '100vh',
      background: '#f5f5f5'
    }}>
      <div style={{
        background: 'white',
        padding: '40px',
        borderRadius: '12px',
        textAlign: 'center',
        boxShadow: '0 2px 8px rgba(0,0,0,0.1)'
      }}>
        <h2 style={{ color: '#218D8D', marginBottom: '16px' }}>Verifying your login...</h2>
        <p style={{ color: '#6b7280' }}>Please wait while we verify your secure link.</p>
        <div style={{
          marginTop: '24px',
          width: '40px',
          height: '40px',
          border: '4px solid #e5e7eb',
          borderTopColor: '#218D8D',
          borderRadius: '50%',
          animation: 'spin 1s linear infinite',
          margin: '24px auto 0'
        }} />
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
        `}</style>
      </div>
    </div>
  );
}

import React, { useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';

import { POSContainer } from '../../features/pos';

const POSEntryPage: React.FC = () => {
  const [searchParams] = useSearchParams();

  const token = searchParams.get('token');
  const loanIdParam = searchParams.get('loan_id');
  const loanId = loanIdParam ? parseInt(loanIdParam, 10) : undefined;
  const borrowerName = searchParams.get('name') || 'there';
  const initials = searchParams.get('initials') || '';

  useEffect(() => {
    if (token) {
      localStorage.setItem('perennia_purl_token', token);
      (window as any).__PURL_TOKEN__ = token;
    }
    return () => {
      if (token) {
        localStorage.removeItem('perennia_purl_token');
        delete (window as any).__PURL_TOKEN__;
      }
    };
  }, [token]);

  if (!token && !localStorage.getItem('perennia_purl_token')) {
    return (
      <div style={{
        minHeight: '100vh',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        color: '#1F3D2E',
        padding: 40,
      }}>
        <div style={{
          width: 56, height: 56, borderRadius: 16,
          background: '#1F3D2E', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
          marginBottom: 24,
        }}>
          <svg width="28" height="28" viewBox="0 0 32 32" fill="none">
            <path d="M16 2 C 9 2 4 8 4 16 C 4 22 8 27 14 28 L 14 14 C 14 11 16 9 19 9 C 22 9 24 11 24 14 C 24 17 22 19 19 19 L 17 19 L 17 28 C 24 27 28 22 28 16 C 28 8 23 2 16 2 Z" fill="#F5F2E9" />
            <circle cx="19" cy="14" r="2.5" fill="#B8924A" />
          </svg>
        </div>
        <h1 style={{ fontSize: 24, fontWeight: 600, marginBottom: 8 }}>
          Perennia Loan Application
        </h1>
        <p style={{ fontSize: 15, color: '#6B7B75', maxWidth: 400, textAlign: 'center', lineHeight: 1.5 }}>
          To access your application, use the personalized link sent to your email or phone.
        </p>
        <p style={{ fontSize: 13, color: '#9CA8A2', marginTop: 24 }}>
          Contact your loan officer if you need a new link.
        </p>
      </div>
    );
  }

  return (
    <POSContainer
      loanId={loanId}
      borrowerName={borrowerName}
      userInitials={initials}
    />
  );
};

export default POSEntryPage;

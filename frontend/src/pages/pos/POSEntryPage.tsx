import React, { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { POSContainer } from '../../features/pos';

const API_BASE = '';

const POSEntryPage: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const tokenParam = searchParams.get('token');
  const loanIdParam = searchParams.get('loan_id');
  const loanId = loanIdParam ? parseInt(loanIdParam, 10) : undefined;

  const [purlToken, setPurlToken] = useState<string | null>(
    tokenParam || localStorage.getItem('perennia_purl_token'),
  );

  useEffect(() => {
    if (tokenParam) {
      localStorage.setItem('perennia_purl_token', tokenParam);
      (window as any).__PURL_TOKEN__ = tokenParam;
      setPurlToken(tokenParam);
    }
  }, [tokenParam]);

  if (!purlToken) {
    return <StartForm onStarted={(token) => {
      localStorage.setItem('perennia_purl_token', token);
      (window as any).__PURL_TOKEN__ = token;
      setPurlToken(token);
      setSearchParams({ token });
    }} />;
  }

  return (
    <POSContainer
      loanId={loanId}
      borrowerName={searchParams.get('name') || 'there'}
      userInitials={searchParams.get('initials') || ''}
    />
  );
};

function StartForm({ onStarted }: { onStarted: (token: string) => void }) {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const resp = await fetch(`${API_BASE}/api/v1/pos/start`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          phone: phone.trim() || null,
        }),
      });

      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.detail || 'Failed to start application');
      }

      const data = await resp.json();
      onStarted(data.token);
    } catch (err: any) {
      setError(err.message || 'Something went wrong');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="pos-start">
      <style>{`
        .pos-start {
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(135deg, #f8f7f4 0%, #eef0eb 100%);
          font-family: system-ui, -apple-system, sans-serif;
          padding: 24px;
        }
        .pos-start__card {
          width: 100%;
          max-width: 440px;
          background: #fff;
          border-radius: 16px;
          box-shadow: 0 4px 24px rgba(31,61,46,0.08);
          padding: 40px;
        }
        .pos-start__logo {
          width: 48px; height: 48px; border-radius: 12px;
          background: #1F3D2E; display: flex;
          align-items: center; justify-content: center;
          margin-bottom: 24px;
        }
        .pos-start__title {
          font-size: 24px; font-weight: 600; color: #1F3D2E;
          margin: 0 0 6px;
        }
        .pos-start__subtitle {
          font-size: 15px; color: #6B7B75; margin: 0 0 28px;
          line-height: 1.5;
        }
        .pos-start__field { margin-bottom: 16px; }
        .pos-start__label {
          display: block; font-size: 13px; font-weight: 500;
          color: #1F3D2E; margin-bottom: 6px;
        }
        .pos-start__input {
          width: 100%; padding: 10px 14px; border: 1px solid #d4d9d6;
          border-radius: 8px; font-size: 15px; font-family: inherit;
          outline: none; transition: border-color 0.15s;
          box-sizing: border-box;
        }
        .pos-start__input:focus { border-color: #1F3D2E; }
        .pos-start__row { display: flex; gap: 12px; }
        .pos-start__row .pos-start__field { flex: 1; }
        .pos-start__btn {
          width: 100%; padding: 12px; border: none;
          border-radius: 10px; font-size: 15px; font-weight: 600;
          cursor: pointer; font-family: inherit;
          background: #1F3D2E; color: #F5F2E9;
          transition: background 0.15s; margin-top: 8px;
        }
        .pos-start__btn:hover { background: #2a5440; }
        .pos-start__btn:disabled { opacity: 0.6; cursor: not-allowed; }
        .pos-start__error {
          background: #fef2f2; color: #b91c1c; padding: 10px 14px;
          border-radius: 8px; font-size: 13px; margin-bottom: 16px;
        }
        .pos-start__footer {
          text-align: center; margin-top: 20px; font-size: 13px; color: #9CA8A2;
        }
      `}</style>

      <div className="pos-start__card">
        <div className="pos-start__logo">
          <svg width="26" height="26" viewBox="0 0 32 32" fill="none">
            <path d="M16 2 C 9 2 4 8 4 16 C 4 22 8 27 14 28 L 14 14 C 14 11 16 9 19 9 C 22 9 24 11 24 14 C 24 17 22 19 19 19 L 17 19 L 17 28 C 24 27 28 22 28 16 C 28 8 23 2 16 2 Z" fill="#F5F2E9" />
            <circle cx="19" cy="14" r="2.5" fill="#B8924A" />
          </svg>
        </div>

        <h1 className="pos-start__title">Start Your Application</h1>
        <p className="pos-start__subtitle">
          Begin your loan application in minutes. Your progress saves automatically.
        </p>

        {error && <div className="pos-start__error">{error}</div>}

        <form onSubmit={handleSubmit}>
          <div className="pos-start__row">
            <div className="pos-start__field">
              <label className="pos-start__label">First name</label>
              <input
                className="pos-start__input"
                value={firstName}
                onChange={e => setFirstName(e.target.value)}
                required
                autoFocus
              />
            </div>
            <div className="pos-start__field">
              <label className="pos-start__label">Last name</label>
              <input
                className="pos-start__input"
                value={lastName}
                onChange={e => setLastName(e.target.value)}
                required
              />
            </div>
          </div>

          <div className="pos-start__field">
            <label className="pos-start__label">Email</label>
            <input
              className="pos-start__input"
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
            />
          </div>

          <div className="pos-start__field">
            <label className="pos-start__label">Phone (optional)</label>
            <input
              className="pos-start__input"
              type="tel"
              value={phone}
              onChange={e => setPhone(e.target.value)}
            />
          </div>

          <button className="pos-start__btn" type="submit" disabled={submitting}>
            {submitting ? 'Starting...' : 'Start Application'}
          </button>
        </form>

        <p className="pos-start__footer">
          Already have a link? Check your email for your personalized access.
        </p>
      </div>
    </div>
  );
}

export default POSEntryPage;

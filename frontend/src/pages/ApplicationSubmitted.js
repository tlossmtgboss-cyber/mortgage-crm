import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import './LandingPage.css';

/**
 * ApplicationSubmitted - Thank you page shown after application submission
 * when no portal URL is available for redirect.
 */
function ApplicationSubmitted() {
  const [searchParams] = useSearchParams();
  const [email, setEmail] = useState('');

  useEffect(() => {
    // Try to get email from URL params or localStorage
    const urlEmail = searchParams.get('email');
    const storedEmail = localStorage.getItem('borrower_email');
    setEmail(urlEmail || storedEmail || '');
  }, [searchParams]);

  return (
    <div className="landing-page">
      {/* Application Submission Success Banner */}
      <div className="application-success-banner" style={{ position: 'relative', marginBottom: '0' }}>
        <div className="success-banner-content">
          <span className="success-icon">&#10003;</span>
          <div className="success-text">
            <h3>Application Submitted Successfully!</h3>
            <p>Thank you for your application. A loan officer will review your information and contact you shortly.</p>
          </div>
        </div>
      </div>

      {/* Navigation Bar */}
      <nav className="landing-nav">
        <div className="landing-nav-container">
          <div className="landing-logo">
            <span className="logo-icon">&#127968;</span>
            <span className="logo-text">Mortgage CRM</span>
          </div>
        </div>
      </nav>

      {/* Main Content */}
      <section className="hero-section" style={{ minHeight: '60vh', paddingTop: '40px' }}>
        <div className="hero-content" style={{ maxWidth: '600px' }}>
          <h1 className="hero-title" style={{ fontSize: '2rem', marginBottom: '24px' }}>
            What Happens Next?
          </h1>

          <div style={{
            background: 'white',
            borderRadius: '12px',
            padding: '32px',
            boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
            textAlign: 'left',
            marginBottom: '24px'
          }}>
            <div style={{ marginBottom: '24px' }}>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: '#2D7A52',
                  color: 'white',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginRight: '12px',
                  fontWeight: 'bold'
                }}>1</div>
                <div>
                  <strong>Application Review</strong>
                  <p style={{ margin: '4px 0 0', color: '#6b7280', fontSize: '14px' }}>
                    Your loan officer will review your application within 1-2 business days.
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '16px' }}>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: '#3b82f6',
                  color: 'white',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginRight: '12px',
                  fontWeight: 'bold'
                }}>2</div>
                <div>
                  <strong>Document Collection</strong>
                  <p style={{ margin: '4px 0 0', color: '#6b7280', fontSize: '14px' }}>
                    You may receive requests for additional documents via email.
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center' }}>
                <div style={{
                  width: '32px',
                  height: '32px',
                  borderRadius: '50%',
                  background: '#B8924A',
                  color: 'white',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginRight: '12px',
                  fontWeight: 'bold'
                }}>3</div>
                <div>
                  <strong>Pre-Approval Decision</strong>
                  <p style={{ margin: '4px 0 0', color: '#6b7280', fontSize: '14px' }}>
                    Once complete, you'll receive your pre-approval letter.
                  </p>
                </div>
              </div>
            </div>

            {email && (
              <div style={{
                background: '#f3f4f6',
                borderRadius: '8px',
                padding: '16px',
                marginTop: '24px'
              }}>
                <p style={{ margin: 0, fontSize: '14px', color: '#374151' }}>
                  <strong>Watch your inbox!</strong> We'll send updates to{' '}
                  <span style={{ color: '#2563eb' }}>{email}</span>
                </p>
              </div>
            )}
          </div>

          <p style={{ color: '#6b7280', fontSize: '14px' }}>
            Questions? Contact your loan officer or reply to any email we send you.
          </p>
        </div>
      </section>
    </div>
  );
}

export default ApplicationSubmitted;

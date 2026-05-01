import { useNavigate } from 'react-router-dom';

/**
 * Forbidden - 403 page displayed when user lacks required role/permissions
 */
function Forbidden() {
  const navigate = useNavigate();

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      minHeight: '100vh',
      padding: '40px 20px',
      backgroundColor: '#f9fafb',
      textAlign: 'center',
    }}>
      <h1 style={{
        fontSize: '72px',
        fontWeight: 700,
        color: '#fbbf24',
        margin: '0 0 8px 0',
        lineHeight: 1,
      }}>
        403
      </h1>
      <h2 style={{
        fontSize: '24px',
        fontWeight: 600,
        color: '#1f2937',
        margin: '0 0 12px 0',
      }}>
        Access Denied
      </h2>
      <p style={{
        fontSize: '15px',
        color: '#6b7280',
        margin: '0 0 32px 0',
        maxWidth: '400px',
      }}>
        You do not have permission to access this page. Contact your administrator if you believe this is an error.
      </p>
      <div style={{ display: 'flex', gap: '12px' }}>
        <button
          onClick={() => navigate(-1)}
          style={{
            padding: '10px 24px',
            backgroundColor: '#fff',
            color: '#374151',
            border: '1px solid #d1d5db',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Go Back
        </button>
        <button
          onClick={() => navigate('/dashboard')}
          style={{
            padding: '10px 24px',
            backgroundColor: '#3b82f6',
            color: '#fff',
            border: 'none',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Go to Dashboard
        </button>
      </div>
    </div>
  );
}

export default Forbidden;

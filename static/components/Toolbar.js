import React from 'react';
import { Link } from 'react-router-dom';
import { FaCog } from 'react-icons/fa';

function Toolbar({ onSettingsClick }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', height: 64, background: '#fff', boxShadow: '0 2px 8px rgba(44, 62, 80, 0.05)', padding: '0 24px' }}>
      <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: '16px' }}>
        {/* Left side: Logo, Nav, etc */}
        <Link to="/portfolio" style={{ textDecoration: 'none', color: '#2563EB', fontWeight: 500, padding: '8px 16px' }}>Portfolio</Link>
        <Link to="/realtor-portal" style={{ textDecoration: 'none', color: '#2563EB', fontWeight: 500, padding: '8px 16px' }}>Realtor Portal</Link>
      </div>
      <button
        onClick={onSettingsClick}
        style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 8 }}
        title="Settings"
      >
        <FaCog size={26} style={{ color: '#2563EB' }} />
      </button>
    </div>
  );
}

export default Toolbar;

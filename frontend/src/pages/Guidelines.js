import React, { useState, useEffect } from 'react';
import './Guidelines.css';

function Guidelines() {
  const [loading, setLoading] = useState(true);
  const [guidelinesUrl, setGuidelinesUrl] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const [error, setError] = useState(null);

  useEffect(() => {
    loadGuidelines();
  }, []);

  const loadGuidelines = async () => {
    try {
      setLoading(true);
      setError(null);

      // Call backend API to get authenticated session URL
      const response = await fetch('/api/v1/guidelines/session', {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        throw new Error('Failed to load guidelines');
      }

      const data = await response.json();
      setGuidelinesUrl(data.url || 'https://my.mortgageguidelines.com/');
    } catch (err) {
      console.error('Failed to load guidelines:', err);
      setError('Unable to connect to Mortgage Guidelines. Please try again.');
      // Fallback to direct URL
      setGuidelinesUrl('https://my.mortgageguidelines.com/');
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = (e) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      // Encode search query for URL
      const searchUrl = `https://my.mortgageguidelines.com/search?q=${encodeURIComponent(searchQuery)}`;
      setGuidelinesUrl(searchUrl);
    }
  };

  const quickLinks = [
    { title: 'Conventional Guidelines', path: '/conventional' },
    { title: 'FHA Guidelines', path: '/fha' },
    { title: 'VA Guidelines', path: '/va' },
    { title: 'USDA Guidelines', path: '/usda' },
    { title: 'Jumbo Loans', path: '/jumbo' },
    { title: 'Rate Sheets', path: '/rates' },
  ];

  return (
    <div className="guidelines-page">
      <div className="guidelines-header">
        <h1>Mortgage Guidelines</h1>
        <p className="subtitle">Access comprehensive mortgage lending guidelines and rate sheets</p>
      </div>

      {error && (
        <div className="error-banner">
          <span>⚠️ {error}</span>
          <button onClick={loadGuidelines}>Retry</button>
        </div>
      )}

      <div className="guidelines-toolbar">
        <form onSubmit={handleSearch} className="search-form">
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search guidelines..."
            className="search-input"
          />
          <button type="submit" className="search-btn">
            Search
          </button>
        </form>

        <div className="quick-links">
          <span className="quick-links-label">Quick Access:</span>
          {quickLinks.map((link) => (
            <button
              key={link.path}
              className="quick-link-btn"
              onClick={() => setGuidelinesUrl(`https://my.mortgageguidelines.com${link.path}`)}
            >
              {link.title}
            </button>
          ))}
        </div>
      </div>

      <div className="guidelines-content">
        {loading ? (
          <div className="loading">
            <div className="loading-spinner"></div>
            <p>Loading Mortgage Guidelines...</p>
          </div>
        ) : (
          <div className="iframe-container">
            <iframe
              src={guidelinesUrl}
              title="Mortgage Guidelines"
              className="guidelines-iframe"
              sandbox="allow-same-origin allow-scripts allow-forms allow-popups"
            />
          </div>
        )}
      </div>

      <div className="guidelines-footer">
        <button className="refresh-btn" onClick={loadGuidelines}>
          🔄 Refresh
        </button>
        <a
          href="https://my.mortgageguidelines.com/"
          target="_blank"
          rel="noopener noreferrer"
          className="open-new-tab-btn"
        >
          Open in New Tab →
        </a>
      </div>
    </div>
  );
}

export default Guidelines;

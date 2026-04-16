import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './GlobalSearch.css';
import { getToken } from '../utils/tokenStore';

const API_BASE = process.env.REACT_APP_API_URL || '';

function GlobalSearch() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [isOpen, setIsOpen] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const searchRef = useRef(null);
  const inputRef = useRef(null);
  const navigate = useNavigate();

  // Debounce search
  const debounceSearch = useCallback(
    (() => {
      let timeoutId;
      return (searchQuery) => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => {
          performSearch(searchQuery);
        }, 300);
      };
    })(),
    []
  );

  const performSearch = async (searchQuery) => {
    if (!searchQuery || searchQuery.length < 2) {
      setResults([]);
      setIsOpen(false);
      return;
    }

    setLoading(true);
    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE}/api/v1/search/global?q=${encodeURIComponent(searchQuery)}&limit=15`,
        {
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setResults(data.results || []);
        setIsOpen(data.results?.length > 0);
        setSelectedIndex(-1);
      }
    } catch (error) {
      console.error('Global search error:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleInputChange = (e) => {
    const value = e.target.value;
    setQuery(value);
    debounceSearch(value);
  };

  const handleResultClick = (result) => {
    setIsOpen(false);
    setIsModalOpen(false);
    setQuery('');
    navigate(result.url);
  };

  const handleKeyDown = (e) => {
    if (!isOpen || results.length === 0) return;

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev => Math.min(prev + 1, results.length - 1));
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => Math.max(prev - 1, -1));
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && results[selectedIndex]) {
          handleResultClick(results[selectedIndex]);
        }
        break;
      case 'Escape':
        setIsOpen(false);
        setIsModalOpen(false);
        setSelectedIndex(-1);
        inputRef.current?.blur();
        break;
      default:
        break;
    }
  };

  // Close dropdown when clicking outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (searchRef.current && !searchRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Keyboard shortcut to focus search (Cmd/Ctrl + K)
  useEffect(() => {
    const handleKeyboardShortcut = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault();
        setIsModalOpen(true);
        setTimeout(() => inputRef.current?.focus(), 100);
      }
    };

    document.addEventListener('keydown', handleKeyboardShortcut);
    return () => document.removeEventListener('keydown', handleKeyboardShortcut);
  }, []);

  const getTypeIcon = (type) => {
    switch (type) {
      case 'lead': return '👤';
      case 'loan': return '🏠';
      case 'contact': return '📇';
      case 'partner': return '🤝';
      case 'portfolio': return '📊';
      default: return '📄';
    }
  };

  const getTypeLabel = (type) => {
    switch (type) {
      case 'lead': return 'Lead';
      case 'loan': return 'Loan';
      case 'contact': return 'Contact';
      case 'partner': return 'Partner';
      case 'portfolio': return 'Portfolio';
      default: return type;
    }
  };

  // Don't render anything if modal is not open
  if (!isModalOpen) {
    return null;
  }

  return (
    <div className="global-search-overlay" onClick={() => setIsModalOpen(false)}>
      <div className="global-search-modal" ref={searchRef} onClick={e => e.stopPropagation()}>
        <div className="global-search-input-wrapper">
          <span className="search-icon">🔍</span>
          <input
            ref={inputRef}
            type="text"
            className="global-search-input"
            placeholder="Search leads, loans, contacts..."
            value={query}
            onChange={handleInputChange}
            onKeyDown={handleKeyDown}
            onFocus={() => query.length >= 2 && results.length > 0 && setIsOpen(true)}
            autoFocus
          />
          {loading && <span className="search-loading">⏳</span>}
          <span className="search-shortcut">ESC to close</span>
        </div>

        {isOpen && results.length > 0 && (
          <div className="global-search-results">
            <div className="search-results-header">
              {results.length} result{results.length !== 1 ? 's' : ''} found
            </div>
            <div className="search-results-list">
              {results.map((result, index) => (
                <div
                  key={`${result.type}-${result.id}`}
                  className={`search-result-item ${index === selectedIndex ? 'selected' : ''}`}
                  onClick={() => handleResultClick(result)}
                  onMouseEnter={() => setSelectedIndex(index)}
                >
                  <span className="result-icon">{getTypeIcon(result.type)}</span>
                  <div className="result-content">
                    <div className="result-name">{result.name}</div>
                    <div className="result-meta">
                      <span className="result-type">{getTypeLabel(result.type)}</span>
                      {result.email && <span className="result-email">{result.email}</span>}
                      {result.loan_number && <span className="result-loan-number">#{result.loan_number}</span>}
                      {result.status && <span className="result-status">{result.status}</span>}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {isOpen && query.length >= 2 && results.length === 0 && !loading && (
          <div className="global-search-results">
            <div className="no-results">
              No results found for "{query}"
            </div>
          </div>
        )}

        {!isOpen && query.length < 2 && (
          <div className="global-search-hint">
            <p>Start typing to search across leads, loans, contacts, and partners</p>
            <p className="hint-shortcut">Press <kbd>⌘K</kbd> anytime to open search</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default GlobalSearch;

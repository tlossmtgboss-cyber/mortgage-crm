/**
 * RealtorLookupInput - Search CRM for real estate agents
 * Auto-populates contact info when agent is found
 */

import React, { useState, useCallback, useRef, useEffect } from 'react';
import './RealtorLookupInput.css';

const API_BASE_URL = process.env.REACT_APP_API_URL || '';

const RealtorLookupInput = ({
  value,
  onChange,
  onAgentSelect,
  error,
  placeholder = 'Search for agent...',
  helpText,
}) => {
  const [searchQuery, setSearchQuery] = useState(value?.name || '');
  const [suggestions, setSuggestions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState(value?.fromCrm ? value : null);
  const inputRef = useRef(null);
  const dropdownRef = useRef(null);
  const searchTimeoutRef = useRef(null);

  // Search agents in CRM
  const searchAgents = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setSuggestions([]);
      return;
    }

    setIsLoading(true);
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/agents/search?q=${encodeURIComponent(query)}`,
        {
          headers: {
            'Content-Type': 'application/json',
          },
        }
      );

      if (response.ok) {
        const data = await response.json();
        setSuggestions(data.agents || []);
      } else {
        // Fallback: empty results if API not available
        setSuggestions([]);
      }
    } catch (err) {
      console.warn('Agent search not available:', err);
      setSuggestions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Handle input change with debounce
  const handleInputChange = (e) => {
    const query = e.target.value;
    setSearchQuery(query);
    setSelectedAgent(null);
    setShowDropdown(true);

    // Clear previous timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }

    // Debounce search
    searchTimeoutRef.current = setTimeout(() => {
      searchAgents(query);
    }, 300);

    // Update value with just the name (manual entry)
    onChange({
      name: query,
      fromCrm: false,
    });
  };

  // Handle agent selection from dropdown
  const handleSelectAgent = (agent) => {
    setSelectedAgent(agent);
    setSearchQuery(agent.name);
    setShowDropdown(false);
    setSuggestions([]);

    // Pass full agent data
    onChange({
      name: agent.name,
      email: agent.email,
      phone: agent.phone,
      company: agent.company,
      agentId: agent.id,
      fromCrm: true,
    });

    // Notify parent that agent was selected from CRM
    if (onAgentSelect) {
      onAgentSelect(agent);
    }
  };

  // Handle clicking outside to close dropdown
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target) &&
        inputRef.current &&
        !inputRef.current.contains(e.target)
      ) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current);
      }
    };
  }, []);

  return (
    <div className="realtor-lookup-input">
      <div className="search-input-wrapper">
        <input
          ref={inputRef}
          type="text"
          className={`search-input ${error ? 'has-error' : ''} ${selectedAgent ? 'agent-selected' : ''}`}
          value={searchQuery}
          onChange={handleInputChange}
          onFocus={() => searchQuery.length >= 2 && setShowDropdown(true)}
          placeholder={placeholder}
          autoComplete="off"
        />
        {isLoading && (
          <div className="search-loading">
            <span className="spinner"></span>
          </div>
        )}
        {selectedAgent && (
          <div className="selected-badge">
            <span className="badge-icon">✓</span>
            Found in CRM
          </div>
        )}
      </div>

      {showDropdown && suggestions.length > 0 && (
        <div ref={dropdownRef} className="suggestions-dropdown">
          {suggestions.map((agent) => (
            <div
              key={agent.id}
              className="suggestion-item"
              onClick={() => handleSelectAgent(agent)}
            >
              <div className="agent-name">{agent.name}</div>
              {agent.company && (
                <div className="agent-company">{agent.company}</div>
              )}
              {agent.email && (
                <div className="agent-contact">{agent.email}</div>
              )}
            </div>
          ))}
        </div>
      )}

      {showDropdown && searchQuery.length >= 2 && suggestions.length === 0 && !isLoading && (
        <div ref={dropdownRef} className="suggestions-dropdown">
          <div className="no-results">
            <p>No agents found matching "{searchQuery}"</p>
            <p className="hint">You can still enter the agent's information manually</p>
          </div>
        </div>
      )}

      {helpText && <p className="help-text">{helpText}</p>}
      {error && <p className="error-text">{error}</p>}

      {selectedAgent && (
        <div className="agent-details">
          <div className="agent-info-row">
            <span className="label">Email:</span>
            <span className="value">{selectedAgent.email || 'Not available'}</span>
          </div>
          <div className="agent-info-row">
            <span className="label">Phone:</span>
            <span className="value">{selectedAgent.phone || 'Not available'}</span>
          </div>
          {selectedAgent.company && (
            <div className="agent-info-row">
              <span className="label">Brokerage:</span>
              <span className="value">{selectedAgent.company}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default RealtorLookupInput;

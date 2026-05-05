import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import { API_BASE_URL } from '../services/api';
import './EmployerAutocomplete.css';

const API_URL = API_BASE_URL;

/**
 * EmployerAutocomplete - Backend-powered employer/business search
 * 
 * Features:
 * - Real-time business suggestions via backend API
 * - Filters for businesses/establishments
 * - Extracts employer name, address, phone
 * - Mobile-friendly with touch support
 * - No deprecated Google APIs
 */
const EmployerAutocomplete = ({
  value = '',
  onChange,
  onEmployerSelect,
  placeholder = 'Start typing employer name...',
  label,
  required = false,
  disabled = false,
  error,
  className = '',
  country = 'us',
}) => {
  const [inputValue, setInputValue] = useState(value);
  const [suggestions, setSuggestions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  
  const inputRef = useRef(null);
  const dropdownRef = useRef(null);
  const debounceTimer = useRef(null);
  const sessionToken = useRef(generateSessionToken());

  // Generate a simple session token for billing optimization
  function generateSessionToken() {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }

  // Sync external value
  useEffect(() => {
    if (value !== inputValue) {
      setInputValue(value);
    }
  }, [value]);

  // Handle click outside
  useEffect(() => {
    const handleClickOutside = (event) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target) &&
        inputRef.current &&
        !inputRef.current.contains(event.target)
      ) {
        setShowDropdown(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('touchstart', handleClickOutside);

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('touchstart', handleClickOutside);
    };
  }, []);

  // Fetch suggestions from backend API
  const fetchSuggestions = useCallback(async (query) => {
    if (query.length < 2) {
      setSuggestions([]);
      return;
    }

    setIsLoading(true);

    try {
      const response = await axios.get(`${API_URL}/api/v1/places/autocomplete`, {
        params: {
          input: query,
          types: 'establishment',
          session_token: sessionToken.current,
        },
      });

      if (response.data.suggestions) {
        setSuggestions(response.data.suggestions.map(s => ({
          placeId: s.place_id,
          description: s.description,
          mainText: s.main_text || s.description,
          secondaryText: s.secondary_text || '',
        })));
        setShowDropdown(true);
      } else {
        setSuggestions([]);
      }
    } catch (error) {
      console.error('Error fetching employer suggestions:', error);
      setSuggestions([]);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Handle input change
  const handleInputChange = (e) => {
    const newValue = e.target.value;
    setInputValue(newValue);
    setSelectedIndex(-1);

    if (onChange) {
      onChange(newValue);
    }

    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }

    debounceTimer.current = setTimeout(() => {
      fetchSuggestions(newValue);
    }, 300);
  };

  // Select suggestion and get details
  const handleSelectSuggestion = async (suggestion) => {
    try {
      const response = await axios.get(`${API_URL}/api/v1/places/details/${suggestion.placeId}`, {
        params: {
          session_token: sessionToken.current,
        },
      });

      if (response.data) {
        const place = response.data;
        const employerData = {
          name: place.name || suggestion.mainText,
          address: place.formatted_address || '',
          phone: place.phone || '',
          website: place.website || '',
          types: place.types || [],
        };

        // Parse address components for city/state/zip
        if (place.address_components) {
          employerData.city = place.address_components.city || '';
          employerData.state = place.address_components.state_code || '';
          employerData.zip = place.address_components.zip_code || '';
          
          // Use street address if main address is missing
          if (!employerData.address && place.address_components.street_address) {
            employerData.address = place.address_components.street_address;
          }
        }

        console.log('[EmployerAutocomplete] Built employerData:', employerData);

        // Update internal state
        setInputValue(place.name || suggestion.mainText);
        setShowDropdown(false);
        setSuggestions([]);
        sessionToken.current = generateSessionToken();

        // Call callback with full employer data
        if (onEmployerSelect) {
          console.log('[EmployerAutocomplete] Calling onEmployerSelect with:', employerData);
          onEmployerSelect(employerData);
        } else if (onChange) {
          console.log('[EmployerAutocomplete] Falling back to onChange with:', place.name);
          onChange(place.name || suggestion.mainText);
        }
      }
    } catch (error) {
      console.error('Error fetching employer details:', error);
      // Fallback to basic info
      console.warn('Places API getDetails failed, using fallback data');
      setInputValue(suggestion.mainText);
      setShowDropdown(false);
      setSuggestions([]);

      if (onEmployerSelect) {
        onEmployerSelect({
          name: suggestion.mainText,
          address: suggestion.secondaryText || '',
          phone: '',
        });
      } else if (onChange) {
        onChange(suggestion.mainText);
      }
    }
  };

  // Keyboard navigation
  const handleKeyDown = (e) => {
    if (!showDropdown || suggestions.length === 0) {
      if (e.key === 'ArrowDown' && inputValue.length >= 2) {
        fetchSuggestions(inputValue);
      }
      return;
    }

    switch (e.key) {
      case 'ArrowDown':
        e.preventDefault();
        setSelectedIndex(prev =>
          prev < suggestions.length - 1 ? prev + 1 : prev
        );
        break;
      case 'ArrowUp':
        e.preventDefault();
        setSelectedIndex(prev => (prev > 0 ? prev - 1 : -1));
        break;
      case 'Enter':
        e.preventDefault();
        if (selectedIndex >= 0 && suggestions[selectedIndex]) {
          handleSelectSuggestion(suggestions[selectedIndex]);
        }
        break;
      case 'Escape':
        setShowDropdown(false);
        setSelectedIndex(-1);
        break;
      default:
        break;
    }
  };

  const handleFocus = () => {
    if (suggestions.length > 0) {
      setShowDropdown(true);
    }
  };

  // Get icon based on business type
  const getBusinessIcon = (description) => {
    const lower = description.toLowerCase();
    if (lower.includes('hospital') || lower.includes('medical') || lower.includes('health')) {
      return '🏥';
    }
    if (lower.includes('school') || lower.includes('university') || lower.includes('college')) {
      return '🎓';
    }
    if (lower.includes('bank') || lower.includes('credit union')) {
      return '🏦';
    }
    if (lower.includes('store') || lower.includes('shop')) {
      return '🏪';
    }
    if (lower.includes('restaurant') || lower.includes('cafe') || lower.includes('food')) {
      return '🍽️';
    }
    if (lower.includes('hotel') || lower.includes('inn')) {
      return '🏨';
    }
    return '🏢';
  };

  return (
    <div className={`employer-autocomplete ${className}`}>
      {label && (
        <label className="employer-label">
          {label}
          {required && <span className="required">*</span>}
        </label>
      )}

      <div className="input-wrapper">
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={handleFocus}
          placeholder={placeholder}
          disabled={disabled}
          className={`employer-input ${error ? 'has-error' : ''}`}
          autoComplete="off"
          aria-label={label || 'Employer name'}
          aria-expanded={showDropdown}
          aria-autocomplete="list"
          role="combobox"
        />

        {isLoading && (
          <div className="input-spinner">
            <div className="spinner-small"></div>
          </div>
        )}
      </div>

      {/* Suggestions Dropdown */}
      {showDropdown && suggestions.length > 0 && (
        <div ref={dropdownRef} className="suggestions-dropdown" role="listbox">
          {suggestions.map((suggestion, index) => (
            <div
              key={suggestion.placeId}
              className={`suggestion-item ${index === selectedIndex ? 'selected' : ''}`}
              onClick={() => handleSelectSuggestion(suggestion)}
              onMouseEnter={() => setSelectedIndex(index)}
              role="option"
              aria-selected={index === selectedIndex}
            >
              <span className="suggestion-icon">
                {getBusinessIcon(suggestion.description)}
              </span>
              <div className="suggestion-text">
                <span className="suggestion-main">{suggestion.mainText}</span>
                {suggestion.secondaryText && (
                  <span className="suggestion-secondary">{suggestion.secondaryText}</span>
                )}
              </div>
            </div>
          ))}
          <div className="powered-by">
            <img
              src="https://developers.google.com/static/maps/documentation/images/google_on_white.png"
              alt="Powered by Google"
              height="14"
            />
          </div>
        </div>
      )}

      {error && <div className="employer-error">{error}</div>}
    </div>
  );
};

export default EmployerAutocomplete;

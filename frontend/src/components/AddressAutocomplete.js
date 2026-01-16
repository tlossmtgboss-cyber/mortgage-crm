import React, { useState, useEffect, useRef, useCallback } from 'react';
import axios from 'axios';
import './AddressAutocomplete.css';

const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

/**
 * AddressAutocomplete - Backend-powered address input
 * 
 * Features:
 * - Real-time address suggestions via backend API
 * - Parses full address into components (street, city, state, zip)
 * - Mobile-friendly with touch support
 * - No deprecated Google APIs
 */
const AddressAutocomplete = ({
  value = '',
  onChange,
  onAddressSelect,
  placeholder = 'Start typing an address...',
  label,
  required = false,
  disabled = false,
  error,
  className = '',
  types = ['address'],
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

  // Sync external value changes
  useEffect(() => {
    if (value !== inputValue) {
      setInputValue(value);
    }
  }, [value]);

  // Handle click outside to close dropdown
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
    if (query.length < 3) {
      setSuggestions([]);
      return;
    }

    setIsLoading(true);

    try {
      const response = await axios.get(`${API_URL}/api/v1/places/autocomplete`, {
        params: {
          input: query,
          types: types.join(','),
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
      console.error('Error fetching address suggestions:', error);
      setSuggestions([]);
    } finally {
      setIsLoading(false);
    }
  }, [types]);

  // Handle input change with debounce
  const handleInputChange = (e) => {
    const newValue = e.target.value;
    setInputValue(newValue);
    setSelectedIndex(-1);

    if (onChange) {
      onChange(newValue);
    }

    // Debounce API calls
    if (debounceTimer.current) {
      clearTimeout(debounceTimer.current);
    }

    debounceTimer.current = setTimeout(() => {
      fetchSuggestions(newValue);
    }, 300);
  };

  // Get place details when user selects a suggestion
  const handleSelectSuggestion = async (suggestion) => {
    try {
      const response = await axios.get(`${API_URL}/api/v1/places/details/${suggestion.placeId}`, {
        params: {
          session_token: sessionToken.current,
        },
      });

      if (response.data) {
        const place = response.data;
        const addressData = {
          formatted: place.formatted_address,
          street: place.address_components?.street_address || '',
          street_number: place.address_components?.street_number || '',
          street_name: place.address_components?.street_name || '',
          city: place.address_components?.city || '',
          state: place.address_components?.state || '',
          state_code: place.address_components?.state_code || '',
          zip: place.address_components?.zip_code || '',
          county: place.address_components?.county || '',
          country: place.address_components?.country || '',
          country_code: place.address_components?.country_code || '',
          lat: place.location?.latitude,
          lng: place.location?.longitude,
        };

        setInputValue(place.formatted_address);
        setShowDropdown(false);
        setSuggestions([]);

        // Generate new session token for next search
        sessionToken.current = generateSessionToken();

        if (onChange) onChange(place.formatted_address);
        if (onAddressSelect) onAddressSelect(addressData);
      }
    } catch (error) {
      console.error('Error fetching place details:', error);
      // Fallback to basic info
      setInputValue(suggestion.description);
      setShowDropdown(false);
      if (onChange) onChange(suggestion.description);
      if (onAddressSelect) {
        onAddressSelect({
          formatted: suggestion.description,
          street: suggestion.mainText,
        });
      }
    }
  };

  // Keyboard navigation
  const handleKeyDown = (e) => {
    if (!showDropdown || suggestions.length === 0) {
      if (e.key === 'ArrowDown' && inputValue.length >= 3) {
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

  // Handle focus
  const handleFocus = () => {
    if (suggestions.length > 0) {
      setShowDropdown(true);
    }
  };

  return (
    <div className={`address-autocomplete ${className}`}>
      {label && (
        <label className="address-label">
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
          className={`address-input ${error ? 'has-error' : ''}`}
          autoComplete="off"
          aria-label={label || 'Address'}
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
              <span className="suggestion-icon">📍</span>
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

      {error && <div className="address-error">{error}</div>}
    </div>
  );
};

export default AddressAutocomplete;

import React, { useState, useEffect, useRef, useCallback } from 'react';
import './AddressAutocomplete.css';

/**
 * AddressAutocomplete - Google Places powered address input
 *
 * Features:
 * - Real-time address suggestions as user types
 * - Parses full address into components (street, city, state, zip)
 * - Mobile-friendly with touch support
 * - Fallback to manual entry if Google API unavailable
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
  types = ['address'], // 'address', 'geocode', 'establishment', '(cities)'
  country = 'us',
}) => {
  const [inputValue, setInputValue] = useState(value);
  const [suggestions, setSuggestions] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [isGoogleLoaded, setIsGoogleLoaded] = useState(false);

  const inputRef = useRef(null);
  const dropdownRef = useRef(null);
  const autocompleteService = useRef(null);
  const placesService = useRef(null);
  const sessionToken = useRef(null);
  const debounceTimer = useRef(null);

  // Initialize Google Places
  useEffect(() => {
    const initGooglePlaces = () => {
      if (window.google && window.google.maps && window.google.maps.places) {
        autocompleteService.current = new window.google.maps.places.AutocompleteService();

        // Create a dummy div for PlacesService (required but not displayed)
        const dummyDiv = document.createElement('div');
        placesService.current = new window.google.maps.places.PlacesService(dummyDiv);

        // Create session token for billing optimization
        sessionToken.current = new window.google.maps.places.AutocompleteSessionToken();
        setIsGoogleLoaded(true);
      }
    };

    // Check if already loaded
    if (window.google && window.google.maps) {
      initGooglePlaces();
    } else {
      // Wait for script to load
      const checkInterval = setInterval(() => {
        if (window.google && window.google.maps) {
          initGooglePlaces();
          clearInterval(checkInterval);
        }
      }, 100);

      // Cleanup after 10 seconds
      setTimeout(() => clearInterval(checkInterval), 10000);

      return () => clearInterval(checkInterval);
    }
  }, []);

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

  // Fetch suggestions from Google Places
  const fetchSuggestions = useCallback((query) => {
    if (!autocompleteService.current || query.length < 3) {
      setSuggestions([]);
      return;
    }

    setIsLoading(true);

    const request = {
      input: query,
      sessionToken: sessionToken.current,
      componentRestrictions: { country },
      types: types,
    };

    autocompleteService.current.getPlacePredictions(request, (predictions, status) => {
      setIsLoading(false);

      if (status === window.google.maps.places.PlacesServiceStatus.OK && predictions) {
        setSuggestions(predictions.map(p => ({
          placeId: p.place_id,
          description: p.description,
          mainText: p.structured_formatting?.main_text || p.description,
          secondaryText: p.structured_formatting?.secondary_text || '',
        })));
        setShowDropdown(true);
      } else {
        setSuggestions([]);
      }
    });
  }, [country, types]);

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
  const handleSelectSuggestion = (suggestion) => {
    if (!placesService.current) {
      // Fallback if Places service not available
      setInputValue(suggestion.description);
      setShowDropdown(false);
      if (onChange) onChange(suggestion.description);
      if (onAddressSelect) {
        onAddressSelect({
          formatted: suggestion.description,
          street: suggestion.mainText,
        });
      }
      return;
    }

    const request = {
      placeId: suggestion.placeId,
      fields: ['address_components', 'formatted_address', 'geometry'],
      sessionToken: sessionToken.current,
    };

    placesService.current.getDetails(request, (place, status) => {
      if (status === window.google.maps.places.PlacesServiceStatus.OK && place) {
        // Parse address components
        const addressData = parseAddressComponents(place.address_components);
        addressData.formatted = place.formatted_address;

        // Add coordinates if available
        if (place.geometry && place.geometry.location) {
          addressData.lat = place.geometry.location.lat();
          addressData.lng = place.geometry.location.lng();
        }

        setInputValue(place.formatted_address);
        setShowDropdown(false);
        setSuggestions([]);

        // Create new session token for next search
        sessionToken.current = new window.google.maps.places.AutocompleteSessionToken();

        if (onChange) onChange(place.formatted_address);
        if (onAddressSelect) onAddressSelect(addressData);
      }
    });
  };

  // Parse Google address components into structured data
  const parseAddressComponents = (components) => {
    const result = {
      street_number: '',
      street_name: '',
      street: '',
      city: '',
      state: '',
      state_code: '',
      zip: '',
      county: '',
      country: '',
      country_code: '',
    };

    if (!components) return result;

    components.forEach(component => {
      const types = component.types;

      if (types.includes('street_number')) {
        result.street_number = component.long_name;
      }
      if (types.includes('route')) {
        result.street_name = component.long_name;
      }
      if (types.includes('locality')) {
        result.city = component.long_name;
      }
      if (types.includes('administrative_area_level_1')) {
        result.state = component.long_name;
        result.state_code = component.short_name;
      }
      if (types.includes('postal_code')) {
        result.zip = component.long_name;
      }
      if (types.includes('administrative_area_level_2')) {
        result.county = component.long_name;
      }
      if (types.includes('country')) {
        result.country = component.long_name;
        result.country_code = component.short_name;
      }
    });

    // Combine street number and name
    result.street = `${result.street_number} ${result.street_name}`.trim();

    return result;
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

        {!isGoogleLoaded && inputValue.length >= 3 && (
          <div className="input-icon manual">
            <span title="Manual entry mode">✎</span>
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

      {!isGoogleLoaded && (
        <div className="manual-entry-hint">
          Enter address manually - autocomplete unavailable
        </div>
      )}
    </div>
  );
};

export default AddressAutocomplete;

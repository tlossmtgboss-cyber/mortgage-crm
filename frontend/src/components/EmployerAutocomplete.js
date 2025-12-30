import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useGooglePlaces } from '../hooks/useGooglePlaces';
import './EmployerAutocomplete.css';

/**
 * EmployerAutocomplete - Google Places powered employer/business search
 *
 * Features:
 * - Real-time business suggestions as user types
 * - Filters for businesses/establishments
 * - Extracts employer name, address, phone
 * - Mobile-friendly with touch support
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
  const [isGoogleLoaded, setIsGoogleLoaded] = useState(false);

  // Use the hook to trigger loading of Google Places script
  const { isLoaded: isGoogleScriptLoaded } = useGooglePlaces();

  const inputRef = useRef(null);
  const dropdownRef = useRef(null);
  const autocompleteService = useRef(null);
  const placesService = useRef(null);
  const sessionToken = useRef(null);
  const debounceTimer = useRef(null);

  // Initialize Google Places services when script is loaded
  useEffect(() => {
    if (isGoogleScriptLoaded && window.google && window.google.maps && window.google.maps.places) {
      console.log('EmployerAutocomplete: Initializing Google Places services');
      autocompleteService.current = new window.google.maps.places.AutocompleteService();

      const dummyDiv = document.createElement('div');
      placesService.current = new window.google.maps.places.PlacesService(dummyDiv);
      sessionToken.current = new window.google.maps.places.AutocompleteSessionToken();
      setIsGoogleLoaded(true);
    } else if (isGoogleScriptLoaded) {
      console.warn('EmployerAutocomplete: Script loaded but window.google.maps.places not available');
    }
  }, [isGoogleScriptLoaded]);

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

  // Fetch suggestions
  const fetchSuggestions = useCallback((query) => {
    if (!autocompleteService.current || query.length < 2) {
      setSuggestions([]);
      return;
    }

    setIsLoading(true);

    const request = {
      input: query,
      sessionToken: sessionToken.current,
      componentRestrictions: { country },
      types: ['establishment'], // Search for businesses
    };

    autocompleteService.current.getPlacePredictions(request, (predictions, status) => {
      setIsLoading(false);

      // Log status for debugging
      if (status !== window.google.maps.places.PlacesServiceStatus.OK) {
        console.warn('Google Places API error:', status);
      }

      if (status === window.google.maps.places.PlacesServiceStatus.OK && predictions) {
        setSuggestions(predictions.map(p => ({
          placeId: p.place_id,
          description: p.description,
          mainText: p.structured_formatting?.main_text || p.description,
          secondaryText: p.structured_formatting?.secondary_text || '',
          types: p.types || [],
        })));
        setShowDropdown(true);
      } else {
        setSuggestions([]);
      }
    });
  }, [country]);

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
  const handleSelectSuggestion = (suggestion) => {
    if (!placesService.current) {
      setInputValue(suggestion.mainText);
      setShowDropdown(false);
      if (onChange) onChange(suggestion.mainText);
      if (onEmployerSelect) {
        onEmployerSelect({
          name: suggestion.mainText,
          address: suggestion.secondaryText,
        });
      }
      return;
    }

    const request = {
      placeId: suggestion.placeId,
      fields: ['name', 'formatted_address', 'address_components', 'formatted_phone_number', 'website', 'types'],
      sessionToken: sessionToken.current,
    };

    placesService.current.getDetails(request, (place, status) => {
      if (status === window.google.maps.places.PlacesServiceStatus.OK && place) {
        const employerData = {
          name: place.name,
          address: place.formatted_address,
          phone: place.formatted_phone_number,
          website: place.website,
          types: place.types,
        };

        // Parse address components
        if (place.address_components) {
          place.address_components.forEach(component => {
            if (component.types.includes('locality')) {
              employerData.city = component.long_name;
            }
            if (component.types.includes('administrative_area_level_1')) {
              employerData.state = component.short_name;
            }
            if (component.types.includes('postal_code')) {
              employerData.zip = component.long_name;
            }
          });
        }

        setInputValue(place.name);
        setShowDropdown(false);
        setSuggestions([]);
        sessionToken.current = new window.google.maps.places.AutocompleteSessionToken();

        if (onChange) onChange(place.name);
        if (onEmployerSelect) onEmployerSelect(employerData);
      }
    });
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
  const getBusinessIcon = (types) => {
    if (types.includes('hospital') || types.includes('doctor') || types.includes('health')) {
      return '🏥';
    }
    if (types.includes('school') || types.includes('university')) {
      return '🎓';
    }
    if (types.includes('bank') || types.includes('finance')) {
      return '🏦';
    }
    if (types.includes('store') || types.includes('shopping')) {
      return '🏪';
    }
    if (types.includes('restaurant') || types.includes('food')) {
      return '🍽️';
    }
    if (types.includes('lodging')) {
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
        <div ref={dropdownRef} className="employer-dropdown" role="listbox">
          {suggestions.map((suggestion, index) => (
            <div
              key={suggestion.placeId}
              className={`employer-suggestion ${index === selectedIndex ? 'selected' : ''}`}
              onClick={() => handleSelectSuggestion(suggestion)}
              onMouseEnter={() => setSelectedIndex(index)}
              role="option"
              aria-selected={index === selectedIndex}
            >
              <span className="suggestion-icon">{getBusinessIcon(suggestion.types)}</span>
              <div className="suggestion-content">
                <span className="suggestion-name">{suggestion.mainText}</span>
                {suggestion.secondaryText && (
                  <span className="suggestion-location">{suggestion.secondaryText}</span>
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

      {!isGoogleLoaded && (
        <div className="manual-hint">
          Type employer name manually
        </div>
      )}
    </div>
  );
};

export default EmployerAutocomplete;

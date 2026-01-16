import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useGooglePlaces } from '../hooks/useGooglePlaces';
import './EmployerAutocomplete.css';

/**
 * EmployerAutocomplete - Google Places powered employer/business search
 *
 * Uses the new Places Autocomplete element API (not deprecated AutocompleteService)
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
  const [isGoogleLoaded, setIsGoogleLoaded] = useState(false);

  // Use the hook to trigger loading of Google Places script
  const { isLoaded: isGoogleScriptLoaded } = useGooglePlaces();

  const inputRef = useRef(null);
  const autocompleteRef = useRef(null);

  // Initialize Google Places Autocomplete when script is loaded
  useEffect(() => {
    if (!isGoogleScriptLoaded || !window.google || !window.google.maps || !window.google.maps.places) {
      return;
    }

    if (!inputRef.current) {
      return;
    }

    // Check if Autocomplete class exists
    if (typeof window.google.maps.places.Autocomplete !== 'function') {
      console.warn('[Google Places] Autocomplete class not available');
      return;
    }

    try {
      // Create Autocomplete instance for establishments (businesses)
      const autocomplete = new window.google.maps.places.Autocomplete(inputRef.current, {
        types: ['establishment'],
        componentRestrictions: { country: country },
        fields: ['name', 'formatted_address', 'address_components', 'formatted_phone_number', 'website', 'types', 'geometry'],
      });

      // Handle place selection
      autocomplete.addListener('place_changed', () => {
        const place = autocomplete.getPlace();

        if (!place || !place.name) {
          // User pressed Enter without selecting, or selection failed
          return;
        }

        const employerData = {
          name: place.name,
          address: place.formatted_address || '',
          phone: place.formatted_phone_number || '',
          website: place.website || '',
          types: place.types || [],
        };

        // Parse address components for city/state/zip
        if (place.address_components) {
          let streetNumber = '';
          let streetName = '';

          place.address_components.forEach(component => {
            if (component.types.includes('street_number')) {
              streetNumber = component.long_name;
            }
            if (component.types.includes('route')) {
              streetName = component.long_name;
            }
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

          // Build street address if formatted_address is missing
          if (!employerData.address && (streetNumber || streetName)) {
            employerData.address = `${streetNumber} ${streetName}`.trim();
          }
        }

        setInputValue(place.name);

        if (onEmployerSelect) {
          onEmployerSelect(employerData);
        } else if (onChange) {
          onChange(place.name);
        }
      });

      autocompleteRef.current = autocomplete;
      setIsGoogleLoaded(true);

    } catch (err) {
      console.warn('[Google Places] Failed to initialize Autocomplete:', err);
    }

    // Cleanup
    return () => {
      if (autocompleteRef.current && window.google && window.google.maps && window.google.maps.event) {
        window.google.maps.event.clearInstanceListeners(autocompleteRef.current);
      }
    };
  }, [isGoogleScriptLoaded, country, onChange, onEmployerSelect]);

  // Sync external value
  useEffect(() => {
    if (value !== inputValue) {
      setInputValue(value);
    }
  }, [value]);

  // Handle input change
  const handleInputChange = (e) => {
    const newValue = e.target.value;
    setInputValue(newValue);

    if (onChange) {
      onChange(newValue);
    }
  };

  // Prevent form submission on Enter (Google handles it)
  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && isGoogleLoaded) {
      e.preventDefault();
    }
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
          placeholder={placeholder}
          disabled={disabled}
          className={`employer-input ${error ? 'has-error' : ''}`}
          autoComplete="off"
          aria-label={label || 'Employer name'}
        />
      </div>

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

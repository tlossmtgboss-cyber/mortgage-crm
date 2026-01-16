import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useGooglePlaces } from '../hooks/useGooglePlaces';
import './AddressAutocomplete.css';

/**
 * AddressAutocomplete - Google Places powered address input
 *
 * Uses the new Places Autocomplete element API (not deprecated AutocompleteService)
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
  const [isGoogleLoaded, setIsGoogleLoaded] = useState(false);

  // Use the hook to trigger loading of Google Places script
  const { isLoaded: isGoogleScriptLoaded } = useGooglePlaces();

  const inputRef = useRef(null);
  const autocompleteRef = useRef(null);

  // Parse Google address components into structured data
  const parseAddressComponents = useCallback((components) => {
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
  }, []);

  // Initialize Google Places Autocomplete when script is loaded
  useEffect(() => {
    if (!isGoogleScriptLoaded || !window.google || !window.google.maps || !window.google.maps.places) {
      return;
    }

    if (!inputRef.current) {
      return;
    }

    // Check if Autocomplete class exists (newer API)
    if (typeof window.google.maps.places.Autocomplete !== 'function') {
      console.warn('[Google Places] Autocomplete class not available');
      return;
    }

    try {
      // Create Autocomplete instance attached to input
      const autocomplete = new window.google.maps.places.Autocomplete(inputRef.current, {
        types: types,
        componentRestrictions: { country: country },
        fields: ['address_components', 'formatted_address', 'geometry', 'place_id'],
      });

      // Handle place selection
      autocomplete.addListener('place_changed', () => {
        const place = autocomplete.getPlace();

        if (!place || !place.address_components) {
          // User pressed Enter without selecting, or selection failed
          return;
        }

        // Parse address components
        const addressData = parseAddressComponents(place.address_components);
        addressData.formatted = place.formatted_address;

        // Add coordinates if available
        if (place.geometry && place.geometry.location) {
          addressData.lat = place.geometry.location.lat();
          addressData.lng = place.geometry.location.lng();
        }

        setInputValue(place.formatted_address);

        if (onChange) onChange(place.formatted_address);
        if (onAddressSelect) onAddressSelect(addressData);
      });

      autocompleteRef.current = autocomplete;
      setIsGoogleLoaded(true);

    } catch (err) {
      console.warn('[Google Places] Failed to initialize Autocomplete:', err);
      // Fall back to manual entry mode
    }

    // Cleanup
    return () => {
      if (autocompleteRef.current && window.google && window.google.maps && window.google.maps.event) {
        window.google.maps.event.clearInstanceListeners(autocompleteRef.current);
      }
    };
  }, [isGoogleScriptLoaded, types, country, parseAddressComponents, onChange, onAddressSelect]);

  // Sync external value changes
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
          placeholder={placeholder}
          disabled={disabled}
          className={`address-input ${error ? 'has-error' : ''}`}
          autoComplete="off"
          aria-label={label || 'Address'}
        />

        {!isGoogleLoaded && inputValue.length >= 3 && (
          <div className="input-icon manual">
            <span title="Manual entry mode">✎</span>
          </div>
        )}
      </div>

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

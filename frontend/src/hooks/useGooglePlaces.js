import { useState, useEffect } from 'react';

/**
 * Hook to load and manage Google Places API
 *
 * Uses the newer Places Autocomplete element API (not deprecated AutocompleteService)
 *
 * Usage:
 * const { isLoaded, loadError } = useGooglePlaces();
 */

// Track loading state globally to avoid multiple loads
let isScriptLoading = false;
let isScriptLoaded = false;
let loadError = null;
const callbacks = [];

const loadGooglePlaces = () => {
  return new Promise((resolve, reject) => {
    // Already loaded
    if (isScriptLoaded && window.google && window.google.maps) {
      resolve();
      return;
    }

    // Already failed
    if (loadError) {
      reject(loadError);
      return;
    }

    // Add to callback queue
    callbacks.push({ resolve, reject });

    // Already loading
    if (isScriptLoading) {
      return;
    }

    isScriptLoading = true;

    // Get API key from environment
    const apiKey = process.env.REACT_APP_GOOGLE_PLACES_API_KEY;

    if (!apiKey) {
      isScriptLoading = false;
      callbacks.forEach(cb => cb.resolve());
      callbacks.length = 0;
      return;
    }

    // Create callback
    window.__GOOGLE_PLACES_CALLBACK__ = () => {
      isScriptLoaded = true;
      isScriptLoading = false;
      callbacks.forEach(cb => cb.resolve());
      callbacks.length = 0;
    };

    // Create and load script - using places library for Autocomplete element
    const script = document.createElement('script');
    script.src = `https://maps.googleapis.com/maps/api/js?key=${apiKey}&libraries=places&callback=__GOOGLE_PLACES_CALLBACK__`;
    script.async = true;
    script.defer = true;

    script.onerror = (error) => {
      loadError = new Error('Failed to load Google Places API');
      isScriptLoading = false;
      callbacks.forEach(cb => cb.reject(loadError));
      callbacks.length = 0;
    };

    document.head.appendChild(script);
  });
};

export function useGooglePlaces() {
  const [isLoaded, setIsLoaded] = useState(
    isScriptLoaded && window.google && window.google.maps && window.google.maps.places
  );
  const [error, setError] = useState(loadError);
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    // Already loaded
    if (window.google && window.google.maps && window.google.maps.places) {
      setIsLoaded(true);
      return;
    }

    setIsLoading(true);

    loadGooglePlaces()
      .then(() => {
        setIsLoaded(window.google && window.google.maps && window.google.maps.places);
        setIsLoading(false);
      })
      .catch((err) => {
        setError(err);
        setIsLoading(false);
      });
  }, []);

  return { isLoaded, isLoading, error };
}

export default useGooglePlaces;

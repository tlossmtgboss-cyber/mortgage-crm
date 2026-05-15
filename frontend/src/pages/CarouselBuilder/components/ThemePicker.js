/**
 * Theme Picker Component
 *
 * Displays available themes in a modal for users to browse and apply.
 */

import React, { useState, useEffect } from 'react';
import { useCarouselBuilder } from '../CarouselBuilderContext';
import { API_BASE_URL } from '../../../services/api';
import { getToken } from '../../../utils/tokenStore';

const THEME_CATEGORIES = [
  { value: 'all', label: 'All Themes' },
  { value: 'professional', label: 'Professional' },
  { value: 'celebratory', label: 'Celebratory' },
  { value: 'friendly', label: 'Friendly' },
  { value: 'bold', label: 'Bold' },
  { value: 'premium', label: 'Premium' },
  { value: 'minimal', label: 'Minimal' },
];

export default function ThemePicker({ open, onClose }) {
  const { currentProject, slides, updateSlide } = useCarouselBuilder();

  const [themes, setThemes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedTheme, setSelectedTheme] = useState(null);
  const [applying, setApplying] = useState(false);

  // Fetch themes on mount
  useEffect(() => {
    if (open) {
      fetchThemes();
    }
  }, [open]);

  const fetchThemes = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/carousels/themes`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setThemes(data);
      }
    } catch (err) {
      console.error('Failed to fetch themes:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredThemes = themes.filter(
    (theme) => selectedCategory === 'all' || theme.category === selectedCategory
  );

  const handleApplyTheme = async () => {
    if (!selectedTheme || !slides.length) return;

    setApplying(true);

    try {
      // Apply theme colors to all slides
      const primaryColor = selectedTheme.colors?.primary || '#1F3D2E';
      const secondaryColor = selectedTheme.colors?.secondary || '#1a5f6a';

      for (let i = 0; i < slides.length; i++) {
        const slide = slides[i];
        const isEvenSlide = i % 2 === 0;

        await updateSlide(slide.id, {
          background_type: isEvenSlide ? 'gradient' : 'solid',
          background_color: isEvenSlide ? primaryColor : secondaryColor,
          background_gradient: isEvenSlide
            ? { angle: 135, colors: [primaryColor, secondaryColor] }
            : null,
          custom_styles: {
            ...slide.custom_styles,
            textColor: selectedTheme.colors?.text || '#ffffff',
          },
        });
      }

      onClose();
    } catch (err) {
      console.error('Failed to apply theme:', err);
    } finally {
      setApplying(false);
    }
  };

  if (!open) return null;

  return (
    <div className="carousel-modal-overlay" onClick={onClose}>
      <div className="carousel-modal carousel-theme-modal" onClick={(e) => e.stopPropagation()}>
        <div className="carousel-modal-header">
          <h2>Choose a Theme</h2>
          <button className="carousel-modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="carousel-modal-body">
          {/* Category Filter */}
          <div className="carousel-theme-categories">
            {THEME_CATEGORIES.map((cat) => (
              <button
                key={cat.value}
                type="button"
                className={`carousel-category-btn ${selectedCategory === cat.value ? 'active' : ''}`}
                onClick={() => setSelectedCategory(cat.value)}
              >
                {cat.label}
              </button>
            ))}
          </div>

          {/* Themes Grid */}
          {loading ? (
            <div className="carousel-theme-loading">
              <div className="carousel-spinner" />
              <p>Loading themes...</p>
            </div>
          ) : filteredThemes.length === 0 ? (
            <div className="carousel-theme-empty">
              <p>No themes found in this category.</p>
            </div>
          ) : (
            <div className="carousel-theme-grid">
              {filteredThemes.map((theme) => (
                <div
                  key={theme.id}
                  className={`carousel-theme-card ${selectedTheme?.id === theme.id ? 'selected' : ''}`}
                  onClick={() => setSelectedTheme(theme)}
                >
                  <div
                    className="carousel-theme-preview"
                    style={{
                      background: `linear-gradient(135deg, ${theme.colors?.primary || '#1F3D2E'}, ${theme.colors?.secondary || '#1a5f6a'})`,
                    }}
                  >
                    <div className="carousel-theme-preview-content">
                      <span className="carousel-theme-preview-title">Aa</span>
                    </div>
                  </div>
                  <div className="carousel-theme-info">
                    <h4>{theme.name}</h4>
                    <p>{theme.description}</p>
                    <div className="carousel-theme-colors">
                      {Object.entries(theme.colors || {})
                        .slice(0, 4)
                        .map(([key, color]) => (
                          <span
                            key={key}
                            className="carousel-theme-color-dot"
                            style={{ backgroundColor: color }}
                            title={key}
                          />
                        ))}
                    </div>
                  </div>
                  {selectedTheme?.id === theme.id && (
                    <div className="carousel-theme-selected-badge">
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                        <path d="M20 6L9 17l-5-5" />
                      </svg>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="carousel-modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleApplyTheme}
            disabled={!selectedTheme || applying}
          >
            {applying ? 'Applying...' : 'Apply Theme'}
          </button>
        </div>
      </div>
    </div>
  );
}

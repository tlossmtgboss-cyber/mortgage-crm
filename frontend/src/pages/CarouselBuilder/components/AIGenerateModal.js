/**
 * AI Generate Modal
 *
 * Modal for generating carousel content using AI.
 * Allows users to configure generation options and preview results.
 */

import React, { useState, useEffect } from 'react';
import { useCarouselBuilder, PROJECT_TYPES } from '../CarouselBuilderContext';
import { API_BASE_URL } from '../../../services/api';
import { getToken } from '../../../utils/tokenStore';

export default function AIGenerateModal({ open, onClose, onApply }) {
  const { currentProject, slides } = useCarouselBuilder();

  const [numSlides, setNumSlides] = useState(5);
  const [customPrompt, setCustomPrompt] = useState('');
  const [includeCrmData, setIncludeCrmData] = useState(true);
  const [generating, setGenerating] = useState(false);
  const [generatedSlides, setGeneratedSlides] = useState([]);
  const [error, setError] = useState(null);
  const [previewIndex, setPreviewIndex] = useState(0);
  const [crmData, setCrmData] = useState(null);
  const [loadingCrm, setLoadingCrm] = useState(false);

  const projectType = PROJECT_TYPES.find(pt => pt.value === currentProject?.project_type);

  // Fetch CRM data when modal opens
  useEffect(() => {
    if (open && currentProject?.id) {
      fetchCrmData();
    }
  }, [open, currentProject?.id]);

  const fetchCrmData = async () => {
    if (!currentProject?.id) return;

    setLoadingCrm(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/carousels/${currentProject.id}/crm-data`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setCrmData(data);
      }
    } catch (err) {
      console.error('Failed to fetch CRM data:', err);
    } finally {
      setLoadingCrm(false);
    }
  };

  const handleGenerate = async () => {
    if (!currentProject?.id) return;

    setGenerating(true);
    setError(null);
    setGeneratedSlides([]);

    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/carousels/${currentProject.id}/generate`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          num_slides: numSlides,
          custom_prompt: customPrompt || null,
          include_crm_data: includeCrmData,
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Generation failed');
      }

      const data = await response.json();
      setGeneratedSlides(data.slides || []);
      setPreviewIndex(0);
    } catch (err) {
      console.error('Generation error:', err);
      setError(err.message || 'Failed to generate content. Please try again.');
    } finally {
      setGenerating(false);
    }
  };

  const handleApply = async () => {
    if (generatedSlides.length === 0) return;

    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/carousels/${currentProject.id}/apply-generated`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(generatedSlides),
      });

      if (!response.ok) {
        throw new Error('Failed to apply generated content');
      }

      // Call the onApply callback to refresh the project
      if (onApply) {
        onApply();
      }
      handleClose();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleClose = () => {
    setGeneratedSlides([]);
    setError(null);
    setPreviewIndex(0);
    setCustomPrompt('');
    onClose();
  };

  if (!open) return null;

  return (
    <div className="carousel-modal-overlay" onClick={handleClose}>
      <div className="carousel-modal carousel-ai-modal" onClick={e => e.stopPropagation()}>
        <div className="carousel-modal-header">
          <h2>
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
            Generate with AI
          </h2>
          <button className="carousel-modal-close" onClick={handleClose}>&times;</button>
        </div>

        <div className="carousel-modal-body">
          {generatedSlides.length === 0 ? (
            <>
              {/* Generation Settings */}
              <div className="carousel-ai-settings">
                <div className="carousel-ai-project-info">
                  <span className="carousel-ai-badge">{projectType?.label || 'Custom'}</span>
                  <span className="carousel-ai-badge">{currentProject?.platform}</span>
                </div>

                {/* CRM Data Status */}
                {loadingCrm ? (
                  <div className="carousel-ai-crm-status loading">
                    Loading CRM data...
                  </div>
                ) : crmData?.has_crm_data ? (
                  <div className="carousel-ai-crm-status success">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                      <path d="M22 4L12 14.01l-3-3" />
                    </svg>
                    CRM data linked ({crmData.data_source?.replace('_', ' ')})
                    <label className="carousel-checkbox-label">
                      <input
                        type="checkbox"
                        checked={includeCrmData}
                        onChange={(e) => setIncludeCrmData(e.target.checked)}
                      />
                      Include in generation
                    </label>
                  </div>
                ) : (
                  <div className="carousel-ai-crm-status none">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 8v4M12 16h.01" />
                    </svg>
                    No CRM data linked - using generic content
                  </div>
                )}

                <div className="carousel-form-group">
                  <label>Number of Slides</label>
                  <div className="carousel-slider-group">
                    <input
                      type="range"
                      min="3"
                      max="10"
                      value={numSlides}
                      onChange={(e) => setNumSlides(parseInt(e.target.value))}
                    />
                    <span className="carousel-slider-value">{numSlides}</span>
                  </div>
                </div>

                <div className="carousel-form-group">
                  <label>Custom Instructions (Optional)</label>
                  <textarea
                    value={customPrompt}
                    onChange={(e) => setCustomPrompt(e.target.value)}
                    placeholder={getPlaceholderForType(currentProject?.project_type)}
                    rows={4}
                  />
                  <span className="carousel-form-hint">
                    Add specific instructions to customize the generated content
                  </span>
                </div>

                {/* Topic Suggestions */}
                {currentProject?.project_type === 'educational' && (
                  <div className="carousel-ai-suggestions">
                    <label>Suggested Topics</label>
                    <div className="carousel-ai-chips">
                      {[
                        'Credit Score Tips',
                        'Down Payment Myths',
                        'First-Time Buyer Programs',
                        'FHA vs Conventional',
                        'Refinancing Guide',
                        'What to Expect at Closing',
                      ].map((topic) => (
                        <button
                          key={topic}
                          type="button"
                          className="carousel-ai-chip"
                          onClick={() => setCustomPrompt(`Create an educational carousel about: ${topic}`)}
                        >
                          {topic}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {error && (
                  <div className="carousel-ai-error">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <circle cx="12" cy="12" r="10" />
                      <path d="M12 8v4M12 16h.01" />
                    </svg>
                    {error}
                  </div>
                )}
              </div>
            </>
          ) : (
            <>
              {/* Preview Generated Content */}
              <div className="carousel-ai-preview">
                <div className="carousel-ai-preview-header">
                  <h3>Preview Generated Content</h3>
                  <span>{generatedSlides.length} slides generated</span>
                </div>

                <div className="carousel-ai-preview-nav">
                  <button
                    type="button"
                    className="btn-icon"
                    onClick={() => setPreviewIndex(Math.max(0, previewIndex - 1))}
                    disabled={previewIndex === 0}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M15 18l-6-6 6-6" />
                    </svg>
                  </button>
                  <span>Slide {previewIndex + 1} of {generatedSlides.length}</span>
                  <button
                    type="button"
                    className="btn-icon"
                    onClick={() => setPreviewIndex(Math.min(generatedSlides.length - 1, previewIndex + 1))}
                    disabled={previewIndex === generatedSlides.length - 1}
                  >
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M9 18l6-6-6-6" />
                    </svg>
                  </button>
                </div>

                <div
                  className="carousel-ai-preview-slide"
                  style={{
                    background: generatedSlides[previewIndex]?.suggested_background === 'gradient'
                      ? `linear-gradient(135deg, ${(generatedSlides[previewIndex]?.suggested_colors || ['#1F3D2E', '#1a5f6a']).join(', ')})`
                      : generatedSlides[previewIndex]?.suggested_colors?.[0] || '#1F3D2E',
                  }}
                >
                  <div className="carousel-ai-preview-content">
                    {generatedSlides[previewIndex]?.title && (
                      <h2>{generatedSlides[previewIndex].title}</h2>
                    )}
                    {generatedSlides[previewIndex]?.subtitle && (
                      <h3>{generatedSlides[previewIndex].subtitle}</h3>
                    )}
                    {generatedSlides[previewIndex]?.body_text && (
                      <p>{generatedSlides[previewIndex].body_text}</p>
                    )}
                  </div>
                </div>

                <div className="carousel-ai-preview-thumbs">
                  {generatedSlides.map((slide, index) => (
                    <button
                      key={index}
                      type="button"
                      className={`carousel-ai-preview-thumb ${index === previewIndex ? 'active' : ''}`}
                      onClick={() => setPreviewIndex(index)}
                      style={{
                        background: slide.suggested_background === 'gradient'
                          ? `linear-gradient(135deg, ${(slide.suggested_colors || ['#1F3D2E', '#1a5f6a']).join(', ')})`
                          : slide.suggested_colors?.[0] || '#1F3D2E',
                      }}
                    >
                      <span>{index + 1}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>

        <div className="carousel-modal-footer">
          {generatedSlides.length === 0 ? (
            <>
              <button type="button" className="btn-secondary" onClick={handleClose}>
                Cancel
              </button>
              <button
                type="button"
                className="btn-primary"
                onClick={handleGenerate}
                disabled={generating}
              >
                {generating ? (
                  <>
                    <span className="carousel-spinner" />
                    Generating...
                  </>
                ) : (
                  <>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                      <path d="M12 2L2 7l10 5 10-5-10-5z" />
                      <path d="M2 17l10 5 10-5" />
                      <path d="M2 12l10 5 10-5" />
                    </svg>
                    Generate Content
                  </>
                )}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={() => {
                  setGeneratedSlides([]);
                  setPreviewIndex(0);
                }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M1 4v6h6" />
                  <path d="M3.51 15a9 9 0 102.13-9.36L1 10" />
                </svg>
                Regenerate
              </button>
              <button type="button" className="btn-primary" onClick={handleApply}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M22 11.08V12a10 10 0 11-5.93-9.14" />
                  <path d="M22 4L12 14.01l-3-3" />
                </svg>
                Apply to Project
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function getPlaceholderForType(projectType) {
  const placeholders = {
    just_closed: 'e.g., "Emphasize the quick closing time" or "Mention it was a first-time buyer"',
    rate_update: 'e.g., "Focus on refinancing opportunities" or "Target first-time buyers"',
    educational: 'e.g., "Create content about FHA loans for first-time buyers"',
    marketing: 'e.g., "Highlight my 15 years of experience" or "Focus on my local market expertise"',
    custom: 'Describe what content you want to generate...',
  };
  return placeholders[projectType] || placeholders.custom;
}

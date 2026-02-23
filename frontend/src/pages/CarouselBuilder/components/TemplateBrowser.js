/**
 * Template Browser Component
 *
 * Displays available templates for users to browse and use as starting points.
 */

import React, { useState, useEffect } from 'react';
import { useCarouselBuilder, PROJECT_TYPES, PLATFORM_DIMENSIONS } from '../CarouselBuilderContext';
import { API_BASE_URL } from '../../../services/api';

const TEMPLATE_CATEGORIES = [
  { value: 'all', label: 'All Templates' },
  { value: 'just_closed', label: 'Just Closed' },
  { value: 'rate_update', label: 'Rate Updates' },
  { value: 'educational', label: 'Educational' },
  { value: 'marketing', label: 'Marketing' },
];

const PLATFORMS = [
  { value: 'all', label: 'All Platforms' },
  { value: 'linkedin', label: 'LinkedIn' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'facebook', label: 'Facebook' },
  { value: 'tiktok', label: 'TikTok' },
];

export default function TemplateBrowser({ open, onClose, onSelectTemplate }) {
  const { currentProject } = useCarouselBuilder();

  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedPlatform, setSelectedPlatform] = useState('all');
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [previewIndex, setPreviewIndex] = useState(0);

  // Fetch templates on mount
  useEffect(() => {
    if (open) {
      fetchTemplates();
      // Default to current project's type and platform
      if (currentProject?.project_type) {
        setSelectedCategory(currentProject.project_type);
      }
      if (currentProject?.platform) {
        setSelectedPlatform(currentProject.platform);
      }
    }
  }, [open, currentProject]);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch(`${API_BASE_URL}/api/v1/carousels/templates`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setTemplates(data);
      }
    } catch (err) {
      console.error('Failed to fetch templates:', err);
    } finally {
      setLoading(false);
    }
  };

  const filteredTemplates = templates.filter((template) => {
    const categoryMatch = selectedCategory === 'all' || template.category === selectedCategory;
    const platformMatch = selectedPlatform === 'all' || template.platform === selectedPlatform;
    return categoryMatch && platformMatch;
  });

  const handleSelectTemplate = () => {
    if (!selectedTemplate) return;
    onSelectTemplate(selectedTemplate);
    onClose();
  };

  const handlePreviewTemplate = (template) => {
    setSelectedTemplate(template);
    setPreviewIndex(0);
  };

  if (!open) return null;

  return (
    <div className="carousel-modal-overlay" onClick={onClose}>
      <div className="carousel-modal carousel-template-modal" onClick={(e) => e.stopPropagation()}>
        <div className="carousel-modal-header">
          <h2>Choose a Template</h2>
          <button className="carousel-modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="carousel-modal-body">
          <div className="carousel-template-layout">
            {/* Left: Filter & List */}
            <div className="carousel-template-list-panel">
              {/* Filters */}
              <div className="carousel-template-filters">
                <div className="carousel-form-group">
                  <label>Category</label>
                  <select
                    value={selectedCategory}
                    onChange={(e) => setSelectedCategory(e.target.value)}
                  >
                    {TEMPLATE_CATEGORIES.map((cat) => (
                      <option key={cat.value} value={cat.value}>
                        {cat.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="carousel-form-group">
                  <label>Platform</label>
                  <select
                    value={selectedPlatform}
                    onChange={(e) => setSelectedPlatform(e.target.value)}
                  >
                    {PLATFORMS.map((plat) => (
                      <option key={plat.value} value={plat.value}>
                        {plat.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              {/* Template List */}
              {loading ? (
                <div className="carousel-template-loading">
                  <div className="carousel-spinner" />
                  <p>Loading templates...</p>
                </div>
              ) : filteredTemplates.length === 0 ? (
                <div className="carousel-template-empty">
                  <p>No templates found for this filter.</p>
                </div>
              ) : (
                <div className="carousel-template-list">
                  {filteredTemplates.map((template) => (
                    <div
                      key={template.id}
                      className={`carousel-template-item ${selectedTemplate?.id === template.id ? 'selected' : ''}`}
                      onClick={() => handlePreviewTemplate(template)}
                    >
                      <div className="carousel-template-item-info">
                        <h4>{template.name}</h4>
                        <div className="carousel-template-meta">
                          <span className="carousel-template-badge">{template.platform}</span>
                          <span className="carousel-template-badge">{template.aspect_ratio}</span>
                          <span className="carousel-template-slides">{template.slide_count} slides</span>
                        </div>
                      </div>
                      {selectedTemplate?.id === template.id && (
                        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--carousel-primary)" strokeWidth="2">
                          <path d="M20 6L9 17l-5-5" />
                        </svg>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Right: Preview */}
            <div className="carousel-template-preview-panel">
              {selectedTemplate ? (
                <>
                  <div className="carousel-template-preview-header">
                    <h3>{selectedTemplate.name}</h3>
                    <p>{selectedTemplate.description}</p>
                  </div>

                  {/* Slide Preview */}
                  <TemplateSlidePreview
                    template={selectedTemplate}
                    slideIndex={previewIndex}
                  />

                  {/* Slide Navigation */}
                  <div className="carousel-template-preview-nav">
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
                    <span>
                      Slide {previewIndex + 1} of {selectedTemplate.slide_count}
                    </span>
                    <button
                      type="button"
                      className="btn-icon"
                      onClick={() => setPreviewIndex(Math.min(selectedTemplate.slide_count - 1, previewIndex + 1))}
                      disabled={previewIndex === selectedTemplate.slide_count - 1}
                    >
                      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                        <path d="M9 18l6-6-6-6" />
                      </svg>
                    </button>
                  </div>

                  {/* Template Info */}
                  <div className="carousel-template-details">
                    <div className="carousel-template-tags">
                      {selectedTemplate.tags?.map((tag) => (
                        <span key={tag} className="carousel-template-tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                    {selectedTemplate.required_data_bindings?.length > 0 && (
                      <div className="carousel-template-bindings">
                        <small>Uses CRM data: {selectedTemplate.required_data_bindings.join(', ')}</small>
                      </div>
                    )}
                  </div>
                </>
              ) : (
                <div className="carousel-template-preview-empty">
                  <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="3" y="3" width="18" height="18" rx="2" />
                    <path d="M3 9h18" />
                    <path d="M9 21V9" />
                  </svg>
                  <p>Select a template to preview</p>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="carousel-modal-footer">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={handleSelectTemplate}
            disabled={!selectedTemplate}
          >
            Use Template
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Preview a single template slide
 */
function TemplateSlidePreview({ template, slideIndex }) {
  // We don't have the actual slide data in the template response,
  // so we'll show a placeholder preview based on template info
  const aspectRatio = template.aspect_ratio?.replace(':', '/') || '1/1';

  // For the preview, we'll use the template's category color
  const categoryColors = {
    just_closed: ['#217F8D', '#1a5f6a'],
    rate_update: ['#0284c7', '#0369a1'],
    educational: ['#7c3aed', '#5b21b6'],
    marketing: ['#166534', '#14532d'],
  };

  const colors = categoryColors[template.category] || ['#217F8D', '#1a5f6a'];
  const bgIndex = slideIndex % 2;

  return (
    <div
      className="carousel-template-slide-preview"
      style={{
        aspectRatio,
        background: bgIndex === 0
          ? `linear-gradient(135deg, ${colors[0]}, ${colors[1]})`
          : colors[bgIndex % colors.length],
      }}
    >
      <div className="carousel-template-slide-content">
        <div className="carousel-template-slide-title">Slide {slideIndex + 1}</div>
        <div className="carousel-template-slide-subtitle">{template.name}</div>
      </div>
    </div>
  );
}

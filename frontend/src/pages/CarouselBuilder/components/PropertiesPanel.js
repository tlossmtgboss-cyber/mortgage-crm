/**
 * Properties Panel
 *
 * Right panel for editing slide and element properties.
 * - Slide: background, layout, text content
 * - Element: position, size, styling
 */

import React, { useState } from 'react';
import { useCarouselBuilder } from '../CarouselBuilderContext';
import ImageUploader from './ImageUploader';

// =============================================================================
// Color Picker
// =============================================================================

function ColorPicker({ value, onChange, label }) {
  const presetColors = [
    '#1F3D2E', '#c9a227', '#1a1a1a', '#ffffff',
    '#ef4444', '#f97316', '#eab308', '#22c55e',
    '#3b82f6', '#B8924A', '#ec4899', '#6b7280',
  ];

  return (
    <div className="carousel-color-picker">
      {label && <label>{label}</label>}
      <div className="carousel-color-input">
        <input
          type="color"
          value={value || '#1F3D2E'}
          onChange={(e) => onChange(e.target.value)}
        />
        <input
          type="text"
          value={value || '#1F3D2E'}
          onChange={(e) => onChange(e.target.value)}
          placeholder="#000000"
        />
      </div>
      <div className="carousel-color-presets">
        {presetColors.map((color) => (
          <button
            key={color}
            className={`carousel-color-preset ${value === color ? 'selected' : ''}`}
            style={{ backgroundColor: color }}
            onClick={() => onChange(color)}
            title={color}
          />
        ))}
      </div>
    </div>
  );
}

// =============================================================================
// Gradient Editor
// =============================================================================

function GradientEditor({ value, onChange }) {
  const gradient = value || { angle: 135, colors: ['#1F3D2E', '#2D7A52'] };

  const updateGradient = (updates) => {
    onChange({ ...gradient, ...updates });
  };

  return (
    <div className="carousel-gradient-editor">
      <div className="carousel-form-group">
        <label>Angle</label>
        <div className="carousel-range-input">
          <input
            type="range"
            min="0"
            max="360"
            value={gradient.angle}
            onChange={(e) => updateGradient({ angle: parseInt(e.target.value) })}
          />
          <span>{gradient.angle}°</span>
        </div>
      </div>

      <div className="carousel-form-group">
        <label>Color 1</label>
        <input
          type="color"
          value={gradient.colors[0]}
          onChange={(e) => updateGradient({ colors: [e.target.value, gradient.colors[1]] })}
        />
      </div>

      <div className="carousel-form-group">
        <label>Color 2</label>
        <input
          type="color"
          value={gradient.colors[1]}
          onChange={(e) => updateGradient({ colors: [gradient.colors[0], e.target.value] })}
        />
      </div>

      <div
        className="carousel-gradient-preview"
        style={{
          background: `linear-gradient(${gradient.angle}deg, ${gradient.colors.join(', ')})`,
        }}
      />
    </div>
  );
}

// =============================================================================
// Slide Properties
// =============================================================================

function SlideProperties() {
  const { selectedSlide, updateSlide, addElement } = useCarouselBuilder();

  if (!selectedSlide) return null;

  const handleBackgroundTypeChange = (type) => {
    const updates = { background_type: type };
    if (type === 'gradient' && !selectedSlide.background_gradient) {
      updates.background_gradient = { angle: 135, colors: ['#1F3D2E', '#2D7A52'] };
    }
    updateSlide(selectedSlide.id, updates);
  };

  const handleAddText = () => {
    addElement(selectedSlide.id, {
      type: 'text',
      content: 'New Text',
      position: { x: 50, y: 70 },
      size: { width: 80 },
      styles: {
        fontSize: 24,
        color: '#ffffff',
        textAlign: 'center',
      },
    });
  };

  return (
    <div className="carousel-properties-section">
      {/* Content Section */}
      <div className="carousel-property-group">
        <h4>Content</h4>

        <div className="carousel-form-group">
          <label>Title</label>
          <input
            type="text"
            value={selectedSlide.title || ''}
            onChange={(e) => updateSlide(selectedSlide.id, { title: e.target.value })}
            placeholder="Slide title"
          />
        </div>

        <div className="carousel-form-group">
          <label>Subtitle</label>
          <input
            type="text"
            value={selectedSlide.subtitle || ''}
            onChange={(e) => updateSlide(selectedSlide.id, { subtitle: e.target.value })}
            placeholder="Slide subtitle"
          />
        </div>

        <div className="carousel-form-group">
          <label>Body Text</label>
          <textarea
            value={selectedSlide.body_text || ''}
            onChange={(e) => updateSlide(selectedSlide.id, { body_text: e.target.value })}
            placeholder="Additional text content"
            rows={3}
          />
        </div>
      </div>

      {/* Background Section */}
      <div className="carousel-property-group">
        <h4>Background</h4>

        <div className="carousel-form-group">
          <label>Type</label>
          <div className="carousel-button-group">
            {['solid', 'gradient', 'image'].map((type) => (
              <button
                key={type}
                className={`carousel-toggle-btn ${selectedSlide.background_type === type ? 'active' : ''}`}
                onClick={() => handleBackgroundTypeChange(type)}
              >
                {type.charAt(0).toUpperCase() + type.slice(1)}
              </button>
            ))}
          </div>
        </div>

        {selectedSlide.background_type === 'solid' && (
          <ColorPicker
            label="Color"
            value={selectedSlide.background_color}
            onChange={(color) => updateSlide(selectedSlide.id, { background_color: color })}
          />
        )}

        {selectedSlide.background_type === 'gradient' && (
          <GradientEditor
            value={selectedSlide.background_gradient}
            onChange={(gradient) => updateSlide(selectedSlide.id, { background_gradient: gradient })}
          />
        )}

        {selectedSlide.background_type === 'image' && (
          <div className="carousel-form-group">
            <label>Background Image</label>
            <ImageUploader
              currentImage={selectedSlide.background_image_url}
              onUpload={(url) => updateSlide(selectedSlide.id, { background_image_url: url })}
            />
          </div>
        )}
      </div>

      {/* Layout Section */}
      <div className="carousel-property-group">
        <h4>Layout</h4>

        <div className="carousel-form-group">
          <label>Alignment</label>
          <select
            value={selectedSlide.layout_template || 'centered'}
            onChange={(e) => updateSlide(selectedSlide.id, { layout_template: e.target.value })}
          >
            <option value="centered">Centered</option>
            <option value="left">Left</option>
            <option value="right">Right</option>
            <option value="split">Split</option>
            <option value="full_image">Full Image</option>
          </select>
        </div>
      </div>

      {/* Add Elements */}
      <div className="carousel-property-group">
        <h4>Elements</h4>
        <button className="btn-secondary btn-block" onClick={handleAddText}>
          + Add Text
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// Element Properties
// =============================================================================

function ElementProperties() {
  const { selectedSlide, selectedElement, updateElement, deleteElement, setSelectedElementId } = useCarouselBuilder();

  if (!selectedElement) return null;

  const handleStyleChange = (key, value) => {
    updateElement(selectedSlide.id, selectedElement.id, {
      styles: { ...selectedElement.styles, [key]: value },
    });
  };

  const handlePositionChange = (axis, value) => {
    updateElement(selectedSlide.id, selectedElement.id, {
      position: { ...selectedElement.position, [axis]: parseFloat(value) },
    });
  };

  const handleDelete = () => {
    deleteElement(selectedSlide.id, selectedElement.id);
    setSelectedElementId(null);
  };

  return (
    <div className="carousel-properties-section">
      <div className="carousel-property-group">
        <div className="carousel-property-header">
          <h4>Text Element</h4>
          <button className="btn-icon-sm btn-danger" onClick={handleDelete} title="Delete">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
            </svg>
          </button>
        </div>

        <div className="carousel-form-group">
          <label>Content</label>
          <textarea
            value={selectedElement.content || ''}
            onChange={(e) => updateElement(selectedSlide.id, selectedElement.id, { content: e.target.value })}
            rows={3}
          />
        </div>
      </div>

      <div className="carousel-property-group">
        <h4>Typography</h4>

        <div className="carousel-form-group">
          <label>Font Size</label>
          <div className="carousel-range-input">
            <input
              type="range"
              min="12"
              max="96"
              value={selectedElement.styles?.fontSize || 24}
              onChange={(e) => handleStyleChange('fontSize', parseInt(e.target.value))}
            />
            <span>{selectedElement.styles?.fontSize || 24}px</span>
          </div>
        </div>

        <div className="carousel-form-group">
          <label>Font Weight</label>
          <select
            value={selectedElement.styles?.fontWeight || 'normal'}
            onChange={(e) => handleStyleChange('fontWeight', e.target.value)}
          >
            <option value="normal">Normal</option>
            <option value="500">Medium</option>
            <option value="600">Semibold</option>
            <option value="bold">Bold</option>
          </select>
        </div>

        <div className="carousel-form-group">
          <label>Text Align</label>
          <div className="carousel-button-group">
            {['left', 'center', 'right'].map((align) => (
              <button
                key={align}
                className={`carousel-toggle-btn ${selectedElement.styles?.textAlign === align ? 'active' : ''}`}
                onClick={() => handleStyleChange('textAlign', align)}
              >
                {align.charAt(0).toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <ColorPicker
          label="Color"
          value={selectedElement.styles?.color}
          onChange={(color) => handleStyleChange('color', color)}
        />
      </div>

      <div className="carousel-property-group">
        <h4>Position</h4>

        <div className="carousel-form-row">
          <div className="carousel-form-group">
            <label>X (%)</label>
            <input
              type="number"
              min="0"
              max="100"
              value={selectedElement.position?.x || 50}
              onChange={(e) => handlePositionChange('x', e.target.value)}
            />
          </div>
          <div className="carousel-form-group">
            <label>Y (%)</label>
            <input
              type="number"
              min="0"
              max="100"
              value={selectedElement.position?.y || 50}
              onChange={(e) => handlePositionChange('y', e.target.value)}
            />
          </div>
        </div>

        <div className="carousel-form-group">
          <label>Width (%)</label>
          <input
            type="number"
            min="10"
            max="100"
            value={selectedElement.size?.width || 80}
            onChange={(e) => updateElement(selectedSlide.id, selectedElement.id, {
              size: { ...selectedElement.size, width: parseFloat(e.target.value) },
            })}
          />
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Main Properties Panel
// =============================================================================

export default function PropertiesPanel() {
  const { selectedSlide, selectedElement } = useCarouselBuilder();
  const [activeTab, setActiveTab] = useState('slide');

  if (!selectedSlide) {
    return (
      <div className="carousel-properties-panel">
        <div className="carousel-properties-empty">
          <p>Select a slide to edit properties</p>
        </div>
      </div>
    );
  }

  return (
    <div className="carousel-properties-panel">
      <div className="carousel-properties-tabs">
        <button
          className={`carousel-tab ${activeTab === 'slide' ? 'active' : ''}`}
          onClick={() => setActiveTab('slide')}
        >
          Slide
        </button>
        <button
          className={`carousel-tab ${activeTab === 'element' ? 'active' : ''}`}
          onClick={() => setActiveTab('element')}
          disabled={!selectedElement}
        >
          Element
        </button>
      </div>

      <div className="carousel-properties-content">
        {activeTab === 'slide' ? (
          <SlideProperties />
        ) : (
          <ElementProperties />
        )}
      </div>
    </div>
  );
}

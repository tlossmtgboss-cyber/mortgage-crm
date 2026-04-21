/**
 * Slide Canvas
 *
 * Center panel showing the current slide at actual dimensions.
 * Supports text editing and element selection.
 */

import React, { useRef, useCallback, useState } from 'react';
import { useCarouselBuilder, ASPECT_RATIO_SIZES } from '../CarouselBuilderContext';

// =============================================================================
// Text Element
// =============================================================================

function TextElement({ element, isSelected, onSelect, onChange }) {
  const [isEditing, setIsEditing] = useState(false);
  const inputRef = useRef(null);

  const handleDoubleClick = () => {
    setIsEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const handleBlur = () => {
    setIsEditing(false);
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      setIsEditing(false);
    }
    if (e.key === 'Escape') {
      setIsEditing(false);
    }
  };

  const styles = {
    position: 'absolute',
    left: `${element.position?.x || 50}%`,
    top: `${element.position?.y || 50}%`,
    transform: 'translate(-50%, -50%)',
    width: element.size?.width ? `${element.size.width}%` : 'auto',
    fontSize: `${element.styles?.fontSize || 24}px`,
    fontWeight: element.styles?.fontWeight || 'normal',
    color: element.styles?.color || '#ffffff',
    textAlign: element.styles?.textAlign || 'center',
    lineHeight: element.styles?.lineHeight || 1.3,
    fontFamily: element.styles?.fontFamily || 'Inter, sans-serif',
    cursor: isEditing ? 'text' : 'pointer',
    outline: isSelected ? '2px solid #217F8D' : 'none',
    outlineOffset: '4px',
    padding: '8px',
    borderRadius: '4px',
    background: isSelected && !isEditing ? 'rgba(33, 127, 141, 0.1)' : 'transparent',
  };

  return (
    <div
      style={styles}
      onClick={(e) => { e.stopPropagation(); onSelect(); }}
      onDoubleClick={handleDoubleClick}
    >
      {isEditing ? (
        <textarea
          ref={inputRef}
          value={element.content || ''}
          onChange={(e) => onChange({ content: e.target.value })}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          style={{
            width: '100%',
            minHeight: '1.5em',
            background: 'transparent',
            border: 'none',
            color: 'inherit',
            fontSize: 'inherit',
            fontWeight: 'inherit',
            fontFamily: 'inherit',
            textAlign: 'inherit',
            lineHeight: 'inherit',
            resize: 'none',
            outline: 'none',
          }}
        />
      ) : (
        <span>{element.content || 'Click to edit'}</span>
      )}
    </div>
  );
}

// =============================================================================
// Slide Content Renderer
// =============================================================================

function SlideContent({ slide, onElementSelect, onElementChange, selectedElementId }) {
  const { updateSlide } = useCarouselBuilder();

  const handleTitleChange = (value) => {
    updateSlide(slide.id, { title: value });
  };

  const handleSubtitleChange = (value) => {
    updateSlide(slide.id, { subtitle: value });
  };

  const handleBodyChange = (value) => {
    updateSlide(slide.id, { body_text: value });
  };

  // Layout styles based on template
  const getLayoutStyles = () => {
    switch (slide.layout_template) {
      case 'left':
        return { alignItems: 'flex-start', textAlign: 'left', paddingLeft: '10%' };
      case 'right':
        return { alignItems: 'flex-end', textAlign: 'right', paddingRight: '10%' };
      case 'split':
        return { alignItems: 'center', justifyContent: 'space-between' };
      case 'full_image':
        return { alignItems: 'flex-end', justifyContent: 'flex-end', padding: '5%' };
      default: // centered
        return { alignItems: 'center', textAlign: 'center' };
    }
  };

  const layoutStyles = getLayoutStyles();

  return (
    <div
      className="carousel-slide-content"
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'center',
        height: '100%',
        padding: '8%',
        ...layoutStyles,
      }}
    >
      {/* Title */}
      {slide.title && (
        <EditableText
          value={slide.title}
          onChange={handleTitleChange}
          placeholder="Add title"
          style={{
            fontSize: '48px',
            fontWeight: 'bold',
            color: slide.custom_styles?.textColor || '#ffffff',
            marginBottom: '16px',
            textAlign: layoutStyles.textAlign || 'center',
            width: '100%',
          }}
        />
      )}

      {/* Subtitle */}
      {slide.subtitle && (
        <EditableText
          value={slide.subtitle}
          onChange={handleSubtitleChange}
          placeholder="Add subtitle"
          style={{
            fontSize: '24px',
            fontWeight: '500',
            color: slide.custom_styles?.textColor || '#ffffff',
            opacity: 0.9,
            marginBottom: '12px',
            textAlign: layoutStyles.textAlign || 'center',
            width: '100%',
          }}
        />
      )}

      {/* Body text */}
      {slide.body_text && (
        <EditableText
          value={slide.body_text}
          onChange={handleBodyChange}
          placeholder="Add body text"
          multiline
          style={{
            fontSize: '18px',
            color: slide.custom_styles?.textColor || '#ffffff',
            opacity: 0.85,
            lineHeight: 1.5,
            textAlign: layoutStyles.textAlign || 'center',
            width: '100%',
          }}
        />
      )}

      {/* Custom elements */}
      {(slide.elements || []).map((element) => (
        <TextElement
          key={element.id}
          element={element}
          isSelected={selectedElementId === element.id}
          onSelect={() => onElementSelect(element.id)}
          onChange={(updates) => onElementChange(element.id, updates)}
        />
      ))}
    </div>
  );
}

// =============================================================================
// Editable Text Component
// =============================================================================

function EditableText({ value, onChange, placeholder, style, multiline = false }) {
  const [isEditing, setIsEditing] = useState(false);
  const [editValue, setEditValue] = useState(value);
  const inputRef = useRef(null);

  const handleClick = () => {
    setEditValue(value);
    setIsEditing(true);
    setTimeout(() => inputRef.current?.focus(), 0);
  };

  const handleBlur = () => {
    setIsEditing(false);
    if (editValue !== value) {
      onChange(editValue);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey && !multiline) {
      e.preventDefault();
      inputRef.current?.blur();
    }
    if (e.key === 'Escape') {
      setEditValue(value);
      setIsEditing(false);
    }
  };

  const sharedStyles = {
    ...style,
    background: 'transparent',
    border: 'none',
    outline: isEditing ? '2px dashed rgba(255,255,255,0.5)' : 'none',
    outlineOffset: '4px',
    cursor: isEditing ? 'text' : 'pointer',
    padding: '4px',
    margin: '-4px',
    borderRadius: '4px',
  };

  if (isEditing) {
    if (multiline) {
      return (
        <textarea
          ref={inputRef}
          value={editValue}
          onChange={(e) => setEditValue(e.target.value)}
          onBlur={handleBlur}
          onKeyDown={handleKeyDown}
          style={{
            ...sharedStyles,
            resize: 'none',
            minHeight: '3em',
          }}
        />
      );
    }
    return (
      <input
        ref={inputRef}
        type="text"
        value={editValue}
        onChange={(e) => setEditValue(e.target.value)}
        onBlur={handleBlur}
        onKeyDown={handleKeyDown}
        style={sharedStyles}
      />
    );
  }

  return (
    <div onClick={handleClick} style={sharedStyles}>
      {value || <span style={{ opacity: 0.5 }}>{placeholder}</span>}
    </div>
  );
}

// =============================================================================
// Main Slide Canvas
// =============================================================================

export default function SlideCanvas() {
  const {
    currentProject,
    selectedSlide,
    selectedElementId,
    setSelectedElementId,
    updateElement,
  } = useCarouselBuilder();

  const canvasRef = useRef(null);

  const handleCanvasClick = useCallback(() => {
    setSelectedElementId(null);
  }, [setSelectedElementId]);

  const handleElementSelect = useCallback((elementId) => {
    setSelectedElementId(elementId);
  }, [setSelectedElementId]);

  const handleElementChange = useCallback((elementId, updates) => {
    if (selectedSlide) {
      updateElement(selectedSlide.id, elementId, updates);
    }
  }, [selectedSlide, updateElement]);

  if (!selectedSlide) {
    return (
      <div className="carousel-canvas-empty">
        <p>Select a slide to edit</p>
      </div>
    );
  }

  const dimensions = ASPECT_RATIO_SIZES[currentProject?.aspect_ratio] || { width: 1080, height: 1080 };
  const aspectRatio = `${dimensions.width} / ${dimensions.height}`;

  // Build background styles (sanitize CSS values to prevent injection)
  const sanitizeCSS = (val) => val ? String(val).replace(/[;{}<>"'\\]/g, '') : '';
  const sanitizeUrl = (url) => {
    if (!url) return '';
    const trimmed = String(url).trim();
    if (!/^(https?:|data:image\/)/i.test(trimmed)) return '';
    return trimmed.replace(/[)"'\\;{}]/g, '');
  };

  const backgroundStyles = {};
  if (selectedSlide.background_type === 'gradient' && selectedSlide.background_gradient) {
    const angle = parseInt(selectedSlide.background_gradient.angle, 10) || 135;
    const colors = (selectedSlide.background_gradient.colors || ['#667eea', '#764ba2'])
      .map(c => sanitizeCSS(c));
    backgroundStyles.background = `linear-gradient(${angle}deg, ${colors.join(', ')})`;
  } else if (selectedSlide.background_type === 'image' && selectedSlide.background_image_url) {
    const safeUrl = sanitizeUrl(selectedSlide.background_image_url);
    if (safeUrl) {
      backgroundStyles.backgroundImage = `url(${safeUrl})`;
      backgroundStyles.backgroundSize = 'cover';
      backgroundStyles.backgroundPosition = 'center';
    } else {
      backgroundStyles.backgroundColor = '#217F8D';
    }
  } else {
    backgroundStyles.backgroundColor = sanitizeCSS(selectedSlide.background_color) || '#217F8D';
  }

  return (
    <div className="carousel-canvas-container">
      <div className="carousel-canvas-wrapper">
        <div
          ref={canvasRef}
          className="carousel-canvas"
          style={{
            aspectRatio,
            ...backgroundStyles,
          }}
          onClick={handleCanvasClick}
        >
          <SlideContent
            slide={selectedSlide}
            selectedElementId={selectedElementId}
            onElementSelect={handleElementSelect}
            onElementChange={handleElementChange}
          />
        </div>
      </div>

      <div className="carousel-canvas-info">
        {dimensions.width} x {dimensions.height}px
      </div>
    </div>
  );
}

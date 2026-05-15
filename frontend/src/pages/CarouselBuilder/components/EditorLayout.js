/**
 * Editor Layout
 *
 * Three-panel layout for the carousel editor:
 * - Left: Slide navigator with thumbnails
 * - Center: Canvas with slide preview
 * - Right: Properties panel for styling
 */

import React, { useCallback, useState } from 'react';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';
import { useCarouselBuilder, ASPECT_RATIO_SIZES } from '../CarouselBuilderContext';
import SlideCanvas from './SlideCanvas';
import PropertiesPanel from './PropertiesPanel';
import ExportModal from './ExportModal';
import AIGenerateModal from './AIGenerateModal';
import ThemePicker from './ThemePicker';
import TemplateBrowser from './TemplateBrowser';

// =============================================================================
// Editor Header/Toolbar
// =============================================================================

function EditorToolbar({ onExport, onAIGenerate, onThemes, onTemplates }) {
  const {
    currentProject,
    saving,
    isDirty,
    saveCurrentSlide,
    updateProject,
  } = useCarouselBuilder();

  const handleBack = () => {
    // Clear current project to go back to list
    window.location.reload(); // Simple approach; could use context method
  };

  return (
    <div className="carousel-editor-toolbar">
      <div className="carousel-toolbar-left">
        <button className="btn-icon" onClick={handleBack} title="Back to projects">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 12H5M12 19l-7-7 7-7" />
          </svg>
        </button>
        <div className="carousel-project-title">
          <input
            type="text"
            value={currentProject?.name || ''}
            onChange={(e) => updateProject({ name: e.target.value })}
            className="carousel-title-input"
          />
          {saving && <span className="carousel-save-indicator">Saving...</span>}
          {!saving && isDirty && <span className="carousel-save-indicator unsaved">Unsaved</span>}
        </div>
      </div>

      <div className="carousel-toolbar-center">
        <button className="btn-toolbar-action btn-templates" onClick={onTemplates} title="Browse templates">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <path d="M3 9h18" />
            <path d="M9 21V9" />
          </svg>
          Templates
        </button>
        <button className="btn-toolbar-action btn-themes" onClick={onThemes} title="Choose theme">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 2v10l7 4" />
          </svg>
          Themes
        </button>
        <span className="carousel-platform-badge">
          {currentProject?.platform}
        </span>
        <span className="carousel-size-badge">
          {ASPECT_RATIO_SIZES[currentProject?.aspect_ratio]?.label || currentProject?.aspect_ratio}
        </span>
      </div>

      <div className="carousel-toolbar-right">
        <button className="btn-ai-generate" onClick={onAIGenerate} title="Generate content with AI">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          AI Generate
        </button>
        <button
          className="btn-secondary"
          onClick={saveCurrentSlide}
          disabled={saving || !isDirty}
        >
          Save
        </button>
        <button className="btn-primary" onClick={onExport}>
          Export
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// Slide Navigator (Left Panel)
// =============================================================================

function SlideNavigator() {
  const {
    slides,
    selectedSlideId,
    setSelectedSlideId,
    addSlide,
    deleteSlide,
    duplicateSlide,
    reorderSlides,
    currentProject,
  } = useCarouselBuilder();

  const handleDragEnd = useCallback((result) => {
    if (!result.destination) return;
    reorderSlides(result.source.index, result.destination.index);
  }, [reorderSlides]);

  const aspectRatio = currentProject?.aspect_ratio?.replace(':', '/') || '1/1';

  return (
    <div className="carousel-slide-navigator">
      <div className="carousel-nav-header">
        <h3>Slides</h3>
        <button className="btn-icon btn-add" onClick={() => addSlide()} title="Add slide">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
      </div>

      <DragDropContext onDragEnd={handleDragEnd}>
        <Droppable droppableId="slides">
          {(provided) => (
            <div
              className="carousel-slide-list"
              ref={provided.innerRef}
              {...provided.droppableProps}
            >
              {slides.map((slide, index) => (
                <Draggable key={slide.id} draggableId={slide.id} index={index}>
                  {(provided, snapshot) => (
                    <div
                      ref={provided.innerRef}
                      {...provided.draggableProps}
                      className={`carousel-slide-thumb ${selectedSlideId === slide.id ? 'selected' : ''} ${snapshot.isDragging ? 'dragging' : ''}`}
                      onClick={() => setSelectedSlideId(slide.id)}
                    >
                      <div
                        className="carousel-thumb-preview"
                        style={{
                          aspectRatio,
                          backgroundColor: slide.background_color || '#1F3D2E',
                          backgroundImage: slide.background_gradient
                            ? `linear-gradient(${slide.background_gradient.angle || 135}deg, ${(slide.background_gradient.colors || ['#1F3D2E', '#2D7A52']).join(', ')})`
                            : undefined,
                        }}
                      >
                        <div className="carousel-thumb-content">
                          {slide.title && (
                            <span className="carousel-thumb-title">{slide.title}</span>
                          )}
                        </div>
                      </div>

                      <div className="carousel-thumb-info">
                        <span
                          className="carousel-thumb-number"
                          {...provided.dragHandleProps}
                        >
                          {index + 1}
                        </span>
                        <div className="carousel-thumb-actions">
                          <button
                            className="btn-icon-sm"
                            onClick={(e) => { e.stopPropagation(); duplicateSlide(slide.id); }}
                            title="Duplicate"
                          >
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                              <rect x="9" y="9" width="13" height="13" rx="2" />
                              <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
                            </svg>
                          </button>
                          {slides.length > 1 && (
                            <button
                              className="btn-icon-sm btn-danger"
                              onClick={(e) => { e.stopPropagation(); deleteSlide(slide.id); }}
                              title="Delete"
                            >
                              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                              </svg>
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </Draggable>
              ))}
              {provided.placeholder}
            </div>
          )}
        </Droppable>
      </DragDropContext>

      <div className="carousel-nav-footer">
        <button className="btn-add-slide" onClick={() => addSlide()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 5v14M5 12h14" />
          </svg>
          Add Slide
        </button>
      </div>
    </div>
  );
}

// =============================================================================
// Main Editor Layout
// =============================================================================

export default function EditorLayout() {
  const [showExportModal, setShowExportModal] = useState(false);
  const [showAIModal, setShowAIModal] = useState(false);
  const [showThemeModal, setShowThemeModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const { loadProject, currentProject, applyTemplate } = useCarouselBuilder();

  const handleAIApply = () => {
    // Reload the project to get the new AI-generated slides
    if (currentProject?.id) {
      loadProject(currentProject.id);
    }
  };

  const handleSelectTemplate = async (template) => {
    // Apply template to project
    if (applyTemplate) {
      await applyTemplate(template);
    }
  };

  return (
    <div className="carousel-editor">
      <EditorToolbar
        onExport={() => setShowExportModal(true)}
        onAIGenerate={() => setShowAIModal(true)}
        onThemes={() => setShowThemeModal(true)}
        onTemplates={() => setShowTemplateModal(true)}
      />

      <div className="carousel-editor-content">
        {/* Left Panel - Slide Navigator */}
        <div className="carousel-editor-left">
          <SlideNavigator />
        </div>

        {/* Center Panel - Canvas */}
        <div className="carousel-editor-center">
          <SlideCanvas />
        </div>

        {/* Right Panel - Properties */}
        <div className="carousel-editor-right">
          <PropertiesPanel />
        </div>
      </div>

      {/* Export Modal */}
      <ExportModal
        open={showExportModal}
        onClose={() => setShowExportModal(false)}
      />

      {/* AI Generate Modal */}
      <AIGenerateModal
        open={showAIModal}
        onClose={() => setShowAIModal(false)}
        onApply={handleAIApply}
      />

      {/* Theme Picker Modal */}
      <ThemePicker
        open={showThemeModal}
        onClose={() => setShowThemeModal(false)}
      />

      {/* Template Browser Modal */}
      <TemplateBrowser
        open={showTemplateModal}
        onClose={() => setShowTemplateModal(false)}
        onSelectTemplate={handleSelectTemplate}
      />
    </div>
  );
}

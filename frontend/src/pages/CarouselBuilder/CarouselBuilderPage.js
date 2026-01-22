/**
 * Carousel Builder Page
 *
 * Main page for the AI-powered carousel builder.
 * Displays project list or editor based on current state.
 */

import React, { useEffect, useState } from 'react';
import {
  CarouselBuilderProvider,
  useCarouselBuilder,
  PROJECT_TYPES,
  PLATFORM_DIMENSIONS,
  ASPECT_RATIO_SIZES,
} from './CarouselBuilderContext';
import EditorLayout from './components/EditorLayout';
import './CarouselBuilder.css';

// =============================================================================
// New Project Modal
// =============================================================================

function NewProjectModal({ open, onClose, onCreate }) {
  const [name, setName] = useState('');
  const [projectType, setProjectType] = useState('custom');
  const [platform, setPlatform] = useState('linkedin');
  const [aspectRatio, setAspectRatio] = useState('1:1');
  const [creating, setCreating] = useState(false);

  const availableRatios = PLATFORM_DIMENSIONS[platform]?.aspectRatios || ['1:1'];

  useEffect(() => {
    if (!availableRatios.includes(aspectRatio)) {
      setAspectRatio(availableRatios[0]);
    }
  }, [platform, availableRatios, aspectRatio]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;

    setCreating(true);
    try {
      await onCreate({
        name: name.trim(),
        project_type: projectType,
        platform,
        aspect_ratio: aspectRatio,
      });
      onClose();
      setName('');
    } catch (err) {
      console.error('Failed to create project:', err);
    } finally {
      setCreating(false);
    }
  };

  if (!open) return null;

  return (
    <div className="carousel-modal-overlay" onClick={onClose}>
      <div className="carousel-modal" onClick={e => e.stopPropagation()}>
        <div className="carousel-modal-header">
          <h2>Create New Carousel</h2>
          <button className="carousel-modal-close" onClick={onClose}>&times;</button>
        </div>

        <form onSubmit={handleSubmit}>
          <div className="carousel-modal-body">
            <div className="carousel-form-group">
              <label>Project Name</label>
              <input
                type="text"
                value={name}
                onChange={e => setName(e.target.value)}
                placeholder="My Awesome Carousel"
                autoFocus
                required
              />
            </div>

            <div className="carousel-form-group">
              <label>Type</label>
              <div className="carousel-type-grid">
                {PROJECT_TYPES.map(type => (
                  <button
                    key={type.value}
                    type="button"
                    className={`carousel-type-card ${projectType === type.value ? 'selected' : ''}`}
                    onClick={() => setProjectType(type.value)}
                  >
                    <span className="carousel-type-label">{type.label}</span>
                    <span className="carousel-type-desc">{type.description}</span>
                  </button>
                ))}
              </div>
            </div>

            <div className="carousel-form-row">
              <div className="carousel-form-group">
                <label>Platform</label>
                <select value={platform} onChange={e => setPlatform(e.target.value)}>
                  {Object.entries(PLATFORM_DIMENSIONS).map(([key, { label }]) => (
                    <option key={key} value={key}>{label}</option>
                  ))}
                </select>
              </div>

              <div className="carousel-form-group">
                <label>Aspect Ratio</label>
                <select value={aspectRatio} onChange={e => setAspectRatio(e.target.value)}>
                  {availableRatios.map(ratio => (
                    <option key={ratio} value={ratio}>
                      {ASPECT_RATIO_SIZES[ratio]?.label || ratio}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="carousel-dimension-preview">
              <div
                className="carousel-dimension-box"
                style={{
                  aspectRatio: aspectRatio.replace(':', '/'),
                  maxHeight: '100px',
                }}
              >
                {ASPECT_RATIO_SIZES[aspectRatio]?.width} x {ASPECT_RATIO_SIZES[aspectRatio]?.height}
              </div>
            </div>
          </div>

          <div className="carousel-modal-footer">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={creating}>
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={creating || !name.trim()}>
              {creating ? 'Creating...' : 'Create Carousel'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// =============================================================================
// Project List View
// =============================================================================

function ProjectList() {
  const {
    projects,
    loading,
    fetchProjects,
    loadProject,
    deleteProject,
    createProject,
  } = useCarouselBuilder();

  const [showNewModal, setShowNewModal] = useState(false);
  const [deleteConfirm, setDeleteConfirm] = useState(null);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleDelete = async (projectId) => {
    await deleteProject(projectId);
    setDeleteConfirm(null);
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '';
    return new Date(dateStr).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
    });
  };

  return (
    <div className="carousel-project-list">
      <div className="carousel-list-header">
        <div>
          <h1>Carousel Builder</h1>
          <p>Create engaging social media carousels for your marketing</p>
        </div>
        <button className="btn-primary" onClick={() => setShowNewModal(true)}>
          + New Carousel
        </button>
      </div>

      {loading ? (
        <div className="carousel-loading">
          <div className="carousel-spinner" />
          <p>Loading projects...</p>
        </div>
      ) : projects.length === 0 ? (
        <div className="carousel-empty">
          <div className="carousel-empty-icon">
            <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="3" y="3" width="7" height="7" rx="1" />
              <rect x="14" y="3" width="7" height="7" rx="1" />
              <rect x="3" y="14" width="7" height="7" rx="1" />
              <rect x="14" y="14" width="7" height="7" rx="1" />
            </svg>
          </div>
          <h3>No carousels yet</h3>
          <p>Create your first carousel to get started</p>
          <button className="btn-primary" onClick={() => setShowNewModal(true)}>
            Create Your First Carousel
          </button>
        </div>
      ) : (
        <div className="carousel-grid">
          {projects.map(project => (
            <div key={project.id} className="carousel-project-card">
              <div
                className="carousel-project-preview"
                onClick={() => loadProject(project.id)}
                style={{
                  aspectRatio: project.aspect_ratio?.replace(':', '/') || '1/1',
                }}
              >
                <div className="carousel-project-preview-inner">
                  <span className="carousel-project-slides">{project.slide_count || 0} slides</span>
                </div>
              </div>

              <div className="carousel-project-info">
                <h3 onClick={() => loadProject(project.id)}>{project.name}</h3>
                <div className="carousel-project-meta">
                  <span className="carousel-project-type">{project.project_type}</span>
                  <span className="carousel-project-platform">{project.platform}</span>
                  <span className="carousel-project-date">{formatDate(project.updated_at)}</span>
                </div>
              </div>

              <div className="carousel-project-actions">
                <button
                  className="btn-icon"
                  onClick={() => loadProject(project.id)}
                  title="Edit"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                </button>
                <button
                  className="btn-icon btn-danger"
                  onClick={() => setDeleteConfirm(project.id)}
                  title="Delete"
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <path d="M3 6h18M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
                  </svg>
                </button>
              </div>

              {deleteConfirm === project.id && (
                <div className="carousel-delete-confirm">
                  <p>Delete "{project.name}"?</p>
                  <div className="carousel-delete-actions">
                    <button className="btn-secondary btn-sm" onClick={() => setDeleteConfirm(null)}>
                      Cancel
                    </button>
                    <button className="btn-danger btn-sm" onClick={() => handleDelete(project.id)}>
                      Delete
                    </button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      <NewProjectModal
        open={showNewModal}
        onClose={() => setShowNewModal(false)}
        onCreate={createProject}
      />
    </div>
  );
}

// =============================================================================
// Main Page Content
// =============================================================================

function CarouselBuilderContent() {
  const { currentProject, loading } = useCarouselBuilder();

  if (loading) {
    return (
      <div className="carousel-loading-page">
        <div className="carousel-spinner" />
        <p>Loading...</p>
      </div>
    );
  }

  if (currentProject) {
    return <EditorLayout />;
  }

  return <ProjectList />;
}

// =============================================================================
// Page Export
// =============================================================================

export default function CarouselBuilderPage() {
  return (
    <CarouselBuilderProvider>
      <div className="carousel-builder-page">
        <CarouselBuilderContent />
      </div>
    </CarouselBuilderProvider>
  );
}

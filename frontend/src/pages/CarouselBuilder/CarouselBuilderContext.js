/**
 * Carousel Builder Context
 *
 * State management for the carousel builder editor.
 * Handles projects, slides, selection, and API operations.
 */

import React, { createContext, useContext, useState, useCallback, useEffect, useRef } from 'react';
import api from '../../services/api';

const CarouselBuilderContext = createContext(null);

export const PLATFORM_DIMENSIONS = {
  linkedin: { label: 'LinkedIn', aspectRatios: ['1:1', '4:5'] },
  instagram: { label: 'Instagram', aspectRatios: ['1:1', '4:5', '9:16'] },
  tiktok: { label: 'TikTok', aspectRatios: ['9:16'] },
  facebook: { label: 'Facebook', aspectRatios: ['1:1'] },
};

export const ASPECT_RATIO_SIZES = {
  '1:1': { width: 1080, height: 1080, label: 'Square (1:1)' },
  '4:5': { width: 1080, height: 1350, label: 'Portrait (4:5)' },
  '9:16': { width: 1080, height: 1920, label: 'Story (9:16)' },
};

export const PROJECT_TYPES = [
  { value: 'just_closed', label: 'Just Closed', description: 'Celebrate a funded loan' },
  { value: 'marketing', label: 'Marketing', description: 'Promotional content' },
  { value: 'rate_update', label: 'Rate Update', description: 'Market rate information' },
  { value: 'educational', label: 'Educational', description: 'Tips and guides' },
  { value: 'custom', label: 'Custom', description: 'Start from scratch' },
];

export function CarouselBuilderProvider({ children }) {
  // Project state
  const [projects, setProjects] = useState([]);
  const [currentProject, setCurrentProject] = useState(null);
  const [slides, setSlides] = useState([]);

  // Selection state
  const [selectedSlideId, setSelectedSlideId] = useState(null);
  const [selectedElementId, setSelectedElementId] = useState(null);

  // UI state
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [isDirty, setIsDirty] = useState(false);
  const [error, setError] = useState(null);

  // Prevent duplicate fetches during mount/unmount cycles
  const isFetchingRef = useRef(false);
  const hasFetchedRef = useRef(false);

  // Computed values
  const selectedSlide = slides.find(s => s.id === selectedSlideId);
  const selectedElement = selectedSlide?.elements?.find(e => e.id === selectedElementId);

  // =========================================================================
  // Project Operations
  // =========================================================================

  const fetchProjects = useCallback(async (force = false) => {
    // Prevent duplicate fetches and infinite loops
    if (isFetchingRef.current) {
      console.log('[CarouselBuilder] Skipping fetch - already fetching');
      return;
    }
    if (hasFetchedRef.current && !force) {
      console.log('[CarouselBuilder] Skipping fetch - already fetched');
      return;
    }

    try {
      isFetchingRef.current = true;
      setLoading(true);
      setError(null);
      const response = await api.get('/api/v1/carousels');
      setProjects(response.data);
      hasFetchedRef.current = true;
    } catch (err) {
      console.error('Failed to fetch projects:', err);
      // Mark as fetched even on error to prevent infinite retry loops
      hasFetchedRef.current = true;
      // Only set error if not a rate limit (429) to avoid confusing users
      if (err.response?.status === 429) {
        setError('Too many requests. Please wait a moment and refresh.');
      } else {
        setError('Failed to load projects');
      }
    } finally {
      setLoading(false);
      isFetchingRef.current = false;
    }
  }, []);

  const loadProject = useCallback(async (projectId) => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.get(`/api/v1/carousels/${projectId}`);
      setCurrentProject(response.data);
      setSlides(response.data.slides || []);
      if (response.data.slides?.length > 0) {
        setSelectedSlideId(response.data.slides[0].id);
      }
      setIsDirty(false);
    } catch (err) {
      console.error('Failed to load project:', err);
      setError('Failed to load project');
    } finally {
      setLoading(false);
    }
  }, []);

  const createProject = useCallback(async (projectData) => {
    try {
      setSaving(true);
      setError(null);
      const response = await api.post('/api/v1/carousels', projectData);
      setCurrentProject(response.data);
      setSlides(response.data.slides || []);
      if (response.data.slides?.length > 0) {
        setSelectedSlideId(response.data.slides[0].id);
      }
      setIsDirty(false);
      return response.data;
    } catch (err) {
      console.error('Failed to create project:', err);
      setError('Failed to create project');
      throw err;
    } finally {
      setSaving(false);
    }
  }, []);

  const updateProject = useCallback(async (updates) => {
    if (!currentProject) return;

    try {
      setSaving(true);
      const response = await api.put(`/api/v1/carousels/${currentProject.id}`, updates);
      setCurrentProject(prev => ({ ...prev, ...response.data }));
      setIsDirty(false);
    } catch (err) {
      console.error('Failed to update project:', err);
      setError('Failed to save changes');
    } finally {
      setSaving(false);
    }
  }, [currentProject]);

  const deleteProject = useCallback(async (projectId) => {
    try {
      setSaving(true);
      await api.delete(`/api/v1/carousels/${projectId}`);
      setProjects(prev => prev.filter(p => p.id !== projectId));
      if (currentProject?.id === projectId) {
        setCurrentProject(null);
        setSlides([]);
        setSelectedSlideId(null);
      }
    } catch (err) {
      console.error('Failed to delete project:', err);
      setError('Failed to delete project');
    } finally {
      setSaving(false);
    }
  }, [currentProject]);

  // =========================================================================
  // Slide Operations
  // =========================================================================

  const addSlide = useCallback(async (slideData = {}) => {
    if (!currentProject) return;

    try {
      setSaving(true);
      const response = await api.post(`/api/v1/carousels/${currentProject.id}/slides`, {
        title: 'New Slide',
        subtitle: '',
        background_type: 'solid',
        background_color: '#1F3D2E',
        layout_template: 'centered',
        elements: [],
        ...slideData,
      });
      setSlides(prev => [...prev, response.data]);
      setSelectedSlideId(response.data.id);
      setIsDirty(true);
      return response.data;
    } catch (err) {
      console.error('Failed to add slide:', err);
      setError('Failed to add slide');
    } finally {
      setSaving(false);
    }
  }, [currentProject]);

  const updateSlide = useCallback(async (slideId, updates) => {
    if (!currentProject) return;

    // Optimistic update
    setSlides(prev => prev.map(s =>
      s.id === slideId ? { ...s, ...updates } : s
    ));
    setIsDirty(true);

    try {
      setSaving(true);
      await api.put(`/api/v1/carousels/${currentProject.id}/slides/${slideId}`, updates);
    } catch (err) {
      console.error('Failed to update slide:', err);
      // Revert on error
      await loadProject(currentProject.id);
    } finally {
      setSaving(false);
    }
  }, [currentProject, loadProject]);

  const deleteSlide = useCallback(async (slideId) => {
    if (!currentProject) return;

    try {
      setSaving(true);
      await api.delete(`/api/v1/carousels/${currentProject.id}/slides/${slideId}`);

      setSlides(prev => {
        const newSlides = prev.filter(s => s.id !== slideId);
        // Update selection if deleted slide was selected
        if (selectedSlideId === slideId && newSlides.length > 0) {
          setSelectedSlideId(newSlides[0].id);
        } else if (newSlides.length === 0) {
          setSelectedSlideId(null);
        }
        return newSlides;
      });
      setIsDirty(true);
    } catch (err) {
      console.error('Failed to delete slide:', err);
      setError('Failed to delete slide');
    } finally {
      setSaving(false);
    }
  }, [currentProject, selectedSlideId]);

  const duplicateSlide = useCallback(async (slideId) => {
    if (!currentProject) return;

    try {
      setSaving(true);
      const response = await api.post(
        `/api/v1/carousels/${currentProject.id}/slides/${slideId}/duplicate`
      );

      // Insert after the original
      setSlides(prev => {
        const index = prev.findIndex(s => s.id === slideId);
        const newSlides = [...prev];
        newSlides.splice(index + 1, 0, response.data);
        return newSlides.map((s, i) => ({ ...s, order: i }));
      });

      setSelectedSlideId(response.data.id);
      setIsDirty(true);
      return response.data;
    } catch (err) {
      console.error('Failed to duplicate slide:', err);
      setError('Failed to duplicate slide');
    } finally {
      setSaving(false);
    }
  }, [currentProject]);

  const reorderSlides = useCallback(async (fromIndex, toIndex) => {
    if (!currentProject || fromIndex === toIndex) return;

    // Optimistic update
    setSlides(prev => {
      const newSlides = [...prev];
      const [removed] = newSlides.splice(fromIndex, 1);
      newSlides.splice(toIndex, 0, removed);
      return newSlides.map((s, i) => ({ ...s, order: i }));
    });
    setIsDirty(true);

    try {
      setSaving(true);
      const newOrder = slides.map((_, i) => {
        if (i === fromIndex) return slides[toIndex].id;
        if (i === toIndex) return slides[fromIndex].id;
        return slides[i].id;
      });

      // Actually recompute the order
      const reordered = [...slides];
      const [removed] = reordered.splice(fromIndex, 1);
      reordered.splice(toIndex, 0, removed);

      await api.put(`/api/v1/carousels/${currentProject.id}/slides/reorder`, {
        slide_ids: reordered.map(s => s.id),
      });
    } catch (err) {
      console.error('Failed to reorder slides:', err);
      // Revert on error
      await loadProject(currentProject.id);
    } finally {
      setSaving(false);
    }
  }, [currentProject, slides, loadProject]);

  // =========================================================================
  // Element Operations
  // =========================================================================

  const addElement = useCallback((slideId, element) => {
    const newElement = {
      id: `elem_${Date.now()}`,
      type: 'text',
      content: 'New Text',
      position: { x: 50, y: 50 },
      size: { width: 80, height: null },
      styles: {
        fontSize: 24,
        fontWeight: 'normal',
        color: '#ffffff',
        textAlign: 'center',
      },
      ...element,
    };

    setSlides(prev => prev.map(s => {
      if (s.id === slideId) {
        return { ...s, elements: [...(s.elements || []), newElement] };
      }
      return s;
    }));

    setSelectedElementId(newElement.id);
    setIsDirty(true);

    return newElement;
  }, []);

  const updateElement = useCallback((slideId, elementId, updates) => {
    setSlides(prev => prev.map(s => {
      if (s.id === slideId) {
        return {
          ...s,
          elements: (s.elements || []).map(e =>
            e.id === elementId ? { ...e, ...updates } : e
          ),
        };
      }
      return s;
    }));
    setIsDirty(true);
  }, []);

  const deleteElement = useCallback((slideId, elementId) => {
    setSlides(prev => prev.map(s => {
      if (s.id === slideId) {
        return {
          ...s,
          elements: (s.elements || []).filter(e => e.id !== elementId),
        };
      }
      return s;
    }));

    if (selectedElementId === elementId) {
      setSelectedElementId(null);
    }
    setIsDirty(true);
  }, [selectedElementId]);

  // =========================================================================
  // Save current slide state to API
  // =========================================================================

  const saveCurrentSlide = useCallback(async () => {
    if (!currentProject || !selectedSlide) return;

    try {
      setSaving(true);
      await api.put(
        `/api/v1/carousels/${currentProject.id}/slides/${selectedSlide.id}`,
        {
          title: selectedSlide.title,
          subtitle: selectedSlide.subtitle,
          body_text: selectedSlide.body_text,
          background_type: selectedSlide.background_type,
          background_color: selectedSlide.background_color,
          background_gradient: selectedSlide.background_gradient,
          background_image_url: selectedSlide.background_image_url,
          layout_template: selectedSlide.layout_template,
          elements: selectedSlide.elements,
          custom_styles: selectedSlide.custom_styles,
        }
      );
      setIsDirty(false);
    } catch (err) {
      console.error('Failed to save slide:', err);
      setError('Failed to save changes');
    } finally {
      setSaving(false);
    }
  }, [currentProject, selectedSlide]);

  // Auto-save when dirty (debounced)
  useEffect(() => {
    if (!isDirty || !currentProject || !selectedSlide) return;

    const timer = setTimeout(() => {
      saveCurrentSlide();
    }, 2000);

    return () => clearTimeout(timer);
  }, [isDirty, currentProject, selectedSlide, saveCurrentSlide]);

  // Initial fetch on mount - do this in the provider to avoid mount/unmount loops
  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // =========================================================================
  // Template Operations
  // =========================================================================

  const applyTemplate = useCallback(async (template) => {
    if (!currentProject || !template) return;

    try {
      setSaving(true);
      setError(null);

      // Apply template to the project via API
      const response = await api.post(
        `/api/v1/carousels/${currentProject.id}/apply-template`,
        { template_id: template.id }
      );

      // Update local state with the new slides
      if (response.data.slides) {
        setSlides(response.data.slides);
        if (response.data.slides.length > 0) {
          setSelectedSlideId(response.data.slides[0].id);
        }
      }

      // Update project if theme was changed
      if (response.data.project) {
        setCurrentProject(prev => ({ ...prev, ...response.data.project }));
      }

      setIsDirty(false);
      return response.data;
    } catch (err) {
      console.error('Failed to apply template:', err);
      setError('Failed to apply template');
      throw err;
    } finally {
      setSaving(false);
    }
  }, [currentProject]);

  // =========================================================================
  // Context value
  // =========================================================================

  const value = {
    // State
    projects,
    currentProject,
    slides,
    selectedSlideId,
    selectedSlide,
    selectedElementId,
    selectedElement,
    loading,
    saving,
    isDirty,
    error,

    // Project operations
    fetchProjects,
    loadProject,
    createProject,
    updateProject,
    deleteProject,

    // Slide operations
    addSlide,
    updateSlide,
    deleteSlide,
    duplicateSlide,
    reorderSlides,
    setSelectedSlideId,

    // Element operations
    addElement,
    updateElement,
    deleteElement,
    setSelectedElementId,

    // Template operations
    applyTemplate,

    // Utilities
    saveCurrentSlide,
    setError,
  };

  return (
    <CarouselBuilderContext.Provider value={value}>
      {children}
    </CarouselBuilderContext.Provider>
  );
}

export function useCarouselBuilder() {
  const context = useContext(CarouselBuilderContext);
  if (!context) {
    throw new Error('useCarouselBuilder must be used within CarouselBuilderProvider');
  }
  return context;
}

export default CarouselBuilderContext;

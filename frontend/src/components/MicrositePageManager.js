/**
 * MicrositePageManager - Manage multiple pages for a microsite
 *
 * Features:
 * - View/add/edit/delete pages
 * - Reorder pages via drag or buttons
 * - Toggle page visibility
 * - Page content editing
 */

import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import './MicrositePageManager.css';

// Page type icons
const PAGE_ICONS = {
  about: '👤',
  services: '🏠',
  testimonials: '⭐',
  blog: '📝',
  contact: '📞',
  custom: '📄',
  home: '🏡'
};

// Default page templates
const PAGE_TEMPLATES = [
  {
    type: 'about',
    name: 'About Me / Bio',
    description: 'Showcase your background, experience, and credentials',
    suggestedSlug: 'about'
  },
  {
    type: 'services',
    name: 'Loan Programs',
    description: 'Highlight the loan programs and services you offer',
    suggestedSlug: 'services'
  },
  {
    type: 'testimonials',
    name: 'Client Reviews',
    description: 'Display client reviews and success stories',
    suggestedSlug: 'testimonials'
  },
  {
    type: 'blog',
    name: 'Blog',
    description: 'Share articles, tips, and market updates (AI-powered)',
    suggestedSlug: 'blog'
  }
];

const MicrositePageManager = ({ onToast }) => {
  const [pages, setPages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showAddModal, setShowAddModal] = useState(false);
  const [editingPage, setEditingPage] = useState(null);
  const [newPage, setNewPage] = useState({
    page_type: 'about',
    slug: 'about',
    title: 'About Me',
    is_enabled: true,
    show_in_nav: true
  });

  // Fetch pages
  const fetchPages = useCallback(async () => {
    try {
      const { data } = await api.get('/api/v1/microsites/my-microsite/pages');
      setPages(data);
    } catch (err) {
      console.error('Error fetching pages:', err);
      onToast?.('Failed to load pages', 'error');
    } finally {
      setLoading(false);
    }
  }, [onToast]);

  useEffect(() => {
    fetchPages();
  }, [fetchPages]);

  // Create new page
  const handleCreatePage = async () => {
    setSaving(true);
    try {
      const { data } = await api.post('/api/v1/microsites/my-microsite/pages', {
        ...newPage,
        display_order: pages.length
      });

      setPages(prev => [...prev, data]);
      setShowAddModal(false);
      setNewPage({
        page_type: 'about',
        slug: 'about',
        title: 'About Me',
        is_enabled: true,
        show_in_nav: true
      });
      onToast?.('Page created successfully!', 'success');
    } catch (err) {
      console.error('Error creating page:', err);
      onToast?.(err.response?.data?.detail || 'Failed to create page', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Update page
  const handleUpdatePage = async (slug, updates) => {
    setSaving(true);
    try {
      const { data } = await api.put(`/api/v1/microsites/my-microsite/pages/${slug}`, updates);
      setPages(prev => prev.map(p => p.slug === slug ? data : p));
      if (editingPage?.slug === slug) {
        setEditingPage(data);
      }
      onToast?.('Page updated!', 'success');
    } catch (err) {
      console.error('Error updating page:', err);
      onToast?.(err.response?.data?.detail || 'Failed to update page', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Delete page
  const handleDeletePage = async (slug) => {
    if (!window.confirm('Are you sure you want to delete this page?')) {
      return;
    }

    setSaving(true);
    try {
      await api.delete(`/api/v1/microsites/my-microsite/pages/${slug}`);
      setPages(prev => prev.filter(p => p.slug !== slug));
      if (editingPage?.slug === slug) {
        setEditingPage(null);
      }
      onToast?.('Page deleted', 'success');
    } catch (err) {
      console.error('Error deleting page:', err);
      onToast?.(err.response?.data?.detail || 'Failed to delete page', 'error');
    } finally {
      setSaving(false);
    }
  };

  // Toggle page enabled
  const handleToggleEnabled = async (page) => {
    await handleUpdatePage(page.slug, { is_enabled: !page.isEnabled });
  };

  // Toggle show in nav
  const handleToggleNav = async (page) => {
    await handleUpdatePage(page.slug, { show_in_nav: !page.showInNav });
  };

  // Move page up/down
  const handleMoveUp = async (index) => {
    if (index === 0) return;
    const newPages = [...pages];
    [newPages[index - 1], newPages[index]] = [newPages[index], newPages[index - 1]];

    // Update display orders
    const reorder = newPages.map((p, i) => ({ slug: p.slug, display_order: i }));

    try {
      await api.post('/api/v1/microsites/my-microsite/pages/reorder', reorder);
      setPages(newPages.map((p, i) => ({ ...p, displayOrder: i })));
    } catch (err) {
      console.error('Error reordering:', err);
    }
  };

  const handleMoveDown = async (index) => {
    if (index === pages.length - 1) return;
    const newPages = [...pages];
    [newPages[index], newPages[index + 1]] = [newPages[index + 1], newPages[index]];

    const reorder = newPages.map((p, i) => ({ slug: p.slug, display_order: i }));

    try {
      await api.post('/api/v1/microsites/my-microsite/pages/reorder', reorder);
      setPages(newPages.map((p, i) => ({ ...p, displayOrder: i })));
    } catch (err) {
      console.error('Error reordering:', err);
    }
  };

  // Select page template
  const handleSelectTemplate = (template) => {
    setNewPage(prev => ({
      ...prev,
      page_type: template.type,
      slug: template.suggestedSlug,
      title: template.name.split('/')[0].trim()
    }));
  };

  // Check if page type already exists
  const pageTypeExists = (type) => {
    return pages.some(p => p.pageType === type);
  };

  if (loading) {
    return (
      <div className="page-manager-loading">
        <div className="loading-spinner"></div>
        <p>Loading pages...</p>
      </div>
    );
  }

  return (
    <div className="page-manager">
      {/* Header */}
      <div className="page-manager-header">
        <div>
          <h3>Website Pages</h3>
          <p>Add and manage pages for your microsite</p>
        </div>
        <button
          className="btn-add-page"
          onClick={() => setShowAddModal(true)}
        >
          + Add Page
        </button>
      </div>

      {/* Pages List */}
      {pages.length === 0 ? (
        <div className="no-pages">
          <div className="no-pages-icon">📄</div>
          <h4>No pages yet</h4>
          <p>Add pages to build your website. Start with an About page or Loan Programs page.</p>
          <button
            className="btn-add-first"
            onClick={() => setShowAddModal(true)}
          >
            Add Your First Page
          </button>
        </div>
      ) : (
        <div className="pages-list">
          {pages.map((page, index) => (
            <div
              key={page.id}
              className={`page-item ${!page.isEnabled ? 'disabled' : ''} ${editingPage?.id === page.id ? 'editing' : ''}`}
            >
              <div className="page-drag-handle">
                <button
                  className="btn-move"
                  onClick={() => handleMoveUp(index)}
                  disabled={index === 0}
                  title="Move up"
                >
                  ↑
                </button>
                <button
                  className="btn-move"
                  onClick={() => handleMoveDown(index)}
                  disabled={index === pages.length - 1}
                  title="Move down"
                >
                  ↓
                </button>
              </div>

              <div className="page-icon">
                {PAGE_ICONS[page.pageType] || PAGE_ICONS.custom}
              </div>

              <div className="page-info">
                <h4>{page.title}</h4>
                <span className="page-slug">/{page.slug}</span>
              </div>

              <div className="page-toggles">
                <label className="toggle" title="Show in navigation">
                  <input
                    type="checkbox"
                    checked={page.showInNav}
                    onChange={() => handleToggleNav(page)}
                  />
                  <span className="toggle-label">Nav</span>
                </label>
                <label className="toggle" title="Page enabled">
                  <input
                    type="checkbox"
                    checked={page.isEnabled}
                    onChange={() => handleToggleEnabled(page)}
                  />
                  <span className="toggle-label">Active</span>
                </label>
              </div>

              <div className="page-actions">
                <button
                  className="btn-edit"
                  onClick={() => setEditingPage(editingPage?.id === page.id ? null : page)}
                  title="Edit page"
                >
                  {editingPage?.id === page.id ? 'Close' : 'Edit'}
                </button>
                <button
                  className="btn-delete"
                  onClick={() => handleDeletePage(page.slug)}
                  title="Delete page"
                >
                  🗑️
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Page Editor Panel */}
      {editingPage && (
        <div className="page-editor-panel">
          <h4>
            {PAGE_ICONS[editingPage.pageType] || PAGE_ICONS.custom} Edit: {editingPage.title}
          </h4>

          <div className="editor-fields">
            <div className="field-group">
              <label>Page Title</label>
              <input
                type="text"
                value={editingPage.title}
                onChange={(e) => setEditingPage(prev => ({ ...prev, title: e.target.value }))}
              />
            </div>

            <div className="field-group">
              <label>Meta Title (SEO)</label>
              <input
                type="text"
                value={editingPage.metaTitle || ''}
                onChange={(e) => setEditingPage(prev => ({ ...prev, metaTitle: e.target.value }))}
                placeholder="Leave blank to use page title"
              />
            </div>

            <div className="field-group">
              <label>Meta Description (SEO)</label>
              <textarea
                value={editingPage.metaDescription || ''}
                onChange={(e) => setEditingPage(prev => ({ ...prev, metaDescription: e.target.value }))}
                placeholder="Brief description for search engines"
                rows={2}
              />
            </div>

            {/* Page-type specific content editor */}
            {editingPage.pageType === 'about' && (
              <AboutPageEditor
                content={editingPage.content || {}}
                onChange={(content) => setEditingPage(prev => ({ ...prev, content }))}
              />
            )}

            {editingPage.pageType === 'services' && (
              <ServicesPageEditor
                content={editingPage.content || {}}
                onChange={(content) => setEditingPage(prev => ({ ...prev, content }))}
              />
            )}

            {editingPage.pageType === 'testimonials' && (
              <TestimonialsPageEditor
                content={editingPage.content || {}}
                onChange={(content) => setEditingPage(prev => ({ ...prev, content }))}
              />
            )}

            {editingPage.pageType === 'blog' && (
              <BlogPageEditor
                content={editingPage.content || {}}
                onChange={(content) => setEditingPage(prev => ({ ...prev, content }))}
              />
            )}
          </div>

          <div className="editor-actions">
            <button
              className="btn-cancel"
              onClick={() => setEditingPage(null)}
            >
              Cancel
            </button>
            <button
              className="btn-save-page"
              onClick={() => handleUpdatePage(editingPage.slug, {
                title: editingPage.title,
                content: editingPage.content,
                meta_title: editingPage.metaTitle,
                meta_description: editingPage.metaDescription
              })}
              disabled={saving}
            >
              {saving ? 'Saving...' : 'Save Page'}
            </button>
          </div>
        </div>
      )}

      {/* Add Page Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Add New Page</h3>
              <button className="btn-close" onClick={() => setShowAddModal(false)}>×</button>
            </div>

            <div className="modal-body">
              {/* Page Type Selection */}
              <div className="page-templates">
                <label>Select Page Type</label>
                <div className="template-options">
                  {PAGE_TEMPLATES.map(template => (
                    <div
                      key={template.type}
                      className={`template-option ${newPage.page_type === template.type ? 'selected' : ''} ${pageTypeExists(template.type) ? 'exists' : ''}`}
                      onClick={() => !pageTypeExists(template.type) && handleSelectTemplate(template)}
                    >
                      <span className="template-icon">{PAGE_ICONS[template.type]}</span>
                      <div className="template-text">
                        <strong>{template.name}</strong>
                        <span>{template.description}</span>
                      </div>
                      {pageTypeExists(template.type) && (
                        <span className="exists-badge">Already added</span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Page Details */}
              <div className="field-group">
                <label>Page Title</label>
                <input
                  type="text"
                  value={newPage.title}
                  onChange={(e) => setNewPage(prev => ({ ...prev, title: e.target.value }))}
                  placeholder="e.g., About Me"
                />
              </div>

              <div className="field-group">
                <label>URL Slug</label>
                <div className="slug-input">
                  <span className="slug-prefix">/</span>
                  <input
                    type="text"
                    value={newPage.slug}
                    onChange={(e) => setNewPage(prev => ({
                      ...prev,
                      slug: e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, '-')
                    }))}
                    placeholder="about"
                  />
                </div>
              </div>

              <div className="field-row">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={newPage.show_in_nav}
                    onChange={(e) => setNewPage(prev => ({ ...prev, show_in_nav: e.target.checked }))}
                  />
                  Show in navigation menu
                </label>
              </div>
            </div>

            <div className="modal-footer">
              <button className="btn-cancel" onClick={() => setShowAddModal(false)}>
                Cancel
              </button>
              <button
                className="btn-create-page"
                onClick={handleCreatePage}
                disabled={saving || !newPage.title || !newPage.slug}
              >
                {saving ? 'Creating...' : 'Create Page'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

// ========================================
// Page-specific content editors
// ========================================

const AboutPageEditor = ({ content, onChange }) => {
  const sections = content.sections || [
    { type: 'bio', heading: 'About Me', text: '', image: '' },
    { type: 'experience', heading: 'My Experience', yearsExperience: null, loansFunded: null, volumeFunded: null },
    { type: 'certifications', heading: 'Certifications', items: [] }
  ];

  const updateSection = (index, updates) => {
    const newSections = [...sections];
    newSections[index] = { ...newSections[index], ...updates };
    onChange({ ...content, sections: newSections });
  };

  return (
    <div className="about-editor">
      {/* Bio Section */}
      <div className="section-editor">
        <h5>Bio Section</h5>
        <div className="field-group">
          <label>Heading</label>
          <input
            type="text"
            value={sections[0]?.heading || ''}
            onChange={(e) => updateSection(0, { heading: e.target.value })}
          />
        </div>
        <div className="field-group">
          <label>Bio Text</label>
          <textarea
            rows={4}
            value={sections[0]?.text || ''}
            onChange={(e) => updateSection(0, { text: e.target.value })}
            placeholder="Tell potential clients about yourself, your background, and why they should work with you..."
          />
        </div>
      </div>

      {/* Experience Section */}
      <div className="section-editor">
        <h5>Experience Stats</h5>
        <div className="stats-row">
          <div className="field-group">
            <label>Years of Experience</label>
            <input
              type="number"
              value={sections[1]?.yearsExperience || ''}
              onChange={(e) => updateSection(1, { yearsExperience: parseInt(e.target.value) || null })}
            />
          </div>
          <div className="field-group">
            <label>Loans Funded</label>
            <input
              type="number"
              value={sections[1]?.loansFunded || ''}
              onChange={(e) => updateSection(1, { loansFunded: parseInt(e.target.value) || null })}
            />
          </div>
          <div className="field-group">
            <label>Volume Funded ($)</label>
            <input
              type="number"
              value={sections[1]?.volumeFunded || ''}
              onChange={(e) => updateSection(1, { volumeFunded: parseFloat(e.target.value) || null })}
            />
          </div>
        </div>
      </div>
    </div>
  );
};

const ServicesPageEditor = ({ content, onChange }) => {
  const programs = content.programs || [
    { name: 'Conventional Loans', description: 'Traditional financing with competitive rates', icon: 'home' },
    { name: 'FHA Loans', description: 'Low down payment options for first-time buyers', icon: 'key' },
    { name: 'VA Loans', description: 'Special financing for veterans and service members', icon: 'star' },
    { name: 'Jumbo Loans', description: 'Financing for high-value properties', icon: 'building' }
  ];

  const updateProgram = (index, updates) => {
    const newPrograms = [...programs];
    newPrograms[index] = { ...newPrograms[index], ...updates };
    onChange({ ...content, programs: newPrograms });
  };

  const addProgram = () => {
    onChange({
      ...content,
      programs: [...programs, { name: '', description: '', icon: 'home' }]
    });
  };

  const removeProgram = (index) => {
    onChange({
      ...content,
      programs: programs.filter((_, i) => i !== index)
    });
  };

  return (
    <div className="services-editor">
      <div className="field-group">
        <label>Page Heading</label>
        <input
          type="text"
          value={content.heading || 'Loan Programs I Offer'}
          onChange={(e) => onChange({ ...content, heading: e.target.value })}
        />
      </div>
      <div className="field-group">
        <label>Description</label>
        <textarea
          rows={2}
          value={content.description || ''}
          onChange={(e) => onChange({ ...content, description: e.target.value })}
          placeholder="Brief introduction to your services..."
        />
      </div>

      <h5>Loan Programs</h5>
      {programs.map((program, index) => (
        <div key={index} className="program-item">
          <input
            type="text"
            value={program.name}
            onChange={(e) => updateProgram(index, { name: e.target.value })}
            placeholder="Program name"
          />
          <input
            type="text"
            value={program.description}
            onChange={(e) => updateProgram(index, { description: e.target.value })}
            placeholder="Brief description"
          />
          <button className="btn-remove" onClick={() => removeProgram(index)}>×</button>
        </div>
      ))}
      <button className="btn-add-item" onClick={addProgram}>+ Add Program</button>
    </div>
  );
};

const TestimonialsPageEditor = ({ content, onChange }) => {
  const testimonials = content.testimonials || [];

  const updateTestimonial = (index, updates) => {
    const newTestimonials = [...testimonials];
    newTestimonials[index] = { ...newTestimonials[index], ...updates };
    onChange({ ...content, testimonials: newTestimonials });
  };

  const addTestimonial = () => {
    onChange({
      ...content,
      testimonials: [...testimonials, { name: '', text: '', location: '', date: '' }]
    });
  };

  const removeTestimonial = (index) => {
    onChange({
      ...content,
      testimonials: testimonials.filter((_, i) => i !== index)
    });
  };

  return (
    <div className="testimonials-editor">
      <div className="field-group">
        <label>Page Heading</label>
        <input
          type="text"
          value={content.heading || 'What My Clients Say'}
          onChange={(e) => onChange({ ...content, heading: e.target.value })}
        />
      </div>

      <h5>Client Testimonials</h5>
      {testimonials.length === 0 ? (
        <p className="no-items">No testimonials yet. Add your first client review!</p>
      ) : (
        testimonials.map((testimonial, index) => (
          <div key={index} className="testimonial-item">
            <div className="field-group">
              <label>Client Name</label>
              <input
                type="text"
                value={testimonial.name}
                onChange={(e) => updateTestimonial(index, { name: e.target.value })}
                placeholder="John D."
              />
            </div>
            <div className="field-group">
              <label>Testimonial Text</label>
              <textarea
                rows={3}
                value={testimonial.text}
                onChange={(e) => updateTestimonial(index, { text: e.target.value })}
                placeholder="What did they say about working with you?"
              />
            </div>
            <div className="field-row">
              <div className="field-group">
                <label>Location</label>
                <input
                  type="text"
                  value={testimonial.location || ''}
                  onChange={(e) => updateTestimonial(index, { location: e.target.value })}
                  placeholder="City, State"
                />
              </div>
              <button className="btn-remove" onClick={() => removeTestimonial(index)}>Remove</button>
            </div>
          </div>
        ))
      )}
      <button className="btn-add-item" onClick={addTestimonial}>+ Add Testimonial</button>
    </div>
  );
};

const BlogPageEditor = ({ content, onChange }) => {
  return (
    <div className="blog-editor">
      <div className="field-group">
        <label>Page Heading</label>
        <input
          type="text"
          value={content.heading || 'Latest Insights'}
          onChange={(e) => onChange({ ...content, heading: e.target.value })}
        />
      </div>
      <div className="field-group">
        <label>Description</label>
        <textarea
          rows={2}
          value={content.description || ''}
          onChange={(e) => onChange({ ...content, description: e.target.value })}
          placeholder="Brief intro for your blog page..."
        />
      </div>

      <div className="blog-info">
        <div className="info-icon">🤖</div>
        <div className="info-text">
          <strong>AI-Powered Blog Posts</strong>
          <p>Blog posts will be automatically generated and managed by the AI blog feature. You can create and edit posts from the Blog management section in the CRM.</p>
        </div>
      </div>

      <div className="blog-stats">
        <p><strong>{content.posts?.length || 0}</strong> blog posts published</p>
      </div>
    </div>
  );
};

export default MicrositePageManager;

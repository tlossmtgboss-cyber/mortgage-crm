import React, { useState, useEffect, useRef, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import './KnowledgeBase.css';
import { getToken } from '../utils/tokenStore';

const CATEGORIES = [
  { value: 'loan_products', label: 'Loan Products' },
  { value: 'compliance', label: 'Compliance & Regulations' },
  { value: 'underwriting', label: 'Underwriting Guidelines' },
  { value: 'sales_scripts', label: 'Sales Scripts' },
  { value: 'company_policies', label: 'Company Policies' },
  { value: 'workflows', label: 'Workflows & Processes' },
  { value: 'training', label: 'Training Materials' },
  { value: 'other', label: 'Other' }
];

const KnowledgeBase = () => {
  const [entries, setEntries] = useState([]);
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [selectedEntry, setSelectedEntry] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [notification, setNotification] = useState(null);
  const fileInputRef = useRef(null);

  // Form state
  const [formData, setFormData] = useState({
    title: '',
    category: 'other',
    content: '',
    tags: '',
    priority: 5
  });

  const getToken = () => getToken();

  const showNotification = (message, type = 'success') => {
    setNotification({ message, type });
    setTimeout(() => setNotification(null), 4000);
  };

  const fetchEntries = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (selectedCategory !== 'all') {
        params.append('category', selectedCategory);
      }
      if (searchQuery) {
        params.append('search', searchQuery);
      }

      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai/knowledge-base?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) throw new Error('Failed to fetch entries');
      const data = await response.json();
      setEntries(data);
    } catch (err) {
      console.error('Error fetching entries:', err);
      showNotification('Failed to load knowledge base entries', 'error');
    } finally {
      setLoading(false);
    }
  }, [selectedCategory, searchQuery]);

  const fetchCategories = async () => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai/knowledge-base/categories`,
        {
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) throw new Error('Failed to fetch categories');
      const data = await response.json();
      setCategories(data);
    } catch (err) {
      console.error('Error fetching categories:', err);
    }
  };

  useEffect(() => {
    fetchEntries();
    fetchCategories();
  }, [fetchEntries]);

  const handleCreateEntry = async (e) => {
    e.preventDefault();
    try {
      const tags = formData.tags
        ? formData.tags.split(',').map(t => t.trim()).filter(t => t)
        : [];

      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai/knowledge-base`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            ...formData,
            tags,
            priority: parseInt(formData.priority)
          })
        }
      );

      if (!response.ok) throw new Error('Failed to create entry');

      showNotification('Knowledge entry created successfully!');
      setShowAddModal(false);
      resetForm();
      fetchEntries();
      fetchCategories();
    } catch (err) {
      console.error('Error creating entry:', err);
      showNotification('Failed to create entry', 'error');
    }
  };

  const handleUpdateEntry = async (e) => {
    e.preventDefault();
    if (!selectedEntry) return;

    try {
      const tags = formData.tags
        ? formData.tags.split(',').map(t => t.trim()).filter(t => t)
        : [];

      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai/knowledge-base/${selectedEntry.id}`,
        {
          method: 'PUT',
          headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            ...formData,
            tags,
            priority: parseInt(formData.priority)
          })
        }
      );

      if (!response.ok) throw new Error('Failed to update entry');

      showNotification('Knowledge entry updated successfully!');
      setShowEditModal(false);
      setSelectedEntry(null);
      resetForm();
      fetchEntries();
    } catch (err) {
      console.error('Error updating entry:', err);
      showNotification('Failed to update entry', 'error');
    }
  };

  const handleDeleteEntry = async (entryId) => {
    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai/knowledge-base/${entryId}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${getToken()}`
          }
        }
      );

      if (!response.ok) throw new Error('Failed to delete entry');

      showNotification('Entry deleted successfully!');
      fetchEntries();
      fetchCategories();
    } catch (err) {
      console.error('Error deleting entry:', err);
      showNotification('Failed to delete entry', 'error');
    }
  };

  const handleFileUpload = async (file) => {
    if (!file) return;

    const allowedTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain', 'text/markdown'];
    const allowedExtensions = ['.pdf', '.docx', '.txt', '.md'];

    const fileExtension = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowedExtensions.includes(fileExtension)) {
      showNotification('Please upload a PDF, DOCX, TXT, or MD file', 'error');
      return;
    }

    setUploading(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('category', 'other');

      const response = await fetch(
        `${API_BASE_URL}/api/v1/ai/knowledge-base/upload`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getToken()}`
          },
          body: formData
        }
      );

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || 'Upload failed');
      }

      const data = await response.json();
      showNotification(`Document "${data.title}" uploaded and processed successfully!`);
      fetchEntries();
      fetchCategories();
    } catch (err) {
      console.error('Error uploading file:', err);
      showNotification(err.message || 'Failed to upload document', 'error');
    } finally {
      setUploading(false);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileInputChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  };

  const resetForm = () => {
    setFormData({
      title: '',
      category: 'other',
      content: '',
      tags: '',
      priority: 5
    });
  };

  const openEditModal = (entry) => {
    setSelectedEntry(entry);
    setFormData({
      title: entry.title,
      category: entry.category,
      content: entry.content,
      tags: entry.tags ? entry.tags.join(', ') : '',
      priority: entry.priority || 5
    });
    setShowEditModal(true);
  };

  const getCategoryLabel = (value) => {
    const cat = CATEGORIES.find(c => c.value === value);
    return cat ? cat.label : value;
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'N/A';
    return new Date(dateStr).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'short',
      day: 'numeric'
    });
  };

  return (
    <div className="knowledge-base-page">
      {/* Notification */}
      {notification && (
        <div className={`kb-notification ${notification.type}`}>
          {notification.message}
        </div>
      )}

      {/* Header */}
      <div className="page-header">
        <div className="header-content">
          <h1>AI Knowledge Base</h1>
          <p>Upload documents and add content to teach the AI about your business</p>
        </div>
        <button
          className="btn-primary"
          onClick={() => setShowAddModal(true)}
        >
          + Add Knowledge
        </button>
      </div>

      {/* Upload Zone */}
      <section className="upload-section">
        <div
          className={`upload-zone ${dragActive ? 'drag-active' : ''} ${uploading ? 'uploading' : ''}`}
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.docx,.txt,.md"
            onChange={handleFileInputChange}
            style={{ display: 'none' }}
          />
          <div className="upload-icon">
            {uploading ? (
              <div className="spinner"></div>
            ) : (
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            )}
          </div>
          <h3>{uploading ? 'Processing document...' : 'Drag & drop files here'}</h3>
          <p>or click to browse. Supports PDF, DOCX, TXT, and MD files.</p>
        </div>
      </section>

      {/* Filters */}
      <section className="filters-section">
        <div className="search-box">
          <input
            type="text"
            placeholder="Search knowledge base..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </div>
        <div className="category-filters">
          <button
            className={`filter-btn ${selectedCategory === 'all' ? 'active' : ''}`}
            onClick={() => setSelectedCategory('all')}
          >
            All ({entries.length})
          </button>
          {categories.map(cat => (
            <button
              key={cat.category}
              className={`filter-btn ${selectedCategory === cat.category ? 'active' : ''}`}
              onClick={() => setSelectedCategory(cat.category)}
            >
              {getCategoryLabel(cat.category)} ({cat.count})
            </button>
          ))}
        </div>
      </section>

      {/* Entries List */}
      <section className="entries-section">
        {loading ? (
          <div className="loading-state">Loading knowledge base...</div>
        ) : entries.length === 0 ? (
          <div className="empty-state">
            <div className="empty-icon">
              <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
                <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
              </svg>
            </div>
            <h3>No knowledge entries yet</h3>
            <p>Upload documents or add knowledge manually to get started</p>
          </div>
        ) : (
          <div className="entries-grid">
            {entries.map(entry => (
              <div key={entry.id} className="entry-card">
                <div className="entry-header">
                  <span className={`category-badge ${entry.category}`}>
                    {getCategoryLabel(entry.category)}
                  </span>
                  <span className="source-badge">
                    {entry.source_type === 'document_upload' ? 'Document' : 'Manual'}
                  </span>
                </div>
                <h3 className="entry-title">{entry.title}</h3>
                {entry.summary && (
                  <p className="entry-summary">{entry.summary}</p>
                )}
                <div className="entry-meta">
                  <span>Priority: {entry.priority}/10</span>
                  <span>Added: {formatDate(entry.created_at)}</span>
                </div>
                {entry.tags && entry.tags.length > 0 && (
                  <div className="entry-tags">
                    {entry.tags.map((tag, idx) => (
                      <span key={idx} className="tag">{tag}</span>
                    ))}
                  </div>
                )}
                <div className="entry-actions">
                  <button
                    className="btn-secondary"
                    onClick={() => openEditModal(entry)}
                  >
                    Edit
                  </button>
                  <button
                    className="btn-danger"
                    onClick={() => handleDeleteEntry(entry.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {/* Add Modal */}
      {showAddModal && (
        <div className="modal-overlay" onClick={() => setShowAddModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Add Knowledge Entry</h2>
              <button className="close-btn" onClick={() => setShowAddModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleCreateEntry}>
              <div className="form-group">
                <label>Title *</label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({...formData, title: e.target.value})}
                  placeholder="e.g., FHA Loan Guidelines 2024"
                  required
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Category *</label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({...formData, category: e.target.value})}
                    required
                  >
                    {CATEGORIES.map(cat => (
                      <option key={cat.value} value={cat.value}>{cat.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Priority (1-10)</label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={formData.priority}
                    onChange={(e) => setFormData({...formData, priority: e.target.value})}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Content *</label>
                <textarea
                  value={formData.content}
                  onChange={(e) => setFormData({...formData, content: e.target.value})}
                  placeholder="Enter the knowledge content here. This will be used by the AI to answer questions..."
                  rows={10}
                  required
                />
              </div>
              <div className="form-group">
                <label>Tags (comma-separated)</label>
                <input
                  type="text"
                  value={formData.tags}
                  onChange={(e) => setFormData({...formData, tags: e.target.value})}
                  placeholder="e.g., fha, guidelines, 2024"
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowAddModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create Entry
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit Modal */}
      {showEditModal && (
        <div className="modal-overlay" onClick={() => setShowEditModal(false)}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Edit Knowledge Entry</h2>
              <button className="close-btn" onClick={() => setShowEditModal(false)}>&times;</button>
            </div>
            <form onSubmit={handleUpdateEntry}>
              <div className="form-group">
                <label>Title *</label>
                <input
                  type="text"
                  value={formData.title}
                  onChange={(e) => setFormData({...formData, title: e.target.value})}
                  required
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Category *</label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({...formData, category: e.target.value})}
                    required
                  >
                    {CATEGORIES.map(cat => (
                      <option key={cat.value} value={cat.value}>{cat.label}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Priority (1-10)</label>
                  <input
                    type="number"
                    min="1"
                    max="10"
                    value={formData.priority}
                    onChange={(e) => setFormData({...formData, priority: e.target.value})}
                  />
                </div>
              </div>
              <div className="form-group">
                <label>Content *</label>
                <textarea
                  value={formData.content}
                  onChange={(e) => setFormData({...formData, content: e.target.value})}
                  rows={10}
                  required
                />
              </div>
              <div className="form-group">
                <label>Tags (comma-separated)</label>
                <input
                  type="text"
                  value={formData.tags}
                  onChange={(e) => setFormData({...formData, tags: e.target.value})}
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setShowEditModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Update Entry
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default KnowledgeBase;

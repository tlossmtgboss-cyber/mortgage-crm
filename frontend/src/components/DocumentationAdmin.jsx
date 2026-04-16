/**
 * Documentation Admin Panel
 * 
 * Administrative interface for managing Enterprise Documentation Portal content.
 * Allows admins to create, edit, publish, and organize documentation content.
 */
import React, { useState, useEffect, useCallback } from 'react';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './DocumentationAdmin.css';
import { getToken } from '../utils/tokenStore';

function DocumentationAdmin() {
  const { isAdmin } = usePermissions();
  
  // State management
  const [activeTab, setActiveTab] = useState('content-list');
  const [contentList, setContentList] = useState([]);
  const [stats, setStats] = useState({});
  const [loading, setLoading] = useState(true);
  const [selectedContent, setSelectedContent] = useState(null);
  const [isEditing, setIsEditing] = useState(false);

  // Form state for content creation/editing
  const [contentForm, setContentForm] = useState({
    title: '',
    description: '',
    content: '',
    category: 'api-reference',
    content_type: 'reference',
    tags: [],
    is_featured: false,
    is_published: false,
    estimated_read_time: '',
    external_url: ''
  });

  // Check admin access
  if (!isAdmin) {
    return (
      <div className="doc-admin-unauthorized">
        <div className="unauthorized-message">
          <h2>Access Denied</h2>
          <p>You need administrator privileges to access the Documentation Admin Panel.</p>
        </div>
      </div>
    );
  }

  // Load content list
  const loadContentList = useCallback(async () => {
    try {
      const token = getToken();
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
      
      const response = await fetch(`${API_BASE_URL}/api/v1/enterprise-docs/admin/content`, { headers });
      
      if (response.ok) {
        const data = await response.json();
        setContentList(data.content || []);
      } else {
        console.error('Failed to load content list');
      }
    } catch (error) {
      console.error('Error loading content list:', error);
    }
  }, []);

  // Load statistics
  const loadStats = useCallback(async () => {
    try {
      const token = getToken();
      const headers = token ? { 'Authorization': `Bearer ${token}` } : {};
      
      const response = await fetch(`${API_BASE_URL}/api/v1/enterprise-docs/admin/stats`, { headers });
      
      if (response.ok) {
        const data = await response.json();
        setStats(data);
      } else {
        console.error('Failed to load stats');
      }
    } catch (error) {
      console.error('Error loading stats:', error);
    }
  }, []);

  // Load data on mount
  useEffect(() => {
    Promise.all([loadContentList(), loadStats()]).finally(() => setLoading(false));
  }, [loadContentList, loadStats]);

  // Handle content creation/update
  const handleSaveContent = async () => {
    try {
      const token = getToken();
      const headers = {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json'
      };
      
      const url = isEditing 
        ? `${API_BASE_URL}/api/v1/enterprise-docs/admin/content/${selectedContent.id}`
        : `${API_BASE_URL}/api/v1/enterprise-docs/admin/content`;
      
      const method = isEditing ? 'PUT' : 'POST';
      
      const response = await fetch(url, {
        method,
        headers,
        body: JSON.stringify(contentForm)
      });
      
      if (response.ok) {
        toast.success(`Content ${isEditing ? 'updated' : 'created'} successfully`);
        await loadContentList();
        setActiveTab('content-list');
        setSelectedContent(null);
        setIsEditing(false);
        setContentForm({
          title: '',
          description: '',
          content: '',
          category: 'api-reference',
          content_type: 'reference',
          tags: [],
          is_featured: false,
          is_published: false,
          estimated_read_time: '',
          external_url: ''
        });
      } else {
        toast.error('Failed to save content');
      }
    } catch (error) {
      console.error('Error saving content:', error);
      toast.error('Error saving content');
    }
  };

  // Handle content publish/unpublish
  const handleTogglePublish = async (contentId, currentStatus) => {
    try {
      const token = getToken();
      const headers = { 'Authorization': `Bearer ${token}` };
      
      const action = currentStatus ? 'unpublish' : 'publish';
      const response = await fetch(
        `${API_BASE_URL}/api/v1/enterprise-docs/admin/content/${contentId}/${action}`,
        { method: 'POST', headers }
      );
      
      if (response.ok) {
        toast.success(`Content ${action}ed successfully`);
        await loadContentList();
      } else {
        toast.error(`Failed to ${action} content`);
      }
    } catch (error) {
      console.error(`Error ${currentStatus ? 'unpublishing' : 'publishing'} content:`, error);
      toast.error('Error updating content status');
    }
  };

  // Start editing content
  const handleEditContent = (content) => {
    setSelectedContent(content);
    setContentForm({
      title: content.title,
      description: content.description,
      content: content.content || '',
      category: content.category,
      content_type: content.content_type,
      tags: content.tags || [],
      is_featured: content.is_featured || false,
      is_published: content.is_published || false,
      estimated_read_time: content.estimated_read_time || '',
      external_url: content.external_url || ''
    });
    setIsEditing(true);
    setActiveTab('content-form');
  };

  // Start creating new content
  const handleCreateNew = () => {
    setSelectedContent(null);
    setIsEditing(false);
    setContentForm({
      title: '',
      description: '',
      content: '',
      category: 'api-reference',
      content_type: 'reference',
      tags: [],
      is_featured: false,
      is_published: false,
      estimated_read_time: '',
      external_url: ''
    });
    setActiveTab('content-form');
  };

  if (loading) {
    return (
      <div className="doc-admin-loading">
        <div className="loading-spinner"></div>
        <p>Loading documentation admin panel...</p>
      </div>
    );
  }

  return (
    <div className="documentation-admin">
      <div className="doc-admin-header">
        <h1>Documentation Admin Panel</h1>
        <p>Manage Enterprise Documentation Portal content and settings</p>
      </div>

      {/* Navigation tabs */}
      <div className="doc-admin-tabs">
        <button 
          onClick={() => setActiveTab('dashboard')}
          className={`tab ${activeTab === 'dashboard' ? 'active' : ''}`}
        >
          📊 Dashboard
        </button>
        <button 
          onClick={() => setActiveTab('content-list')}
          className={`tab ${activeTab === 'content-list' ? 'active' : ''}`}
        >
          📝 Content List
        </button>
        <button 
          onClick={handleCreateNew}
          className={`tab ${activeTab === 'content-form' ? 'active' : ''}`}
        >
          ➕ {isEditing ? 'Edit' : 'Create'} Content
        </button>
      </div>

      <div className="doc-admin-content">
        {/* Dashboard tab */}
        {activeTab === 'dashboard' && (
          <div className="admin-dashboard">
            <div className="stats-grid">
              <div className="stat-card">
                <h3>Total Content</h3>
                <div className="stat-number">{stats.total_content || 0}</div>
              </div>
              <div className="stat-card">
                <h3>Published</h3>
                <div className="stat-number">{stats.published_content || 0}</div>
              </div>
              <div className="stat-card">
                <h3>Drafts</h3>
                <div className="stat-number">{stats.draft_content || 0}</div>
              </div>
              <div className="stat-card">
                <h3>Total Views</h3>
                <div className="stat-number">{stats.total_views || 0}</div>
              </div>
            </div>

            {/* Top categories */}
            {stats.top_categories && (
              <div className="top-categories">
                <h3>Top Categories</h3>
                {stats.top_categories.map(cat => (
                  <div key={cat.category} className="category-stat">
                    <span className="category-name">{cat.category}</span>
                    <span className="category-count">{cat.count} items</span>
                    <span className="category-views">{cat.views} views</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Content list tab */}
        {activeTab === 'content-list' && (
          <div className="content-list-tab">
            <div className="content-list-header">
              <h2>All Content</h2>
              <button onClick={handleCreateNew} className="create-btn">
                Create New Content
              </button>
            </div>
            
            <div className="content-table">
              {contentList.map(content => (
                <div key={content.id} className="content-row">
                  <div className="content-info">
                    <h4>{content.title}</h4>
                    <p>{content.description}</p>
                    <div className="content-meta">
                      <span className="category">{content.category}</span>
                      <span className="type">{content.content_type}</span>
                      <span className="views">👁 {content.views || 0}</span>
                    </div>
                  </div>
                  <div className="content-status">
                    <span className={`status-badge ${content.is_published ? 'published' : 'draft'}`}>
                      {content.is_published ? '✅ Published' : '📝 Draft'}
                    </span>
                    {content.is_featured && <span className="featured-badge">⭐ Featured</span>}
                  </div>
                  <div className="content-actions">
                    <button 
                      onClick={() => handleEditContent(content)}
                      className="edit-btn"
                    >
                      Edit
                    </button>
                    <button 
                      onClick={() => handleTogglePublish(content.id, content.is_published)}
                      className={`publish-btn ${content.is_published ? 'unpublish' : 'publish'}`}
                    >
                      {content.is_published ? 'Unpublish' : 'Publish'}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Content form tab */}
        {activeTab === 'content-form' && (
          <div className="content-form-tab">
            <h2>{isEditing ? 'Edit Content' : 'Create New Content'}</h2>
            
            <div className="content-form">
              <div className="form-row">
                <label>Title</label>
                <input 
                  type="text"
                  value={contentForm.title}
                  onChange={(e) => setContentForm({...contentForm, title: e.target.value})}
                  placeholder="Enter content title"
                />
              </div>

              <div className="form-row">
                <label>Description</label>
                <textarea 
                  value={contentForm.description}
                  onChange={(e) => setContentForm({...contentForm, description: e.target.value})}
                  placeholder="Enter content description"
                  rows={3}
                />
              </div>

              <div className="form-row">
                <label>Category</label>
                <select 
                  value={contentForm.category}
                  onChange={(e) => setContentForm({...contentForm, category: e.target.value})}
                >
                  <option value="api-reference">API Reference</option>
                  <option value="ai-orchestration">AI Orchestration</option>
                  <option value="business-processes">Business Processes</option>
                  <option value="system-architecture">System Architecture</option>
                  <option value="integrations">Integrations</option>
                  <option value="compliance">Compliance</option>
                  <option value="analytics">Analytics & Reporting</option>
                  <option value="deployment">Deployment & Operations</option>
                </select>
              </div>

              <div className="form-row">
                <label>Content Type</label>
                <select 
                  value={contentForm.content_type}
                  onChange={(e) => setContentForm({...contentForm, content_type: e.target.value})}
                >
                  <option value="overview">Overview</option>
                  <option value="tutorial">Tutorial</option>
                  <option value="reference">Reference</option>
                  <option value="guide">Guide</option>
                  <option value="troubleshooting">Troubleshooting</option>
                  <option value="changelog">Changelog</option>
                </select>
              </div>

              <div className="form-row">
                <label>Content (Markdown)</label>
                <textarea 
                  value={contentForm.content}
                  onChange={(e) => setContentForm({...contentForm, content: e.target.value})}
                  placeholder="Enter content in Markdown format"
                  rows={10}
                  className="content-textarea"
                />
              </div>

              <div className="form-row checkboxes">
                <label>
                  <input 
                    type="checkbox"
                    checked={contentForm.is_featured}
                    onChange={(e) => setContentForm({...contentForm, is_featured: e.target.checked})}
                  />
                  Featured Content
                </label>
                <label>
                  <input 
                    type="checkbox"
                    checked={contentForm.is_published}
                    onChange={(e) => setContentForm({...contentForm, is_published: e.target.checked})}
                  />
                  Published
                </label>
              </div>

              <div className="form-actions">
                <button 
                  onClick={() => setActiveTab('content-list')}
                  className="cancel-btn"
                >
                  Cancel
                </button>
                <button 
                  onClick={handleSaveContent}
                  className="save-btn"
                >
                  {isEditing ? 'Update' : 'Create'} Content
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default DocumentationAdmin;
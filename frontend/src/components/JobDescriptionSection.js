import React, { useState, useEffect, useCallback } from 'react';
import ReactQuill from 'react-quill';
import 'react-quill/dist/quill.snow.css';
import { API_BASE_URL } from '../services/api';
import './JobDescriptionSection.css';

/**
 * Section A: Job Description
 *
 * Rich text editor for comprehensive job description
 * Features:
 * - Rich text formatting
 * - Auto-save every 30 seconds
 * - Manual save button
 * - Last updated timestamp tracking
 * - 5,000 character limit
 */

function JobDescriptionSection({ userId }) {
  const [description, setDescription] = useState('');
  const [savedDescription, setSavedDescription] = useState('');
  const [lastUpdated, setLastUpdated] = useState(null);
  const [updatedBy, setUpdatedBy] = useState(null);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState(''); // 'saving', 'saved', 'error'
  const [characterCount, setCharacterCount] = useState(0);

  const CHARACTER_LIMIT = 5000;

  // Quill modules configuration
  const modules = {
    toolbar: [
      [{ 'header': [1, 2, 3, false] }],
      ['bold', 'italic', 'underline'],
      [{ 'list': 'ordered'}, { 'list': 'bullet' }],
      ['clean']
    ],
  };

  const formats = [
    'header',
    'bold', 'italic', 'underline',
    'list', 'bullet'
  ];

  // Load job description on mount
  useEffect(() => {
    loadJobDescription();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const loadJobDescription = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/api/v1/users/${userId}/job-description`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      });

      if (!response.ok) {
        if (response.status === 404) {
          // No job description yet, start with empty
          setDescription('');
          setSavedDescription('');
          setLoading(false);
          return;
        }
        throw new Error('Failed to load job description');
      }

      const data = await response.json();
      setDescription(data.description || '');
      setSavedDescription(data.description || '');
      setLastUpdated(data.last_updated);
      setUpdatedBy(data.updated_by);
      updateCharacterCount(data.description || '');
    } catch (error) {
      console.error('Failed to load job description:', error);
      setSaveStatus('error');
    } finally {
      setLoading(false);
    }
  };

  const updateCharacterCount = (text) => {
    // Strip HTML tags for character count
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = text;
    const plainText = tempDiv.textContent || tempDiv.innerText || '';
    setCharacterCount(plainText.length);
  };

  const handleDescriptionChange = (value) => {
    // Check character limit
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = value;
    const plainText = tempDiv.textContent || tempDiv.innerText || '';

    if (plainText.length <= CHARACTER_LIMIT) {
      setDescription(value);
      updateCharacterCount(value);
      setSaveStatus(''); // Clear saved status when editing
    }
  };

  const saveJobDescription = useCallback(async () => {
    try {
      setSaving(true);
      setSaveStatus('saving');

      const response = await fetch(`${API_BASE_URL}/api/v1/users/${userId}/job-description`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ description })
      });

      if (!response.ok) {
        throw new Error('Failed to save job description');
      }

      const data = await response.json();
      setSavedDescription(description);
      setLastUpdated(data.updated_at);
      setSaveStatus('saved');

      // Clear "saved" status after 3 seconds
      setTimeout(() => setSaveStatus(''), 3000);
    } catch (error) {
      console.error('Failed to save job description:', error);
      setSaveStatus('error');
    } finally {
      setSaving(false);
    }
  }, [userId, description]);

  // Auto-save every 30 seconds if there are unsaved changes
  useEffect(() => {
    if (description !== savedDescription && description !== '') {
      const autoSaveTimer = setTimeout(() => {
        saveJobDescription();
      }, 30000); // 30 seconds

      return () => clearTimeout(autoSaveTimer);
    }
  }, [description, savedDescription, saveJobDescription]);

  const hasUnsavedChanges = description !== savedDescription;

  if (loading) {
    return (
      <div className="job-description-section">
        <div className="loading">Loading job description...</div>
      </div>
    );
  }

  return (
    <div className="job-description-section">
      <div className="section-header-with-actions">
        <div>
          <h3>Job Description</h3>
          <p className="section-subtitle">
            Comprehensive description of this role's purpose, responsibilities, and requirements
          </p>
        </div>
        <div className="section-actions">
          {saveStatus === 'saving' && <span className="save-status saving">Saving...</span>}
          {saveStatus === 'saved' && <span className="save-status saved">✓ Saved</span>}
          {saveStatus === 'error' && <span className="save-status error">Failed to save</span>}
          <button
            className="btn-save-description"
            onClick={saveJobDescription}
            disabled={saving || !hasUnsavedChanges}
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
        </div>
      </div>

      <div className="rich-text-editor-wrapper">
        <ReactQuill
          theme="snow"
          value={description}
          onChange={handleDescriptionChange}
          modules={modules}
          formats={formats}
          placeholder="Enter a comprehensive job description..."
        />
      </div>

      <div className="editor-footer">
        <div className="character-count">
          {characterCount} / {CHARACTER_LIMIT} characters
          {characterCount >= CHARACTER_LIMIT && (
            <span className="limit-warning"> (Limit reached)</span>
          )}
        </div>
        {lastUpdated && (
          <div className="last-updated">
            Last updated: {new Date(lastUpdated).toLocaleString()}
            {updatedBy && ` by ${updatedBy.name}`}
          </div>
        )}
      </div>

      {hasUnsavedChanges && (
        <div className="unsaved-changes-notice">
          You have unsaved changes. They will be auto-saved in 30 seconds, or click Save now.
        </div>
      )}
    </div>
  );
}

export default JobDescriptionSection;

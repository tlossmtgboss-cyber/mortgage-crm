import React, { useState, useEffect } from 'react';
import { permissionsAPI } from '../services/api';
import PermissionDiffModal from './PermissionDiffModal';
import './PermissionsTab.css';
import { toast } from '../utils/toast';

function PermissionsTab({ userId }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [currentTemplate, setCurrentTemplate] = useState(null);
  const [permissions, setPermissions] = useState({});
  const [availablePermissions, setAvailablePermissions] = useState({});
  const [selectedTemplate, setSelectedTemplate] = useState('');
  const [showDiffModal, setShowDiffModal] = useState(false);
  const [permissionDiff, setPermissionDiff] = useState(null);
  const [hasChanges, setHasChanges] = useState(false);
  const [originalPermissions, setOriginalPermissions] = useState({});

  useEffect(() => {
    fetchData();
  }, [userId]);

  useEffect(() => {
    // Check if there are unsaved changes
    const changed = JSON.stringify(permissions) !== JSON.stringify(originalPermissions);
    setHasChanges(changed);
  }, [permissions, originalPermissions]);

  const fetchData = async () => {
    setLoading(true);
    try {
      // Fetch current template
      const templateResponse = await permissionsAPI.getUserTemplate(userId);
      setCurrentTemplate(templateResponse.template);
      setSelectedTemplate(templateResponse.template || '');

      // Fetch current permissions
      const permsResponse = await permissionsAPI.getUserPermissions(userId);
      setPermissions(permsResponse.permissions || {});
      setOriginalPermissions(permsResponse.permissions || {});

      // Fetch available permissions
      const availableResponse = await permissionsAPI.getAvailablePermissions();
      setAvailablePermissions(availableResponse.permissions || {});
    } catch (error) {
      console.error('Failed to fetch permissions data:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleTemplateChange = (e) => {
    setSelectedTemplate(e.target.value);
  };

  const handleApplyTemplate = async () => {
    if (!selectedTemplate) return;

    try {
      setSaving(true);
      const response = await permissionsAPI.applyTemplate(userId, selectedTemplate);

      // Show diff modal
      setPermissionDiff(response.diff);
      setShowDiffModal(true);

      // Refresh data after applying
      await fetchData();
    } catch (error) {
      console.error('Failed to apply template:', error);
      toast.error('Failed to apply template. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handlePermissionToggle = (permissionKey) => {
    setPermissions(prev => ({
      ...prev,
      [permissionKey]: !prev[permissionKey]
    }));
  };

  const handleSaveChanges = async () => {
    try {
      setSaving(true);
      await permissionsAPI.updatePermissions(userId, permissions);

      // Refresh to get updated data
      await fetchData();
      toast.success('Permissions saved successfully!');
    } catch (error) {
      console.error('Failed to save permissions:', error);
      toast.error('Failed to save permissions. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const handleResetChanges = () => {
    setPermissions({ ...originalPermissions });
  };

  const renderPermissionCategory = (categoryName, categoryPerms) => {
    const categoryPermissions = Object.entries(categoryPerms);
    if (categoryPermissions.length === 0) return null;

    return (
      <div className="permission-category" key={categoryName}>
        <h4 className="category-title">{formatCategoryName(categoryName)}</h4>
        <div className="permission-checkboxes">
          {categoryPermissions.map(([key, description]) => (
            <label key={key} className="permission-checkbox-label">
              <input
                type="checkbox"
                checked={permissions[key] || false}
                onChange={() => handlePermissionToggle(key)}
                disabled={saving}
              />
              <div className="permission-info">
                <span className="permission-name">{formatPermissionName(key)}</span>
                <span className="permission-description">{description}</span>
              </div>
            </label>
          ))}
        </div>
      </div>
    );
  };

  const formatCategoryName = (category) => {
    return category
      .split('_')
      .map(word => word.charAt(0).toUpperCase() + word.slice(1))
      .join(' ');
  };

  const formatPermissionName = (key) => {
    const parts = key.split('.');
    if (parts.length === 2) {
      return parts[1]
        .split('_')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');
    }
    return key;
  };

  const formatTemplateName = (template) => {
    if (!template) return 'None';
    return template.charAt(0).toUpperCase() + template.slice(1);
  };

  if (loading) {
    return <div className="permissions-tab-loading">Loading permissions...</div>;
  }

  return (
    <div className="permissions-tab">
      <div className="permissions-header">
        <div className="template-section">
          <h3>Permission Template</h3>
          <div className="template-selector-row">
            <div className="current-template">
              <span className="label">Current Template:</span>
              <span className={`template-badge template-${currentTemplate || 'none'}`}>
                {formatTemplateName(currentTemplate)}
              </span>
            </div>
            <div className="template-selector">
              <select
                value={selectedTemplate}
                onChange={handleTemplateChange}
                disabled={saving}
              >
                <option value="">Select a template...</option>
                <option value="management">Management</option>
                <option value="sales">Sales</option>
                <option value="operations">Operations</option>
              </select>
              <button
                className="apply-template-btn"
                onClick={handleApplyTemplate}
                disabled={!selectedTemplate || selectedTemplate === currentTemplate || saving}
              >
                {saving ? 'Applying...' : 'Apply Template'}
              </button>
            </div>
          </div>
          <p className="template-note">
            Applying a template will replace all current permissions with the selected role's default permissions.
          </p>
        </div>
      </div>

      <div className="permissions-body">
        <div className="permissions-actions">
          <h3>Individual Permissions</h3>
          {hasChanges && (
            <div className="changes-actions">
              <button
                className="reset-btn"
                onClick={handleResetChanges}
                disabled={saving}
              >
                Reset Changes
              </button>
              <button
                className="save-btn"
                onClick={handleSaveChanges}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </div>
          )}
        </div>

        <div className="permissions-grid">
          {Object.entries(availablePermissions).map(([categoryName, categoryPerms]) =>
            renderPermissionCategory(categoryName, categoryPerms)
          )}
        </div>
      </div>

      {showDiffModal && permissionDiff && (
        <PermissionDiffModal
          diff={permissionDiff}
          templateName={selectedTemplate}
          onClose={() => setShowDiffModal(false)}
        />
      )}
    </div>
  );
}

export default PermissionsTab;

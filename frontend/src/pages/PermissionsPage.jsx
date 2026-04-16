/**
 * PermissionsPage.jsx
 * Role-Based Access Control (RBAC) Permissions Matrix
 * Perennia AI - TL Development LLC
 *
 * Allows administrators to configure which pages/features each role can access.
 * Changes take effect immediately for users with the selected role.
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { API_BASE_URL } from '../services/api';
import { usePermissions } from '../contexts/PermissionContext';
import { toast } from '../utils/toast';
import './PermissionsPage.css';
import { getToken } from '../utils/tokenStore';

// ============================================================================
// CONFIGURATION - Lucide icon names for roles
// ============================================================================

const ROLE_ICONS = {
  loan_officer: 'Users',
  branch_manager: 'Building2',
  area_manager: 'MapPin',
  regional_manager: 'Globe',
  production_assistant: 'Headphones',
  processor: 'FileCheck',
  evp: 'Crown',
  administrator: 'Settings',
};

const ROLE_COLORS = {
  loan_officer: '#3b82f6',
  branch_manager: '#10b981',
  area_manager: '#8b5cf6',
  regional_manager: '#f97316',
  production_assistant: '#ec4899',
  processor: '#06b6d4',
  evp: '#f59e0b',
  administrator: '#ef4444',
};

// ============================================================================
// COMPONENT
// ============================================================================

const PermissionsPage = () => {
  const navigate = useNavigate();
  const { userRole, hasAnyPermission, isAdmin, isPlatformAdmin, isSiteAdmin } = usePermissions();

  // Permission check - only admins can configure RBAC permissions
  const canAccessPermissions = isAdmin || isPlatformAdmin || isSiteAdmin ||
    hasAnyPermission(['admin.manage', 'permissions.manage', 'system.admin']) ||
    userRole === 'admin' || userRole === 'site_admin';

  // State
  const [activeRole, setActiveRole] = useState('loan_officer');
  const [roles, setRoles] = useState([]);
  const [pages, setPages] = useState([]);
  const [categories, setCategories] = useState([]);
  const [permissions, setPermissions] = useState({});
  const [originalPermissions, setOriginalPermissions] = useState({});
  const [searchQuery, setSearchQuery] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [expandedCategories, setExpandedCategories] = useState(new Set());
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [showCopyModal, setShowCopyModal] = useState(false);
  const [copyFromRole, setCopyFromRole] = useState('');

  // Load data on mount
  useEffect(() => {
    loadAllData();
  }, []);

  // Track changes
  useEffect(() => {
    const current = JSON.stringify(permissions[activeRole] || []);
    const original = JSON.stringify(originalPermissions[activeRole] || []);
    setHasChanges(current !== original);
  }, [permissions, originalPermissions, activeRole]);

  // Initialize expanded categories
  useEffect(() => {
    if (categories.length > 0 && expandedCategories.size === 0) {
      setExpandedCategories(new Set(categories));
    }
  }, [categories]);

  // Load all data from API
  const loadAllData = async () => {
    setLoading(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/page-permissions/roles`, {
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to load permissions data');
      }

      const data = await response.json();

      setRoles(data.roles || []);
      setPages(data.pages || []);
      setCategories(data.categories || []);

      // Build permissions map
      const permsMap = {};
      (data.roles || []).forEach(role => {
        permsMap[role.key] = role.permissions || [];
      });
      setPermissions(permsMap);
      setOriginalPermissions(JSON.parse(JSON.stringify(permsMap)));

    } catch (error) {
      console.error('Failed to load permissions:', error);
      toast.error('Failed to load permissions data');
    } finally {
      setLoading(false);
    }
  };

  // Save permissions
  const savePermissions = async () => {
    setSaving(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/page-permissions/role/${activeRole}`, {
        method: 'PUT',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          permissions: permissions[activeRole] || []
        })
      });

      if (!response.ok) {
        throw new Error('Failed to save permissions');
      }

      setOriginalPermissions(JSON.parse(JSON.stringify(permissions)));
      const roleName = roles.find(r => r.key === activeRole)?.name || activeRole;
      toast.success(`Permissions saved for ${roleName}`);
    } catch (error) {
      console.error('Failed to save permissions:', error);
      toast.error('Failed to save permissions');
    } finally {
      setSaving(false);
    }
  };

  // Reset to original
  const resetPermissions = () => {
    setPermissions(JSON.parse(JSON.stringify(originalPermissions)));
    toast.info('Changes reverted');
  };

  // Reset to defaults
  const resetToDefaults = async () => {
    setSaving(true);
    try {
      const token = getToken();
      const response = await fetch(`${API_BASE_URL}/api/v1/page-permissions/role/${activeRole}/reset`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        }
      });

      if (!response.ok) {
        throw new Error('Failed to reset permissions');
      }

      const data = await response.json();
      const newPermissions = {
        ...permissions,
        [activeRole]: data.permissions || []
      };
      setPermissions(newPermissions);
      setOriginalPermissions(JSON.parse(JSON.stringify(newPermissions)));
      toast.success('Reset to default permissions');
    } catch (error) {
      console.error('Failed to reset permissions:', error);
      toast.error('Failed to reset permissions');
    } finally {
      setSaving(false);
    }
  };

  // Toggle single permission
  const togglePermission = (pageKey) => {
    const rolePerms = permissions[activeRole] || [];
    const newPerms = rolePerms.includes(pageKey)
      ? rolePerms.filter(k => k !== pageKey)
      : [...rolePerms, pageKey];

    setPermissions({
      ...permissions,
      [activeRole]: newPerms
    });
  };

  // Toggle all in category
  const toggleCategory = (category, enable) => {
    const categoryPages = pages.filter(p => p.category === category).map(p => p.key);
    const rolePerms = permissions[activeRole] || [];

    let newPerms;
    if (enable) {
      newPerms = [...new Set([...rolePerms, ...categoryPages])];
    } else {
      newPerms = rolePerms.filter(k => !categoryPages.includes(k));
    }

    setPermissions({
      ...permissions,
      [activeRole]: newPerms
    });
  };

  // Select/Deselect all
  const toggleAll = (enable) => {
    const newPerms = enable ? pages.map(p => p.key) : [];
    setPermissions({
      ...permissions,
      [activeRole]: newPerms
    });
  };

  // Copy permissions from another role
  const copyFromOtherRole = async () => {
    if (!copyFromRole) return;

    setSaving(true);
    try {
      const token = getToken();
      const response = await fetch(
        `${API_BASE_URL}/api/v1/page-permissions/role/${activeRole}/copy-from/${copyFromRole}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json'
          }
        }
      );

      if (!response.ok) {
        throw new Error('Failed to copy permissions');
      }

      const data = await response.json();
      const newPermissions = {
        ...permissions,
        [activeRole]: data.permissions || []
      };
      setPermissions(newPermissions);
      setOriginalPermissions(JSON.parse(JSON.stringify(newPermissions)));

      setShowCopyModal(false);
      setCopyFromRole('');
      const sourceName = roles.find(r => r.key === copyFromRole)?.name || copyFromRole;
      toast.success(`Copied permissions from ${sourceName}`);
    } catch (error) {
      console.error('Failed to copy permissions:', error);
      toast.error('Failed to copy permissions');
    } finally {
      setSaving(false);
    }
  };

  // Toggle category expansion
  const toggleCategoryExpand = (category) => {
    const newExpanded = new Set(expandedCategories);
    if (newExpanded.has(category)) {
      newExpanded.delete(category);
    } else {
      newExpanded.add(category);
    }
    setExpandedCategories(newExpanded);
  };

  // Filter pages
  const getFilteredPages = useCallback(() => {
    return pages.filter(page => {
      const matchesSearch = searchQuery === '' ||
        page.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        page.path.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesCategory = categoryFilter === 'all' || page.category === categoryFilter;
      return matchesSearch && matchesCategory;
    });
  }, [pages, searchQuery, categoryFilter]);

  // Group pages by category
  const getGroupedPages = useMemo(() => {
    const filtered = getFilteredPages();
    const grouped = {};

    categories.forEach(cat => {
      const catPages = filtered.filter(p => p.category === cat);
      if (catPages.length > 0) {
        grouped[cat] = catPages;
      }
    });

    return grouped;
  }, [getFilteredPages, categories]);

  // Get category stats
  const getCategoryStats = (category) => {
    const categoryPages = pages.filter(p => p.category === category);
    const rolePerms = permissions[activeRole] || [];
    const enabled = categoryPages.filter(p => rolePerms.includes(p.key)).length;
    return { enabled, total: categoryPages.length };
  };

  // Get role stats
  const getRoleStats = (roleKey) => {
    const rolePerms = permissions[roleKey] || [];
    return {
      enabled: rolePerms.length,
      total: pages.length
    };
  };

  const rolePerms = permissions[activeRole] || [];
  const activeRoleData = roles.find(r => r.key === activeRole);

  // Access denied if user doesn't have admin permissions
  if (!canAccessPermissions) {
    return (
      <div className="permissions-page">
        <div style={{ textAlign: 'center', padding: '60px 20px' }}>
          <h2>Access Denied</h2>
          <p>You don't have permission to manage role permissions.</p>
          <button className="btn-primary" onClick={() => navigate('/dashboard')} style={{ marginTop: '16px' }}>
            Return to Dashboard
          </button>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="permissions-page">
        <div className="permissions-loading">
          <div className="loading-spinner"></div>
          <p>Loading permissions...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="permissions-page">
      {/* Header */}
      <div className="permissions-header">
        <div className="header-left">
          <div className="header-icon">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
            </svg>
          </div>
          <div className="header-text">
            <h1>Permissions Manager</h1>
            <p>Configure role-based page access</p>
          </div>
        </div>

        <div className="header-actions">
          {hasChanges && (
            <span className="unsaved-badge">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                <line x1="12" y1="9" x2="12" y2="13" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
              Unsaved changes
            </span>
          )}

          <button
            onClick={resetPermissions}
            disabled={!hasChanges || saving}
            className="btn-secondary"
          >
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
            Revert
          </button>

          <button
            onClick={savePermissions}
            disabled={!hasChanges || saving}
            className="btn-primary"
          >
            {saving ? (
              <div className="loading-spinner small"></div>
            ) : (
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z" />
                <polyline points="17 21 17 13 7 13 7 21" />
                <polyline points="7 3 7 8 15 8" />
              </svg>
            )}
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
        </div>
      </div>

      {/* Role Tabs */}
      <div className="role-tabs">
        {roles.map(role => {
          const stats = getRoleStats(role.key);
          const isActive = activeRole === role.key;

          return (
            <button
              key={role.key}
              onClick={() => setActiveRole(role.key)}
              className={`role-tab ${isActive ? 'active' : ''}`}
              style={{
                '--role-color': ROLE_COLORS[role.key] || '#6366f1',
              }}
            >
              <span className="role-name">{role.name}</span>
              <span className="role-count">{stats.enabled}/{stats.total}</span>
            </button>
          );
        })}
      </div>

      {/* Active Role Header Card */}
      <div
        className="role-header-card"
        style={{ '--role-color': ROLE_COLORS[activeRole] || '#6366f1' }}
      >
        <div className="role-header-content">
          <div className="role-header-left">
            <div className="role-icon">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
                <circle cx="9" cy="7" r="4" />
                <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
                <path d="M16 3.13a4 4 0 0 1 0 7.75" />
              </svg>
            </div>
            <div className="role-info">
              <h2>{activeRoleData?.name || activeRole}</h2>
              <p>{rolePerms.length} of {pages.length} pages enabled</p>
            </div>
          </div>

          <div className="role-header-actions">
            <button onClick={() => setShowCopyModal(true)} className="btn-ghost">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
              </svg>
              Copy From...
            </button>
            <button onClick={resetToDefaults} className="btn-ghost">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="10" />
                <polyline points="12 6 12 12 16 14" />
              </svg>
              Reset to Default
            </button>
          </div>
        </div>

        {/* Filters & Bulk Actions */}
        <div className="role-header-filters">
          <div className="filters-left">
            {/* Search */}
            <div className="search-input">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                placeholder="Search pages..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            {/* Category Filter */}
            <div className="category-select">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
              </svg>
              <select
                value={categoryFilter}
                onChange={(e) => setCategoryFilter(e.target.value)}
              >
                <option value="all">All Categories</option>
                {categories.map(cat => (
                  <option key={cat} value={cat}>{cat}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Bulk Actions */}
          <div className="filters-right">
            <button onClick={() => toggleAll(true)} className="btn-enable">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="9 11 12 14 22 4" />
                <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
              </svg>
              Select All
            </button>
            <button onClick={() => toggleAll(false)} className="btn-clear">
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              </svg>
              Clear All
            </button>
          </div>
        </div>
      </div>

      {/* Permissions Matrix */}
      <div className="permissions-matrix">
        {Object.entries(getGroupedPages).map(([category, categoryPages]) => {
          const stats = getCategoryStats(category);
          const isExpanded = expandedCategories.has(category);
          const allEnabled = stats.enabled === stats.total;

          return (
            <div key={category} className="category-section">
              {/* Category Header */}
              <div
                className="category-header"
                onClick={() => toggleCategoryExpand(category)}
              >
                <div className="category-header-left">
                  <button className="expand-btn">
                    <svg
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}
                    >
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                  <h3>{category}</h3>
                  <span className="category-count">{stats.enabled}/{stats.total} enabled</span>
                </div>

                <div className="category-actions" onClick={(e) => e.stopPropagation()}>
                  <button
                    onClick={() => toggleCategory(category, true)}
                    disabled={allEnabled}
                    className="btn-sm btn-enable"
                  >
                    Enable All
                  </button>
                  <button
                    onClick={() => toggleCategory(category, false)}
                    disabled={stats.enabled === 0}
                    className="btn-sm btn-clear"
                  >
                    Disable All
                  </button>
                </div>
              </div>

              {/* Pages List */}
              {isExpanded && (
                <div className="pages-list">
                  {categoryPages.map((page) => {
                    const isEnabled = rolePerms.includes(page.key);

                    return (
                      <div
                        key={page.key}
                        className={`page-item ${isEnabled ? 'enabled' : 'disabled'}`}
                      >
                        <div className="page-item-left">
                          <button
                            onClick={() => togglePermission(page.key)}
                            className={`checkbox ${isEnabled ? 'checked' : ''}`}
                          >
                            {isEnabled && (
                              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3">
                                <polyline points="20 6 9 17 4 12" />
                              </svg>
                            )}
                          </button>
                          <div className="page-info">
                            <span className="page-name">{page.name}</span>
                            <span className="page-path">{page.path}</span>
                          </div>
                        </div>

                        <div className="page-item-right">
                          {page.stage !== 'all' && (
                            <span className={`stage-badge ${page.stage}`}>
                              {page.stage === 'lead' ? 'Lead' :
                               page.stage === 'active_loan' ? 'Active Loan' : 'Portfolio'}
                            </span>
                          )}
                          <span className={`status-badge ${isEnabled ? 'visible' : 'hidden'}`}>
                            {isEnabled ? 'Visible' : 'Hidden'}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Copy From Modal */}
      {showCopyModal && (
        <div className="modal-overlay">
          <div className="modal-content">
            <div className="modal-header">
              <h3>Copy Permissions From</h3>
              <p>Select a role to copy its permissions to {activeRoleData?.name}</p>
            </div>

            <div className="modal-body">
              {roles.filter(r => r.key !== activeRole).map(role => {
                const isSelected = copyFromRole === role.key;
                const stats = getRoleStats(role.key);

                return (
                  <button
                    key={role.key}
                    onClick={() => setCopyFromRole(role.key)}
                    className={`role-option ${isSelected ? 'selected' : ''}`}
                    style={{ '--role-color': ROLE_COLORS[role.key] || '#6366f1' }}
                  >
                    <span className="role-option-name">{role.name}</span>
                    <span className="role-option-count">{stats.enabled} pages</span>
                  </button>
                );
              })}
            </div>

            <div className="modal-footer">
              <button
                onClick={() => {
                  setShowCopyModal(false);
                  setCopyFromRole('');
                }}
                className="btn-secondary"
              >
                Cancel
              </button>
              <button
                onClick={copyFromOtherRole}
                disabled={!copyFromRole || saving}
                className="btn-primary"
              >
                {saving ? 'Copying...' : 'Copy Permissions'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Unsaved Changes Warning */}
      {hasChanges && (
        <div className="unsaved-banner">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
            <line x1="12" y1="9" x2="12" y2="13" />
            <line x1="12" y1="17" x2="12.01" y2="17" />
          </svg>
          <span>You have unsaved changes</span>
          <button onClick={resetPermissions} className="btn-ghost">Discard</button>
          <button onClick={savePermissions} disabled={saving} className="btn-primary-sm">
            {saving ? 'Saving...' : 'Save Now'}
          </button>
        </div>
      )}
    </div>
  );
};

export default PermissionsPage;

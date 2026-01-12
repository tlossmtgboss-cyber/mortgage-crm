import React, { useState, useEffect, useCallback } from 'react';
import './IVRMenuDashboard.css';

const API_BASE = '/api/v1/ivr';

// Action type display mappings
const ACTION_LABELS = {
  transfer_user: 'Transfer to User',
  transfer_phone: 'Transfer to Phone',
  transfer_queue: 'Transfer to Queue',
  submenu: 'Go to Submenu',
  voicemail: 'Go to Voicemail',
  ai_receptionist: 'AI Receptionist',
  play_message: 'Play Message',
  hangup: 'Hang Up',
  repeat: 'Repeat Menu'
};

const ACTION_ICONS = {
  transfer_user: '👤',
  transfer_phone: '📞',
  transfer_queue: '📋',
  submenu: '📁',
  voicemail: '📧',
  ai_receptionist: '🤖',
  play_message: '🔊',
  hangup: '📴',
  repeat: '🔄'
};

const IVRMenuDashboard = () => {
  const [menus, setMenus] = useState([]);
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMenu, setSelectedMenu] = useState(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [showOptionModal, setShowOptionModal] = useState(false);
  const [editingOption, setEditingOption] = useState(null);

  const fetchMenus = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/menus?include_inactive=true`);
      if (!response.ok) throw new Error('Failed to fetch menus');
      const data = await response.json();
      setMenus(data.menus || []);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchTemplates = useCallback(async () => {
    try {
      const response = await fetch(`${API_BASE}/templates`);
      if (!response.ok) throw new Error('Failed to fetch templates');
      const data = await response.json();
      setTemplates(data.templates || []);
    } catch (err) {
      console.error('Error fetching templates:', err);
    }
  }, []);

  const fetchMenuDetails = useCallback(async (menuId) => {
    try {
      const response = await fetch(`${API_BASE}/menus/${menuId}`);
      if (!response.ok) throw new Error('Failed to fetch menu details');
      const data = await response.json();
      setSelectedMenu(data);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => {
    fetchMenus();
    fetchTemplates();
  }, [fetchMenus, fetchTemplates]);

  const handleCreateMenu = async (menuData) => {
    try {
      const response = await fetch(`${API_BASE}/menus`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(menuData)
      });
      if (!response.ok) throw new Error('Failed to create menu');
      setShowCreateModal(false);
      fetchMenus();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUpdateMenu = async (menuId, menuData) => {
    try {
      const response = await fetch(`${API_BASE}/menus/${menuId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(menuData)
      });
      if (!response.ok) throw new Error('Failed to update menu');
      fetchMenus();
      if (selectedMenu?.id === menuId) {
        fetchMenuDetails(menuId);
      }
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteMenu = async (menuId) => {
    if (!window.confirm('Are you sure you want to delete this IVR menu?')) return;
    try {
      const response = await fetch(`${API_BASE}/menus/${menuId}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete menu');
      if (selectedMenu?.id === menuId) {
        setSelectedMenu(null);
      }
      fetchMenus();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleApplyTemplate = async (templateId) => {
    try {
      const response = await fetch(`${API_BASE}/templates/${templateId}/apply`, {
        method: 'POST'
      });
      if (!response.ok) throw new Error('Failed to apply template');
      setShowTemplateModal(false);
      fetchMenus();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleCreateOption = async (menuId, optionData) => {
    try {
      const response = await fetch(`${API_BASE}/menus/${menuId}/options`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(optionData)
      });
      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || 'Failed to create option');
      }
      setShowOptionModal(false);
      setEditingOption(null);
      fetchMenuDetails(menuId);
      fetchMenus();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleUpdateOption = async (menuId, optionId, optionData) => {
    try {
      const response = await fetch(`${API_BASE}/menus/${menuId}/options/${optionId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(optionData)
      });
      if (!response.ok) throw new Error('Failed to update option');
      setShowOptionModal(false);
      setEditingOption(null);
      fetchMenuDetails(menuId);
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDeleteOption = async (menuId, optionId) => {
    if (!window.confirm('Are you sure you want to delete this option?')) return;
    try {
      const response = await fetch(`${API_BASE}/menus/${menuId}/options/${optionId}`, {
        method: 'DELETE'
      });
      if (!response.ok) throw new Error('Failed to delete option');
      fetchMenuDetails(menuId);
      fetchMenus();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleSetDefault = async (menuId) => {
    await handleUpdateMenu(menuId, { is_default: true });
  };

  const handleToggleActive = async (menuId, currentStatus) => {
    await handleUpdateMenu(menuId, { is_active: !currentStatus });
  };

  if (loading) {
    return (
      <div className="ivr-loading">
        <div className="ivr-spinner"></div>
        <p>Loading IVR menus...</p>
      </div>
    );
  }

  return (
    <div className="ivr-dashboard">
      {/* Header */}
      <div className="ivr-header">
        <div>
          <h1>IVR Menu Builder</h1>
          <p className="ivr-subtitle">Create and manage interactive voice response menus</p>
        </div>
        <div className="ivr-header-actions">
          <button
            className="ivr-btn ivr-btn-secondary"
            onClick={() => setShowTemplateModal(true)}
          >
            <span className="ivr-icon">📋</span>
            Use Template
          </button>
          <button
            className="ivr-btn ivr-btn-primary"
            onClick={() => setShowCreateModal(true)}
          >
            <span className="ivr-icon">+</span>
            Create Menu
          </button>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="ivr-error-banner">
          <span>⚠️ {error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Main Content */}
      <div className="ivr-content">
        {/* Menu List */}
        <div className="ivr-menu-list">
          <h2>IVR Menus</h2>
          {menus.length === 0 ? (
            <div className="ivr-empty">
              <span className="ivr-empty-icon">📞</span>
              <h3>No IVR Menus</h3>
              <p>Create your first IVR menu or use a template to get started.</p>
            </div>
          ) : (
            <div className="ivr-menus">
              {menus.map(menu => (
                <MenuCard
                  key={menu.id}
                  menu={menu}
                  isSelected={selectedMenu?.id === menu.id}
                  onSelect={() => fetchMenuDetails(menu.id)}
                  onSetDefault={() => handleSetDefault(menu.id)}
                  onToggleActive={() => handleToggleActive(menu.id, menu.is_active)}
                  onDelete={() => handleDeleteMenu(menu.id)}
                />
              ))}
            </div>
          )}
        </div>

        {/* Menu Detail / Editor */}
        <div className="ivr-menu-editor">
          {selectedMenu ? (
            <MenuEditor
              menu={selectedMenu}
              allMenus={menus}
              onUpdateMenu={(data) => handleUpdateMenu(selectedMenu.id, data)}
              onAddOption={() => {
                setEditingOption(null);
                setShowOptionModal(true);
              }}
              onEditOption={(option) => {
                setEditingOption(option);
                setShowOptionModal(true);
              }}
              onDeleteOption={(optionId) => handleDeleteOption(selectedMenu.id, optionId)}
              onClose={() => setSelectedMenu(null)}
            />
          ) : (
            <div className="ivr-editor-empty">
              <span className="ivr-empty-icon">👆</span>
              <h3>Select a Menu</h3>
              <p>Click on an IVR menu to view and edit its options.</p>
            </div>
          )}
        </div>
      </div>

      {/* Create Menu Modal */}
      {showCreateModal && (
        <CreateMenuModal
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreateMenu}
        />
      )}

      {/* Template Modal */}
      {showTemplateModal && (
        <TemplateModal
          templates={templates}
          onClose={() => setShowTemplateModal(false)}
          onApply={handleApplyTemplate}
        />
      )}

      {/* Option Modal */}
      {showOptionModal && selectedMenu && (
        <OptionModal
          menuId={selectedMenu.id}
          option={editingOption}
          allMenus={menus}
          onClose={() => {
            setShowOptionModal(false);
            setEditingOption(null);
          }}
          onCreate={(data) => handleCreateOption(selectedMenu.id, data)}
          onUpdate={(data) => handleUpdateOption(selectedMenu.id, editingOption.id, data)}
        />
      )}
    </div>
  );
};

// Menu Card Component
const MenuCard = ({ menu, isSelected, onSelect, onSetDefault, onToggleActive, onDelete }) => {
  return (
    <div
      className={`ivr-menu-card ${isSelected ? 'selected' : ''} ${!menu.is_active ? 'inactive' : ''}`}
      onClick={onSelect}
    >
      <div className="ivr-menu-card-header">
        <div className="ivr-menu-card-title">
          <h3>{menu.name}</h3>
          {menu.is_default && <span className="ivr-badge ivr-badge-default">Default</span>}
          {!menu.is_active && <span className="ivr-badge ivr-badge-inactive">Inactive</span>}
        </div>
        <div className="ivr-menu-card-actions" onClick={e => e.stopPropagation()}>
          {!menu.is_default && menu.is_active && (
            <button
              className="ivr-btn-icon"
              onClick={onSetDefault}
              title="Set as Default"
            >
              ⭐
            </button>
          )}
          <button
            className="ivr-btn-icon"
            onClick={onToggleActive}
            title={menu.is_active ? 'Deactivate' : 'Activate'}
          >
            {menu.is_active ? '🔘' : '⚪'}
          </button>
          <button
            className="ivr-btn-icon ivr-btn-delete"
            onClick={onDelete}
            title="Delete"
          >
            🗑️
          </button>
        </div>
      </div>
      {menu.description && (
        <p className="ivr-menu-card-desc">{menu.description}</p>
      )}
      <div className="ivr-menu-card-stats">
        <span>📊 {menu.option_count} options</span>
        <span>⏱️ {menu.timeout_seconds}s timeout</span>
      </div>
    </div>
  );
};

// Menu Editor Component
const MenuEditor = ({ menu, allMenus, onUpdateMenu, onAddOption, onEditOption, onDeleteOption, onClose }) => {
  const [isEditingGreeting, setIsEditingGreeting] = useState(false);
  const [greetingText, setGreetingText] = useState(menu.greeting_text || '');

  useEffect(() => {
    setGreetingText(menu.greeting_text || '');
  }, [menu]);

  const handleSaveGreeting = () => {
    onUpdateMenu({ greeting_text: greetingText });
    setIsEditingGreeting(false);
  };

  const usedDigits = menu.options?.map(o => o.dtmf_digit) || [];
  const availableDigits = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '*', '#'].filter(
    d => !usedDigits.includes(d)
  );

  return (
    <div className="ivr-editor">
      <div className="ivr-editor-header">
        <h2>{menu.name}</h2>
        <button className="ivr-close-btn" onClick={onClose}>×</button>
      </div>

      {/* Greeting Section */}
      <div className="ivr-editor-section">
        <div className="ivr-section-header">
          <h3>🎙️ Greeting Message</h3>
          {!isEditingGreeting && (
            <button
              className="ivr-btn ivr-btn-small"
              onClick={() => setIsEditingGreeting(true)}
            >
              Edit
            </button>
          )}
        </div>
        {isEditingGreeting ? (
          <div className="ivr-greeting-edit">
            <textarea
              value={greetingText}
              onChange={(e) => setGreetingText(e.target.value)}
              placeholder="Enter the greeting message callers will hear..."
              rows={4}
            />
            <div className="ivr-greeting-actions">
              <button
                className="ivr-btn ivr-btn-secondary"
                onClick={() => {
                  setGreetingText(menu.greeting_text || '');
                  setIsEditingGreeting(false);
                }}
              >
                Cancel
              </button>
              <button
                className="ivr-btn ivr-btn-primary"
                onClick={handleSaveGreeting}
              >
                Save Greeting
              </button>
            </div>
          </div>
        ) : (
          <div className="ivr-greeting-preview">
            {menu.greeting_text || (
              <span className="ivr-placeholder">No greeting configured. Click Edit to add one.</span>
            )}
          </div>
        )}
      </div>

      {/* Options Section */}
      <div className="ivr-editor-section">
        <div className="ivr-section-header">
          <h3>📞 Menu Options</h3>
          <button
            className="ivr-btn ivr-btn-primary ivr-btn-small"
            onClick={onAddOption}
            disabled={availableDigits.length === 0}
          >
            + Add Option
          </button>
        </div>

        {menu.options?.length === 0 ? (
          <div className="ivr-options-empty">
            <p>No options configured. Add menu options for callers to select.</p>
          </div>
        ) : (
          <div className="ivr-options-list">
            {menu.options?.sort((a, b) => a.display_order - b.display_order).map(option => (
              <div
                key={option.id}
                className={`ivr-option-item ${!option.is_active ? 'inactive' : ''}`}
              >
                <div className="ivr-option-digit">
                  <span className="ivr-digit-key">{option.dtmf_digit}</span>
                </div>
                <div className="ivr-option-content">
                  <div className="ivr-option-label">{option.label}</div>
                  <div className="ivr-option-action">
                    <span className="ivr-action-icon">{ACTION_ICONS[option.action_type]}</span>
                    <span className="ivr-action-type">{ACTION_LABELS[option.action_type]}</span>
                    {option.action_target && (
                      <span className="ivr-action-target">→ {option.action_target}</span>
                    )}
                  </div>
                </div>
                <div className="ivr-option-actions">
                  <button
                    className="ivr-btn-icon"
                    onClick={() => onEditOption(option)}
                    title="Edit"
                  >
                    ✏️
                  </button>
                  <button
                    className="ivr-btn-icon ivr-btn-delete"
                    onClick={() => onDeleteOption(option.id)}
                    title="Delete"
                  >
                    🗑️
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Settings Section */}
      <div className="ivr-editor-section">
        <h3>⚙️ Menu Settings</h3>
        <div className="ivr-settings-grid">
          <div className="ivr-setting-item">
            <label>Timeout (seconds)</label>
            <input
              type="number"
              value={menu.timeout_seconds || 10}
              onChange={(e) => onUpdateMenu({ timeout_seconds: parseInt(e.target.value) })}
              min={5}
              max={60}
            />
          </div>
          <div className="ivr-setting-item">
            <label>Max Attempts</label>
            <input
              type="number"
              value={menu.max_attempts || 3}
              onChange={(e) => onUpdateMenu({ max_attempts: parseInt(e.target.value) })}
              min={1}
              max={5}
            />
          </div>
          <div className="ivr-setting-item">
            <label>Timeout Action</label>
            <select
              value={menu.timeout_action || 'ai_receptionist'}
              onChange={(e) => onUpdateMenu({ timeout_action: e.target.value })}
            >
              <option value="ai_receptionist">Connect to AI Receptionist</option>
              <option value="voicemail">Go to Voicemail</option>
              <option value="hangup">Hang Up</option>
            </select>
          </div>
        </div>
      </div>

      {/* Preview Section */}
      <div className="ivr-editor-section">
        <h3>👁️ Call Flow Preview</h3>
        <div className="ivr-preview">
          <div className="ivr-preview-step">
            <span className="ivr-preview-num">1</span>
            <span className="ivr-preview-text">
              Caller hears: "{menu.greeting_text || 'Default greeting'}"
            </span>
          </div>
          {menu.options?.map((opt, idx) => (
            <div key={opt.id} className="ivr-preview-step">
              <span className="ivr-preview-num">{idx + 2}</span>
              <span className="ivr-preview-text">
                "Press {opt.dtmf_digit} for {opt.label}"
              </span>
            </div>
          ))}
          <div className="ivr-preview-step ivr-preview-timeout">
            <span className="ivr-preview-num">⏱️</span>
            <span className="ivr-preview-text">
              After {menu.max_attempts} attempts or {menu.timeout_seconds}s timeout: {ACTION_LABELS[menu.timeout_action] || 'AI Receptionist'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

// Create Menu Modal
const CreateMenuModal = ({ onClose, onCreate }) => {
  const [formData, setFormData] = useState({
    name: '',
    description: '',
    greeting_text: '',
    is_default: false,
    timeout_seconds: 10,
    max_attempts: 3,
    timeout_action: 'ai_receptionist'
  });
  const [error, setError] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.name.trim()) {
      setError('Menu name is required');
      return;
    }
    onCreate(formData);
  };

  return (
    <div className="ivr-modal-overlay" onClick={onClose}>
      <div className="ivr-modal" onClick={e => e.stopPropagation()}>
        <div className="ivr-modal-header">
          <h2>Create IVR Menu</h2>
          <button className="ivr-close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="ivr-modal-body">
            {error && <div className="ivr-form-error">{error}</div>}

            <div className="ivr-form-group">
              <label>Menu Name *</label>
              <input
                type="text"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="e.g., Main Menu, After Hours"
              />
            </div>

            <div className="ivr-form-group">
              <label>Description</label>
              <input
                type="text"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Brief description of this menu"
              />
            </div>

            <div className="ivr-form-group">
              <label>Greeting Message</label>
              <textarea
                value={formData.greeting_text}
                onChange={(e) => setFormData({ ...formData, greeting_text: e.target.value })}
                placeholder="Welcome message callers will hear..."
                rows={3}
              />
            </div>

            <div className="ivr-form-row">
              <div className="ivr-form-group">
                <label>Timeout (seconds)</label>
                <input
                  type="number"
                  value={formData.timeout_seconds}
                  onChange={(e) => setFormData({ ...formData, timeout_seconds: parseInt(e.target.value) })}
                  min={5}
                  max={60}
                />
              </div>
              <div className="ivr-form-group">
                <label>Max Attempts</label>
                <input
                  type="number"
                  value={formData.max_attempts}
                  onChange={(e) => setFormData({ ...formData, max_attempts: parseInt(e.target.value) })}
                  min={1}
                  max={5}
                />
              </div>
            </div>

            <div className="ivr-form-group">
              <label>Timeout Action</label>
              <select
                value={formData.timeout_action}
                onChange={(e) => setFormData({ ...formData, timeout_action: e.target.value })}
              >
                <option value="ai_receptionist">Connect to AI Receptionist</option>
                <option value="voicemail">Go to Voicemail</option>
                <option value="hangup">Hang Up</option>
              </select>
            </div>

            <div className="ivr-form-group ivr-checkbox">
              <label>
                <input
                  type="checkbox"
                  checked={formData.is_default}
                  onChange={(e) => setFormData({ ...formData, is_default: e.target.checked })}
                />
                Set as default menu
              </label>
              <span className="ivr-hint">Default menu is used when no specific menu is specified</span>
            </div>
          </div>
          <div className="ivr-modal-footer">
            <button type="button" className="ivr-btn ivr-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="ivr-btn ivr-btn-primary">
              Create Menu
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

// Template Modal
const TemplateModal = ({ templates, onClose, onApply }) => {
  return (
    <div className="ivr-modal-overlay" onClick={onClose}>
      <div className="ivr-modal ivr-modal-large" onClick={e => e.stopPropagation()}>
        <div className="ivr-modal-header">
          <h2>Choose a Template</h2>
          <button className="ivr-close-btn" onClick={onClose}>×</button>
        </div>
        <div className="ivr-modal-body">
          <p className="ivr-template-intro">
            Start with a pre-built IVR template and customize it to your needs.
          </p>
          <div className="ivr-templates-grid">
            {templates.map(template => (
              <div key={template.id} className="ivr-template-card">
                <h3>{template.name}</h3>
                <p>{template.description}</p>
                <div className="ivr-template-options">
                  {template.options?.map(opt => (
                    <div key={opt.digit} className="ivr-template-option">
                      <span className="ivr-digit-small">{opt.digit}</span>
                      <span>{opt.label}</span>
                    </div>
                  ))}
                </div>
                <button
                  className="ivr-btn ivr-btn-primary ivr-btn-full"
                  onClick={() => onApply(template.id)}
                >
                  Use This Template
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

// Option Modal
const OptionModal = ({ menuId, option, allMenus, onClose, onCreate, onUpdate }) => {
  const [formData, setFormData] = useState({
    dtmf_digit: option?.dtmf_digit || '1',
    label: option?.label || '',
    action_type: option?.action_type || 'ai_receptionist',
    action_target: option?.action_target || '',
    announcement_text: option?.announcement_text || '',
    display_order: option?.display_order || 0
  });
  const [error, setError] = useState(null);

  const isEditing = !!option;

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!formData.label.trim()) {
      setError('Label is required');
      return;
    }

    // Validate action target for certain actions
    const needsTarget = ['transfer_user', 'transfer_phone', 'transfer_queue', 'submenu', 'play_message'];
    if (needsTarget.includes(formData.action_type) && !formData.action_target.trim()) {
      setError(`Target is required for ${ACTION_LABELS[formData.action_type]}`);
      return;
    }

    if (isEditing) {
      onUpdate(formData);
    } else {
      onCreate(formData);
    }
  };

  const getTargetPlaceholder = () => {
    switch (formData.action_type) {
      case 'transfer_user':
        return 'User ID';
      case 'transfer_phone':
        return 'Phone number (e.g., +15551234567)';
      case 'transfer_queue':
        return 'Queue name';
      case 'submenu':
        return 'Select a menu';
      case 'play_message':
        return 'Message to play';
      default:
        return '';
    }
  };

  const needsTarget = ['transfer_user', 'transfer_phone', 'transfer_queue', 'submenu', 'play_message'];
  const showTargetField = needsTarget.includes(formData.action_type);

  return (
    <div className="ivr-modal-overlay" onClick={onClose}>
      <div className="ivr-modal" onClick={e => e.stopPropagation()}>
        <div className="ivr-modal-header">
          <h2>{isEditing ? 'Edit Option' : 'Add Option'}</h2>
          <button className="ivr-close-btn" onClick={onClose}>×</button>
        </div>
        <form onSubmit={handleSubmit}>
          <div className="ivr-modal-body">
            {error && <div className="ivr-form-error">{error}</div>}

            <div className="ivr-form-row">
              <div className="ivr-form-group ivr-form-digit">
                <label>DTMF Digit *</label>
                <select
                  value={formData.dtmf_digit}
                  onChange={(e) => setFormData({ ...formData, dtmf_digit: e.target.value })}
                  disabled={isEditing}
                >
                  {['1', '2', '3', '4', '5', '6', '7', '8', '9', '0', '*', '#'].map(d => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </div>
              <div className="ivr-form-group ivr-form-label">
                <label>Label *</label>
                <input
                  type="text"
                  value={formData.label}
                  onChange={(e) => setFormData({ ...formData, label: e.target.value })}
                  placeholder="e.g., Sales, Support, Leave Message"
                />
              </div>
            </div>

            <div className="ivr-form-group">
              <label>Action Type</label>
              <select
                value={formData.action_type}
                onChange={(e) => setFormData({ ...formData, action_type: e.target.value, action_target: '' })}
              >
                {Object.entries(ACTION_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {ACTION_ICONS[value]} {label}
                  </option>
                ))}
              </select>
            </div>

            {showTargetField && (
              <div className="ivr-form-group">
                <label>Target *</label>
                {formData.action_type === 'submenu' ? (
                  <select
                    value={formData.action_target}
                    onChange={(e) => setFormData({ ...formData, action_target: e.target.value })}
                  >
                    <option value="">Select a menu...</option>
                    {allMenus.filter(m => m.id !== menuId).map(m => (
                      <option key={m.id} value={m.id}>{m.name}</option>
                    ))}
                  </select>
                ) : formData.action_type === 'play_message' ? (
                  <textarea
                    value={formData.action_target}
                    onChange={(e) => setFormData({ ...formData, action_target: e.target.value })}
                    placeholder={getTargetPlaceholder()}
                    rows={3}
                  />
                ) : (
                  <input
                    type="text"
                    value={formData.action_target}
                    onChange={(e) => setFormData({ ...formData, action_target: e.target.value })}
                    placeholder={getTargetPlaceholder()}
                  />
                )}
              </div>
            )}

            <div className="ivr-form-group">
              <label>Announcement (optional)</label>
              <textarea
                value={formData.announcement_text}
                onChange={(e) => setFormData({ ...formData, announcement_text: e.target.value })}
                placeholder="Message to play before executing the action..."
                rows={2}
              />
              <span className="ivr-hint">This message plays before the action is performed</span>
            </div>
          </div>
          <div className="ivr-modal-footer">
            <button type="button" className="ivr-btn ivr-btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="ivr-btn ivr-btn-primary">
              {isEditing ? 'Save Changes' : 'Add Option'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default IVRMenuDashboard;

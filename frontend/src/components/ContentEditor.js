/**
 * ContentEditor - Schema-driven form builder for microsite content
 *
 * Dynamically generates form fields based on the template schema.
 * Supports various field types including text, textarea, image, URL,
 * repeatable items (like testimonials), and more.
 */

import React, { useState, useCallback, useMemo } from 'react';
import './ContentEditor.css';
import { getToken } from '../utils/tokenStore';

// API base URL for image uploads
const API_BASE = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// Field type components
const FIELD_TYPES = {
  text: TextInput,
  textarea: TextAreaInput,
  richtext: RichTextInput,
  image: ImageUpload,
  url: UrlInput,
  email: EmailInput,
  phone: PhoneInput,
  number: NumberInput,
  select: SelectInput,
  toggle: ToggleInput,
  color: ColorInput,
  date: DateInput,
  social: SocialInput,
};

// Social icons mapping
const SOCIAL_ICONS = {
  linkedin: '🔗',
  facebook: '📘',
  twitter: '🐦',
  instagram: '📷',
  youtube: '📺',
  tiktok: '🎵',
};

/**
 * Main ContentEditor component
 */
const ContentEditor = ({ schema, content, onChange, lockedFields = {} }) => {
  const [activeSection, setActiveSection] = useState(null);

  // Extract sections from schema
  const sections = useMemo(() => {
    if (!schema?.sections) return [];
    return Object.entries(schema.sections).map(([key, sectionDef]) => ({
      key,
      ...sectionDef,
    }));
  }, [schema]);

  // Set initial active section
  React.useEffect(() => {
    if (sections.length > 0 && !activeSection) {
      setActiveSection(sections[0].key);
    }
  }, [sections, activeSection]);

  // Handle field change
  const handleFieldChange = useCallback((sectionKey, fieldKey, value) => {
    const newContent = {
      ...content,
      [sectionKey]: {
        ...(content[sectionKey] || {}),
        [fieldKey]: value,
      },
    };
    onChange(newContent);
  }, [content, onChange]);

  // Handle nested field change (for repeatable items)
  const handleNestedChange = useCallback((sectionKey, fieldKey, index, subFieldKey, value) => {
    const currentItems = content[sectionKey]?.[fieldKey] || [];
    const newItems = [...currentItems];
    newItems[index] = {
      ...newItems[index],
      [subFieldKey]: value,
    };

    const newContent = {
      ...content,
      [sectionKey]: {
        ...(content[sectionKey] || {}),
        [fieldKey]: newItems,
      },
    };
    onChange(newContent);
  }, [content, onChange]);

  // Add repeatable item
  const addRepeatableItem = useCallback((sectionKey, fieldKey, defaultItem = {}) => {
    const currentItems = content[sectionKey]?.[fieldKey] || [];

    const newContent = {
      ...content,
      [sectionKey]: {
        ...(content[sectionKey] || {}),
        [fieldKey]: [...currentItems, defaultItem],
      },
    };
    onChange(newContent);
  }, [content, onChange]);

  // Remove repeatable item
  const removeRepeatableItem = useCallback((sectionKey, fieldKey, index) => {
    const currentItems = content[sectionKey]?.[fieldKey] || [];
    const newItems = currentItems.filter((_, i) => i !== index);

    const newContent = {
      ...content,
      [sectionKey]: {
        ...(content[sectionKey] || {}),
        [fieldKey]: newItems,
      },
    };
    onChange(newContent);
  }, [content, onChange]);

  // Move repeatable item
  const moveRepeatableItem = useCallback((sectionKey, fieldKey, fromIndex, toIndex) => {
    const currentItems = content[sectionKey]?.[fieldKey] || [];
    const newItems = [...currentItems];
    const [removed] = newItems.splice(fromIndex, 1);
    newItems.splice(toIndex, 0, removed);

    const newContent = {
      ...content,
      [sectionKey]: {
        ...(content[sectionKey] || {}),
        [fieldKey]: newItems,
      },
    };
    onChange(newContent);
  }, [content, onChange]);

  // Check if field is locked
  const isFieldLocked = useCallback((sectionKey, fieldKey) => {
    return lockedFields[`${sectionKey}.${fieldKey}`] || false;
  }, [lockedFields]);

  // Get field value
  const getFieldValue = useCallback((sectionKey, fieldKey) => {
    return content[sectionKey]?.[fieldKey] ?? '';
  }, [content]);

  if (!schema || sections.length === 0) {
    return (
      <div className="content-editor">
        <div className="empty-section">
          <div className="icon">📄</div>
          <p>No content schema available</p>
        </div>
      </div>
    );
  }

  return (
    <div className="content-editor">
      {/* Section Navigation */}
      <div className="section-nav">
        {sections.map((section) => (
          <button
            key={section.key}
            className={activeSection === section.key ? 'active' : ''}
            onClick={() => setActiveSection(section.key)}
          >
            {section.label || section.key}
          </button>
        ))}
      </div>

      {/* Active Section Content */}
      {sections.map((section) => {
        if (section.key !== activeSection) return null;

        return (
          <div key={section.key} className="section-container">
            <div className="section-header">
              <h3>{section.label || section.key}</h3>
              {section.description && <p>{section.description}</p>}
            </div>

            <div className="fields-grid">
              {Object.entries(section.fields || {}).map(([fieldKey, fieldDef]) => {
                const isLocked = isFieldLocked(section.key, fieldKey);
                const value = getFieldValue(section.key, fieldKey);

                // Handle repeatable fields
                if (fieldDef.repeatable) {
                  return (
                    <RepeatableField
                      key={fieldKey}
                      fieldKey={fieldKey}
                      fieldDef={fieldDef}
                      items={value || []}
                      sectionKey={section.key}
                      onAdd={(defaultItem) => addRepeatableItem(section.key, fieldKey, defaultItem)}
                      onRemove={(index) => removeRepeatableItem(section.key, fieldKey, index)}
                      onMove={(from, to) => moveRepeatableItem(section.key, fieldKey, from, to)}
                      onChange={(index, subFieldKey, val) =>
                        handleNestedChange(section.key, fieldKey, index, subFieldKey, val)
                      }
                      isLocked={isLocked}
                    />
                  );
                }

                // Get field component
                const FieldComponent = FIELD_TYPES[fieldDef.type] || TextInput;

                return (
                  <div
                    key={fieldKey}
                    className={`field-group ${fieldDef.fullWidth ? 'full-width' : ''}`}
                  >
                    <FieldComponent
                      fieldKey={fieldKey}
                      fieldDef={fieldDef}
                      value={value}
                      onChange={(val) => handleFieldChange(section.key, fieldKey, val)}
                      disabled={isLocked}
                    />
                  </div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};

/**
 * Repeatable Field Component
 */
function RepeatableField({
  fieldKey,
  fieldDef,
  items,
  sectionKey,
  onAdd,
  onRemove,
  onMove,
  onChange,
  isLocked,
}) {
  const maxItems = fieldDef.maxItems || 10;
  const minItems = fieldDef.minItems || 0;
  const canAdd = items.length < maxItems && !isLocked;
  const canRemove = items.length > minItems && !isLocked;

  return (
    <div className="field-group full-width">
      <div className="repeatable-field">
        <div className="repeatable-header">
          <h4>{fieldDef.label || fieldKey}</h4>
          <span className="item-count">
            {items.length} / {maxItems} items
          </span>
        </div>

        <div className="repeatable-items">
          {items.map((item, index) => (
            <RepeatableItem
              key={index}
              index={index}
              item={item}
              fieldDef={fieldDef}
              onChange={onChange}
              onRemove={() => canRemove && onRemove(index)}
              onMoveUp={() => index > 0 && onMove(index, index - 1)}
              onMoveDown={() => index < items.length - 1 && onMove(index, index + 1)}
              canRemove={canRemove}
              isLocked={isLocked}
            />
          ))}

          <button
            className="add-item-btn"
            onClick={() => onAdd(fieldDef.defaultItem || {})}
            disabled={!canAdd}
          >
            <span>+</span>
            Add {fieldDef.itemLabel || 'Item'}
          </button>
        </div>
      </div>
    </div>
  );
}

/**
 * Single Repeatable Item
 */
function RepeatableItem({
  index,
  item,
  fieldDef,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
  canRemove,
  isLocked,
}) {
  const [collapsed, setCollapsed] = useState(false);
  const itemFields = fieldDef.itemFields || {};

  // Get item title for display
  const getItemTitle = () => {
    if (fieldDef.titleField && item[fieldDef.titleField]) {
      return item[fieldDef.titleField].substring(0, 50);
    }
    return `${fieldDef.itemLabel || 'Item'} ${index + 1}`;
  };

  return (
    <div className="repeatable-item">
      <div className="repeatable-item-header">
        <span className="drag-handle">⋮⋮</span>
        <span className="item-title" onClick={() => setCollapsed(!collapsed)}>
          {getItemTitle()}
        </span>
        <div className="item-actions">
          <button onClick={onMoveUp} disabled={isLocked} title="Move up">↑</button>
          <button onClick={onMoveDown} disabled={isLocked} title="Move down">↓</button>
          <button
            className="delete"
            onClick={onRemove}
            disabled={!canRemove || isLocked}
            title="Remove"
          >
            ×
          </button>
        </div>
      </div>

      {!collapsed && (
        <div className="repeatable-item-content">
          {Object.entries(itemFields).map(([subFieldKey, subFieldDef]) => {
            const FieldComponent = FIELD_TYPES[subFieldDef.type] || TextInput;

            return (
              <div key={subFieldKey} className="field-group">
                <FieldComponent
                  fieldKey={subFieldKey}
                  fieldDef={subFieldDef}
                  value={item[subFieldKey] ?? ''}
                  onChange={(val) => onChange(index, subFieldKey, val)}
                  disabled={isLocked}
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

/**
 * Text Input Field
 */
function TextInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  const maxLength = fieldDef.maxLength || 500;
  const charCount = (value || '').length;

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
        {fieldDef.maxLength && (
          <span
            className={`char-count ${
              charCount > maxLength * 0.9 ? 'near-limit' : ''
            } ${charCount >= maxLength ? 'at-limit' : ''}`}
          >
            {charCount}/{maxLength}
          </span>
        )}
      </div>
      <input
        id={fieldKey}
        type="text"
        className="field-input"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={fieldDef.placeholder}
        maxLength={maxLength}
        disabled={disabled}
      />
      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * TextArea Input Field
 */
function TextAreaInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  const maxLength = fieldDef.maxLength || 2000;
  const charCount = (value || '').length;

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
        <span
          className={`char-count ${
            charCount > maxLength * 0.9 ? 'near-limit' : ''
          } ${charCount >= maxLength ? 'at-limit' : ''}`}
        >
          {charCount}/{maxLength}
        </span>
      </div>
      <textarea
        id={fieldKey}
        className="field-input"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={fieldDef.placeholder}
        maxLength={maxLength}
        rows={fieldDef.rows || 4}
        disabled={disabled}
      />
      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Rich Text Input (simplified version)
 */
function RichTextInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  const [showToolbar, setShowToolbar] = useState(false);

  const applyFormat = (format) => {
    // Simplified formatting - wrap selection or append
    const formatMap = {
      bold: { prefix: '**', suffix: '**' },
      italic: { prefix: '_', suffix: '_' },
      link: { prefix: '[', suffix: '](url)' },
    };

    const f = formatMap[format];
    if (f) {
      onChange(`${value || ''}${f.prefix}text${f.suffix}`);
    }
  };

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      {!disabled && (
        <div className="rich-text-toolbar">
          <button type="button" onClick={() => applyFormat('bold')} title="Bold">
            <strong>B</strong>
          </button>
          <button type="button" onClick={() => applyFormat('italic')} title="Italic">
            <em>I</em>
          </button>
          <button type="button" onClick={() => applyFormat('link')} title="Link">
            🔗
          </button>
        </div>
      )}

      <textarea
        id={fieldKey}
        className="field-input rich-text-content"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={fieldDef.placeholder}
        rows={fieldDef.rows || 6}
        disabled={disabled}
      />
      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Image Upload Field
 */
function ImageUpload({ fieldKey, fieldDef, value, onChange, disabled }) {
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState(null);

  const handleUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;

    // Validate file type
    if (!file.type.startsWith('image/')) {
      setError('Please select an image file');
      return;
    }

    // Validate file size (max 5MB)
    const maxSize = fieldDef.maxSize || 5 * 1024 * 1024;
    if (file.size > maxSize) {
      setError(`File must be less than ${Math.round(maxSize / 1024 / 1024)}MB`);
      return;
    }

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('asset_type', fieldDef.assetType || 'image');

      const response = await fetch(`${API_BASE}/api/v1/microsites/my/assets/upload`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        onChange(data.public_url);
      } else {
        setError('Upload failed');
      }
    } catch (err) {
      console.error('Upload error:', err);
      setError('Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <input
        type="file"
        id={fieldKey}
        accept="image/*"
        onChange={handleUpload}
        style={{ display: 'none' }}
        disabled={disabled || uploading}
      />

      <label htmlFor={fieldKey} className={`image-upload ${value ? 'has-image' : ''}`}>
        {value ? (
          <>
            <img src={value} alt="Preview" className="image-preview" />
            <p>Click to change image</p>
          </>
        ) : (
          <div className="upload-placeholder">
            <span className="icon">{uploading ? '⏳' : '📤'}</span>
            <p>{uploading ? 'Uploading...' : 'Click to upload image'}</p>
            <span>
              {fieldDef.recommendedSize || 'Recommended: 1200x630px'}
            </span>
          </div>
        )}
      </label>

      {error && (
        <div className="field-error">
          <span className="error-icon">⚠️</span>
          {error}
        </div>
      )}

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * URL Input Field
 */
function UrlInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  const validateUrl = (url) => {
    if (!url) return true;
    try {
      new URL(url);
      return true;
    } catch {
      return false;
    }
  };

  const isValid = validateUrl(value);

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <div className="url-input-group">
        <input
          id={fieldKey}
          type="url"
          className={`field-input ${!isValid ? 'error' : ''}`}
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={fieldDef.placeholder || 'https://'}
          disabled={disabled}
        />
      </div>

      {!isValid && value && (
        <div className="field-error">
          <span className="error-icon">⚠️</span>
          Please enter a valid URL
        </div>
      )}

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Email Input Field
 */
function EmailInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  const validateEmail = (email) => {
    if (!email) return true;
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  };

  const isValid = validateEmail(value);

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <input
        id={fieldKey}
        type="email"
        className={`field-input ${!isValid ? 'error' : ''}`}
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder={fieldDef.placeholder || 'email@example.com'}
        disabled={disabled}
      />

      {!isValid && value && (
        <div className="field-error">
          <span className="error-icon">⚠️</span>
          Please enter a valid email address
        </div>
      )}

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Phone Input Field
 */
function PhoneInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  const formatPhone = (phone) => {
    if (!phone) return '';
    const digits = phone.replace(/\D/g, '');
    if (digits.length <= 3) return digits;
    if (digits.length <= 6) return `(${digits.slice(0, 3)}) ${digits.slice(3)}`;
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6, 10)}`;
  };

  const handleChange = (e) => {
    const formatted = formatPhone(e.target.value);
    onChange(formatted);
  };

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <input
        id={fieldKey}
        type="tel"
        className="field-input"
        value={value || ''}
        onChange={handleChange}
        placeholder={fieldDef.placeholder || '(555) 123-4567'}
        disabled={disabled}
      />

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Number Input Field
 */
function NumberInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <div className="number-with-unit">
        <input
          id={fieldKey}
          type="number"
          className="field-input"
          value={value || ''}
          onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
          placeholder={fieldDef.placeholder}
          min={fieldDef.min}
          max={fieldDef.max}
          step={fieldDef.step || 1}
          disabled={disabled}
        />
        {fieldDef.unit && <span className="unit">{fieldDef.unit}</span>}
      </div>

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Select Input Field
 */
function SelectInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  const options = fieldDef.options || [];

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <select
        id={fieldKey}
        className="field-input select-input"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
      >
        <option value="">
          {fieldDef.placeholder || 'Select an option'}
        </option>
        {options.map((option) => (
          <option
            key={typeof option === 'string' ? option : option.value}
            value={typeof option === 'string' ? option : option.value}
          >
            {typeof option === 'string' ? option : option.label}
          </option>
        ))}
      </select>

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Toggle Input Field
 */
function ToggleInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  return (
    <div className="toggle-field">
      <div className="toggle-label">
        <span>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </span>
        {fieldDef.description && <span>{fieldDef.description}</span>}
      </div>

      <div
        className={`toggle-switch ${value ? 'active' : ''}`}
        onClick={() => !disabled && onChange(!value)}
        role="checkbox"
        aria-checked={!!value}
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            !disabled && onChange(!value);
          }
        }}
      />
    </div>
  );
}

/**
 * Color Input Field
 */
function ColorInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <div className="color-field">
        <input
          type="color"
          value={value || '#000000'}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
        />
        <input
          id={fieldKey}
          type="text"
          className="field-input"
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder="#000000"
          disabled={disabled}
        />
      </div>

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Date Input Field
 */
function DateInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <input
        id={fieldKey}
        type="date"
        className="field-input"
        value={value || ''}
        onChange={(e) => onChange(e.target.value)}
        min={fieldDef.minDate}
        max={fieldDef.maxDate}
        disabled={disabled}
      />

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

/**
 * Social Link Input Field
 */
function SocialInput({ fieldKey, fieldDef, value, onChange, disabled }) {
  const platform = fieldDef.platform || fieldKey;
  const icon = SOCIAL_ICONS[platform.toLowerCase()] || '🔗';

  return (
    <>
      <div className="field-label">
        <label htmlFor={fieldKey}>
          {fieldDef.label || fieldKey}
          {fieldDef.required && <span className="required">*</span>}
        </label>
        {disabled && <span className="locked">🔒 Locked</span>}
      </div>

      <div className="social-link-field">
        <span className="social-icon">{icon}</span>
        <input
          id={fieldKey}
          type="url"
          className="field-input"
          value={value || ''}
          onChange={(e) => onChange(e.target.value)}
          placeholder={fieldDef.placeholder || `Your ${platform} URL`}
          disabled={disabled}
        />
      </div>

      {fieldDef.hint && <div className="field-hint">{fieldDef.hint}</div>}
    </>
  );
}

export default ContentEditor;

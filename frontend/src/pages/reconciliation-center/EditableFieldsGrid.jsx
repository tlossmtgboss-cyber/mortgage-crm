import React from 'react';
import { FIELD_TYPE_OPTIONS } from './constants';
import { formatFieldName, formatDisplayValue } from './helpers';

/**
 * EditableFieldsGrid - Shared component for displaying and editing extracted fields.
 * Used in New tab detail panel and Pending Review tab detail panel.
 * Supports field editing, deletion, restoration, renaming, and adding new fields.
 */
export default function EditableFieldsGrid({
  selectedItem,
  editedFields,
  deletedFields,
  renamedFields,
  addedFields,
  editingFieldKey,
  showAddFieldForm,
  newFieldKey,
  newFieldValue,
  // Handlers
  handleFieldEdit,
  handleFieldDelete,
  handleFieldRestore,
  handleFieldRename,
  handleFieldRenameUndo,
  handleAddField,
  handleRemoveAddedField,
  setEditingFieldKey,
  setShowAddFieldForm,
  setNewFieldKey,
  setNewFieldValue,
  setAddedFields,
  getEffectiveFieldKey,
  // Optional: custom className for the grid container
  gridClassName = 'fields-grid-recon',
}) {
  return (
    <>
      <div className="section-header-row" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <h3 style={{ margin: 0 }}>Extracted Fields</h3>
        <button
          onClick={() => setShowAddFieldForm(true)}
          style={{
            padding: '6px 12px',
            fontSize: '12px',
            background: '#2D7A52',
            color: 'white',
            border: 'none',
            borderRadius: '6px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          + Add Field
        </button>
      </div>

      {/* Add Field Form */}
      {showAddFieldForm && (
        <div className="add-field-form" style={{
          background: '#f0fdf4',
          border: '1px solid #86efac',
          borderRadius: '8px',
          padding: '12px',
          marginBottom: '12px'
        }}>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'flex-end' }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: '11px', color: '#374151', marginBottom: '4px' }}>Field Name</label>
              <select
                value={newFieldKey}
                onChange={(e) => setNewFieldKey(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '13px'
                }}
              >
                <option value="">Select field type...</option>
                {FIELD_TYPE_OPTIONS.map(opt => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            </div>
            <div style={{ flex: 2 }}>
              <label style={{ display: 'block', fontSize: '11px', color: '#374151', marginBottom: '4px' }}>Value</label>
              <input
                type="text"
                value={newFieldValue}
                onChange={(e) => setNewFieldValue(e.target.value)}
                placeholder="Enter value..."
                style={{
                  width: '100%',
                  padding: '8px',
                  border: '1px solid #d1d5db',
                  borderRadius: '6px',
                  fontSize: '13px'
                }}
              />
            </div>
            <button
              onClick={handleAddField}
              disabled={!newFieldKey || !newFieldValue}
              style={{
                padding: '8px 16px',
                background: newFieldKey && newFieldValue ? '#2D7A52' : '#d1d5db',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                cursor: newFieldKey && newFieldValue ? 'pointer' : 'not-allowed',
                fontSize: '13px'
              }}
            >
              Add
            </button>
            <button
              onClick={() => {
                setShowAddFieldForm(false);
                setNewFieldKey('');
                setNewFieldValue('');
              }}
              style={{
                padding: '8px 12px',
                background: '#f3f4f6',
                color: '#374151',
                border: '1px solid #d1d5db',
                borderRadius: '6px',
                cursor: 'pointer',
                fontSize: '13px'
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      <div className={gridClassName}>
        {/* Existing fields */}
        {Object.entries(selectedItem.fields || {}).map(([fieldName, fieldData]) => {
          const isDeleted = deletedFields.has(fieldName);
          const isRenamed = fieldName in renamedFields;
          const effectiveKey = getEffectiveFieldKey(fieldName);
          const confidence = fieldData.confidence || 0;
          const value = fieldData.value;
          const isEdited = fieldName in editedFields;

          if (isDeleted) {
            return (
              <div key={fieldName} className="field-row-recon deleted" style={{ opacity: 0.5, background: '#fee2e2', borderRadius: '6px' }}>
                <div className="field-header-recon" style={{ textDecoration: 'line-through' }}>
                  <span className="field-name">{formatFieldName(fieldName)}</span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span style={{ color: '#991b1b', fontSize: '12px' }}>Deleted</span>
                  <button
                    onClick={() => handleFieldRestore(fieldName)}
                    style={{
                      padding: '4px 8px',
                      fontSize: '11px',
                      background: '#f3f4f6',
                      border: '1px solid #d1d5db',
                      borderRadius: '4px',
                      cursor: 'pointer'
                    }}
                  >
                    Restore
                  </button>
                </div>
              </div>
            );
          }

          return (
            <div key={fieldName} className={`field-row-recon ${isRenamed ? 'renamed' : ''}`}>
              <div className="field-header-recon" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                {editingFieldKey === fieldName ? (
                  <select
                    value={effectiveKey}
                    onChange={(e) => handleFieldRename(fieldName, e.target.value)}
                    onBlur={() => setEditingFieldKey(null)}
                    autoFocus
                    style={{
                      padding: '4px 8px',
                      fontSize: '12px',
                      borderRadius: '4px',
                      border: '1px solid #3b82f6',
                      minWidth: '140px'
                    }}
                  >
                    <option value={fieldName}>{formatFieldName(fieldName)}</option>
                    {FIELD_TYPE_OPTIONS
                      .filter(opt => opt.value !== fieldName)
                      .map(opt => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
                      ))}
                  </select>
                ) : (
                  <span
                    className="field-name"
                    onClick={() => setEditingFieldKey(fieldName)}
                    style={{ cursor: 'pointer', borderBottom: '1px dashed #9ca3af' }}
                    title="Click to change field type"
                  >
                    {formatFieldName(effectiveKey)}
                  </span>
                )}
                {isRenamed && (
                  <span style={{
                    fontSize: '10px',
                    color: '#2563eb',
                    background: '#dbeafe',
                    padding: '2px 6px',
                    borderRadius: '4px'
                  }}>
                    was: {formatFieldName(fieldName)}
                    <button
                      onClick={() => handleFieldRenameUndo(fieldName)}
                      style={{ background: 'transparent', border: 'none', cursor: 'pointer', fontSize: '10px', marginLeft: '4px' }}
                    >&times;</button>
                  </span>
                )}
                <span
                  className="field-confidence-badge"
                  style={{
                    backgroundColor: confidence > 0.8 ? '#2D7A52' : confidence > 0.6 ? '#f59e0b' : '#ef4444',
                    color: 'white',
                    marginLeft: 'auto'
                  }}
                >
                  {Math.round(confidence * 100)}%
                </span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <input
                  type="text"
                  className={`field-value-input ${isEdited ? 'edited' : ''}`}
                  value={isEdited ? editedFields[fieldName] : formatDisplayValue(fieldName, value) || ''}
                  onChange={(e) => handleFieldEdit(fieldName, e.target.value)}
                  style={{
                    flex: 1,
                    padding: '8px 10px',
                    border: isEdited ? '2px solid #3b82f6' : '1px solid #e5e7eb',
                    borderRadius: '6px',
                    fontSize: '14px',
                    background: isEdited ? '#eff6ff' : 'white'
                  }}
                />
                <button
                  onClick={() => handleFieldDelete(fieldName)}
                  style={{
                    padding: '6px 10px',
                    background: '#fef2f2',
                    border: '1px solid #fecaca',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    color: '#dc2626',
                    fontSize: '14px'
                  }}
                  title="Delete field"
                >
                  Delete
                </button>
              </div>
            </div>
          );
        })}

        {/* Added fields */}
        {Object.entries(addedFields).map(([fieldKey, fieldData]) => (
          <div key={`added-${fieldKey}`} className="field-row-recon added" style={{ background: '#f0fdf4', borderRadius: '6px' }}>
            <div className="field-header-recon" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="field-name">{formatFieldName(fieldKey)}</span>
              <span style={{
                fontSize: '10px',
                color: '#166534',
                background: '#dcfce7',
                padding: '2px 6px',
                borderRadius: '4px'
              }}>
                NEW
              </span>
              <span
                className="field-confidence-badge"
                style={{ backgroundColor: '#2D7A52', color: 'white', marginLeft: 'auto' }}
              >
                100%
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <input
                type="text"
                value={fieldData.value}
                onChange={(e) => setAddedFields(prev => ({
                  ...prev,
                  [fieldKey]: { ...prev[fieldKey], value: e.target.value }
                }))}
                style={{
                  flex: 1,
                  padding: '8px 10px',
                  border: '2px solid #2D7A52',
                  borderRadius: '6px',
                  fontSize: '14px',
                  background: '#f0fdf4'
                }}
              />
              <button
                onClick={() => handleRemoveAddedField(fieldKey)}
                style={{
                  padding: '6px 10px',
                  background: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: '4px',
                  cursor: 'pointer',
                  color: '#dc2626',
                  fontSize: '14px'
                }}
                title="Remove field"
              >
                Delete
              </button>
            </div>
          </div>
        ))}
      </div>

      {/* Changes summary */}
      {(Object.keys(editedFields).length > 0 || deletedFields.size > 0 || Object.keys(renamedFields).length > 0 || Object.keys(addedFields).length > 0) && (
        <div style={{
          marginTop: '12px',
          padding: '10px',
          background: '#fef3c7',
          border: '1px solid #fcd34d',
          borderRadius: '6px',
          fontSize: '12px',
          color: '#92400e'
        }}>
          <strong>Changes:</strong>{' '}
          {Object.keys(addedFields).length > 0 && `${Object.keys(addedFields).length} added`}
          {Object.keys(addedFields).length > 0 && (Object.keys(editedFields).length > 0 || deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && ', '}
          {Object.keys(editedFields).length > 0 && `${Object.keys(editedFields).length} edited`}
          {Object.keys(editedFields).length > 0 && (deletedFields.size > 0 || Object.keys(renamedFields).length > 0) && ', '}
          {deletedFields.size > 0 && `${deletedFields.size} deleted`}
          {deletedFields.size > 0 && Object.keys(renamedFields).length > 0 && ', '}
          {Object.keys(renamedFields).length > 0 && `${Object.keys(renamedFields).length} renamed`}
        </div>
      )}
    </>
  );
}

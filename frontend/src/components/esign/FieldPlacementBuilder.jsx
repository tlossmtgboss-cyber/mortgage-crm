/**
 * Field Placement Builder
 *
 * Staff-facing component for placing signature fields onto PDFs.
 * Features:
 * - PDF viewer with page navigation
 * - Draggable field overlays
 * - Field palette (signature, initial, date, text, checkbox)
 * - Signer assignment for each field
 */

import React, { useState, useRef, useCallback, useEffect } from 'react';
import { esignApi, FIELD_TYPES, pdfPointsToScreen, pdfSizeToScreen } from '../../services/esignApi';

// Default page dimensions (Letter size in points)
const DEFAULT_PAGE = { width_points: 612, height_points: 792 };

export default function FieldPlacementBuilder({
  envelopeId,
  pdfUrl,
  pageCount = 1,
  pageDimensions = [],
  signers = [],
  initialFields = [],
  onFieldsChange,
  onSave,
  readOnly = false,
}) {
  // State
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom, setZoom] = useState(100);
  const [fields, setFields] = useState(initialFields);
  const [selectedFieldId, setSelectedFieldId] = useState(null);
  const [draggedFieldType, setDraggedFieldType] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const [saving, setSaving] = useState(false);

  // Refs
  const viewerRef = useRef(null);
  const pdfContainerRef = useRef(null);

  // Get page dimensions for current page
  const getPageDimensions = useCallback((pageNum) => {
    return pageDimensions[pageNum - 1] || DEFAULT_PAGE;
  }, [pageDimensions]);

  // Update parent when fields change
  useEffect(() => {
    if (onFieldsChange) {
      onFieldsChange(fields);
    }
  }, [fields, onFieldsChange]);

  // Handle dropping a new field onto the PDF
  const handleDrop = useCallback((e) => {
    e.preventDefault();
    if (!draggedFieldType || readOnly) return;

    const viewerRect = pdfContainerRef.current?.getBoundingClientRect();
    if (!viewerRect) return;

    const pageDims = getPageDimensions(currentPage);
    const fieldConfig = FIELD_TYPES[draggedFieldType];

    // Calculate position relative to viewer
    const dropX = e.clientX - viewerRect.left;
    const dropY = e.clientY - viewerRect.top;

    // Scale to PDF points
    const scaleX = pageDims.width_points / viewerRect.width;
    const scaleY = pageDims.height_points / viewerRect.height;

    const pdfX = dropX * scaleX;
    // Flip Y coordinate (PDF origin is bottom-left)
    const pdfY = pageDims.height_points - (dropY * scaleY);

    // Create new field
    const newField = {
      id: `temp_${Date.now()}`,
      field_type: draggedFieldType,
      page_number: currentPage,
      x_position_points: Math.max(0, pdfX - fieldConfig.widthPoints / 2),
      y_position_points: Math.max(0, pdfY - fieldConfig.heightPoints / 2),
      width_points: fieldConfig.widthPoints,
      height_points: fieldConfig.heightPoints,
      signer_id: signers[0]?.id || null,
      is_required: true,
      tab_order: fields.length,
    };

    setFields([...fields, newField]);
    setSelectedFieldId(newField.id);
    setDraggedFieldType(null);
  }, [draggedFieldType, currentPage, getPageDimensions, fields, signers, readOnly]);

  const handleDragOver = (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  };

  // Handle field movement
  const handleFieldMouseDown = (e, fieldId) => {
    if (readOnly) return;
    e.stopPropagation();
    setSelectedFieldId(fieldId);
    setIsDragging(true);

    const field = fields.find(f => f.id === fieldId);
    if (!field) return;

    const viewerRect = pdfContainerRef.current?.getBoundingClientRect();
    if (!viewerRect) return;

    const pageDims = getPageDimensions(field.page_number);

    const startX = e.clientX;
    const startY = e.clientY;

    const screenPos = pdfPointsToScreen(
      field.x_position_points,
      field.y_position_points,
      viewerRect,
      pageDims,
      zoom
    );

    const handleMouseMove = (moveEvent) => {
      const deltaX = moveEvent.clientX - startX;
      const deltaY = moveEvent.clientY - startY;

      const scaleX = pageDims.width_points / viewerRect.width;
      const scaleY = pageDims.height_points / viewerRect.height;

      const newPdfX = field.x_position_points + (deltaX * scaleX);
      // Note: Y movement is inverted since PDF origin is at bottom
      const newPdfY = field.y_position_points - (deltaY * scaleY);

      setFields(prevFields =>
        prevFields.map(f =>
          f.id === fieldId
            ? {
                ...f,
                x_position_points: Math.max(0, Math.min(newPdfX, pageDims.width_points - f.width_points)),
                y_position_points: Math.max(0, Math.min(newPdfY, pageDims.height_points - f.height_points)),
              }
            : f
        )
      );
    };

    const handleMouseUp = () => {
      setIsDragging(false);
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };

    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
  };

  // Handle field deletion
  const handleDeleteField = (fieldId) => {
    setFields(fields.filter(f => f.id !== fieldId));
    if (selectedFieldId === fieldId) {
      setSelectedFieldId(null);
    }
  };

  // Handle field property changes
  const handleFieldPropertyChange = (fieldId, property, value) => {
    setFields(prevFields =>
      prevFields.map(f =>
        f.id === fieldId ? { ...f, [property]: value } : f
      )
    );
  };

  // Save fields to server
  const handleSave = async () => {
    if (!envelopeId) return;

    setSaving(true);
    try {
      // Convert to API format
      const apiFields = fields.map(f => ({
        field_type: f.field_type,
        page_number: f.page_number,
        x_position_points: f.x_position_points,
        y_position_points: f.y_position_points,
        width_points: f.width_points,
        height_points: f.height_points,
        signer_id: f.signer_id,
        is_required: f.is_required,
        placeholder_text: f.placeholder_text,
        tab_order: f.tab_order,
      }));

      await esignApi.bulkSaveFields(envelopeId, apiFields);

      if (onSave) {
        onSave(fields);
      }
    } catch (error) {
      console.error('Error saving fields:', error);
    } finally {
      setSaving(false);
    }
  };

  // Get fields for current page
  const pageFields = fields.filter(f => f.page_number === currentPage);

  // Get selected field
  const selectedField = fields.find(f => f.id === selectedFieldId);

  return (
    <div style={styles.container}>
      {/* Left: Page Thumbnails */}
      <div style={styles.thumbnailPanel}>
        <div style={styles.panelHeader}>Pages</div>
        <div style={styles.thumbnailList}>
          {Array.from({ length: pageCount }, (_, i) => i + 1).map(pageNum => (
            <div
              key={pageNum}
              style={{
                ...styles.thumbnail,
                ...(pageNum === currentPage ? styles.thumbnailActive : {}),
              }}
              onClick={() => setCurrentPage(pageNum)}
            >
              <div style={styles.thumbnailPage}>{pageNum}</div>
              <div style={styles.thumbnailLabel}>
                {fields.filter(f => f.page_number === pageNum).length} fields
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Center: PDF Viewer */}
      <div style={styles.viewerPanel}>
        {/* Toolbar */}
        <div style={styles.toolbar}>
          <div style={styles.toolbarLeft}>
            <button
              style={styles.toolbarBtn}
              onClick={() => setCurrentPage(Math.max(1, currentPage - 1))}
              disabled={currentPage === 1}
            >
              Prev
            </button>
            <span style={styles.pageInfo}>
              Page {currentPage} of {pageCount}
            </span>
            <button
              style={styles.toolbarBtn}
              onClick={() => setCurrentPage(Math.min(pageCount, currentPage + 1))}
              disabled={currentPage === pageCount}
            >
              Next
            </button>
          </div>
          <div style={styles.toolbarRight}>
            <select
              style={styles.zoomSelect}
              value={zoom}
              onChange={(e) => setZoom(Number(e.target.value))}
            >
              <option value={50}>50%</option>
              <option value={75}>75%</option>
              <option value={100}>100%</option>
              <option value={125}>125%</option>
              <option value={150}>150%</option>
            </select>
            {!readOnly && (
              <button
                style={styles.saveBtn}
                onClick={handleSave}
                disabled={saving}
              >
                {saving ? 'Saving...' : 'Save Fields'}
              </button>
            )}
          </div>
        </div>

        {/* PDF Container */}
        <div
          ref={viewerRef}
          style={styles.viewerContainer}
        >
          <div
            ref={pdfContainerRef}
            style={{
              ...styles.pdfContainer,
              transform: `scale(${zoom / 100})`,
              transformOrigin: 'top left',
            }}
            onDrop={handleDrop}
            onDragOver={handleDragOver}
            onClick={() => setSelectedFieldId(null)}
          >
            {/* PDF iframe or embed */}
            {pdfUrl ? (
              <iframe
                src={`${pdfUrl}#page=${currentPage}&toolbar=0`}
                style={styles.pdfFrame}
                title="PDF Document"
              />
            ) : (
              <div style={styles.pdfPlaceholder}>
                <p>PDF Preview</p>
                <p style={{ fontSize: '12px', color: '#666' }}>
                  Page {currentPage} - {getPageDimensions(currentPage).width_points} x {getPageDimensions(currentPage).height_points} pts
                </p>
              </div>
            )}

            {/* Field overlays */}
            {pageFields.map(field => {
              const pageDims = getPageDimensions(currentPage);
              const viewerRect = pdfContainerRef.current?.getBoundingClientRect() || { width: 612, height: 792 };

              // Convert PDF points to screen position
              const scaleX = viewerRect.width / pageDims.width_points;
              const scaleY = viewerRect.height / pageDims.height_points;

              const screenX = field.x_position_points * scaleX;
              // Flip Y and offset by height
              const screenY = (pageDims.height_points - field.y_position_points - field.height_points) * scaleY;
              const screenWidth = field.width_points * scaleX;
              const screenHeight = field.height_points * scaleY;

              const fieldConfig = FIELD_TYPES[field.field_type] || FIELD_TYPES.text;
              const isSelected = field.id === selectedFieldId;
              const signer = signers.find(s => s.id === field.signer_id);

              return (
                <div
                  key={field.id}
                  style={{
                    ...styles.fieldOverlay,
                    left: screenX,
                    top: screenY,
                    width: screenWidth,
                    height: screenHeight,
                    borderColor: fieldConfig.color,
                    backgroundColor: isSelected ? `${fieldConfig.color}30` : `${fieldConfig.color}15`,
                    boxShadow: isSelected ? `0 0 0 2px ${fieldConfig.color}` : 'none',
                    cursor: readOnly ? 'default' : 'move',
                  }}
                  onMouseDown={(e) => handleFieldMouseDown(e, field.id)}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedFieldId(field.id);
                  }}
                >
                  <div style={styles.fieldLabel}>
                    {fieldConfig.label}
                    {signer && <span style={styles.signerBadge}>{signer.name?.split(' ')[0]}</span>}
                  </div>
                  {!readOnly && isSelected && (
                    <button
                      style={styles.deleteBtn}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDeleteField(field.id);
                      }}
                    >
                      X
                    </button>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Right: Field Palette & Properties */}
      <div style={styles.propertiesPanel}>
        {/* Field Palette */}
        {!readOnly && (
          <>
            <div style={styles.panelHeader}>Add Fields</div>
            <div style={styles.fieldPalette}>
              {Object.entries(FIELD_TYPES).map(([type, config]) => (
                <div
                  key={type}
                  style={{
                    ...styles.paletteItem,
                    borderColor: config.color,
                  }}
                  draggable
                  onDragStart={() => setDraggedFieldType(type)}
                  onDragEnd={() => setDraggedFieldType(null)}
                >
                  <span style={{ color: config.color, fontWeight: 'bold' }}>
                    {config.label}
                  </span>
                </div>
              ))}
            </div>
          </>
        )}

        {/* Field Properties */}
        {selectedField && (
          <>
            <div style={styles.panelHeader}>Field Properties</div>
            <div style={styles.properties}>
              <div style={styles.propertyRow}>
                <label>Type</label>
                <span>{FIELD_TYPES[selectedField.field_type]?.label || selectedField.field_type}</span>
              </div>

              <div style={styles.propertyRow}>
                <label>Assigned To</label>
                <select
                  style={styles.propertySelect}
                  value={selectedField.signer_id || ''}
                  onChange={(e) => handleFieldPropertyChange(selectedField.id, 'signer_id', e.target.value ? Number(e.target.value) : null)}
                  disabled={readOnly}
                >
                  <option value="">Select Signer</option>
                  {signers.map(s => (
                    <option key={s.id} value={s.id}>{s.name} ({s.email})</option>
                  ))}
                </select>
              </div>

              <div style={styles.propertyRow}>
                <label>Required</label>
                <input
                  type="checkbox"
                  checked={selectedField.is_required}
                  onChange={(e) => handleFieldPropertyChange(selectedField.id, 'is_required', e.target.checked)}
                  disabled={readOnly}
                />
              </div>

              <div style={styles.propertyRow}>
                <label>Position</label>
                <span style={{ fontSize: '12px' }}>
                  X: {Math.round(selectedField.x_position_points)} pts<br />
                  Y: {Math.round(selectedField.y_position_points)} pts
                </span>
              </div>

              <div style={styles.propertyRow}>
                <label>Size</label>
                <span style={{ fontSize: '12px' }}>
                  W: {Math.round(selectedField.width_points)} pts<br />
                  H: {Math.round(selectedField.height_points)} pts
                </span>
              </div>

              {!readOnly && (
                <button
                  style={styles.deleteFieldBtn}
                  onClick={() => handleDeleteField(selectedField.id)}
                >
                  Delete Field
                </button>
              )}
            </div>
          </>
        )}

        {/* Summary */}
        <div style={styles.panelHeader}>Summary</div>
        <div style={styles.summary}>
          <div>Total Fields: {fields.length}</div>
          <div>Signers: {signers.length}</div>
          {signers.map(signer => (
            <div key={signer.id} style={styles.signerSummary}>
              {signer.name}: {fields.filter(f => f.signer_id === signer.id).length} fields
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// Styles
const styles = {
  container: {
    display: 'flex',
    height: '100%',
    minHeight: '600px',
    backgroundColor: '#f5f5f5',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
  },
  thumbnailPanel: {
    width: '120px',
    backgroundColor: '#fff',
    borderRight: '1px solid #e0e0e0',
    display: 'flex',
    flexDirection: 'column',
  },
  panelHeader: {
    padding: '12px',
    fontWeight: '600',
    fontSize: '14px',
    borderBottom: '1px solid #e0e0e0',
    backgroundColor: '#fafafa',
  },
  thumbnailList: {
    flex: 1,
    overflowY: 'auto',
    padding: '8px',
  },
  thumbnail: {
    padding: '8px',
    marginBottom: '8px',
    borderRadius: '4px',
    border: '2px solid transparent',
    cursor: 'pointer',
    textAlign: 'center',
    backgroundColor: '#f5f5f5',
  },
  thumbnailActive: {
    borderColor: '#1a73e8',
    backgroundColor: '#e8f0fe',
  },
  thumbnailPage: {
    fontWeight: 'bold',
    fontSize: '18px',
  },
  thumbnailLabel: {
    fontSize: '10px',
    color: '#666',
  },
  viewerPanel: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
  },
  toolbar: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '8px 16px',
    backgroundColor: '#fff',
    borderBottom: '1px solid #e0e0e0',
  },
  toolbarLeft: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  toolbarRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '12px',
  },
  toolbarBtn: {
    padding: '6px 12px',
    borderRadius: '4px',
    border: '1px solid #ccc',
    backgroundColor: '#fff',
    cursor: 'pointer',
  },
  pageInfo: {
    fontSize: '14px',
  },
  zoomSelect: {
    padding: '6px 8px',
    borderRadius: '4px',
    border: '1px solid #ccc',
  },
  saveBtn: {
    padding: '8px 16px',
    borderRadius: '4px',
    border: 'none',
    backgroundColor: '#1a73e8',
    color: '#fff',
    fontWeight: '500',
    cursor: 'pointer',
  },
  viewerContainer: {
    flex: 1,
    overflow: 'auto',
    backgroundColor: '#e0e0e0',
    padding: '20px',
  },
  pdfContainer: {
    position: 'relative',
    width: '612px',
    height: '792px',
    backgroundColor: '#fff',
    boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
    margin: '0 auto',
  },
  pdfFrame: {
    width: '100%',
    height: '100%',
    border: 'none',
  },
  pdfPlaceholder: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    height: '100%',
    color: '#999',
    fontSize: '18px',
  },
  fieldOverlay: {
    position: 'absolute',
    border: '2px dashed',
    borderRadius: '4px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    fontSize: '11px',
    userSelect: 'none',
  },
  fieldLabel: {
    display: 'flex',
    alignItems: 'center',
    gap: '4px',
    padding: '2px 4px',
    backgroundColor: 'rgba(255,255,255,0.8)',
    borderRadius: '2px',
    fontSize: '10px',
    fontWeight: '500',
  },
  signerBadge: {
    padding: '1px 4px',
    backgroundColor: '#333',
    color: '#fff',
    borderRadius: '2px',
    fontSize: '9px',
  },
  deleteBtn: {
    position: 'absolute',
    top: '-10px',
    right: '-10px',
    width: '20px',
    height: '20px',
    borderRadius: '50%',
    border: 'none',
    backgroundColor: '#d32f2f',
    color: '#fff',
    fontSize: '12px',
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
  },
  propertiesPanel: {
    width: '280px',
    backgroundColor: '#fff',
    borderLeft: '1px solid #e0e0e0',
    display: 'flex',
    flexDirection: 'column',
  },
  fieldPalette: {
    padding: '12px',
    display: 'flex',
    flexDirection: 'column',
    gap: '8px',
    borderBottom: '1px solid #e0e0e0',
  },
  paletteItem: {
    padding: '10px 12px',
    border: '2px dashed',
    borderRadius: '4px',
    cursor: 'grab',
    textAlign: 'center',
    backgroundColor: '#fafafa',
    transition: 'background-color 0.15s',
  },
  properties: {
    padding: '12px',
    borderBottom: '1px solid #e0e0e0',
  },
  propertyRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: '12px',
    fontSize: '13px',
  },
  propertySelect: {
    padding: '4px 8px',
    borderRadius: '4px',
    border: '1px solid #ccc',
    fontSize: '12px',
    maxWidth: '160px',
  },
  deleteFieldBtn: {
    width: '100%',
    padding: '8px',
    marginTop: '8px',
    borderRadius: '4px',
    border: 'none',
    backgroundColor: '#d32f2f',
    color: '#fff',
    cursor: 'pointer',
  },
  summary: {
    padding: '12px',
    fontSize: '13px',
  },
  signerSummary: {
    marginTop: '4px',
    paddingLeft: '12px',
    fontSize: '12px',
    color: '#666',
  },
};

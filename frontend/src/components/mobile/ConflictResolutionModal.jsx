/**
 * ConflictResolutionModal
 *
 * Bottom-sheet style modal for resolving offline mutation conflicts.
 * When the user makes changes while offline and the server state has diverged,
 * this UI shows a side-by-side comparison and lets the user choose:
 *   - Keep Mine  (force-push local changes)
 *   - Keep Theirs (discard local changes)
 *   - Merge (field-by-field cherry-pick)
 *
 * Also supports batch actions for resolving all conflicts at once.
 */

import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  getUnresolvedConflicts,
  resolveConflict,
  resolveAllConflicts,
  onConflictsChanged,
  getFieldLabel,
  formatFieldValue,
  ENTITY_TYPE_LABELS,
} from '../../services/conflictResolver';
import { toast } from '../../utils/toast';
import './ConflictResolutionModal.css';

// ============================================================================
// CONFLICT BADGE (for embedding in toolbar / sync status area)
// ============================================================================

export function ConflictBadge({ onClick }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    // Initial count
    setCount(getUnresolvedConflicts().length);

    // Subscribe to changes
    const unsubscribe = onConflictsChanged((conflicts) => {
      setCount(conflicts.filter((c) => c.status === 'unresolved').length);
    });

    return unsubscribe;
  }, []);

  if (count === 0) return null;

  return (
    <button
      className="conflict-badge"
      onClick={onClick}
      aria-label={`${count} sync conflict${count !== 1 ? 's' : ''} to resolve`}
      title={`${count} conflict${count !== 1 ? 's' : ''}`}
    >
      <span className={`conflict-badge-icon has-conflicts`}>&#x26A0;</span>
      <span className="conflict-badge-count">{count > 9 ? '9+' : count}</span>
    </button>
  );
}

// ============================================================================
// SINGLE CONFLICT CARD
// ============================================================================

function ConflictCard({ conflict, onResolve }) {
  const [mergeMode, setMergeMode] = useState(false);
  const [mergeSelections, setMergeSelections] = useState({});

  const isResolved = conflict.status === 'resolved';

  // Initialize merge selections: default to local values
  useEffect(() => {
    const initial = {};
    conflict.conflictFields.forEach((field) => {
      initial[field] = 'local';
    });
    setMergeSelections(initial);
  }, [conflict.conflictFields]);

  const handleKeepMine = useCallback(() => {
    onResolve(conflict.id, 'keep_local');
  }, [conflict.id, onResolve]);

  const handleKeepTheirs = useCallback(() => {
    onResolve(conflict.id, 'keep_server');
  }, [conflict.id, onResolve]);

  const handleMergeToggle = useCallback(() => {
    setMergeMode((prev) => !prev);
  }, []);

  const handleMergeSelection = useCallback((field, source) => {
    setMergeSelections((prev) => ({ ...prev, [field]: source }));
  }, []);

  const handleApplyMerge = useCallback(() => {
    // Build merged fields from selections
    const mergedFields = {};
    conflict.conflictFields.forEach((field) => {
      const source = mergeSelections[field] || 'local';
      mergedFields[field] = source === 'local'
        ? conflict.localChanges[field]
        : conflict.serverState[field];
    });
    onResolve(conflict.id, 'merge', mergedFields);
    setMergeMode(false);
  }, [conflict, mergeSelections, onResolve]);

  const timeAgo = formatTimeAgo(conflict.createdAt);

  return (
    <div className={`conflict-card ${isResolved ? 'resolved' : ''}`}>
      {/* Card header */}
      <div className="conflict-card-header">
        <div className="conflict-entity-info">
          <span className={`conflict-entity-badge ${conflict.entityType}`}>
            {ENTITY_TYPE_LABELS[conflict.entityType] || conflict.entityType}
          </span>
          <span className="conflict-entity-label">{conflict.entityLabel}</span>
        </div>
        <span className="conflict-time">{timeAgo}</span>
      </div>

      {/* Side-by-side comparison */}
      <div className="conflict-comparison">
        {/* Local (Your changes) */}
        <div className="conflict-side local">
          <div className="conflict-side-label">
            <span>&#x270E;</span> Your Changes
          </div>
          {conflict.conflictFields.map((field) => (
            <div key={field} className="conflict-field-row">
              <span className="conflict-field-name">{getFieldLabel(field)}</span>
              <span className={`conflict-field-value changed ${
                conflict.localChanges[field] == null ? 'empty' : ''
              }`}>
                {formatFieldValue(conflict.localChanges[field], field)}
              </span>
            </div>
          ))}
        </div>

        {/* Server (Current version) */}
        <div className="conflict-side server">
          <div className="conflict-side-label">
            <span>&#x2601;</span> Current Version
          </div>
          {conflict.conflictFields.map((field) => (
            <div key={field} className="conflict-field-row">
              <span className="conflict-field-name">{getFieldLabel(field)}</span>
              <span className={`conflict-field-value changed ${
                conflict.serverState[field] == null ? 'empty' : ''
              }`}>
                {formatFieldValue(conflict.serverState[field], field)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Merge field picker (expanded) */}
      {mergeMode && !isResolved && (
        <div className="conflict-merge-picker">
          <div className="merge-picker-title">Pick a value for each field</div>
          {conflict.conflictFields.map((field) => (
            <div key={field} className="merge-field-row">
              <span className="merge-field-label">{getFieldLabel(field)}</span>
              <button
                className={`merge-option local-opt ${mergeSelections[field] === 'local' ? 'selected' : ''}`}
                onClick={() => handleMergeSelection(field, 'local')}
                type="button"
              >
                {formatFieldValue(conflict.localChanges[field], field)}
              </button>
              <button
                className={`merge-option server-opt ${mergeSelections[field] === 'server' ? 'selected' : ''}`}
                onClick={() => handleMergeSelection(field, 'server')}
                type="button"
              >
                {formatFieldValue(conflict.serverState[field], field)}
              </button>
            </div>
          ))}
          <button
            className="merge-apply-btn"
            onClick={handleApplyMerge}
            type="button"
          >
            Apply Merged Values
          </button>
        </div>
      )}

      {/* Action buttons */}
      {!isResolved && !mergeMode && (
        <div className="conflict-actions">
          <button
            className="conflict-action-btn keep-mine"
            onClick={handleKeepMine}
            type="button"
          >
            Keep Mine
          </button>
          <button
            className="conflict-action-btn keep-theirs"
            onClick={handleKeepTheirs}
            type="button"
          >
            Keep Theirs
          </button>
          <button
            className="conflict-action-btn merge"
            onClick={handleMergeToggle}
            type="button"
          >
            Merge
          </button>
        </div>
      )}

      {/* Resolved indicator */}
      {isResolved && (
        <div className="conflict-resolved-badge">
          &#x2713; Resolved
        </div>
      )}
    </div>
  );
}

// ============================================================================
// MAIN MODAL
// ============================================================================

function ConflictResolutionModal({ isOpen, onClose }) {
  const [conflicts, setConflicts] = useState([]);
  const overlayRef = useRef(null);
  const modalRef = useRef(null);

  // Load and subscribe to conflicts
  useEffect(() => {
    setConflicts(getUnresolvedConflicts());

    const unsubscribe = onConflictsChanged((all) => {
      setConflicts(all.filter((c) => c.status === 'unresolved'));
    });

    return unsubscribe;
  }, []);

  // Focus trap and escape key
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    // Prevent background scroll
    document.body.style.overflow = 'hidden';

    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [isOpen, onClose]);

  // Handle overlay click (close when tapping outside)
  const handleOverlayClick = useCallback((e) => {
    if (e.target === overlayRef.current) {
      onClose();
    }
  }, [onClose]);

  // Handle single conflict resolution
  const handleResolve = useCallback((conflictId, resolution, mergedFields) => {
    try {
      const { conflict } = resolveConflict(conflictId, resolution, mergedFields);
      const label = ENTITY_TYPE_LABELS[conflict.entityType] || conflict.entityType;

      if (resolution === 'keep_local') {
        toast.success(`Kept your changes for ${label}: ${conflict.entityLabel}`);
      } else if (resolution === 'keep_server') {
        toast.info(`Kept server version for ${label}: ${conflict.entityLabel}`);
      } else {
        toast.success(`Merged changes for ${label}: ${conflict.entityLabel}`);
      }

      // If no more conflicts, auto-close after a brief delay
      const remaining = getUnresolvedConflicts();
      if (remaining.length === 0) {
        setTimeout(onClose, 500);
      }
    } catch (err) {
      console.error('Failed to resolve conflict:', err);
      toast.error('Failed to resolve conflict. Please try again.');
    }
  }, [onClose]);

  // Batch: keep all mine
  const handleKeepAllMine = useCallback(() => {
    try {
      const { resolved } = resolveAllConflicts('keep_local');
      toast.success(`Kept your changes for ${resolved.length} conflict${resolved.length !== 1 ? 's' : ''}`);
      setTimeout(onClose, 500);
    } catch (err) {
      console.error('Batch resolve failed:', err);
      toast.error('Failed to resolve conflicts. Please try again.');
    }
  }, [onClose]);

  // Batch: keep all theirs
  const handleKeepAllTheirs = useCallback(() => {
    try {
      const { resolved } = resolveAllConflicts('keep_server');
      toast.info(`Kept server version for ${resolved.length} conflict${resolved.length !== 1 ? 's' : ''}`);
      setTimeout(onClose, 500);
    } catch (err) {
      console.error('Batch resolve failed:', err);
      toast.error('Failed to resolve conflicts. Please try again.');
    }
  }, [onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="conflict-overlay"
      ref={overlayRef}
      onClick={handleOverlayClick}
      role="dialog"
      aria-modal="true"
      aria-label="Resolve sync conflicts"
    >
      <div className="conflict-modal" ref={modalRef}>
        {/* Drag handle (mobile bottom sheet affordance) */}
        <div className="conflict-drag-handle"><span /></div>

        {/* Header */}
        <div className="conflict-header">
          <div className="conflict-header-left">
            <div className="conflict-header-icon">&#x26A0;</div>
            <div>
              <h2>Sync Conflicts</h2>
              <span className="conflict-header-count">
                {conflicts.length} conflict{conflicts.length !== 1 ? 's' : ''} to resolve
              </span>
            </div>
          </div>
          <button
            className="conflict-close-btn"
            onClick={onClose}
            aria-label="Close"
            type="button"
          >
            &#x2715;
          </button>
        </div>

        {/* Warning */}
        <div className="conflict-warning">
          <span className="conflict-warning-icon">&#x1F4F6;</span>
          <span>These changes were made while you were offline. The server has newer data for these records.</span>
        </div>

        {/* Batch actions */}
        {conflicts.length > 1 && (
          <div className="conflict-batch-actions">
            <button
              className="conflict-batch-btn keep-mine"
              onClick={handleKeepAllMine}
              type="button"
            >
              Keep All Mine ({conflicts.length})
            </button>
            <button
              className="conflict-batch-btn keep-theirs"
              onClick={handleKeepAllTheirs}
              type="button"
            >
              Keep All Theirs ({conflicts.length})
            </button>
          </div>
        )}

        {/* Conflict list */}
        <div className="conflict-list">
          {conflicts.length === 0 ? (
            <div className="conflict-empty">
              <div className="conflict-empty-icon">&#x2705;</div>
              <h3>All Synced</h3>
              <p>No conflicts to resolve. Your data is up to date.</p>
            </div>
          ) : (
            conflicts.map((conflict) => (
              <ConflictCard
                key={conflict.id}
                conflict={conflict}
                onResolve={handleResolve}
              />
            ))
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================================
// HELPERS
// ============================================================================

/**
 * Format a timestamp into a human-readable "time ago" string.
 */
function formatTimeAgo(timestamp) {
  const seconds = Math.floor((Date.now() - timestamp) / 1000);

  if (seconds < 60) return 'just now';
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return 'yesterday';
  if (days < 7) return `${days}d ago`;
  return new Date(timestamp).toLocaleDateString('en-US');
}

export default ConflictResolutionModal;

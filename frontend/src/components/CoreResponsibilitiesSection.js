import React, { useState, useEffect } from 'react';
import { DragDropContext, Droppable, Draggable } from 'react-beautiful-dnd';
import ResponsibilityCard from './ResponsibilityCard';
import ResponsibilityModal from './ResponsibilityModal';
import ArchivedResponsibilitiesModal from './ArchivedResponsibilitiesModal';
import responsibilitiesApi from '../services/responsibilitiesApi';
import './CoreResponsibilitiesSection.css';
import { toast } from '../utils/toast';

/**
 * CoreResponsibilitiesSection - Main component for Tab 2, Section B
 *
 * Features:
 * - Display all active responsibilities with drag-and-drop reordering
 * - Time allocation tracking with visual warnings (over 100%, under 80%)
 * - CRUD operations (Create, Read, Update, Archive, Restore)
 * - Skills library management
 * - Empty state, loading state, error handling
 */

function CoreResponsibilitiesSection({ userId, userEmail }) {
  // State management
  const [responsibilities, setResponsibilities] = useState([]);
  const [archivedResponsibilities, setArchivedResponsibilities] = useState([]);
  const [availableSkills, setAvailableSkills] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [totalAllocation, setTotalAllocation] = useState(0);

  // Modal states
  const [showAddModal, setShowAddModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [showArchivedModal, setShowArchivedModal] = useState(false);
  const [editingResponsibility, setEditingResponsibility] = useState(null);

  // Action states
  const [saving, setSaving] = useState(false);
  const [archiving, setArchiving] = useState(false);
  const [restoring, setRestoring] = useState(false);

  // Load initial data
  useEffect(() => {
    loadAllData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  // Calculate total time allocation whenever responsibilities change
  useEffect(() => {
    const total = responsibilities.reduce((sum, resp) => sum + (resp.time_allocation || 0), 0);
    setTotalAllocation(total);
  }, [responsibilities]);

  const loadAllData = async () => {
    try {
      setLoading(true);
      setError(null);

      // Load all data in parallel using API service
      const [responsibilitiesData, archivedData, skillsData] = await Promise.all([
        responsibilitiesApi.fetchResponsibilities(userId),
        responsibilitiesApi.fetchArchivedResponsibilities(userId),
        responsibilitiesApi.fetchSkillsLibrary()
      ]);

      setResponsibilities(responsibilitiesData);
      setArchivedResponsibilities(archivedData);
      setAvailableSkills(skillsData);
    } catch (err) {
      console.error('Error loading data:', err);
      setError(err.message || 'Failed to load responsibilities');
    } finally {
      setLoading(false);
    }
  };

  const addSkillToLibrary = async (skillData) => {
    const newSkill = await responsibilitiesApi.addSkillToLibrary(skillData);
    setAvailableSkills(prev => [...prev, newSkill]);
    return newSkill;
  };

  // Event handlers
  const handleDragEnd = async (result) => {
    if (!result.destination) return;

    const { source, destination } = result;
    if (source.index === destination.index) return;

    // Optimistic update
    const reordered = Array.from(responsibilities);
    const [moved] = reordered.splice(source.index, 1);
    reordered.splice(destination.index, 0, moved);
    setResponsibilities(reordered);

    try {
      // Send new order to backend using API service
      const orderedIds = reordered.map(r => r.id);
      await responsibilitiesApi.reorderResponsibilities(userId, orderedIds);
    } catch (err) {
      console.error('Error reordering responsibilities:', err);
      // Rollback on error
      loadAllData();
      toast.error('Failed to reorder responsibilities. Please try again.');
    }
  };

  const handleSaveResponsibility = async (formData) => {
    try {
      setSaving(true);

      if (editingResponsibility) {
        // Update existing using API service
        const updated = await responsibilitiesApi.updateResponsibility(userId, editingResponsibility.id, formData);
        setResponsibilities(prev =>
          prev.map(r => r.id === updated.id ? updated : r)
        );
      } else {
        // Create new using API service
        const created = await responsibilitiesApi.createResponsibility(userId, formData);
        setResponsibilities(prev => [...prev, created]);
      }

      setShowAddModal(false);
      setShowEditModal(false);
      setEditingResponsibility(null);
    } catch (err) {
      console.error('Error saving responsibility:', err);
      throw err; // Let modal handle error display
    } finally {
      setSaving(false);
    }
  };

  const handleEditResponsibility = (responsibility) => {
    setEditingResponsibility(responsibility);
    setShowEditModal(true);
  };

  const handleArchiveResponsibility = async (respId) => {
    const responsibility = responsibilities.find(r => r.id === respId);
    if (!window.confirm(`Archive "${responsibility.title}"? You can restore it later from archived items.`)) {
      return;
    }

    try {
      setArchiving(true);
      const archived = await responsibilitiesApi.archiveResponsibility(userId, respId);

      // Remove from active list and add to archived list
      setResponsibilities(prev => prev.filter(r => r.id !== respId));
      setArchivedResponsibilities(prev => [...prev, archived]);
    } catch (err) {
      console.error('Error archiving responsibility:', err);
      toast.error('Failed to archive responsibility. Please try again.');
    } finally {
      setArchiving(false);
    }
  };

  const handleRestoreResponsibility = async (respId) => {
    try {
      setRestoring(true);
      const restored = await responsibilitiesApi.restoreResponsibility(userId, respId);

      // Remove from archived list and add to active list
      setArchivedResponsibilities(prev => prev.filter(r => r.id !== respId));
      setResponsibilities(prev => [...prev, restored]);
    } catch (err) {
      console.error('Error restoring responsibility:', err);
      toast.error('Failed to restore responsibility. Please try again.');
    } finally {
      setRestoring(false);
    }
  };

  const handleCloseModal = () => {
    setShowAddModal(false);
    setShowEditModal(false);
    setEditingResponsibility(null);
  };

  // Render functions
  const renderTimeAllocationSummary = () => {
    const percentage = totalAllocation;
    let statusClass = 'allocation-normal';
    let statusMessage = 'Balanced workload';
    let statusIcon = '✓';

    if (percentage > 100) {
      statusClass = 'allocation-over';
      statusMessage = `Over-allocated by ${percentage - 100}%`;
      statusIcon = '⚠️';
    } else if (percentage < 80 && responsibilities.length > 0) {
      statusClass = 'allocation-under';
      statusMessage = `Under-utilized: ${100 - percentage}% capacity available`;
      statusIcon = 'ℹ️';
    }

    return (
      <div className={`allocation-summary ${statusClass}`}>
        <div className="allocation-header">
          <h4>Time Allocation Summary</h4>
          <span className="allocation-percentage">
            {statusIcon} {percentage}% of capacity
          </span>
        </div>
        <div className="allocation-bar">
          <div
            className="allocation-fill"
            style={{ width: `${Math.min(percentage, 100)}%` }}
          />
          {percentage > 100 && (
            <div
              className="allocation-overflow"
              style={{ width: `${Math.min(percentage - 100, 100)}%` }}
            />
          )}
        </div>
        <p className="allocation-message">{statusMessage}</p>
      </div>
    );
  };

  // Loading state
  if (loading) {
    return (
      <div className="core-responsibilities-section">
        <div className="loading-state">
          <div className="spinner" />
          <p>Loading responsibilities...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (error) {
    return (
      <div className="core-responsibilities-section">
        <div className="error-state">
          <span className="error-icon">⚠️</span>
          <h3>Error Loading Responsibilities</h3>
          <p>{error}</p>
          <button onClick={loadAllData} className="btn-retry">
            Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="core-responsibilities-section">
      {/* Section Header */}
      <div className="section-header">
        <div className="header-content">
          <h3>Core Responsibilities</h3>
          <p className="section-description">
            Define and manage this team member's primary responsibilities, time allocation, and required skills.
          </p>
        </div>
        <div className="header-actions">
          <button
            onClick={() => setShowArchivedModal(true)}
            className="btn-view-archived"
            disabled={archivedResponsibilities.length === 0}
          >
            🗄️ View Archived ({archivedResponsibilities.length})
          </button>
          <button onClick={() => setShowAddModal(true)} className="btn-add-responsibility">
            + Add Responsibility
          </button>
        </div>
      </div>

      {/* Time Allocation Summary */}
      {responsibilities.length > 0 && renderTimeAllocationSummary()}

      {/* Responsibilities List */}
      {responsibilities.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📋</div>
          <h4>No Responsibilities Defined</h4>
          <p>Start by adding this team member's core responsibilities and duties.</p>
          <button onClick={() => setShowAddModal(true)} className="btn-add-first">
            + Add First Responsibility
          </button>
        </div>
      ) : (
        <DragDropContext onDragEnd={handleDragEnd}>
          <Droppable droppableId="responsibilities">
            {(provided, snapshot) => (
              <div
                {...provided.droppableProps}
                ref={provided.innerRef}
                className={`responsibilities-list ${snapshot.isDraggingOver ? 'dragging-over' : ''}`}
              >
                {responsibilities.map((responsibility, index) => (
                  <Draggable
                    key={responsibility.id}
                    draggableId={String(responsibility.id)}
                    index={index}
                  >
                    {(provided, snapshot) => (
                      <ResponsibilityCard
                        responsibility={responsibility}
                        provided={provided}
                        snapshot={snapshot}
                        onEdit={() => handleEditResponsibility(responsibility)}
                        onArchive={() => handleArchiveResponsibility(responsibility.id)}
                      />
                    )}
                  </Draggable>
                ))}
                {provided.placeholder}
              </div>
            )}
          </Droppable>
        </DragDropContext>
      )}

      {/* Add/Edit Modal */}
      {(showAddModal || showEditModal) && (
        <ResponsibilityModal
          responsibility={editingResponsibility}
          onSave={handleSaveResponsibility}
          onClose={handleCloseModal}
          availableSkills={availableSkills}
          onAddSkill={addSkillToLibrary}
        />
      )}

      {/* Archived Modal */}
      {showArchivedModal && (
        <ArchivedResponsibilitiesModal
          archivedResponsibilities={archivedResponsibilities}
          onRestore={handleRestoreResponsibility}
          onClose={() => setShowArchivedModal(false)}
          isRestoring={restoring}
        />
      )}
    </div>
  );
}

export default CoreResponsibilitiesSection;

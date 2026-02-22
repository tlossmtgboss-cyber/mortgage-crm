import React, { useState, useEffect } from 'react';
import goalsApi from '../services/goalsApi';
import GoalCard from './GoalCard';
import GoalModal from './GoalModal';
import './GoalsOKRsSection.css';
import { toast } from '../utils/toast';

const GoalsOKRsSection = ({ userId, isManager = true }) => {
  const [goals, setGoals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterPeriod, setFilterPeriod] = useState('current');
  const [filterStatus, setFilterStatus] = useState('all');
  const [error, setError] = useState(null);

  const [showModal, setShowModal] = useState(false);
  const [editingGoal, setEditingGoal] = useState(null);

  useEffect(() => {
    loadGoals();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId, filterPeriod, filterStatus]);

  const loadGoals = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await goalsApi.getUserGoals(userId, {
        period: filterPeriod !== 'all' ? filterPeriod : undefined,
        status: filterStatus !== 'all' ? filterStatus : undefined
      });
      setGoals(response.goals || []);
    } catch (err) {
      console.error('Error loading goals:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const openAddModal = () => {
    setEditingGoal(null);
    setShowModal(true);
  };

  const openEditModal = (goal) => {
    setEditingGoal(goal);
    setShowModal(true);
  };

  const handleSave = async (goalData) => {
    try {
      if (editingGoal) {
        await goalsApi.updateGoal(userId, editingGoal.id, goalData);
      } else {
        await goalsApi.createGoal(userId, goalData);
      }
      await loadGoals();
      setShowModal(false);
    } catch (err) {
      console.error('Error saving goal:', err);
      throw err;
    }
  };

  const handleDelete = async (goalId) => {
    try {
      await goalsApi.deleteGoal(userId, goalId);
      await loadGoals();
    } catch (err) {
      console.error('Error deleting goal:', err);
      toast.error('Failed to delete goal');
    }
  };

  const handleKeyResultUpdate = async (goalId, krId, currentValue) => {
    try {
      await goalsApi.updateKeyResult(userId, goalId, krId, { current: currentValue });
      await loadGoals();
    } catch (err) {
      console.error('Error updating key result:', err);
    }
  };

  if (loading) {
    return <div className="loading-state">Loading goals...</div>;
  }

  if (error) {
    return (
      <div className="error-state">
        <p>Error loading goals: {error}</p>
        <button onClick={loadGoals} className="btn-secondary">Retry</button>
      </div>
    );
  }

  return (
    <div className="goals-okrs-section">
      {/* Header */}
      <div className="section-header">
        <div className="header-content">
          <h3>Goals & OKRs</h3>
          <p className="section-description">
            Set objectives and track key results with employee and manager assessments.
          </p>
        </div>
        {isManager && (
          <button onClick={openAddModal} className="btn-primary">
            + Add Goal
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="filters-bar">
        <div className="filter-group">
          <label>Period:</label>
          <select value={filterPeriod} onChange={(e) => setFilterPeriod(e.target.value)}>
            <option value="current">Current</option>
            <option value="q4_2025">Q4 2025</option>
            <option value="q3_2025">Q3 2025</option>
            <option value="2025">All 2025</option>
            <option value="all">All Time</option>
          </select>
        </div>
        <div className="filter-group">
          <label>Status:</label>
          <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
            <option value="all">All</option>
            <option value="active">Active</option>
            <option value="completed">Completed</option>
          </select>
        </div>
      </div>

      {/* Goals List */}
      {goals.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">🎯</div>
          <h4>No goals defined yet</h4>
          <p>
            Set goals with measurable key results to track progress and performance.
          </p>
          {isManager && (
            <button onClick={openAddModal} className="btn-primary">
              Add First Goal
            </button>
          )}
        </div>
      ) : (
        <div className="goals-list">
          {goals.map(goal => (
            <GoalCard
              key={goal.id}
              goal={goal}
              userId={userId}
              isManager={isManager}
              onEdit={() => openEditModal(goal)}
              onDelete={() => handleDelete(goal.id)}
              onKeyResultUpdate={(krId, value) => handleKeyResultUpdate(goal.id, krId, value)}
              onRefresh={loadGoals}
            />
          ))}
        </div>
      )}

      {/* Modal */}
      {showModal && (
        <GoalModal
          goal={editingGoal}
          userId={userId}
          onSave={handleSave}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
};

export default GoalsOKRsSection;

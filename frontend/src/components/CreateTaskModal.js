import React, { useState } from 'react';
import { api } from '../utils/api/client';
import './CreateTaskModal.css';
import { toast } from '../utils/toast';

function CreateTaskModal({ isOpen, onClose, lead, onTaskCreated }) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [priority, setPriority] = useState('medium');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!title.trim()) {
      setError('Please enter a task title');
      return;
    }

    setIsSubmitting(true);
    setError('');

    try {
      const taskData = {
        title: title.trim(),
        description: description.trim() || null,
        priority,
        lead_id: lead?.id || null,
      };

      // Only include due_date if provided (backend expects datetime format)
      if (dueDate) {
        taskData.due_date = new Date(dueDate).toISOString();
      }

      const data = await api.post('/api/v1/tasks', taskData);

      // Reset form
      setTitle('');
      setDescription('');
      setDueDate('');
      setPriority('medium');

      if (onTaskCreated) {
        onTaskCreated(data);
      }

      toast.success('Task created successfully!');
      onClose();
    } catch (err) {
      console.error('Error creating task:', err);
      const errorMessage = err.message || 'Failed to create task. Please try again.';
      setError(errorMessage);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content task-modal-content" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Create Task</h2>
          <button className="close-button" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit} className="task-modal-form">
          {lead && (
            <div className="lead-info">
              <strong>For:</strong> {lead.name || lead.first_name || 'Unknown'}
              {lead.loan_number && <span> | Loan #{lead.loan_number}</span>}
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Task Title *</label>
            <input
              type="text"
              className="form-input"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="e.g., Follow up on application"
              required
            />
          </div>

          <div className="form-group">
            <label className="form-label">Description</label>
            <textarea
              className="form-textarea"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Add details about the task..."
              rows="3"
            />
          </div>

          <div className="form-row">
            <div className="form-group">
              <label className="form-label">Due Date</label>
              <input
                type="date"
                className="form-input"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Priority</label>
              <select
                className="form-select"
                value={priority}
                onChange={(e) => setPriority(e.target.value)}
              >
                <option value="low">Low</option>
                <option value="medium">Medium</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>
          </div>

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <div className="modal-actions">
            <button
              type="button"
              className="cancel-button"
              onClick={onClose}
              disabled={isSubmitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="submit-button"
              disabled={isSubmitting || !title.trim()}
            >
              {isSubmitting ? 'Creating...' : 'Create Task'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default CreateTaskModal;

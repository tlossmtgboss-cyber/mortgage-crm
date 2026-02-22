import React, { useState, useEffect } from 'react';
import responsibilitiesApi from '../services/responsibilitiesApi';
import './SkillModal.css';
import { toast } from '../utils/toast';

const AddSkillModal = ({ userId, onSave, onClose }) => {
  const [availableSkills, setAvailableSkills] = useState([]);
  const [selectedSkillId, setSelectedSkillId] = useState('');
  const [requiredProficiency, setRequiredProficiency] = useState(3);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadAvailableSkills();
  }, []);

  const loadAvailableSkills = async () => {
    try {
      setLoading(true);
      // Get all skills from library
      const response = await responsibilitiesApi.fetchSkillsLibrary();
      setAvailableSkills(response.skills || []);
    } catch (err) {
      console.error('Error loading skills:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!selectedSkillId) {
      toast.error('Please select a skill');
      return;
    }

    setSaving(true);
    try {
      await onSave({
        skill_id: parseInt(selectedSkillId),
        required_proficiency: requiredProficiency
      });
    } catch (err) {
      toast.error('Failed to add skill');
      console.error(err);
    } finally {
      setSaving(false);
    }
  };

  const getProficiencyLabel = (level) => {
    const labels = {
      1: 'Basic',
      2: 'Developing',
      3: 'Proficient',
      4: 'Advanced',
      5: 'Expert'
    };
    return labels[level] || '';
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content skill-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>Add Skill to Assessment Matrix</h3>
          <button className="close-btn" onClick={onClose}>×</button>
        </div>

        <form onSubmit={handleSubmit}>
          {loading ? (
            <div className="loading-state">Loading skills...</div>
          ) : (
            <>
              <div className="form-group">
                <label>Select Skill: *</label>
                <select
                  value={selectedSkillId}
                  onChange={(e) => setSelectedSkillId(e.target.value)}
                  required
                >
                  <option value="">Choose a skill...</option>
                  {availableSkills.map(skill => (
                    <option key={skill.id} value={skill.id}>
                      {skill.name}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Required Proficiency Level: * ({requiredProficiency}/5)</label>
                <div className="proficiency-selector">
                  {[1, 2, 3, 4, 5].map(level => (
                    <label key={level} className="proficiency-option">
                      <input
                        type="radio"
                        value={level}
                        checked={requiredProficiency === level}
                        onChange={(e) => setRequiredProficiency(parseInt(e.target.value))}
                      />
                      <span className="star-display">
                        {'⭐'.repeat(level)}{'☆'.repeat(5 - level)}
                      </span>
                      <span className="level-label">
                        {getProficiencyLabel(level)}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            </>
          )}

          <div className="modal-actions">
            <button type="button" onClick={onClose} className="btn-secondary">
              Cancel
            </button>
            <button type="submit" className="btn-primary" disabled={saving || loading}>
              {saving ? 'Adding...' : 'Add Skill'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default AddSkillModal;

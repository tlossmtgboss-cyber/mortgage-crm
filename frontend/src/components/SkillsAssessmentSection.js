import React, { useState, useEffect } from 'react';
import SkillsTable from './SkillsTable';
import AddSkillModal from './AddSkillModal';
import AssessSkillModal from './AssessSkillModal';
import responsibilitiesApi from '../services/responsibilitiesApi';
import './SkillsAssessmentSection.css';
import { toast } from '../utils/toast';

const SkillsAssessmentSection = ({ userId, isManager = true }) => {
  const [skills, setSkills] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all'); // all, gaps, meeting

  const [showAddModal, setShowAddModal] = useState(false);
  const [showAssessModal, setShowAssessModal] = useState(false);
  const [assessingSkill, setAssessingSkill] = useState(null);

  useEffect(() => {
    loadSkills();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userId]);

  const loadSkills = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await responsibilitiesApi.getUserSkills(userId);
      setSkills(response.skills || []);
      setSummary(response.summary || {});
    } catch (err) {
      console.error('Error loading skills:', err);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const openAssessModal = (skill) => {
    setAssessingSkill(skill);
    setShowAssessModal(true);
  };

  const handleAddSkill = async (skillData) => {
    try {
      await responsibilitiesApi.addUserSkill(userId, skillData);
      await loadSkills();
      setShowAddModal(false);
    } catch (err) {
      console.error('Error adding skill:', err);
      throw err;
    }
  };

  const handleAssess = async (assessmentData) => {
    try {
      await responsibilitiesApi.assessSkill(userId, assessingSkill.skill_id, assessmentData);
      await loadSkills();
      setShowAssessModal(false);
    } catch (err) {
      console.error('Error assessing skill:', err);
      throw err;
    }
  };

  const handleRemove = async (skillId) => {
    try {
      await responsibilitiesApi.removeUserSkill(userId, skillId);
      await loadSkills();
    } catch (err) {
      console.error('Error removing skill:', err);
      toast.error('Failed to remove skill');
    }
  };

  const filteredSkills = skills.filter(skill => {
    if (filter === 'gaps') {
      return skill.gap < 0; // Has a gap
    }
    if (filter === 'meeting') {
      return skill.gap >= 0 && skill.current_proficiency > 0; // Meeting or exceeding requirement
    }
    return true; // all
  });

  if (loading) {
    return <div className="loading-state">Loading skills assessment...</div>;
  }

  if (error) {
    return (
      <div className="error-state">
        <p>Error loading skills: {error}</p>
        <button onClick={loadSkills} className="btn-secondary">Retry</button>
      </div>
    );
  }

  return (
    <div className="skills-assessment-section">
      {/* Header */}
      <div className="section-header">
        <div className="header-content">
          <h3>Skills Assessment</h3>
          <p className="section-description">
            Track required skills, current proficiency levels, and identify gaps for development.
          </p>
        </div>
        {isManager && (
          <button onClick={() => setShowAddModal(true)} className="btn-primary">
            + Add Skill
          </button>
        )}
      </div>

      {/* Summary Stats */}
      {skills.length > 0 && (
        <div className="skills-summary">
          <div className="summary-card">
            <div className="summary-value">{summary.total_skills || 0}</div>
            <div className="summary-label">Total Skills</div>
          </div>
          <div className="summary-card">
            <div className="summary-value">{summary.meeting_requirements || 0}</div>
            <div className="summary-label">Meeting Requirements</div>
          </div>
          <div className="summary-card">
            <div className="summary-value warning">{summary.with_gaps || 0}</div>
            <div className="summary-label">Skills with Gaps</div>
          </div>
          <div className="summary-card">
            <div className="summary-value">{summary.average_proficiency?.toFixed(1) || '0.0'}</div>
            <div className="summary-label">Average Proficiency</div>
          </div>
        </div>
      )}

      {/* Filter */}
      {skills.length > 0 && (
        <div className="filters-bar">
          <label>Show:</label>
          <select value={filter} onChange={(e) => setFilter(e.target.value)}>
            <option value="all">All Skills ({skills.length})</option>
            <option value="gaps">Skills with Gaps ({skills.filter(s => s.gap < 0).length})</option>
            <option value="meeting">Meeting Requirements ({skills.filter(s => s.gap >= 0 && s.current_proficiency > 0).length})</option>
          </select>
        </div>
      )}

      {/* Skills Table */}
      {filteredSkills.length === 0 && skills.length === 0 ? (
        <div className="empty-state">
          <div className="empty-icon">📚</div>
          <h4>No skills assessed yet</h4>
          <p>
            Add skills to create an assessment matrix and track proficiency levels.
          </p>
          {isManager && (
            <button onClick={() => setShowAddModal(true)} className="btn-primary">
              Add First Skill
            </button>
          )}
        </div>
      ) : filteredSkills.length === 0 ? (
        <div className="empty-state">
          <p>No skills match the selected filter.</p>
        </div>
      ) : (
        <SkillsTable
          skills={filteredSkills}
          isManager={isManager}
          onAssess={openAssessModal}
          onRemove={handleRemove}
        />
      )}

      {/* Training Recommendations */}
      {skills.some(s => s.gap < 0 && s.training_recommendations?.length > 0) && (
        <div className="training-recommendations">
          <h4>📚 Recommended Training</h4>
          <ul>
            {skills
              .filter(s => s.gap < 0 && s.training_recommendations?.length > 0)
              .flatMap(s => s.training_recommendations.map(rec => ({ skill: s.skill_name, rec })))
              .map((item, i) => (
                <li key={i}>
                  <strong>{item.skill}:</strong> {item.rec}
                </li>
              ))
            }
          </ul>
        </div>
      )}

      {/* Modals */}
      {showAddModal && (
        <AddSkillModal
          userId={userId}
          onSave={handleAddSkill}
          onClose={() => setShowAddModal(false)}
        />
      )}

      {showAssessModal && (
        <AssessSkillModal
          skill={assessingSkill}
          userId={userId}
          onSave={handleAssess}
          onClose={() => setShowAssessModal(false)}
        />
      )}
    </div>
  );
};

export default SkillsAssessmentSection;

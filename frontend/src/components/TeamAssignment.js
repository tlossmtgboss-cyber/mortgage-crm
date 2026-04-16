import React, { useState, useEffect } from 'react';
import { API_BASE_URL } from '../services/api';
import './TeamAssignment.css';
import { getToken } from '../utils/tokenStore';

function TeamAssignment({ leadId, onUpdate }) {
  const [teamMembers, setTeamMembers] = useState([]);
  const [assignedMembers, setAssignedMembers] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadTeamMembers();
    if (leadId) {
      loadAssignedMembers();
    }
  }, [leadId]);

  const loadTeamMembers = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/team/members`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setTeamMembers(data.team_members || data || []);
      }
    } catch (error) {
      console.error('Error loading team members:', error);
    } finally {
      setLoading(false);
    }
  };

  const loadAssignedMembers = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/leads/${leadId}/team-assignments`, {
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
      });

      if (response.ok) {
        const data = await response.json();
        setAssignedMembers(data.assignments || []);
      }
    } catch (error) {
      // If endpoint doesn't exist, start with empty assignments
      console.error('Error loading assignments:', error);
      setAssignedMembers([]);
    }
  };

  const addMemberSlot = () => {
    setAssignedMembers(prev => [...prev, { id: null, member_id: '', role: '' }]);
  };

  const removeMemberSlot = (index) => {
    const member = assignedMembers[index];
    setAssignedMembers(prev => prev.filter((_, i) => i !== index));

    // If it was saved, delete from backend
    if (member.id) {
      deleteAssignment(member.id);
    }
  };

  const deleteAssignment = async (assignmentId) => {
    try {
      await fetch(`${API_BASE_URL}/api/v1/leads/${leadId}/team-assignments/${assignmentId}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${getToken()}`,
        },
      });
    } catch (error) {
      console.error('Error deleting assignment:', error);
    }
  };

  const handleMemberChange = async (index, memberId) => {
    const selectedMember = teamMembers.find(m => m.id === parseInt(memberId));

    const updatedAssignments = [...assignedMembers];
    updatedAssignments[index] = {
      ...updatedAssignments[index],
      member_id: memberId,
      name: selectedMember ? (selectedMember.name || `${selectedMember.first_name} ${selectedMember.last_name}`) : '',
      email: selectedMember?.email || '',
      role: selectedMember?.role || '',
    };
    setAssignedMembers(updatedAssignments);

    // Save to backend
    if (memberId && leadId) {
      try {
        const response = await fetch(`${API_BASE_URL}/api/v1/leads/${leadId}/team-assignments`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${getToken()}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            user_id: parseInt(memberId),
            role: selectedMember?.role || 'Team Member',
          }),
        });

        if (response.ok) {
          const data = await response.json();
          updatedAssignments[index].id = data.id;
          setAssignedMembers([...updatedAssignments]);
        }
      } catch (error) {
        console.error('Error saving assignment:', error);
      }
    }

    if (onUpdate) {
      onUpdate(updatedAssignments);
    }
  };

  // Get available members (not already assigned)
  const getAvailableMembers = (currentIndex) => {
    const assignedIds = assignedMembers
      .filter((_, i) => i !== currentIndex)
      .map(m => m.member_id)
      .filter(id => id);

    return teamMembers.filter(m => !assignedIds.includes(m.id.toString()));
  };

  if (loading) {
    return <div className="team-assignment-loading">Loading team...</div>;
  }

  return (
    <div className="team-assignment-container">
      <div className="team-assignment-header">
        <h4>Team Members on File</h4>
      </div>

      <div className="team-assignment-list">
        {assignedMembers.length === 0 ? (
          <div className="no-members-message">
            No team members assigned yet
          </div>
        ) : (
          assignedMembers.map((assignment, index) => (
            <div key={index} className="team-member-slot">
              <select
                className="member-select"
                value={assignment.member_id || ''}
                onChange={(e) => handleMemberChange(index, e.target.value)}
              >
                <option value="">Select team member...</option>
                {getAvailableMembers(index).map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name || `${member.first_name} ${member.last_name}`} - {member.role || 'Team Member'}
                  </option>
                ))}
              </select>
              <button
                type="button"
                className="remove-member-btn"
                onClick={() => removeMemberSlot(index)}
                title="Remove team member"
              >
                ×
              </button>
            </div>
          ))
        )}
      </div>

      <button
        type="button"
        className="add-member-btn"
        onClick={addMemberSlot}
        disabled={assignedMembers.length >= teamMembers.length}
      >
        <span className="plus-icon">+</span>
        <span>Add Team Member</span>
      </button>
    </div>
  );
}

export default TeamAssignment;

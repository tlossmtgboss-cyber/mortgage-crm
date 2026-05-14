import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI } from '../../services/api';

const TeamMembersSection = () => {
  const navigate = useNavigate();
  const [teamMembers, setTeamMembers] = useState([]);
  const [loadingTeam, setLoadingTeam] = useState(false);

  useEffect(() => {
    loadTeamMembers();
  }, []);

  const loadTeamMembers = async () => {
    setLoadingTeam(true);
    try {
      const data = await teamAPI.getMembers();
      let members = [];
      if (Array.isArray(data)) { members = data; }
      else if (data && typeof data === 'object') { members = data.team_members || data.members || []; }
      const mappedMembers = members.map(m => ({
        ...m,
        name: m.full_name || `${m.first_name || ''} ${m.last_name || ''}`.trim() || 'Unknown',
        user_id: m.id,
        loan_count: m.tasks_count || 0
      }));
      setTeamMembers(mappedMembers);
    } catch (error) {
      console.error('Error loading team members:', error);
      setTeamMembers([]);
    } finally {
      setLoadingTeam(false);
    }
  };

  return (
    <div className="team-members-section">
      <div className="section-header">
        <div>
          <h2>Team Members ({teamMembers.length})</h2>
          <p className="section-description">
            Team members involved in your loan workflow (processors, underwriters, loan officers, etc.)
          </p>
        </div>
        <button className="btn-primary" onClick={() => navigate('/team-members')}>
          Manage Team Members
        </button>
      </div>

      {loadingTeam ? (
        <div className="loading-state">Loading team members...</div>
      ) : (
        <>
          {teamMembers.length === 0 ? (
            <div className="empty-state">
              <p>No workflow team members found. Team members will appear once they are assigned to loans.</p>
            </div>
          ) : (
            <div className="team-members-table-container">
              <table className="team-members-table">
                <thead>
                  <tr>
                    <th>Member</th><th>Role</th><th>Email</th><th>Loans</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {teamMembers.map((member, index) => (
                    <tr key={member.id || `${member.name || 'unknown'}-${index}`}
                      className="team-member-row"
                      onClick={() => { if (member.user_id) navigate(`/team/${member.user_id}`); }}
                      style={{ cursor: member.user_id ? 'pointer' : 'default' }}>
                      <td>
                        <div className="member-info-cell">
                          <div className="member-avatar-small">{(member.name || 'U').charAt(0).toUpperCase()}</div>
                          <div><div className="member-name">{member.name || 'Unknown'}</div></div>
                        </div>
                      </td>
                      <td><span className="role-badge-inline">{member.role || 'N/A'}</span></td>
                      <td><span className="member-email-text">{member.email || 'N/A'}</span></td>
                      <td>
                        <span className="loan-count-badge">
                          {member.loan_count} {member.loan_count === 1 ? 'loan' : 'loans'}
                        </span>
                      </td>
                      <td>
                        <button className="btn-view-profile"
                          onClick={(e) => { e.stopPropagation(); if (member.user_id) navigate(`/team/${member.user_id}`); }}
                          disabled={!member.user_id}>View Profile</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default TeamMembersSection;

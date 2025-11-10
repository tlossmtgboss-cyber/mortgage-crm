import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { teamAPI } from '../services/api';
import './UserProfile.css';

function UserProfile() {
  const { userId, id } = useParams(); // Support both /team/:userId and legacy /user/:id routes
  const actualUserId = userId || id;
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [memberData, setMemberData] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    loadMemberData();
  }, [actualUserId]);

  const loadMemberData = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await teamAPI.getMemberDetail(actualUserId);
      setMemberData(data);
    } catch (err) {
      console.error('Error loading member data:', err);
      setError('Failed to load member profile');
    } finally {
      setLoading(false);
    }
  };

  const handleViewAsUser = () => {
    // Store the original user context
    const currentUser = localStorage.getItem('user');
    localStorage.setItem('originalUser', currentUser);
    localStorage.setItem('viewAsUserId', actualUserId);

    // Navigate to dashboard to see it from this user's perspective
    alert(`Switching to view as user ${memberData.user.email}. You will now see the CRM from their perspective.`);
    navigate('/');
    window.location.reload(); // Reload to apply the context
  };

  const handleExitViewAsUser = () => {
    // Restore original user context
    const originalUser = localStorage.getItem('originalUser');
    if (originalUser) {
      localStorage.setItem('user', originalUser);
      localStorage.removeItem('originalUser');
      localStorage.removeItem('viewAsUserId');
      alert('Returning to your own view');
      navigate('/');
      window.location.reload();
    }
  };

  if (loading) {
    return (
      <div className="user-profile-container">
        <div className="loading-state">Loading profile...</div>
      </div>
    );
  }

  if (error || !memberData) {
    return (
      <div className="user-profile-container">
        <div className="error-state">
          <p>{error || 'User not found'}</p>
          <button onClick={() => navigate('/settings')} className="btn-back">
            ← Back to Settings
          </button>
        </div>
      </div>
    );
  }

  const { user, roles_with_tasks } = memberData;
  const isViewingAsUser = localStorage.getItem('viewAsUserId') !== null;

  return (
    <div className="user-profile-container">
      {/* View As User Banner - at top if active */}
      {isViewingAsUser && (
        <div className="view-as-banner">
          <span className="banner-icon">👁️</span>
          <span className="banner-text">You are viewing the CRM as this user</span>
          <button onClick={handleExitViewAsUser} className="banner-btn">
            Exit View Mode
          </button>
        </div>
      )}

      {/* Header */}
      <div className="profile-header">
        <button onClick={() => navigate('/settings')} className="btn-back">
          ← Back to Team
        </button>

        <div className="header-content">
          <div className="profile-avatar-large">
            {user.full_name ? user.full_name.charAt(0).toUpperCase() : user.email.charAt(0).toUpperCase()}
          </div>
          <div className="profile-info">
            <h1>{user.full_name || user.email}</h1>
            <p className="profile-email">{user.email}</p>
            <div className="profile-meta">
              <span className="meta-item">
                👤 User ID: {user.id}
              </span>
              {user.created_at && (
                <span className="meta-item">
                  📅 Joined: {new Date(user.created_at).toLocaleDateString()}
                </span>
              )}
              {user.onboarding_completed && (
                <span className="status-badge completed">✓ Onboarded</span>
              )}
            </div>
          </div>
        </div>

        <div className="profile-actions">
          {isViewingAsUser ? (
            <button onClick={handleExitViewAsUser} className="btn-exit-view-as">
              🔙 Exit View As User
            </button>
          ) : (
            <button onClick={handleViewAsUser} className="btn-view-as-user">
              👁️ View as This User
            </button>
          )}
        </div>
      </div>

      {/* Roles and Tasks */}
      <div className="profile-content">
        <h2>Assigned Roles & Tasks</h2>

        {roles_with_tasks && roles_with_tasks.length > 0 ? (
          <div className="roles-tasks-container">
            {roles_with_tasks.map(({ role, tasks }) => (
              <div key={role.id} className="role-task-section">
                <div className="role-section-header">
                  <div className="role-info-header">
                    <h3>{role.role_title}</h3>
                    <span className="role-badge">{role.role_name}</span>
                    <span className="tasks-count-badge">{tasks.length} tasks</span>
                  </div>
                </div>

                {role.responsibilities && (
                  <div className="role-responsibilities">
                    <h4>Responsibilities</h4>
                    <p>{role.responsibilities}</p>
                  </div>
                )}

                {role.skills_required && role.skills_required.length > 0 && (
                  <div className="role-skills">
                    <h4>Required Skills</h4>
                    <div className="skills-tags">
                      {role.skills_required.map((skill, idx) => (
                        <span key={idx} className="skill-tag">{skill}</span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Tasks List */}
                <div className="tasks-list">
                  <h4>Tasks ({tasks.length})</h4>
                  <div className="tasks-grid-profile">
                    {tasks.map((task, idx) => (
                      <div key={task.id} className="task-card-profile">
                        <div className="task-card-header">
                          <span className="task-index">{idx + 1}</span>
                          <h5>{task.task_name}</h5>
                        </div>
                        {task.task_description && (
                          <p className="task-description-profile">{task.task_description}</p>
                        )}
                        <div className="task-meta-badges">
                          {task.estimated_duration && (
                            <span className="task-meta-badge">⏱️ {task.estimated_duration}min</span>
                          )}
                          {task.sla && (
                            <span className="task-meta-badge">⏰ {task.sla}{task.sla_unit}</span>
                          )}
                          {task.ai_automatable && (
                            <span className="task-meta-badge ai">🤖 AI Auto</span>
                          )}
                          {task.is_required && (
                            <span className="task-meta-badge required">Required</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-roles-state">
            <p>No roles or tasks assigned yet. Complete the onboarding process to assign roles and tasks to team members.</p>
          </div>
        )}
      </div>
    </div>
  );
}

export default UserProfile;

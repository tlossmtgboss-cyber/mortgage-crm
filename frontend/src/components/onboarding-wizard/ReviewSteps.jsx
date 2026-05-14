import React from 'react';

// STEP 4: Assign Roles
export const AssignRolesStep = ({ formData }) => {
  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🎯</div>
        <h2>Assign Users to Roles</h2>
        <p className="step-description">
          Map your team members to the roles identified from your process documents. You can also modify roles and add additional tasks.
        </p>
      </div>

      <div className="role-assignment-container">
        {formData.extractedRoles && formData.extractedRoles.length > 0 ? (
          formData.extractedRoles.map((role, index) => (
            <div key={role.id || index} className="role-assignment-card">
              <h3>{role.role_title || role.role_name}</h3>
              <p>{role.responsibilities}</p>
              <div className="assign-member-section">
                <label>Assign Team Member:</label>
                <select className="form-select">
                  <option value="">Select a team member</option>
                  {formData.members.map((member, mIndex) => (
                    <option key={mIndex} value={member.email}>
                      {member.firstName} {member.lastName} - {member.email}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          ))
        ) : (
          <div className="no-data-message">
            <p>No roles have been extracted yet. Please complete Step 3 to upload and analyze your process documents.</p>
          </div>
        )}
      </div>
    </div>
  );
};

// STEP 5: Review Tasks
export const ReviewTasksStep = ({
  formData, setFormData,
  selectedMemberForTasks, setSelectedMemberForTasks,
  memberTaskModal, setMemberTaskModal
}) => {
  const handleMemberClick = (member, index) => {
    setSelectedMemberForTasks({ ...member, index });
    setMemberTaskModal(true);
  };

  return (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">✅</div>
        <h2>Review Individual Team Members</h2>
        <p className="step-description">
          Review each team member's assigned tasks. Click on any team member to add, review, or delete tasks.
        </p>
      </div>

      <div className="member-tasks-container">
        {formData.members && formData.members.length > 0 ? (
          formData.members.map((member, index) => {
            const memberTasks = formData.extractedTasks?.filter(task =>
              task.assigned_user_id === member.id ||
              task.assigned_user_email === member.email ||
              task.role_id === formData.extractedRoles?.find(r => r.role_title === member.role)?.id
            ) || [];

            return (
              <div
                key={index}
                className="member-tasks-card clickable"
                onClick={() => handleMemberClick(member, index)}
                style={{ cursor: 'pointer' }}
              >
                <h3>{member.firstName} {member.lastName}</h3>
                <p className="member-role">{member.role}</p>
                <div className="tasks-list">
                  <h4>Assigned Tasks: {memberTasks.length}</h4>
                  {memberTasks.length > 0 ? (
                    <ul>
                      {memberTasks.slice(0, 3).map((task, tIndex) => (
                        <li key={tIndex}>{task.task_name || task.title}</li>
                      ))}
                      {memberTasks.length > 3 && (
                        <li className="more-tasks">+{memberTasks.length - 3} more...</li>
                      )}
                    </ul>
                  ) : (
                    <p className="no-tasks">No tasks assigned yet</p>
                  )}
                </div>
                <p className="click-hint">Click to manage tasks</p>
              </div>
            );
          })
        ) : (
          <div className="no-data-message">
            <p>No team members added yet. Please complete Step 2 to add your team.</p>
          </div>
        )}
      </div>

      {/* Task Management Modal */}
      {memberTaskModal && selectedMemberForTasks && (
        <div className="modal-overlay" onClick={() => setMemberTaskModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Manage Tasks for {selectedMemberForTasks.firstName} {selectedMemberForTasks.lastName}</h3>
              <button className="btn-close" onClick={() => setMemberTaskModal(false)}>×</button>
            </div>
            <div className="modal-body">
              <p className="member-role">Role: {selectedMemberForTasks.role}</p>

              <div className="task-management-section">
                <h4>Assigned Tasks</h4>
                {formData.extractedTasks && formData.extractedTasks.length > 0 ? (
                  <div className="tasks-list-modal">
                    {formData.extractedTasks
                      .filter(task =>
                        task.assigned_user_id === selectedMemberForTasks.id ||
                        task.assigned_user_email === selectedMemberForTasks.email ||
                        task.role_id === formData.extractedRoles?.find(r => r.role_title === selectedMemberForTasks.role)?.id
                      )
                      .map((task, tIndex) => (
                        <div key={tIndex} className="task-item-modal">
                          <div className="task-info">
                            <strong>{task.task_name || task.title}</strong>
                            <p>{task.description}</p>
                            {task.milestone_id && (
                              <span className="task-milestone">
                                Milestone: {formData.extractedMilestones?.find(m => m.id === task.milestone_id)?.milestone_name}
                              </span>
                            )}
                          </div>
                          <button
                            className="btn-delete-task"
                            onClick={() => {
                              setFormData(prev => ({
                                ...prev,
                                extractedTasks: prev.extractedTasks.filter((_, i) => i !== tIndex)
                              }));
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      ))}
                  </div>
                ) : (
                  <p>No tasks assigned yet</p>
                )}

                <button
                  className="btn-add-task"
                  onClick={() => {
                    const taskName = prompt('Enter task name:');
                    if (taskName) {
                      const newTask = {
                        id: `task_${Date.now()}`,
                        task_name: taskName,
                        title: taskName,
                        description: '',
                        assigned_user_email: selectedMemberForTasks.email,
                        assigned_user_id: selectedMemberForTasks.id,
                        role_id: formData.extractedRoles?.find(r => r.role_title === selectedMemberForTasks.role)?.id
                      };
                      setFormData(prev => ({
                        ...prev,
                        extractedTasks: [...(prev.extractedTasks || []), newTask]
                      }));
                    }
                  }}
                >
                  + Add New Task
                </button>
              </div>
            </div>
            <div className="modal-footer">
              <button className="btn-primary" onClick={() => setMemberTaskModal(false)}>Done</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

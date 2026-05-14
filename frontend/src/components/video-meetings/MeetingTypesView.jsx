import React from 'react';

const MeetingTypesView = ({
  meetingTypes, seedDefaultTemplates,
  setEditingType, resetTypeForm, setShowNewTypeModal,
  handleEditType
}) => (
  <div className="scheduler-types-view">
    <div className="types-header">
      <h3>Meeting Types</h3>
      <div className="types-actions">
        <button className="seed-btn" onClick={seedDefaultTemplates}>
          Seed Defaults
        </button>
        <button className="add-type-btn" onClick={() => {
          setEditingType(null);
          resetTypeForm();
          setShowNewTypeModal(true);
        }}>
          + New Type
        </button>
      </div>
    </div>

    {meetingTypes.length === 0 ? (
      <div className="empty-state">
        <p>No meeting types configured</p>
        <button onClick={seedDefaultTemplates}>Create Default Types</button>
      </div>
    ) : (
      <div className="types-grid">
        {meetingTypes.map(type => (
          <div
            key={type.id || type.template_key}
            className="type-card clickable"
            style={{ borderLeftColor: type.color }}
            onClick={() => handleEditType(type)}
          >
            <div className="type-header">
              <h4>{type.template_name || type.type_name}</h4>
            </div>
            <p className="type-description">{type.description}</p>
            <div className="type-meta">
              <span>{type.default_duration_minutes} min</span>
              <span className={`public-badge ${type.is_public ? 'public' : 'private'}`}>
                {type.is_public ? 'Public' : 'Private'}
              </span>
            </div>
            <div className="type-durations">
              {(type.allowed_durations || [type.default_duration_minutes]).map(d => (
                <span key={d} className="duration-chip">{d}m</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);

export default MeetingTypesView;

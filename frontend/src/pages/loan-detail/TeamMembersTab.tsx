/**
 * Team Members tab -- Workflow role assignments + transaction partners.
 */
import React from 'react';
import { ClickablePhone } from '../../components/ClickableContact';
import WorkflowRoleAssignment from '../../components/WorkflowRoleAssignment';
import { formatPhoneNumber } from '../../utils/phoneUtils';
import type { TeamMember, TeamMemberForm } from './types';

interface TeamMembersTabProps {
  standardMembers: TeamMember[];
  teamMembers: TeamMember[];
  showTeamMemberModal: boolean;
  setShowTeamMemberModal: (show: boolean) => void;
  editingTeamMember: TeamMember | null;
  teamMemberForm: TeamMemberForm;
  setTeamMemberForm: (form: TeamMemberForm) => void;
  teamMemberLoading: boolean;
  teamMemberSearchResults: any[];
  showTeamMemberSearchResults: boolean;
  setShowTeamMemberSearchResults: (show: boolean) => void;
  teamMemberSearchLoading: boolean;
  teamMemberRoles: string[];
  handleAddTeamMember: () => void;
  handleEditTeamMember: (member: TeamMember) => void;
  handleSaveTeamMember: () => void;
  handleDeleteTeamMember: (memberId: number) => void;
  handleTeamMemberNameChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  selectTeamMemberSearchResult: (partner: any) => void;
}

export default function TeamMembersTab({
  standardMembers,
  teamMembers,
  showTeamMemberModal,
  setShowTeamMemberModal,
  editingTeamMember,
  teamMemberForm,
  setTeamMemberForm,
  teamMemberLoading,
  teamMemberSearchResults,
  showTeamMemberSearchResults,
  setShowTeamMemberSearchResults,
  teamMemberSearchLoading,
  teamMemberRoles,
  handleAddTeamMember,
  handleEditTeamMember,
  handleSaveTeamMember,
  handleDeleteTeamMember,
  handleTeamMemberNameChange,
  selectTeamMemberSearchResult,
}: TeamMembersTabProps) {
  return (
    <div className="info-section">
      <h2>TEAM MEMBERS</h2>

      {/* Workflow Role Assignments */}
      <div style={{ marginBottom: '24px' }}>
        <WorkflowRoleAssignment onUpdate={() => {}} />
      </div>

      <div className="team-members-display">
        <h4 style={{ marginBottom: '15px', color: '#333' }}>Transaction Partners</h4>

        {/* Standard/Internal Team Members */}
        {standardMembers.map((member, index) => {
          const colors = ['#2563eb', '#059669', '#7c3aed', '#dc2626', '#f59e0b'];
          const bgColor = colors[index % colors.length];
          return (
            <div key={member.id} className="team-member-card" style={{
              display: 'flex', alignItems: 'center', padding: '12px 16px',
              backgroundColor: '#f8f9fa', borderRadius: '8px', marginBottom: '10px'
            }}>
              <div style={{
                width: '40px', height: '40px', borderRadius: '50%', backgroundColor: bgColor,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: 'white', fontWeight: 'bold', marginRight: '12px', flexShrink: 0
              }}>
                {member.name?.charAt(0)?.toUpperCase() || '?'}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: '600', color: '#333' }}>{member.name}</div>
                <div style={{ fontSize: '12px', color: '#666' }}>{member.role}</div>
                {member.email && <div style={{ fontSize: '12px', color: '#2563eb' }}>{member.email}</div>}
              </div>
              <span style={{ fontSize: '10px', backgroundColor: '#e5e7eb', padding: '2px 8px', borderRadius: '4px', color: '#666' }}>
                Employee
              </span>
            </div>
          );
        })}

        {/* Custom Team Members (Transaction Partners) */}
        {teamMembers.map((member) => (
          <div key={member.id} className="team-member-card" style={{
            display: 'flex', alignItems: 'center', padding: '12px 16px',
            backgroundColor: '#f8f9fa', borderRadius: '8px', marginBottom: '10px'
          }}>
            <div style={{
              width: '40px', height: '40px', borderRadius: '50%',
              backgroundColor: member.is_employee ? '#3b82f6' : '#f59e0b',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'white', fontWeight: 'bold', marginRight: '12px', flexShrink: 0
            }}>
              {member.name?.charAt(0)?.toUpperCase() || '?'}
            </div>
            <div style={{ flex: 1 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontWeight: '600', color: '#333' }}>{member.name}</span>
                {member.is_new && (
                  <span style={{
                    fontSize: '10px', backgroundColor: '#10b981', color: 'white',
                    padding: '2px 6px', borderRadius: '4px', fontWeight: '600'
                  }}>NEW</span>
                )}
              </div>
              <div style={{ fontSize: '12px', color: '#666' }}>{member.role}</div>
              {member.company && <div style={{ fontSize: '11px', color: '#888' }}>{member.company}</div>}
              {member.email && <div style={{ fontSize: '12px', color: '#2563eb' }}>{member.email}</div>}
              {member.phone && <div style={{ fontSize: '12px' }}><ClickablePhone phone={member.phone} /></div>}
            </div>
            <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
              {!member.is_employee && member.referral_partner_id && (
                <span style={{ fontSize: '10px', backgroundColor: '#fef3c7', padding: '2px 8px', borderRadius: '4px', color: '#92400e' }}>
                  Partner
                </span>
              )}
              <button onClick={() => handleEditTeamMember(member)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px', padding: '4px', color: '#6b7280' }} title="Edit">
                ✎
              </button>
              <button onClick={() => handleDeleteTeamMember(member.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px', padding: '4px', color: '#ef4444' }} title="Remove">
                ×
              </button>
            </div>
          </div>
        ))}

        {/* Show message if no team members */}
        {standardMembers.length === 0 && teamMembers.length === 0 && (
          <div style={{ padding: '20px', backgroundColor: '#f8f9fa', borderRadius: '8px', textAlign: 'center', color: '#666' }}>
            No team members assigned yet
          </div>
        )}

        {/* Add Team Member Button */}
        <button onClick={handleAddTeamMember} style={{
          marginTop: '15px', padding: '10px 20px', backgroundColor: 'white',
          border: '1px dashed #d1d5db', borderRadius: '8px', color: '#666',
          cursor: 'pointer', width: '100%', display: 'flex', alignItems: 'center',
          justifyContent: 'center', gap: '8px'
        }}>
          <span style={{ fontSize: '18px' }}>+</span>
          <span>Add Team Member</span>
        </button>
      </div>

      {/* Team Member Add/Edit Modal */}
      {showTeamMemberModal && (
        <div className="modal-overlay" onClick={() => setShowTeamMemberModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{ maxWidth: '500px' }}>
            <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
              <h2 style={{ margin: 0 }}>{editingTeamMember ? 'Edit Team Member' : 'Add Team Member'}</h2>
              <button onClick={() => setShowTeamMemberModal(false)} style={{ background: 'none', border: 'none', fontSize: '24px', cursor: 'pointer', color: '#666' }}>×</button>
            </div>

            <div className="form-group" style={{ marginBottom: '16px', position: 'relative' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Name *</label>
              <input type="text" value={teamMemberForm.name} onChange={handleTeamMemberNameChange}
                onFocus={() => teamMemberForm.name.length >= 2 && setShowTeamMemberSearchResults(true)}
                placeholder="Start typing to search partners..." autoComplete="off"
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}
              />
              {teamMemberSearchLoading && (
                <div style={{ position: 'absolute', right: '10px', top: '35px', color: '#999', fontSize: '12px' }}>Searching...</div>
              )}
              {showTeamMemberSearchResults && teamMemberSearchResults.length > 0 && (
                <div style={{
                  position: 'absolute', top: '100%', left: 0, right: 0, backgroundColor: 'white',
                  border: '1px solid #ddd', borderRadius: '4px', boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                  maxHeight: '200px', overflowY: 'auto', zIndex: 1000
                }}>
                  {teamMemberSearchResults.map(result => (
                    <div key={result.id} onClick={() => selectTeamMemberSearchResult(result)}
                      style={{ padding: '10px 12px', cursor: 'pointer', borderBottom: '1px solid #eee', transition: 'background-color 0.15s' }}
                      onMouseEnter={e => (e.target as HTMLDivElement).style.backgroundColor = '#f5f5f5'}
                      onMouseLeave={e => (e.target as HTMLDivElement).style.backgroundColor = 'white'}
                    >
                      <div style={{ fontWeight: '500' }}>{result.name}</div>
                      {result.company && <div style={{ fontSize: '12px', color: '#888' }}>{result.company}</div>}
                      <div style={{ fontSize: '12px', color: '#666' }}>
                        {result.email && <span>{result.email}</span>}
                        {result.email && result.phone && <span> &bull; </span>}
                        {result.phone && <ClickablePhone phone={result.phone} />}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Role *</label>
              <select value={teamMemberForm.role} onChange={(e) => setTeamMemberForm({ ...teamMemberForm, role: e.target.value })}
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }}>
                <option value="">Select a role...</option>
                {teamMemberRoles.map(role => (<option key={role} value={role}>{role}</option>))}
              </select>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
              <div className="form-group">
                <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Email</label>
                <input type="email" value={teamMemberForm.email} onChange={(e) => setTeamMemberForm({ ...teamMemberForm, email: e.target.value })}
                  placeholder="email@example.com" style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }} />
              </div>
              <div className="form-group">
                <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Phone</label>
                <input type="tel" value={teamMemberForm.phone} onChange={(e) => setTeamMemberForm({ ...teamMemberForm, phone: formatPhoneNumber(e.target.value) })}
                  placeholder="(555) 123-4567" style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }} />
              </div>
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Company</label>
              <input type="text" value={teamMemberForm.company} onChange={(e) => setTeamMemberForm({ ...teamMemberForm, company: e.target.value })}
                placeholder="Company or brokerage name" style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }} />
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>License Number</label>
              <input type="text" value={teamMemberForm.license_number} onChange={(e) => setTeamMemberForm({ ...teamMemberForm, license_number: e.target.value })}
                placeholder="License or NMLS number" style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px' }} />
            </div>

            <div className="form-group" style={{ marginBottom: '16px' }}>
              <label style={{ display: 'block', marginBottom: '6px', fontWeight: '500' }}>Notes</label>
              <textarea value={teamMemberForm.notes} onChange={(e) => setTeamMemberForm({ ...teamMemberForm, notes: e.target.value })}
                placeholder="Additional notes..." rows={3}
                style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '6px', resize: 'vertical' }} />
            </div>

            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: '8px', cursor: 'pointer' }}>
                <input type="checkbox" checked={teamMemberForm.is_employee}
                  onChange={(e) => setTeamMemberForm({ ...teamMemberForm, is_employee: e.target.checked })} />
                <span>This is an internal employee</span>
              </label>
              {!teamMemberForm.is_employee && (
                <p style={{ fontSize: '12px', color: '#666', marginTop: '8px', marginLeft: '24px' }}>
                  External team members will be saved as referral partners.
                </p>
              )}
            </div>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'flex-end' }}>
              <button onClick={() => setShowTeamMemberModal(false)}
                style={{ padding: '10px 20px', border: '1px solid #d1d5db', borderRadius: '6px', background: 'white', cursor: 'pointer' }}>
                Cancel
              </button>
              <button onClick={handleSaveTeamMember} disabled={teamMemberLoading}
                style={{
                  padding: '10px 20px', border: 'none', borderRadius: '6px', background: '#2563eb',
                  color: 'white', cursor: teamMemberLoading ? 'not-allowed' : 'pointer', opacity: teamMemberLoading ? 0.7 : 1
                }}>
                {teamMemberLoading ? 'Saving...' : (editingTeamMember ? 'Update' : 'Add Team Member')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

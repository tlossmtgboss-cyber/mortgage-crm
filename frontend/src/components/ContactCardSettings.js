import React, { useState, useEffect, useCallback } from 'react';
import api from '../services/api';
import { toast } from '../utils/toast';

const ROLE_OPTIONS = [
  'Loan Officer',
  'Processor',
  'Underwriter',
  'Closer',
  'Production Assistant',
  'Team Lead',
  'Branch Manager',
];

const emptyMember = { name: '', role_label: 'Loan Officer', phone: '', email: '', sort_order: 0, is_active: true };

const ContactCardSettings = () => {
  const [members, setMembers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState({ ...emptyMember });
  const [saving, setSaving] = useState(false);

  const fetchMembers = useCallback(async () => {
    try {
      const { data } = await api.get('/api/v1/settings/contact-card/members');
      setMembers(data);
    } catch (err) {
      console.error('Failed to load contact card team:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchMembers(); }, [fetchMembers]);

  const handleSave = async () => {
    if (!form.name.trim() || !form.role_label.trim()) {
      toast.error('Name and role are required');
      return;
    }
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/api/v1/settings/contact-card/members/${editing}`, form);
        toast.success('Team member updated');
      } else {
        await api.post('/api/v1/settings/contact-card/members', { ...form, sort_order: members.length });
        toast.success('Team member added');
      }
      setEditing(null);
      setForm({ ...emptyMember });
      fetchMembers();
    } catch (err) {
      toast.error('Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const handleEdit = (member) => {
    setEditing(member.id);
    setForm({
      name: member.name,
      role_label: member.role_label,
      phone: member.phone || '',
      email: member.email || '',
      sort_order: member.sort_order,
      is_active: member.is_active,
    });
  };

  const handleDelete = async (id) => {
    try {
      await api.delete(`/api/v1/settings/contact-card/members/${id}`);
      toast.success('Removed');
      fetchMembers();
    } catch {
      toast.error('Failed to remove');
    }
  };

  const handleCancel = () => {
    setEditing(null);
    setForm({ ...emptyMember });
  };

  if (loading) return <div style={{ padding: 20 }}>Loading...</div>;

  return (
    <div style={{ maxWidth: 700 }}>
      <h2 style={{ margin: '0 0 4px' }}>Contact Card Team</h2>
      <p style={{ color: '#666', margin: '0 0 20px', fontSize: 14 }}>
        These team members appear on the vCard contact card sent to borrowers after application completion.
        Borrowers save one contact with everyone's name, role, phone, and email.
      </p>

      {members.length > 0 && (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 24 }}>
          <thead>
            <tr style={{ borderBottom: '2px solid #e5e7eb', textAlign: 'left' }}>
              <th style={{ padding: '8px 12px' }}>Name</th>
              <th style={{ padding: '8px 12px' }}>Role</th>
              <th style={{ padding: '8px 12px' }}>Phone</th>
              <th style={{ padding: '8px 12px' }}>Email</th>
              <th style={{ padding: '8px 12px', width: 100 }}></th>
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.id} style={{ borderBottom: '1px solid #f3f4f6', opacity: m.is_active ? 1 : 0.5 }}>
                <td style={{ padding: '10px 12px', fontWeight: 500 }}>{m.name}</td>
                <td style={{ padding: '10px 12px', color: '#6b7280' }}>{m.role_label}</td>
                <td style={{ padding: '10px 12px', fontSize: 13 }}>{m.phone || '—'}</td>
                <td style={{ padding: '10px 12px', fontSize: 13 }}>{m.email || '—'}</td>
                <td style={{ padding: '10px 12px', display: 'flex', gap: 8 }}>
                  <button
                    onClick={() => handleEdit(m)}
                    style={{
                      background: 'none', border: 'none', color: '#3b82f6',
                      cursor: 'pointer', fontSize: 13, padding: 0,
                    }}
                  >
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(m.id)}
                    style={{
                      background: 'none', border: 'none', color: '#ef4444',
                      cursor: 'pointer', fontSize: 13, padding: 0,
                    }}
                  >
                    Remove
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {members.length === 0 && !editing && (
        <div style={{
          padding: 24, background: '#f9fafb', borderRadius: 8,
          border: '1px dashed #d1d5db', textAlign: 'center', marginBottom: 20,
        }}>
          <p style={{ color: '#6b7280', margin: '0 0 12px' }}>
            No team members configured yet. Add your team so borrowers get a contact card after applying.
          </p>
        </div>
      )}

      <div style={{
        padding: 16, background: '#f9fafb', borderRadius: 8,
        border: '1px solid #e5e7eb',
      }}>
        <h3 style={{ margin: '0 0 12px', fontSize: 15 }}>
          {editing ? 'Edit Team Member' : 'Add Team Member'}
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#374151', marginBottom: 4 }}>Name *</label>
            <input
              type="text"
              placeholder="Tim Loss"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              style={{
                width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                borderRadius: 6, fontSize: 14, boxSizing: 'border-box',
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#374151', marginBottom: 4 }}>Role *</label>
            <select
              value={form.role_label}
              onChange={(e) => setForm({ ...form, role_label: e.target.value })}
              style={{
                width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                borderRadius: 6, fontSize: 14, boxSizing: 'border-box',
              }}
            >
              {ROLE_OPTIONS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#374151', marginBottom: 4 }}>Phone</label>
            <input
              type="tel"
              placeholder="+18431234567"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
              style={{
                width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                borderRadius: 6, fontSize: 14, boxSizing: 'border-box',
              }}
            />
          </div>
          <div>
            <label style={{ display: 'block', fontSize: 13, color: '#374151', marginBottom: 4 }}>Email</label>
            <input
              type="email"
              placeholder="tloss@cmghomeloans.com"
              value={form.email}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              style={{
                width: '100%', padding: '8px 12px', border: '1px solid #d1d5db',
                borderRadius: 6, fontSize: 14, boxSizing: 'border-box',
              }}
            />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginTop: 16 }}>
          <button
            onClick={handleSave}
            disabled={saving}
            style={{
              padding: '8px 20px', background: '#3b82f6', color: '#fff',
              border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 14,
              opacity: saving ? 0.7 : 1,
            }}
          >
            {saving ? 'Saving...' : editing ? 'Update' : 'Add Member'}
          </button>
          {editing && (
            <button
              onClick={handleCancel}
              style={{
                padding: '8px 20px', background: '#fff', color: '#374151',
                border: '1px solid #d1d5db', borderRadius: 6, cursor: 'pointer', fontSize: 14,
              }}
            >
              Cancel
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ContactCardSettings;

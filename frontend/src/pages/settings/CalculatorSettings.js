/**
 * Calculator Settings
 *
 * Matrix UI for assigning calculator types to buyer types.
 * Rows = buyer types, columns = calculator types, cells = toggle checkboxes.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import './CalculatorSettings.css';
import { getToken } from '../../utils/tokenStore';

const API_URL = process.env.REACT_APP_API_URL || '';

function CalculatorSettings() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [setupDone, setSetupDone] = useState(false);
  const [settingUp, setSettingUp] = useState(false);
  const [calculatorTypes, setCalculatorTypes] = useState([]);
  const [buyerTypes, setBuyerTypes] = useState([]);
  const [assignments, setAssignments] = useState({}); // { "buyer_type|calc_type": true }
  const [originalAssignments, setOriginalAssignments] = useState({});
  const [newBuyerType, setNewBuyerType] = useState('');
  const [addingBuyerType, setAddingBuyerType] = useState(false);
  const [error, setError] = useState(null);

  const token = getToken();

  const apiFetch = useCallback(async (url, options = {}) => {
    const res = await fetch(`${API_URL}${url}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`,
        ...options.headers,
      },
    });
    if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
    return res.json();
  }, [token]);

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true);
      const data = await apiFetch('/api/v1/settings/calculator-types');
      setCalculatorTypes(data.calculator_types || []);
      setBuyerTypes(data.buyer_types || []);

      const map = {};
      for (const a of (data.assignments || [])) {
        if (a.enabled) {
          map[`${a.buyer_type}|${a.calculator_type}`] = true;
        }
      }
      setAssignments(map);
      setOriginalAssignments(map);
      setSetupDone(true);
      setError(null);
    } catch (err) {
      if (err.message.includes('relation') || err.message.includes('does not exist')) {
        setSetupDone(false);
      } else {
        setError(err.message);
      }
    } finally {
      setLoading(false);
    }
  }, [apiFetch]);

  useEffect(() => {
    loadSettings();
  }, [loadSettings]);

  const handleSetup = async () => {
    try {
      setSettingUp(true);
      await apiFetch('/api/v1/settings/calculator-types/setup', { method: 'POST' });
      await loadSettings();
    } catch (err) {
      setError('Setup failed: ' + err.message);
    } finally {
      setSettingUp(false);
    }
  };

  const toggleAssignment = (buyerType, calcType) => {
    const key = `${buyerType}|${calcType}`;
    setAssignments(prev => {
      const next = { ...prev };
      if (next[key]) {
        delete next[key];
      } else {
        next[key] = true;
      }
      return next;
    });
  };

  const hasChanges = JSON.stringify(assignments) !== JSON.stringify(originalAssignments);

  const handleSave = async () => {
    try {
      setSaving(true);
      const assignmentList = [];
      for (const [key, enabled] of Object.entries(assignments)) {
        const [buyer_type, calculator_type] = key.split('|');
        assignmentList.push({ buyer_type, calculator_type, enabled, priority: 0 });
      }

      await apiFetch('/api/v1/settings/calculator-types', {
        method: 'PUT',
        body: JSON.stringify({ assignments: assignmentList }),
      });

      setOriginalAssignments({ ...assignments });
      setError(null);
    } catch (err) {
      setError('Save failed: ' + err.message);
    } finally {
      setSaving(false);
    }
  };

  const handleCancel = () => {
    setAssignments({ ...originalAssignments });
  };

  const handleAddBuyerType = async () => {
    if (!newBuyerType.trim()) return;
    try {
      setAddingBuyerType(true);
      const result = await apiFetch('/api/v1/settings/calculator-types/buyer-types', {
        method: 'POST',
        body: JSON.stringify({ label: newBuyerType.trim() }),
      });
      if (result.buyer_type) {
        setBuyerTypes(prev => [...prev, result.buyer_type]);
      }
      setNewBuyerType('');
    } catch (err) {
      setError('Failed to add buyer type: ' + err.message);
    } finally {
      setAddingBuyerType(false);
    }
  };

  const handleDeleteBuyerType = async (typeId) => {
    if (!window.confirm('Delete this custom buyer type and all its assignments?')) return;
    try {
      await apiFetch(`/api/v1/settings/calculator-types/buyer-types/${typeId}`, {
        method: 'DELETE',
      });
      setBuyerTypes(prev => prev.filter(bt => bt.id !== typeId));
      setAssignments(prev => {
        const next = { ...prev };
        Object.keys(next).forEach(key => {
          if (key.startsWith(`${typeId}|`)) delete next[key];
        });
        return next;
      });
    } catch (err) {
      setError('Failed to delete buyer type: ' + err.message);
    }
  };

  const selectAllForBuyer = (buyerTypeId) => {
    setAssignments(prev => {
      const next = { ...prev };
      calculatorTypes.forEach(ct => {
        next[`${buyerTypeId}|${ct.id}`] = true;
      });
      return next;
    });
  };

  const clearAllForBuyer = (buyerTypeId) => {
    setAssignments(prev => {
      const next = { ...prev };
      calculatorTypes.forEach(ct => {
        delete next[`${buyerTypeId}|${ct.id}`];
      });
      return next;
    });
  };

  if (loading) {
    return (
      <div className="calc-settings-page">
        <div className="calc-settings-loading">Loading calculator settings...</div>
      </div>
    );
  }

  if (!setupDone) {
    return (
      <div className="calc-settings-page">
        <div className="calc-settings-header">
          <button className="calc-back-btn" onClick={() => navigate(-1)}>Back</button>
          <h1>Calculator Settings</h1>
        </div>
        <div className="calc-settings-setup">
          <h2>Initial Setup Required</h2>
          <p>Create the calculator assignment tables to configure which calculators are suggested for each buyer type.</p>
          <button
            className="calc-setup-btn"
            onClick={handleSetup}
            disabled={settingUp}
          >
            {settingUp ? 'Setting up...' : 'Run Setup'}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="calc-settings-page">
      <div className="calc-settings-header">
        <div className="calc-header-left">
          <button className="calc-back-btn" onClick={() => navigate(-1)}>Back</button>
          <div>
            <h1>Calculator Settings</h1>
            <p>Assign which calculators the AI suggests for each buyer type during calls</p>
          </div>
        </div>
        <div className="calc-header-actions">
          {hasChanges && (
            <>
              <button className="calc-cancel-btn" onClick={handleCancel} disabled={saving}>
                Cancel
              </button>
              <button className="calc-save-btn" onClick={handleSave} disabled={saving}>
                {saving ? 'Saving...' : 'Save Changes'}
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="calc-error-banner">
          {error}
          <button onClick={() => setError(null)}>&times;</button>
        </div>
      )}

      <div className="calc-matrix-container">
        <table className="calc-matrix-table">
          <thead>
            <tr>
              <th className="calc-buyer-col">Buyer Type</th>
              {calculatorTypes.map(ct => (
                <th key={ct.id} className="calc-type-col" title={ct.description}>
                  {ct.label}
                </th>
              ))}
              <th className="calc-actions-col">Actions</th>
            </tr>
          </thead>
          <tbody>
            {buyerTypes.map(bt => (
              <tr key={bt.id}>
                <td className="calc-buyer-cell">
                  <span className="calc-buyer-label">{bt.label}</span>
                  {bt.id.startsWith('custom_') && (
                    <button
                      className="calc-delete-buyer-btn"
                      onClick={() => handleDeleteBuyerType(bt.id)}
                      title="Delete custom buyer type"
                    >
                      &times;
                    </button>
                  )}
                </td>
                {calculatorTypes.map(ct => {
                  const key = `${bt.id}|${ct.id}`;
                  const checked = !!assignments[key];
                  return (
                    <td key={ct.id} className="calc-toggle-cell">
                      <label className="calc-checkbox-label">
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleAssignment(bt.id, ct.id)}
                        />
                        <span className={`calc-checkbox-visual ${checked ? 'checked' : ''}`} />
                      </label>
                    </td>
                  );
                })}
                <td className="calc-row-actions">
                  <button
                    className="calc-row-action-btn"
                    onClick={() => selectAllForBuyer(bt.id)}
                    title="Select all"
                  >
                    All
                  </button>
                  <button
                    className="calc-row-action-btn"
                    onClick={() => clearAllForBuyer(bt.id)}
                    title="Clear all"
                  >
                    None
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="calc-add-buyer-section">
        <h3>Add Custom Buyer Type</h3>
        <div className="calc-add-buyer-form">
          <input
            type="text"
            value={newBuyerType}
            onChange={(e) => setNewBuyerType(e.target.value)}
            placeholder="e.g., DSCR Investor"
            onKeyDown={(e) => e.key === 'Enter' && handleAddBuyerType()}
          />
          <button
            onClick={handleAddBuyerType}
            disabled={addingBuyerType || !newBuyerType.trim()}
          >
            {addingBuyerType ? 'Adding...' : 'Add'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default CalculatorSettings;

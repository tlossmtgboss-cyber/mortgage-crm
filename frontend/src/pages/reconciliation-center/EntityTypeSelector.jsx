import React from 'react';
import { ALL_STAGES } from './constants';

/**
 * EntityTypeSelector - Shared panel for choosing where extracted data goes.
 * Used in both New and Pending Review detail panels.
 * Shows Lead / Active Loan / Portfolio / Create New Loan buttons with stage selector.
 */
export default function EntityTypeSelector({
  selectedItem,
  selectedEntityType,
  setSelectedEntityType,
  createNewLoan,
  setCreateNewLoan,
  selectedLoanStage,
  setSelectedLoanStage,
  showMumCategory = false,
  showOtherCategory = false,
}) {
  return (
    <div className="entity-type-selection" style={{ marginBottom: '20px', padding: '15px', background: '#f8fafc', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
      <h3 style={{ margin: '0 0 15px 0', fontSize: '14px', fontWeight: '600', color: '#374151' }}>
        Where should this data go?
      </h3>
      <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
        <button
          onClick={() => { setSelectedEntityType('lead'); setCreateNewLoan(false); }}
          style={{
            flex: 1,
            padding: '12px',
            border: selectedEntityType === 'lead' && !createNewLoan ? '2px solid #2D7A52' : '1px solid #e5e7eb',
            borderRadius: '8px',
            background: selectedEntityType === 'lead' && !createNewLoan ? '#ecfdf5' : 'white',
            cursor: 'pointer',
            fontWeight: selectedEntityType === 'lead' && !createNewLoan ? '600' : '400'
          }}
        >
          Lead
          <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
            {selectedItem.match_entity_type === 'lead' && selectedItem.match_entity_name ?
              `Match: ${selectedItem.match_entity_name}` : 'No match found'}
          </div>
        </button>
        <button
          onClick={() => { setSelectedEntityType('loan'); setCreateNewLoan(false); }}
          style={{
            flex: 1,
            padding: '12px',
            border: selectedEntityType === 'loan' && !createNewLoan ? '2px solid #3b82f6' : '1px solid #e5e7eb',
            borderRadius: '8px',
            background: selectedEntityType === 'loan' && !createNewLoan ? '#eff6ff' : 'white',
            cursor: 'pointer',
            fontWeight: selectedEntityType === 'loan' && !createNewLoan ? '600' : '400'
          }}
        >
          Active Loan
          <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
            {selectedItem.match_entity_type === 'loan' && selectedItem.match_entity_name ?
              `Match: ${selectedItem.match_entity_name}` : 'No match found'}
          </div>
        </button>
        <button
          onClick={() => { setSelectedEntityType('portfolio'); setCreateNewLoan(false); }}
          style={{
            flex: 1,
            padding: '12px',
            border: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '2px solid #f59e0b' : '1px solid #e5e7eb',
            borderRadius: '8px',
            background: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '#fef3c7' : 'white',
            cursor: 'pointer',
            fontWeight: (selectedEntityType === 'portfolio' || selectedEntityType === 'active_loan') ? '600' : '400'
          }}
        >
          Portfolio
          <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
            {(selectedItem.match_entity_type === 'portfolio' || selectedItem.match_entity_type === 'active_loan') && selectedItem.match_entity_name ?
              `Match: ${selectedItem.match_entity_name}` : 'No match found'}
          </div>
        </button>
        <button
          onClick={() => { setCreateNewLoan(true); setSelectedEntityType('loan'); }}
          style={{
            flex: 1,
            padding: '12px',
            border: createNewLoan ? '2px solid #B8924A' : '1px solid #e5e7eb',
            borderRadius: '8px',
            background: createNewLoan ? '#FDF9F0' : 'white',
            cursor: 'pointer',
            fontWeight: createNewLoan ? '600' : '400'
          }}
        >
          + Create New Loan
          <div style={{ fontSize: '11px', color: '#6b7280', marginTop: '4px' }}>
            {selectedItem.fields?.loan_number?.value || 'Add to pipeline'}
          </div>
        </button>
      </div>

      {/* Loan Stage Selector - shows when creating new loan */}
      {createNewLoan && (
        <div style={{ marginTop: '15px', padding: '12px', background: 'white', borderRadius: '6px', border: '1px solid #e5e7eb' }}>
          <label style={{ display: 'block', marginBottom: '8px', fontWeight: '500', color: '#374151' }}>
            Select Loan Stage:
          </label>
          <select
            value={selectedLoanStage}
            onChange={(e) => setSelectedLoanStage(e.target.value)}
            style={{
              width: '100%',
              padding: '10px',
              border: '1px solid #d1d5db',
              borderRadius: '6px',
              fontSize: '14px'
            }}
          >
            <optgroup label="Lead Stages">
              {ALL_STAGES.filter(s => s.category === 'Lead').map(stage => (
                <option key={stage.value} value={stage.value}>{stage.label}</option>
              ))}
            </optgroup>
            <optgroup label="Active Loan Stages">
              {ALL_STAGES.filter(s => s.category === 'Active Loan').map(stage => (
                <option key={stage.value} value={stage.value}>{stage.label}</option>
              ))}
            </optgroup>
            {showMumCategory && (
              <optgroup label="MUM / Portfolio">
                {ALL_STAGES.filter(s => s.category === 'MUM').map(stage => (
                  <option key={stage.value} value={stage.value}>{stage.label}</option>
                ))}
              </optgroup>
            )}
            {showOtherCategory && (
              <optgroup label="Other">
                {ALL_STAGES.filter(s => s.category === 'Other').map(stage => (
                  <option key={stage.value} value={stage.value}>{stage.label}</option>
                ))}
              </optgroup>
            )}
          </select>
        </div>
      )}
    </div>
  );
}

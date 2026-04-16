import React, { useState, useEffect, useCallback } from 'react';
import { toast } from '../../utils/toast';
import './SalesforceFieldMapping.css';
import { getToken } from '../../utils/tokenStore';

// Always use api.perenniaai.com for production API calls
const API_URL = window.location.hostname.includes('perenniaai.com')
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// Available CRM fields that can be mapped to
const CRM_LOAN_FIELDS = [
  { name: 'loan_number', label: 'Loan Number', type: 'string' },
  { name: 'loan_amount', label: 'Loan Amount', type: 'decimal' },
  { name: 'loan_type', label: 'Loan Type', type: 'string' },
  { name: 'interest_rate', label: 'Interest Rate', type: 'decimal' },
  { name: 'property_address', label: 'Property Address', type: 'string' },
  { name: 'property_city', label: 'Property City', type: 'string' },
  { name: 'property_state', label: 'Property State', type: 'string' },
  { name: 'property_zip', label: 'Property Zip', type: 'string' },
  { name: 'purchase_price', label: 'Purchase Price', type: 'decimal' },
  { name: 'down_payment', label: 'Down Payment', type: 'decimal' },
  { name: 'borrower_name', label: 'Borrower Name', type: 'string' },
  { name: 'borrower_first_name', label: 'Borrower First Name', type: 'string' },
  { name: 'borrower_last_name', label: 'Borrower Last Name', type: 'string' },
  { name: 'borrower_email', label: 'Borrower Email', type: 'string' },
  { name: 'borrower_phone', label: 'Borrower Phone', type: 'string' },
  { name: 'coborrower_name', label: 'Co-Borrower Name', type: 'string' },
  { name: 'co_borrower_email', label: 'Co-Borrower Email', type: 'string' },
  { name: 'stage', label: 'Stage', type: 'string' },
  { name: 'closing_date', label: 'Closing Date', type: 'date' },
  { name: 'lock_date', label: 'Lock Date', type: 'date' },
  { name: 'lock_expiration_date', label: 'Lock Expiration Date', type: 'date' },
  { name: 'application_date', label: 'Application Date', type: 'date' },
  { name: 'program', label: 'Program', type: 'string' },
  { name: 'lender', label: 'Lender', type: 'string' },
  // ============================================================
  // JUNGO CUSTOM BYTE MAPPINGS - All 33 Date Fields
  // ============================================================

  // Lead & Application Phase
  { name: 'prospect_date', label: 'Prospect Date', type: 'date' },
  { name: 'le_pending_date', label: 'LE Pending Date', type: 'date' },
  { name: 'credit_only_date', label: 'Credit Only Date', type: 'date' },
  { name: 'file_received_date', label: 'File Received Date', type: 'date' },
  { name: 'preapproval_date', label: 'Pre-Approval Date', type: 'date' },

  // Processing & Underwriting Phase
  { name: 'uw_received_date', label: 'UW Received Date', type: 'date' },
  { name: 'conditions_for_review_date', label: 'Conditions for Review Date', type: 'date' },
  { name: 'suspended_date', label: 'Suspended Date', type: 'date' },
  { name: 'loan_approved_date', label: 'Loan Approved Date', type: 'date' },
  { name: 'approved_not_accepted_date', label: 'Approved Not Accepted Date', type: 'date' },
  { name: 'approval_expires_date', label: 'Approval Expires Date', type: 'date' },

  // Appraisal Phase
  { name: 'appraisal_ordered_date', label: 'Appraisal Ordered Date', type: 'date' },
  { name: 'appraisal_received_date', label: 'Appraisal Received Date', type: 'date' },
  { name: 'appraisal_docs_expire_date', label: 'Appraisal Docs Expire Date', type: 'date' },

  // Closing Disclosure Phase
  { name: 'cd_requested_date', label: 'CD Requested Date', type: 'date' },
  { name: 'cd_sent_to_borrower_date', label: 'CD Sent to Borrower Date', type: 'date' },
  { name: 'cd_acknowledged_date', label: 'CD Acknowledged Date', type: 'date' },

  // Clear to Close & Docs Phase
  { name: 'clear_to_close_date', label: 'Clear to Close Date', type: 'date' },
  { name: 'docs_ordered_date', label: 'Docs Ordered Date', type: 'date' },
  { name: 'docs_out_date', label: 'Docs Out Date', type: 'date' },
  { name: 'credit_docs_expire_date', label: 'Credit Docs Expire Date', type: 'date' },

  // Funding Phase
  { name: 'scheduled_closing_date', label: 'Scheduled Closing Date', type: 'date' },
  { name: 'scheduled_funding_date', label: 'Scheduled Funding Date', type: 'date' },
  { name: 'funds_ordered_date', label: 'Funds Ordered Date', type: 'date' },
  { name: 'funds_sent_date', label: 'Funds Sent Date', type: 'date' },
  { name: 'funded_date', label: 'Funded Date', type: 'date' },
  { name: 'first_payment_date', label: 'First Payment Date', type: 'date' },

  // Post-Closing & Status
  { name: 'investor_purchased_date', label: 'Investor Purchased Date', type: 'date' },
  { name: 'withdrawn_date', label: 'Withdrawn Date', type: 'date' },
  { name: 'contract_received_date', label: 'Contract Received Date', type: 'date' },
];

// Transform types available
const TRANSFORM_TYPES = [
  { value: null, label: 'None (as-is)' },
  { value: 'decimal', label: 'Decimal Number' },
  { value: 'integer', label: 'Integer' },
  { value: 'date', label: 'Date' },
  { value: 'datetime', label: 'DateTime' },
  { value: 'boolean', label: 'Boolean' },
  { value: 'stage_mapping', label: 'Stage Mapping' },
];

function SalesforceFieldMapping({ isConnected, onMappingSaved }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [currentMappings, setCurrentMappings] = useState([]);
  const [usingDefaults, setUsingDefaults] = useState(true);
  const [salesforceObjects, setSalesforceObjects] = useState([]);
  const [selectedObject, setSelectedObject] = useState('');
  const [objectFields, setObjectFields] = useState([]);
  const [loadingFields, setLoadingFields] = useState(false);

  // New mapping form
  const [showAddForm, setShowAddForm] = useState(false);
  const [newMapping, setNewMapping] = useState({
    salesforce_field: '',
    crm_field: '',
    transform_type: null,
  });

  // Fetch current mappings
  const fetchMappings = useCallback(async () => {
    try {
      setLoading(true);
      const token = getToken();
      const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        const data = await res.json();
        setCurrentMappings(data.mappings || []);
        setUsingDefaults(data.using_defaults || false);
      }
    } catch (err) {
      console.error('Failed to fetch mappings:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Fetch available Salesforce objects
  const fetchSalesforceObjects = useCallback(async () => {
    if (!isConnected) return;

    try {
      const token = getToken();
      const res = await fetch(`${API_URL}/api/integrations/salesforce/schema/objects`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        const data = await res.json();
        setSalesforceObjects(data.relevant_objects || []);

        // Auto-select the MtgPlanner object if available
        const mtgPlannerObj = data.relevant_objects?.find(o =>
          o.name.includes('MtgPlanner_CRM__Transaction_Property__c')
        );
        if (mtgPlannerObj) {
          setSelectedObject(mtgPlannerObj.name);
        } else if (data.relevant_objects?.length > 0) {
          // Try to find Opportunity as fallback
          const oppObj = data.relevant_objects.find(o => o.name === 'Opportunity');
          if (oppObj) {
            setSelectedObject('Opportunity');
          }
        }
      }
    } catch (err) {
      console.error('Failed to fetch Salesforce objects:', err);
    }
  }, [isConnected]);

  // Fetch fields for selected object
  const fetchObjectFields = useCallback(async (objectName) => {
    if (!objectName) return;

    try {
      setLoadingFields(true);
      const token = getToken();
      const res = await fetch(`${API_URL}/api/integrations/salesforce/schema/objects/${objectName}`, {
        headers: { 'Authorization': `Bearer ${token}` }
      });

      if (res.ok) {
        const data = await res.json();
        setObjectFields(data.fields || []);
      }
    } catch (err) {
      console.error('Failed to fetch object fields:', err);
    } finally {
      setLoadingFields(false);
    }
  }, []);

  useEffect(() => {
    fetchMappings();
    fetchSalesforceObjects();
  }, [fetchMappings, fetchSalesforceObjects]);

  useEffect(() => {
    if (selectedObject) {
      fetchObjectFields(selectedObject);
    }
  }, [selectedObject, fetchObjectFields]);

  const handleAddMapping = async () => {
    if (!newMapping.salesforce_field || !newMapping.crm_field) {
      toast.error('Please select both Salesforce and CRM fields');
      return;
    }

    try {
      setSaving(true);
      const token = getToken();
      const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(newMapping)
      });

      if (res.ok) {
        toast.success('Field mapping saved');
        setShowAddForm(false);
        setNewMapping({ salesforce_field: '', crm_field: '', transform_type: null });
        fetchMappings();
        if (onMappingSaved) onMappingSaved();
      } else {
        const error = await res.json();
        toast.error(error.detail?.message || 'Failed to save mapping');
      }
    } catch (err) {
      toast.error('Failed to save field mapping');
    } finally {
      setSaving(false);
    }
  };

  const getSuggestedTransform = (sfType) => {
    const typeTransforms = {
      'currency': 'decimal',
      'double': 'decimal',
      'percent': 'decimal',
      'int': 'integer',
      'date': 'date',
      'datetime': 'datetime',
      'boolean': 'boolean',
      'checkbox': 'boolean',
    };
    return typeTransforms[sfType] || null;
  };

  const handleSalesforceFieldChange = (fieldName) => {
    setNewMapping(prev => {
      const field = objectFields.find(f => f.name === fieldName);
      return {
        ...prev,
        salesforce_field: fieldName,
        transform_type: field ? getSuggestedTransform(field.type) : null
      };
    });
  };

  if (!isConnected) {
    return (
      <div className="sf-mapping-container">
        <div className="sf-mapping-empty">
          <span className="sf-mapping-empty-icon">🔗</span>
          <h3>Salesforce Not Connected</h3>
          <p>Connect to Salesforce to configure field mappings.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="sf-mapping-container">
      <div className="sf-mapping-header">
        <div className="sf-mapping-title">
          <h3>Field Mappings</h3>
          <p>Configure how Salesforce fields map to your CRM</p>
        </div>
        <button
          className="sf-mapping-add-btn"
          onClick={() => setShowAddForm(true)}
          disabled={objectFields.length === 0}
        >
          + Add Mapping
        </button>
      </div>

      {/* Object Selector */}
      <div className="sf-mapping-object-selector">
        <label>Salesforce Object</label>
        <select
          value={selectedObject}
          onChange={(e) => setSelectedObject(e.target.value)}
        >
          <option value="">Select an object...</option>
          {salesforceObjects.map(obj => (
            <option key={obj.name} value={obj.name}>
              {obj.label} ({obj.name})
            </option>
          ))}
        </select>
        {loadingFields && <span className="sf-mapping-loading">Loading fields...</span>}
      </div>

      {/* Current Mappings */}
      <div className="sf-mapping-list">
        {usingDefaults && (
          <div className="sf-mapping-defaults-notice">
            <span className="notice-icon">ℹ️</span>
            <span>Using default field mappings. Add custom mappings below to override.</span>
          </div>
        )}

        {loading ? (
          <div className="sf-mapping-loading-state">Loading mappings...</div>
        ) : currentMappings.length === 0 ? (
          <div className="sf-mapping-empty-list">
            No custom mappings configured. Using system defaults.
          </div>
        ) : (
          <div className="sf-mapping-table">
            <div className="sf-mapping-row sf-mapping-header-row">
              <div className="sf-mapping-cell">Salesforce Field</div>
              <div className="sf-mapping-cell sf-mapping-arrow"></div>
              <div className="sf-mapping-cell">CRM Field</div>
              <div className="sf-mapping-cell">Transform</div>
              <div className="sf-mapping-cell sf-mapping-status">Status</div>
            </div>
            {currentMappings.map((mapping, idx) => (
              <div key={idx} className="sf-mapping-row">
                <div className="sf-mapping-cell sf-field">
                  <span className="field-name">{mapping.salesforce_field}</span>
                </div>
                <div className="sf-mapping-cell sf-mapping-arrow">→</div>
                <div className="sf-mapping-cell crm-field">
                  <span className="field-name">{mapping.crm_field}</span>
                </div>
                <div className="sf-mapping-cell transform">
                  <span className={`transform-badge ${mapping.transform_type || 'none'}`}>
                    {mapping.transform_type || 'as-is'}
                  </span>
                </div>
                <div className="sf-mapping-cell sf-mapping-status">
                  <span className={`status-dot ${mapping.is_active !== false ? 'active' : 'inactive'}`}></span>
                  {mapping.is_custom ? 'Custom' : 'Default'}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Add Mapping Form */}
      {showAddForm && (
        <div className="sf-mapping-modal-overlay">
          <div className="sf-mapping-modal">
            <div className="sf-mapping-modal-header">
              <h4>Add Field Mapping</h4>
              <button className="sf-mapping-close" onClick={() => setShowAddForm(false)}>×</button>
            </div>

            <div className="sf-mapping-modal-body">
              <div className="sf-mapping-form-group">
                <label>Salesforce Field</label>
                <select
                  value={newMapping.salesforce_field}
                  onChange={(e) => handleSalesforceFieldChange(e.target.value)}
                >
                  <option value="">Select a field...</option>
                  {objectFields.map(field => (
                    <option key={field.name} value={field.name}>
                      {field.label} ({field.type})
                    </option>
                  ))}
                </select>
              </div>

              <div className="sf-mapping-arrow-container">
                <span className="sf-mapping-arrow-big">↓</span>
                <span className="sf-mapping-arrow-label">maps to</span>
              </div>

              <div className="sf-mapping-form-group">
                <label>CRM Field</label>
                <select
                  value={newMapping.crm_field}
                  onChange={(e) => setNewMapping({...newMapping, crm_field: e.target.value})}
                >
                  <option value="">Select a field...</option>
                  {CRM_LOAN_FIELDS.map(field => (
                    <option key={field.name} value={field.name}>
                      {field.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="sf-mapping-form-group">
                <label>Transform Type</label>
                <select
                  value={newMapping.transform_type || ''}
                  onChange={(e) => setNewMapping({...newMapping, transform_type: e.target.value || null})}
                >
                  {TRANSFORM_TYPES.map(type => (
                    <option key={type.value || 'none'} value={type.value || ''}>
                      {type.label}
                    </option>
                  ))}
                </select>
                <span className="sf-mapping-hint">
                  Transform converts the Salesforce value format to CRM format
                </span>
              </div>
            </div>

            <div className="sf-mapping-modal-footer">
              <button
                className="sf-mapping-cancel-btn"
                onClick={() => setShowAddForm(false)}
              >
                Cancel
              </button>
              <button
                className="sf-mapping-save-btn"
                onClick={handleAddMapping}
                disabled={saving || !newMapping.salesforce_field || !newMapping.crm_field}
              >
                {saving ? 'Saving...' : 'Save Mapping'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SalesforceFieldMapping;

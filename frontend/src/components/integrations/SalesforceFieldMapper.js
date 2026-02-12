import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { toast } from '../../utils/toast';

// Always use api.perenniaai.com for production API calls
const API_URL = window.location.hostname.includes('perenniaai.com')
  ? 'https://api.perenniaai.com'
  : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

// ---------------------------------------------------------------
// CANONICAL SLA MILESTONES
// ---------------------------------------------------------------
const SLA_MILESTONES = [
  // Lead Phase
  { key: "new_lead", label: "New Lead", subtitle: "Lead Received", target: "4 hours", triggerFrom: "Lead Created", phase: "lead", status: "active", suggestedSF: ["Lead_Received_Date__c", "CreatedDate", "Lead_Created_Date__c"] },
  { key: "attempted_contact", label: "Attempted Contact", subtitle: "Lead Received", target: "2 hours", triggerFrom: "Lead Created", phase: "lead", status: "active", suggestedSF: ["Attempted_Contact_Date__c", "First_Contact_Attempt__c", "Last_Contacted_Date__c"] },
  { key: "application_complete", label: "Application Complete", subtitle: null, target: "2 business days", triggerFrom: "Lead Created", phase: "lead", status: "active", suggestedSF: ["Application_Complete_Date__c", "App_Complete__c", "Application_Date__c"] },
  { key: "initial_consultation", label: "Initial Consultation", subtitle: "In for Consultation", target: "3 business days", triggerFrom: "Previous Milestone", phase: "lead", status: "active", suggestedSF: ["Initial_Consultation_Date__c", "Consultation_Date__c", "First_Meeting_Date__c"] },
  { key: "pre_qualified", label: "Pre-Qualified", subtitle: "Prequalified", target: "1 hour", triggerFrom: "Previous Milestone", phase: "lead", status: "active", suggestedSF: ["Pre_Qualified_Date__c", "Prequalification_Date__c", "PQ_Date__c"] },
  { key: "pre_approved", label: "Pre-Approved", subtitle: "Preapproved", target: "3 business days", triggerFrom: "Previous Milestone", phase: "lead", status: "active", suggestedSF: ["Pre_Approved_Date__c", "Preapproval_Date__c", "PA_Date__c"] },

  // Processing Phase
  { key: "contract_received", label: "Contract Received", subtitle: "Contract Received", target: "3 business days", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["Contract_Received_Date__c", "Contract_Date__c", "Purchase_Contract_Date__c"] },
  { key: "contact_received", label: "Contact Received", subtitle: "Contact Received", target: "3 business days", triggerFrom: "Disclosed Received", phase: "processing", status: "active", suggestedSF: ["Contact_Received_Date__c", "Borrower_Contact_Date__c"] },
  { key: "submitted_to_processing", label: "Submitted to Processing", subtitle: null, target: "3 business days", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["Submitted_To_Processing_Date__c", "Processing_Start_Date__c", "File_Submitted_Date__c"] },
  { key: "application_submission", label: "Application Submission", subtitle: null, target: "3 business days", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["Application_Submission_Date__c", "App_Submitted_Date__c", "Application_Submitted__c"] },
  { key: "document_collection", label: "Document Collection", subtitle: null, target: "5 business days", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["Document_Collection_Date__c", "Docs_Collected_Date__c", "Document_Package_Date__c"] },
  { key: "documents_requested", label: "Documents Requested", subtitle: null, target: "1 business day", triggerFrom: "Previous Milestone", phase: "processing", status: "inactive", suggestedSF: ["Documents_Requested_Date__c", "Doc_Request_Date__c", "Stips_Requested_Date__c"] },
  { key: "documents_received", label: "Documents Received", subtitle: "Documents Received", target: "5 business days", triggerFrom: "Documents Requested", phase: "processing", status: "active", suggestedSF: ["Documents_Received_Date__c", "Docs_Received_Date__c", "Doc_Package_Received__c"] },

  // Third Party Phase
  { key: "appraisal_ordered", label: "Appraisal Ordered", subtitle: "Appraisal Ordered", target: "1 business day", triggerFrom: "Disclosed", phase: "third_party", status: "active", suggestedSF: ["Appraisal_Ordered_Date__c", "Appraisal_Order_Date__c", "AMC_Order_Date__c"] },
  { key: "appraisal_received", label: "Appraisal Received", subtitle: "Appraisal Received", target: "7 business days", triggerFrom: "Appraisal Ordered", phase: "third_party", status: "active", suggestedSF: ["Appraisal_Received_Date__c", "Appraisal_Complete_Date__c", "Appraisal_Report_Date__c"] },
  { key: "insurance_ordered", label: "Insurance Ordered", subtitle: null, target: "10 business days", triggerFrom: "Disclosed", phase: "third_party", status: "active", suggestedSF: ["Insurance_Ordered_Date__c", "HOI_Ordered_Date__c", "Insurance_Order_Date__c"] },
  { key: "insurance_received", label: "Insurance Received", subtitle: "Insurance Received", target: "10 biz days before closing", triggerFrom: "Closing Date", phase: "third_party", status: "active", suggestedSF: ["Insurance_Received_Date__c", "HOI_Received_Date__c", "Insurance_Binder_Date__c"] },
  { key: "title_ordered", label: "Title Ordered", subtitle: "Title Ordered", target: "1 business day", triggerFrom: "Disclosed", phase: "third_party", status: "active", suggestedSF: ["Title_Ordered_Date__c", "Title_Order_Date__c", "Title_Request_Date__c"] },
  { key: "title_received", label: "Title Received", subtitle: null, target: "10 biz days before closing", triggerFrom: "Closing Date", phase: "third_party", status: "active", suggestedSF: ["Title_Received_Date__c", "Title_Report_Date__c", "Title_Commitment_Date__c"] },

  // Underwriting Phase
  { key: "submit_to_underwriting", label: "Submit to Underwriting", subtitle: "Submitted To UW", target: "3 business days", triggerFrom: "Previous Milestone", phase: "underwriting", status: "active", suggestedSF: ["Submitted_To_UW_Date__c", "UW_Submit_Date__c", "Submit_To_UW__c"] },
  { key: "underwriting_decision", label: "Underwriting Decision", subtitle: "UW Decision", target: "3 business days", triggerFrom: "Previous Milestone", phase: "underwriting", status: "active", suggestedSF: ["UW_Decision_Date__c", "Underwriting_Decision_Date__c", "Decision_Date__c"] },
  { key: "approved", label: "Approved", subtitle: "Approved", target: "3 business days", triggerFrom: "Previous Milestone", phase: "underwriting", status: "active", suggestedSF: ["Approved_Date__c", "Approval_Date__c", "UW_Approved_Date__c", "Conditional_Approval_Date__c"] },
  { key: "conditions_cleared", label: "Conditions Cleared", subtitle: "Conditions Cleared", target: "3 business days", triggerFrom: "Previous Milestone", phase: "underwriting", status: "active", suggestedSF: ["Conditions_Cleared_Date__c", "Conditions_Met_Date__c", "Stips_Cleared_Date__c"] },

  // Closing Phase
  { key: "clear_to_close", label: "Clear to Close", subtitle: "Clear To Close", target: "3 business days", triggerFrom: "Clear To Close", phase: "closing", status: "active", suggestedSF: ["Clear_To_Close_Date__c", "CTC_Date__c", "CTC__c"] },
  { key: "closing_docs_out", label: "Closing Docs Out", subtitle: null, target: "1 business day", triggerFrom: "Previous Milestone", phase: "closing", status: "active", suggestedSF: ["Closing_Docs_Out_Date__c", "CD_Sent_Date__c", "Docs_Out_Date__c", "Closing_Package_Sent__c"] },
  { key: "closing_date", label: "Closing Date", subtitle: null, target: "45 days", triggerFrom: "Clear To Close", phase: "closing", status: "inactive", suggestedSF: ["Closing_Date__c", "Close_Date__c", "CloseDate", "Settlement_Date__c"] },
  { key: "loan_funded", label: "Loan Funded", subtitle: null, target: "1 business day", triggerFrom: "Previous Milestone", phase: "closing", status: "active", suggestedSF: ["Funding_Date__c", "Funded_Date__c", "Fund_Date__c", "Loan_Funded_Date__c"] },
];

const PHASES = {
  lead: { label: "Lead", icon: "\uD83C\uDFAF", color: "#6366f1", gradient: "linear-gradient(135deg, #6366f1, #818cf8)" },
  processing: { label: "Processing", icon: "\uD83D\uDCCB", color: "#0891b2", gradient: "linear-gradient(135deg, #0891b2, #22d3ee)" },
  third_party: { label: "Third Party", icon: "\uD83C\uDFD7\uFE0F", color: "#d97706", gradient: "linear-gradient(135deg, #d97706, #fbbf24)" },
  underwriting: { label: "Underwriting", icon: "\uD83D\uDD0D", color: "#7c3aed", gradient: "linear-gradient(135deg, #7c3aed, #a78bfa)" },
  closing: { label: "Closing", icon: "\uD83C\uDFE0", color: "#059669", gradient: "linear-gradient(135deg, #059669, #34d399)" },
};

// CRM Standard Fields (non-SLA) by stage
const CRM_FIELDS = {
  lead: {
    label: "Lead",
    icon: "\uD83C\uDFAF",
    color: "#6366f1",
    sections: [
      {
        title: "Contact Info",
        fields: [
          { key: "lead_first_name", label: "First Name", type: "string", required: true, suggestedSF: ["FirstName", "First_Name__c"] },
          { key: "lead_last_name", label: "Last Name", type: "string", required: true, suggestedSF: ["LastName", "Last_Name__c"] },
          { key: "lead_email", label: "Email", type: "email", required: true, suggestedSF: ["Email", "Email__c"] },
          { key: "lead_phone", label: "Phone", type: "phone", required: false, suggestedSF: ["Phone", "MobilePhone", "Phone__c"] },
          { key: "lead_company", label: "Company", type: "string", required: false, suggestedSF: ["Company"] },
        ],
      },
      {
        title: "Lead Details",
        fields: [
          { key: "lead_source", label: "Lead Source", type: "picklist", required: false, suggestedSF: ["LeadSource", "Lead_Source__c"] },
          { key: "lead_status", label: "Lead Status", type: "picklist", required: true, suggestedSF: ["Status", "Lead_Status__c"] },
          { key: "referral_partner", label: "Referral Partner", type: "string", required: false, suggestedSF: ["Referral_Partner__c", "Referred_By__c"] },
          { key: "lead_state", label: "State", type: "string", required: false, suggestedSF: ["State", "State__c"] },
          { key: "lead_city", label: "City", type: "string", required: false, suggestedSF: ["City", "City__c"] },
        ],
      },
    ],
  },
  active_loan: {
    label: "Active Loan",
    icon: "\uD83D\uDCCB",
    color: "#059669",
    sections: [
      {
        title: "Borrower",
        fields: [
          { key: "borrower_first_name", label: "First Name", type: "string", required: true, suggestedSF: ["FirstName", "Borrower_First_Name__c"] },
          { key: "borrower_last_name", label: "Last Name", type: "string", required: true, suggestedSF: ["LastName", "Borrower_Last_Name__c"] },
          { key: "borrower_email", label: "Email", type: "email", required: true, suggestedSF: ["Email", "Borrower_Email__c"] },
          { key: "borrower_phone", label: "Phone", type: "phone", required: false, suggestedSF: ["Phone", "MobilePhone"] },
          { key: "borrower_ssn", label: "SSN", type: "sensitive", required: true, suggestedSF: ["SSN__c", "Social__c"] },
          { key: "borrower_dob", label: "Date of Birth", type: "date", required: true, suggestedSF: ["Birthdate", "DOB__c"] },
          { key: "mailing_address", label: "Mailing Address", type: "string", required: false, suggestedSF: ["MailingStreet"] },
          { key: "mailing_city", label: "Mailing City", type: "string", required: false, suggestedSF: ["MailingCity"] },
          { key: "mailing_state", label: "Mailing State", type: "string", required: false, suggestedSF: ["MailingState"] },
          { key: "mailing_zip", label: "Mailing Zip", type: "string", required: false, suggestedSF: ["MailingPostalCode"] },
        ],
      },
      {
        title: "Loan Details",
        fields: [
          { key: "loan_amount", label: "Loan Amount", type: "currency", required: true, suggestedSF: ["Amount", "Loan_Amount__c"] },
          { key: "loan_purpose", label: "Loan Purpose", type: "picklist", required: true, suggestedSF: ["Loan_Purpose__c", "Purpose__c"] },
          { key: "loan_type", label: "Loan Type", type: "picklist", required: true, suggestedSF: ["Loan_Type__c", "Product_Type__c"] },
          { key: "interest_rate", label: "Interest Rate", type: "decimal", required: false, suggestedSF: ["Interest_Rate__c", "Rate__c", "Note_Rate__c"] },
          { key: "loan_term", label: "Loan Term", type: "integer", required: false, suggestedSF: ["Loan_Term__c", "Term__c"] },
          { key: "ltv", label: "LTV", type: "decimal", required: false, suggestedSF: ["LTV__c"] },
          { key: "dti", label: "DTI", type: "decimal", required: false, suggestedSF: ["DTI__c"] },
          { key: "loan_stage", label: "Loan Stage", type: "picklist", required: true, suggestedSF: ["StageName", "Stage__c"] },
          { key: "assigned_lo", label: "Assigned LO", type: "user", required: true, suggestedSF: ["OwnerId", "Loan_Officer__c"] },
          { key: "assigned_processor", label: "Processor", type: "user", required: false, suggestedSF: ["Processor__c"] },
        ],
      },
      {
        title: "Property",
        fields: [
          { key: "property_address", label: "Property Address", type: "string", required: true, suggestedSF: ["Property_Address__c"] },
          { key: "property_city", label: "City", type: "string", required: true, suggestedSF: ["Property_City__c"] },
          { key: "property_state", label: "State", type: "string", required: true, suggestedSF: ["Property_State__c"] },
          { key: "property_zip", label: "Zip", type: "string", required: true, suggestedSF: ["Property_Zip__c"] },
          { key: "property_type", label: "Property Type", type: "picklist", required: true, suggestedSF: ["Property_Type__c"] },
          { key: "occupancy_type", label: "Occupancy", type: "picklist", required: true, suggestedSF: ["Occupancy_Type__c"] },
          { key: "estimated_value", label: "Estimated Value", type: "currency", required: false, suggestedSF: ["Estimated_Value__c", "Purchase_Price__c"] },
          { key: "appraisal_value", label: "Appraisal Value", type: "currency", required: false, suggestedSF: ["Appraisal_Value__c"] },
        ],
      },
    ],
  },
  mum: {
    label: "MUM Clients",
    icon: "\uD83C\uDFE0",
    color: "#d97706",
    sections: [
      {
        title: "Client Profile",
        fields: [
          { key: "mum_first_name", label: "First Name", type: "string", required: true, suggestedSF: ["FirstName"] },
          { key: "mum_last_name", label: "Last Name", type: "string", required: true, suggestedSF: ["LastName"] },
          { key: "mum_email", label: "Email", type: "email", required: true, suggestedSF: ["Email"] },
          { key: "mum_phone", label: "Phone", type: "phone", required: false, suggestedSF: ["Phone"] },
          { key: "mum_property_address", label: "Property Address", type: "string", required: true, suggestedSF: ["Property_Address__c", "MailingStreet"] },
        ],
      },
      {
        title: "Loan Summary",
        fields: [
          { key: "original_loan_amount", label: "Original Loan Amount", type: "currency", required: true, suggestedSF: ["Amount", "Original_Loan_Amount__c"] },
          { key: "current_rate", label: "Current Rate", type: "decimal", required: false, suggestedSF: ["Interest_Rate__c", "Current_Rate__c"] },
          { key: "mum_loan_type", label: "Loan Type", type: "picklist", required: true, suggestedSF: ["Loan_Type__c"] },
          { key: "servicer", label: "Servicer", type: "string", required: false, suggestedSF: ["Servicer__c"] },
          { key: "maturity_date", label: "Maturity Date", type: "date", required: false, suggestedSF: ["Maturity_Date__c"] },
        ],
      },
      {
        title: "Retention & Monitoring",
        fields: [
          { key: "estimated_home_value", label: "Est. Home Value", type: "currency", required: false, suggestedSF: ["Current_Home_Value__c", "Estimated_Value__c"] },
          { key: "estimated_equity", label: "Est. Equity", type: "currency", required: false, suggestedSF: ["Estimated_Equity__c"] },
          { key: "current_ltv", label: "Current LTV", type: "decimal", required: false, suggestedSF: ["Current_LTV__c"] },
          { key: "refi_score", label: "Refi Opportunity Score", type: "integer", required: false, suggestedSF: ["Refi_Score__c"] },
        ],
      },
    ],
  },
};

// ---------------------------------------------------------------
// UI Sub-components
// ---------------------------------------------------------------

const TypeBadge = ({ type }) => {
  const c = {
    string: { bg: "#f0f9ff", fg: "#0369a1", t: "Text" },
    email: { bg: "#fdf4ff", fg: "#a21caf", t: "Email" },
    phone: { bg: "#fdf4ff", fg: "#a21caf", t: "Phone" },
    picklist: { bg: "#fefce8", fg: "#a16207", t: "Picklist" },
    currency: { bg: "#f0fdf4", fg: "#15803d", t: "Currency" },
    decimal: { bg: "#f0fdf4", fg: "#15803d", t: "Decimal" },
    integer: { bg: "#f0fdf4", fg: "#15803d", t: "Number" },
    datetime: { bg: "#fff7ed", fg: "#c2410c", t: "DateTime" },
    date: { bg: "#fff7ed", fg: "#c2410c", t: "Date" },
    user: { bg: "#f5f3ff", fg: "#6d28d9", t: "User" },
    sensitive: { bg: "#fef2f2", fg: "#b91c1c", t: "PII" },
  }[type] || { bg: "#f3f4f6", fg: "#374151", t: type };
  return <span style={{ fontSize: 10, fontWeight: 600, padding: "2px 6px", borderRadius: 4, background: c.bg, color: c.fg, letterSpacing: "0.03em", textTransform: "uppercase", whiteSpace: "nowrap" }}>{c.t}</span>;
};

const SearchableSelect = ({ value, onChange, suggestedSF, sfFields, disabled, placeholderText }) => {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);
  useEffect(() => { if (open && inputRef.current) inputRef.current.focus(); }, [open]);

  const filtered = useMemo(() => {
    const fields = sfFields || [];
    const q = search.toLowerCase();
    let res = fields.filter(f => f.apiName.toLowerCase().includes(q) || f.label.toLowerCase().includes(q) || f.object.toLowerCase().includes(q));
    const sugSet = new Set((suggestedSF || []).map(s => s.toLowerCase()));
    res.sort((a, b) => {
      const aS = sugSet.has(a.apiName.toLowerCase()) ? 0 : 1;
      const bS = sugSet.has(b.apiName.toLowerCase()) ? 0 : 1;
      return aS !== bS ? aS - bS : a.apiName.localeCompare(b.apiName);
    });
    return res.slice(0, 40);
  }, [search, suggestedSF, sfFields]);

  const sel = value ? (sfFields || []).find(f => `${f.object}.${f.apiName}` === value) : null;

  return (
    <div ref={ref} style={{ position: "relative", flex: 1, minWidth: 0 }}>
      <button onClick={() => !disabled && setOpen(!open)} disabled={disabled} style={{
        width: "100%", padding: "7px 10px", border: value ? "1.5px solid #059669" : "1.5px solid #d1d5db",
        borderRadius: 6, background: value ? "#f0fdf4" : "#fff", cursor: disabled ? "not-allowed" : "pointer",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        fontSize: 13, color: value ? "#065f46" : "#9ca3af", fontFamily: "inherit", minHeight: 34, transition: "all 0.15s",
        opacity: disabled ? 0.5 : 1,
      }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {sel ? (<><span style={{ color: "#9ca3af", fontSize: 11 }}>{sel.object}.</span><span style={{ fontWeight: 600, color: "#065f46" }}>{sel.apiName}</span></>) : (disabled ? (placeholderText || "Loading fields...") : "Select Salesforce field...")}
        </span>
        <span style={{ fontSize: 9, marginLeft: 4, flexShrink: 0, color: "#9ca3af" }}>{open ? "\u25B2" : "\u25BC"}</span>
      </button>

      {open && (
        <div style={{ position: "absolute", top: "calc(100% + 3px)", left: 0, right: 0, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, boxShadow: "0 12px 40px rgba(0,0,0,0.15)", zIndex: 1000, maxHeight: 300, display: "flex", flexDirection: "column" }}>
          <div style={{ padding: 6, borderBottom: "1px solid #f3f4f6" }}>
            <input ref={inputRef} type="text" placeholder="Search fields..." value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: "100%", padding: "7px 10px", border: "1.5px solid #e5e7eb", borderRadius: 6, fontSize: 12, outline: "none", fontFamily: "inherit", boxSizing: "border-box" }}
              onFocus={e => { e.target.style.borderColor = "#6366f1"; }} onBlur={e => { e.target.style.borderColor = "#e5e7eb"; }} />
          </div>
          <div style={{ overflowY: "auto", flex: 1 }}>
            {filtered.length === 0 && <div style={{ padding: 14, textAlign: "center", color: "#9ca3af", fontSize: 12 }}>No fields found</div>}
            {filtered.map(f => {
              const k = `${f.object}.${f.apiName}`;
              const isSug = (suggestedSF || []).some(s => s.toLowerCase() === f.apiName.toLowerCase());
              return (
                <button key={k} onClick={() => { onChange(k); setOpen(false); setSearch(""); }}
                  style={{ width: "100%", padding: "7px 10px", border: "none", background: value === k ? "#ede9fe" : isSug && !search ? "#f0fdf4" : "transparent", cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontSize: 12, textAlign: "left", fontFamily: "inherit", borderBottom: "1px solid #f9fafb" }}
                  onMouseEnter={e => { if (value !== k) e.currentTarget.style.background = "#f3f4f6"; }}
                  onMouseLeave={e => { if (value !== k) e.currentTarget.style.background = isSug && !search ? "#f0fdf4" : "transparent"; }}>
                  <span style={{ color: "#9ca3af", fontSize: 10, minWidth: 72, flexShrink: 0 }}>{f.object}</span>
                  <span style={{ fontWeight: 500, color: "#111827", flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.apiName}</span>
                  {isSug && <span style={{ fontSize: 8, fontWeight: 800, color: "#059669", background: "#d1fae5", padding: "1px 5px", borderRadius: 3, flexShrink: 0 }}>MATCH</span>}
                  {value === k && <span style={{ color: "#6366f1", fontWeight: 700 }}>{"\u2713"}</span>}
                </button>
              );
            })}
          </div>
          {value && (
            <button onClick={() => { onChange(null); setOpen(false); }} style={{ width: "100%", padding: "7px", border: "none", borderTop: "1px solid #e5e7eb", background: "#fef2f2", cursor: "pointer", fontSize: 11, color: "#dc2626", fontWeight: 600, fontFamily: "inherit" }}>
              {"\u2715"} Clear
            </button>
          )}
        </div>
      )}
    </div>
  );
};

// ---------------------------------------------------------------
// Main Component
// ---------------------------------------------------------------
export default function SalesforceFieldMapper({ isConnected, onMappingSaved }) {
  const [tab, setTab] = useState("sla");
  const [activeStage, setActiveStage] = useState("lead");
  const [activePhase, setActivePhase] = useState("all");
  const [mappings, setMappings] = useState({});
  const [expandedSections, setExpandedSections] = useState(() => {
    const init = {};
    for (const s of Object.values(CRM_FIELDS)) for (const sec of s.sections) init[sec.title] = true;
    for (const p of Object.keys(PHASES)) init[`sla-${p}`] = true;
    return init;
  });
  const [filterUnmapped, setFilterUnmapped] = useState(false);
  const [sfFields, setSfFields] = useState([]);
  const [loadingSfFields, setLoadingSfFields] = useState(false);
  const [loadingMappings, setLoadingMappings] = useState(false);
  const [saving, setSaving] = useState(false);

  // Fetch Salesforce schema fields on mount
  useEffect(() => {
    if (!isConnected) return;
    const fetchSchema = async () => {
      setLoadingSfFields(true);
      try {
        const token = localStorage.getItem('token');
        const objectsRes = await fetch(`${API_URL}/api/integrations/salesforce/schema/objects`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (!objectsRes.ok) throw new Error('Failed to load SF objects');
        const objectsData = await objectsRes.json();
        const relevantObjects = objectsData.objects || objectsData.relevant_objects || [];

        // Fetch fields for each relevant object in parallel
        const allFields = [];
        const fieldPromises = relevantObjects.map(async (obj) => {
          try {
            const res = await fetch(`${API_URL}/api/integrations/salesforce/schema/objects/${obj.name}`, {
              headers: { 'Authorization': `Bearer ${token}` }
            });
            if (res.ok) {
              const data = await res.json();
              const fields = data.fields || [];
              for (const f of fields) {
                allFields.push({
                  object: obj.name,
                  apiName: f.name,
                  label: f.label || f.name.replace(/__c$/i, "").replace(/_/g, " "),
                  custom: f.name.endsWith("__c"),
                });
              }
            }
          } catch (err) {
            console.error(`Failed to fetch fields for ${obj.name}:`, err);
          }
        });
        await Promise.all(fieldPromises);
        setSfFields(allFields);
      } catch (err) {
        console.error('Failed to load Salesforce schema:', err);
        toast.error('Failed to load Salesforce fields');
      } finally {
        setLoadingSfFields(false);
      }
    };
    fetchSchema();
  }, [isConnected]);

  // Load existing mappings on mount
  useEffect(() => {
    if (!isConnected) return;
    const fetchMappings = async () => {
      setLoadingMappings(true);
      try {
        const token = localStorage.getItem('token');
        const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings`, {
          headers: { 'Authorization': `Bearer ${token}` }
        });
        if (res.ok) {
          const data = await res.json();
          const loaded = {};
          for (const m of (data.mappings || [])) {
            const sfValue = `${m.source_object}.${m.source_field}`;
            if (m.mapping_category === 'sla_milestone') {
              loaded[`sla_${m.target_field}`] = sfValue;
            } else if (m.mapping_category === 'crm_field') {
              loaded[m.target_field] = sfValue;
            } else {
              // Legacy mappings without category — use target_field as key
              loaded[m.target_field] = sfValue;
            }
          }
          setMappings(loaded);
        }
      } catch (err) {
        console.error('Failed to load existing mappings:', err);
      } finally {
        setLoadingMappings(false);
      }
    };
    fetchMappings();
  }, [isConnected]);

  const setMapping = useCallback((key, val) => {
    setMappings(prev => { const n = { ...prev }; if (val === null) delete n[key]; else n[key] = val; return n; });
  }, []);

  const toggle = (k) => setExpandedSections(p => ({ ...p, [k]: !p[k] }));

  // Save all mappings to backend
  const handleSaveAll = useCallback(async () => {
    setSaving(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/integrations/salesforce/mappings/save-all`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ mappings })
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`${data.mappings_saved} field mappings saved`);
        if (onMappingSaved) onMappingSaved();
      } else {
        const err = await res.json();
        toast.error(err.detail || 'Failed to save mappings');
      }
    } catch (err) {
      toast.error('Failed to save mappings');
    } finally {
      setSaving(false);
    }
  }, [mappings, onMappingSaved]);

  // SLA Stats
  const slaByPhase = useMemo(() => {
    const groups = {};
    for (const p of Object.keys(PHASES)) groups[p] = SLA_MILESTONES.filter(m => m.phase === p);
    return groups;
  }, []);

  const slaStats = useMemo(() => {
    const s = { total: SLA_MILESTONES.length, mapped: 0, active: 0, activeMapped: 0 };
    for (const m of SLA_MILESTONES) {
      if (mappings[`sla_${m.key}`]) s.mapped++;
      if (m.status === "active") { s.active++; if (mappings[`sla_${m.key}`]) s.activeMapped++; }
    }
    return s;
  }, [mappings]);

  // Field Stats per stage
  const fieldStats = useMemo(() => {
    const stats = {};
    for (const [key, stage] of Object.entries(CRM_FIELDS)) {
      let total = 0, mapped = 0, req = 0, reqMapped = 0;
      for (const sec of stage.sections) for (const f of sec.fields) {
        total++; if (mappings[f.key]) mapped++;
        if (f.required) { req++; if (mappings[f.key]) reqMapped++; }
      }
      stats[key] = { total, mapped, req, reqMapped };
    }
    return stats;
  }, [mappings]);

  const totalMapped = slaStats.mapped + Object.values(fieldStats).reduce((s, v) => s + v.mapped, 0);
  const totalFields = slaStats.total + Object.values(fieldStats).reduce((s, v) => s + v.total, 0);

  // Auto-map helpers
  const autoMap = useCallback((fields, prefix = "") => {
    setMappings(prev => {
      const n = { ...prev };
      for (const f of fields) {
        const k = prefix ? `${prefix}${f.key}` : f.key;
        if (n[k]) continue;
        const sug = f.suggestedSF || [];
        for (const s of sug) {
          const match = sfFields.find(x => x.apiName.toLowerCase() === s.toLowerCase());
          if (match) { n[k] = `${match.object}.${match.apiName}`; break; }
        }
      }
      return n;
    });
  }, [sfFields]);

  const autoMapPhase = useCallback((phase) => {
    const milestones = phase === "all" ? SLA_MILESTONES : slaByPhase[phase] || [];
    autoMap(milestones, "sla_");
  }, [autoMap, slaByPhase]);

  const autoMapSection = useCallback((fields) => autoMap(fields, ""), [autoMap]);

  // Filtered SLA milestones
  const visibleMilestones = useMemo(() => {
    let list = activePhase === "all" ? SLA_MILESTONES : slaByPhase[activePhase] || [];
    if (filterUnmapped) list = list.filter(m => !mappings[`sla_${m.key}`]);
    return list;
  }, [activePhase, filterUnmapped, mappings, slaByPhase]);

  // Group by phase for display
  const groupedMilestones = useMemo(() => {
    const groups = {};
    for (const m of visibleMilestones) {
      if (!groups[m.phase]) groups[m.phase] = [];
      groups[m.phase].push(m);
    }
    return groups;
  }, [visibleMilestones]);

  if (!isConnected) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "#6b7280" }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>{"\uD83D\uDD17"}</div>
        <h3 style={{ margin: 0, color: "#374151" }}>Salesforce Not Connected</h3>
        <p>Connect to Salesforce first to configure field mappings.</p>
      </div>
    );
  }

  if (loadingMappings) {
    return (
      <div style={{ padding: 40, textAlign: "center", color: "#6b7280" }}>
        <div style={{ fontSize: 14 }}>Loading field mappings...</div>
      </div>
    );
  }

  const fieldsDisabled = loadingSfFields || sfFields.length === 0;
  const fieldsPlaceholder = loadingSfFields ? "Loading fields..." : (sfFields.length === 0 ? "Run Schema Discovery first" : "Select Salesforce field...");

  return (
    <div style={{ fontFamily: "'DM Sans', 'Segoe UI', system-ui, sans-serif" }}>
      {/* HEADER */}
      <div style={{ background: "linear-gradient(135deg, #0f172a 0%, #1e293b 100%)", padding: "16px 24px", borderRadius: "8px 8px 0 0", borderBottom: "3px solid #6366f1" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 30, height: 30, borderRadius: 8, background: "linear-gradient(135deg, #6366f1, #8b5cf6)", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14 }}>{"\u26A1"}</div>
            <div>
              <h3 style={{ color: "#fff", fontSize: 16, fontWeight: 700, margin: 0 }}>Salesforce Field Mapper</h3>
              <p style={{ color: "#64748b", fontSize: 11, margin: 0 }}>Map CRM fields & SLA milestones {"\u2192"} Salesforce</p>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            {loadingSfFields && <span style={{ color: "#fbbf24", fontSize: 11 }}>Loading SF fields...</span>}
            <div style={{ textAlign: "right" }}>
              <div style={{ color: "#e2e8f0", fontSize: 20, fontWeight: 700 }}>{totalMapped}<span style={{ color: "#64748b", fontSize: 13 }}>/{totalFields}</span></div>
              <div style={{ color: "#64748b", fontSize: 10 }}>Total Mapped</div>
            </div>
            <button onClick={handleSaveAll} disabled={saving}
              style={{ padding: "8px 16px", borderRadius: 7, border: "1.5px solid #059669", background: "transparent", color: "#34d399", fontSize: 12, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer", fontFamily: "inherit", opacity: saving ? 0.6 : 1 }}>
              {saving ? "Saving..." : "\uD83D\uDCBE Save All"}
            </button>
          </div>
        </div>
      </div>

      {/* MAIN TABS */}
      <div style={{ padding: "0 24px", background: "#f8fafc" }}>
        <div style={{ display: "flex", gap: 0, borderBottom: "2px solid #e2e8f0", marginBottom: 16, paddingTop: 12 }}>
          {[
            { key: "sla", label: `SLA Milestones (${slaStats.mapped}/${slaStats.total})`, icon: "\uD83D\uDD34" },
            { key: "fields", label: `CRM Fields (${Object.values(fieldStats).reduce((s,v) => s+v.mapped, 0)}/${Object.values(fieldStats).reduce((s,v) => s+v.total, 0)})`, icon: "\uD83D\uDCCB" },
          ].map(t => (
            <button key={t.key} onClick={() => setTab(t.key)} style={{
              padding: "10px 20px", border: "none", borderBottom: tab === t.key ? "3px solid #6366f1" : "3px solid transparent",
              background: "transparent", cursor: "pointer", fontSize: 13, fontWeight: 700, fontFamily: "inherit",
              color: tab === t.key ? "#6366f1" : "#6b7280", marginBottom: -2, transition: "all 0.15s",
            }}>{t.icon} {t.label}</button>
          ))}
        </div>

        {/* SLA MILESTONES TAB */}
        {tab === "sla" && (
          <div>
            {/* Phase filter pills */}
            <div style={{ display: "flex", gap: 6, marginBottom: 12, flexWrap: "wrap", alignItems: "center" }}>
              <button onClick={() => setActivePhase("all")} style={{
                padding: "6px 14px", borderRadius: 100, border: activePhase === "all" ? "1.5px solid #6366f1" : "1.5px solid #d1d5db",
                background: activePhase === "all" ? "#eef2ff" : "#fff", color: activePhase === "all" ? "#4338ca" : "#6b7280",
                fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
              }}>All ({SLA_MILESTONES.length})</button>
              {Object.entries(PHASES).map(([k, p]) => {
                const count = slaByPhase[k]?.length || 0;
                const mapped = (slaByPhase[k] || []).filter(m => mappings[`sla_${m.key}`]).length;
                return (
                  <button key={k} onClick={() => setActivePhase(k)} style={{
                    padding: "6px 14px", borderRadius: 100,
                    border: activePhase === k ? `1.5px solid ${p.color}` : "1.5px solid #d1d5db",
                    background: activePhase === k ? `${p.color}11` : "#fff",
                    color: activePhase === k ? p.color : "#6b7280",
                    fontSize: 12, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
                  }}>{p.icon} {p.label} ({mapped}/{count})</button>
                );
              })}
              <span style={{ width: 1, height: 20, background: "#e5e7eb" }} />
              <button onClick={() => setFilterUnmapped(!filterUnmapped)} style={{
                padding: "6px 12px", borderRadius: 100, border: filterUnmapped ? "1.5px solid #f59e0b" : "1.5px solid #d1d5db",
                background: filterUnmapped ? "#fffbeb" : "#fff", color: filterUnmapped ? "#d97706" : "#9ca3af",
                fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
              }}>{filterUnmapped ? "\u2713 " : ""}Unmapped only</button>
              <button onClick={() => autoMapPhase(activePhase)} disabled={fieldsDisabled} style={{
                padding: "6px 14px", borderRadius: 100, border: "none", background: fieldsDisabled ? "#94a3b8" : "#6366f1", color: "#fff",
                fontSize: 11, fontWeight: 700, cursor: fieldsDisabled ? "not-allowed" : "pointer", fontFamily: "inherit", marginLeft: "auto",
              }}>{"\u26A1"} Auto-Map All</button>
            </div>

            {/* SLA coverage bar */}
            <div style={{ background: "#fff", borderRadius: 8, padding: "10px 14px", marginBottom: 12, border: "1px solid #e2e8f0", display: "flex", gap: 20, alignItems: "center" }}>
              <div style={{ flex: 1 }}>
                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 3 }}>
                  <span style={{ fontSize: 11, fontWeight: 600, color: "#374151" }}>SLA Coverage</span>
                  <span style={{ fontSize: 11, fontWeight: 700, color: slaStats.mapped === slaStats.total ? "#059669" : "#dc2626" }}>{slaStats.total > 0 ? Math.round(slaStats.mapped / slaStats.total * 100) : 0}%</span>
                </div>
                <div style={{ height: 5, background: "#fee2e2", borderRadius: 100, overflow: "hidden" }}>
                  <div style={{ height: "100%", width: `${slaStats.total > 0 ? (slaStats.mapped / slaStats.total) * 100 : 0}%`, background: "linear-gradient(90deg, #dc2626, #059669)", borderRadius: 100, transition: "width 0.4s" }} />
                </div>
              </div>
              <div style={{ width: 1, height: 28, background: "#e2e8f0" }} />
              <div style={{ textAlign: "center" }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: slaStats.activeMapped === slaStats.active ? "#059669" : "#f59e0b" }}>{slaStats.activeMapped}/{slaStats.active}</div>
                <div style={{ fontSize: 9, color: "#6b7280" }}>Active SLAs</div>
              </div>
            </div>

            {/* Milestone rows grouped by phase */}
            {Object.entries(groupedMilestones).map(([phase, milestones]) => {
              const p = PHASES[phase];
              const sectionKey = `sla-${phase}`;
              const expanded = expandedSections[sectionKey] !== false;
              const mapped = milestones.filter(m => mappings[`sla_${m.key}`]).length;
              return (
                <div key={phase} style={{ marginBottom: 6, background: "#fff", borderRadius: 8, border: "1px solid #e2e8f0", overflow: "hidden" }}>
                  <button onClick={() => toggle(sectionKey)} style={{
                    width: "100%", padding: "10px 14px", border: "none", background: "#fafafa", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "space-between", fontFamily: "inherit",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, color: "#9ca3af" }}>{expanded ? "\u25BE" : "\u25B8"}</span>
                      <span style={{ fontSize: 14 }}>{p.icon}</span>
                      <span style={{ fontWeight: 700, fontSize: 13, color: p.color }}>{p.label}</span>
                      <span style={{ fontSize: 11, color: "#9ca3af" }}>({milestones.length} milestones)</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: mapped === milestones.length ? "#059669" : "#6b7280", background: mapped === milestones.length ? "#d1fae5" : "#f3f4f6", padding: "2px 8px", borderRadius: 100 }}>
                        {mapped}/{milestones.length}
                      </span>
                      {mapped < milestones.length && !fieldsDisabled && (
                        <button onClick={e => { e.stopPropagation(); autoMap(milestones, "sla_"); }}
                          style={{ padding: "3px 8px", borderRadius: 4, border: "1px solid #d1d5db", background: "#fff", fontSize: 10, fontWeight: 700, color: "#6366f1", cursor: "pointer", fontFamily: "inherit" }}>
                          Accept All
                        </button>
                      )}
                    </div>
                  </button>

                  {expanded && milestones.map((m) => {
                    const k = `sla_${m.key}`;
                    const isMapped = !!mappings[k];
                    return (
                      <div key={m.key} style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "9px 14px",
                        borderTop: "1px solid #f3f4f6",
                        background: isMapped ? "#fafffe" : "transparent",
                      }}>
                        <div style={{
                          width: 7, height: 7, borderRadius: 100, flexShrink: 0,
                          background: isMapped ? "#059669" : m.status === "active" ? "#f59e0b" : "#d1d5db",
                          boxShadow: isMapped ? "0 0 0 3px #d1fae5" : m.status === "active" && !isMapped ? "0 0 0 3px #fef3c7" : "none",
                        }} />
                        <div style={{ width: 185, flexShrink: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                            <span style={{ fontWeight: 600, fontSize: 13, color: "#111827" }}>{m.label}</span>
                            {m.status === "inactive" && <span style={{ fontSize: 8, fontWeight: 700, color: "#9ca3af", background: "#f3f4f6", padding: "1px 4px", borderRadius: 3 }}>INACTIVE</span>}
                          </div>
                          {m.subtitle && <div style={{ fontSize: 10, color: "#9ca3af" }}>{m.subtitle}</div>}
                        </div>
                        <div style={{ width: 110, flexShrink: 0 }}>
                          <span style={{
                            fontSize: 10, fontWeight: 700, padding: "3px 7px", borderRadius: 4,
                            background: m.target.includes("hour") ? "#fef2f2" : "#fff7ed",
                            color: m.target.includes("hour") ? "#dc2626" : "#c2410c",
                            whiteSpace: "nowrap",
                          }}>{m.target}</span>
                        </div>
                        <div style={{ width: 120, flexShrink: 0, fontSize: 11, color: "#6b7280" }}>
                          {"\u2190"} {m.triggerFrom}
                        </div>
                        <div style={{ color: isMapped ? "#059669" : "#d1d5db", fontSize: 13, flexShrink: 0 }}>{"\u2192"}</div>
                        <SearchableSelect
                          value={mappings[k] || null}
                          onChange={val => setMapping(k, val)}
                          suggestedSF={m.suggestedSF}
                          sfFields={sfFields}
                          disabled={fieldsDisabled}
                          placeholderText={fieldsPlaceholder}
                        />
                      </div>
                    );
                  })}
                </div>
              );
            })}

            {visibleMilestones.length === 0 && (
              <div style={{ textAlign: "center", padding: 40, color: "#9ca3af" }}>
                <div style={{ fontSize: 32, marginBottom: 8 }}>{"\u2705"}</div>
                <div style={{ fontSize: 14, fontWeight: 600 }}>All SLA milestones are mapped!</div>
              </div>
            )}
          </div>
        )}

        {/* CRM FIELDS TAB */}
        {tab === "fields" && (
          <div>
            {/* Stage tabs */}
            <div style={{ display: "flex", gap: 6, marginBottom: 12 }}>
              {Object.entries(CRM_FIELDS).map(([k, s]) => {
                const st = fieldStats[k];
                const pct = st.total > 0 ? Math.round(st.mapped / st.total * 100) : 0;
                return (
                  <button key={k} onClick={() => setActiveStage(k)} style={{
                    flex: 1, padding: "12px 14px", border: activeStage === k ? `2px solid ${s.color}` : "2px solid #e2e8f0",
                    borderRadius: 10, background: "#fff", cursor: "pointer", fontFamily: "inherit",
                    boxShadow: activeStage === k ? `0 3px 10px ${s.color}18` : "none", position: "relative", overflow: "hidden",
                  }}>
                    <div style={{ position: "absolute", bottom: 0, left: 0, width: `${pct}%`, height: 3, background: s.color, transition: "width 0.4s" }} />
                    <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
                      <span style={{ fontSize: 16 }}>{s.icon}</span>
                      <span style={{ fontWeight: 700, fontSize: 13, color: activeStage === k ? s.color : "#374151" }}>{s.label}</span>
                    </div>
                    <div style={{ fontSize: 11, color: "#6b7280" }}>{st.mapped}/{st.total} {"\u2022"} {st.reqMapped}/{st.req} req</div>
                  </button>
                );
              })}
            </div>

            {/* Toolbar */}
            <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 10 }}>
              <button onClick={() => setFilterUnmapped(!filterUnmapped)} style={{
                padding: "5px 12px", borderRadius: 6, border: filterUnmapped ? "1.5px solid #f59e0b" : "1.5px solid #d1d5db",
                background: filterUnmapped ? "#fffbeb" : "#fff", color: filterUnmapped ? "#d97706" : "#9ca3af",
                fontSize: 11, fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
              }}>{filterUnmapped ? "\u2713 " : ""}Unmapped only</button>
              <button onClick={() => { for (const sec of CRM_FIELDS[activeStage].sections) autoMapSection(sec.fields); }} disabled={fieldsDisabled}
                style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: fieldsDisabled ? "#94a3b8" : CRM_FIELDS[activeStage].color, color: "#fff", fontSize: 11, fontWeight: 700, cursor: fieldsDisabled ? "not-allowed" : "pointer", fontFamily: "inherit" }}>
                {"\u26A1"} Auto-Map {CRM_FIELDS[activeStage].label}
              </button>
            </div>

            {/* Sections */}
            {CRM_FIELDS[activeStage].sections.map(section => {
              let fields = section.fields;
              if (filterUnmapped) fields = fields.filter(f => !mappings[f.key]);
              if (fields.length === 0) return null;
              const expanded = expandedSections[section.title] !== false;
              const mapped = section.fields.filter(f => mappings[f.key]).length;
              return (
                <div key={section.title} style={{ marginBottom: 6, background: "#fff", borderRadius: 8, border: "1px solid #e2e8f0", overflow: "hidden" }}>
                  <button onClick={() => toggle(section.title)} style={{
                    width: "100%", padding: "10px 14px", border: "none", background: "#fafafa", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "space-between", fontFamily: "inherit",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, color: "#9ca3af" }}>{expanded ? "\u25BE" : "\u25B8"}</span>
                      <span style={{ fontWeight: 700, fontSize: 13, color: "#374151" }}>{section.title}</span>
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: mapped === section.fields.length ? "#059669" : "#6b7280", background: mapped === section.fields.length ? "#d1fae5" : "#f3f4f6", padding: "2px 8px", borderRadius: 100 }}>
                        {mapped}/{section.fields.length}
                      </span>
                      {mapped < section.fields.length && !fieldsDisabled && (
                        <button onClick={e => { e.stopPropagation(); autoMapSection(section.fields); }}
                          style={{ padding: "3px 8px", borderRadius: 4, border: "1px solid #d1d5db", background: "#fff", fontSize: 10, fontWeight: 700, color: "#6366f1", cursor: "pointer", fontFamily: "inherit" }}>
                          Accept All
                        </button>
                      )}
                    </div>
                  </button>
                  {expanded && fields.map((f) => {
                    const isMapped = !!mappings[f.key];
                    return (
                      <div key={f.key} style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "9px 14px",
                        borderTop: "1px solid #f3f4f6", background: isMapped ? "#fafffe" : f.required && !isMapped ? "#fffbeb" : "transparent",
                      }}>
                        <div style={{
                          width: 7, height: 7, borderRadius: 100, flexShrink: 0,
                          background: isMapped ? "#059669" : f.required ? "#f59e0b" : "#d1d5db",
                          boxShadow: isMapped ? "0 0 0 3px #d1fae5" : f.required && !isMapped ? "0 0 0 3px #fef3c7" : "none",
                        }} />
                        <div style={{ width: 170, flexShrink: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                            <span style={{ fontWeight: 600, fontSize: 13, color: "#111827" }}>{f.label}</span>
                            {f.required && <span style={{ fontSize: 8, fontWeight: 800, color: "#dc2626" }}>REQ</span>}
                          </div>
                          <TypeBadge type={f.type} />
                        </div>
                        <div style={{ color: isMapped ? "#059669" : "#d1d5db", fontSize: 13, flexShrink: 0 }}>{"\u2192"}</div>
                        <SearchableSelect value={mappings[f.key] || null} onChange={val => setMapping(f.key, val)} suggestedSF={f.suggestedSF} sfFields={sfFields} disabled={fieldsDisabled} placeholderText={fieldsPlaceholder} />
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        )}

        {/* Footer */}
        <div style={{ marginTop: 16, marginBottom: 24, padding: "12px 16px", background: "#1e293b", borderRadius: 10, display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <div style={{ display: "flex", gap: 16 }}>
            <div style={{ textAlign: "center" }}>
              <div style={{ fontSize: 9, color: "#64748b", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>SLA Dates</div>
              <div style={{ fontSize: 15, fontWeight: 700, color: slaStats.mapped === slaStats.total ? "#34d399" : "#fbbf24" }}>{slaStats.mapped}/{slaStats.total}</div>
            </div>
            {Object.entries(CRM_FIELDS).map(([k, s]) => {
              const st = fieldStats[k];
              return (
                <div key={k} style={{ textAlign: "center" }}>
                  <div style={{ fontSize: 9, color: "#64748b", fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em" }}>{s.label}</div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: st.mapped === st.total ? "#34d399" : "#e2e8f0" }}>{st.mapped}/{st.total}</div>
                </div>
              );
            })}
          </div>
          <button onClick={handleSaveAll} disabled={saving}
            style={{
              padding: "9px 20px", borderRadius: 8, border: "none",
              background: saving ? "#334155" : "linear-gradient(135deg, #059669, #10b981)",
              color: saving ? "#64748b" : "#fff",
              fontSize: 12, fontWeight: 700, cursor: saving ? "not-allowed" : "pointer", fontFamily: "inherit",
            }}>
            {saving ? "Saving..." : "\uD83D\uDCBE Save All Mappings"}
          </button>
        </div>
      </div>
    </div>
  );
}

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
  { key: "new_lead", label: "New Lead", subtitle: "Lead Received", target: "4 hours", triggerFrom: "Lead Created", phase: "lead", status: "active", suggestedSF: ["Lead_Received_Date__c", "CreatedDate", "Lead_Created_Date__c", "jungo__Lead_Received_Date__c"] },
  { key: "prospect_date", label: "Prospect Date", subtitle: "Prospect Date", target: "N/A", triggerFrom: "Lead Created", phase: "lead", status: "active", suggestedSF: ["Prospect_Date__c", "jungo__Prospect_Date__c"] },
  { key: "attempted_contact", label: "Attempted Contact", subtitle: "First Response", target: "2 hours", triggerFrom: "Lead Created", phase: "lead", status: "active", suggestedSF: ["Attempted_Contact_Date__c", "First_Contact_Attempt__c", "Last_Contacted_Date__c", "First_Response_Date__c", "jungo__First_Response_Date__c"] },
  { key: "app_received", label: "App Received", subtitle: "App Received Date", target: "2 business days", triggerFrom: "Lead Created", phase: "lead", status: "active", suggestedSF: ["App_Received_Date__c", "jungo__App_Received_Date__c", "App_Received__c", "jungo__App_Received__c"] },
  { key: "application_complete", label: "Application Date", subtitle: "Application Date", target: "2 business days", triggerFrom: "Lead Created", phase: "lead", status: "active", suggestedSF: ["Application_Date__c", "jungo__Application_Date__c", "Application_Complete_Date__c", "App_Complete__c", "Loan_Application_Date__c", "jungo__Loan_Application_Date__c"] },
  { key: "acknowledged", label: "Acknowledged Date", subtitle: "Acknowledged Date", target: "1 business day", triggerFrom: "Application", phase: "lead", status: "active", suggestedSF: ["Acknowledged_Date__c", "jungo__Acknowledged_Date__c"] },
  { key: "initial_consultation", label: "Initial Consultation", subtitle: "In for Consultation", target: "3 business days", triggerFrom: "Previous Milestone", phase: "lead", status: "active", suggestedSF: ["Initial_Consultation_Date__c", "Consultation_Date__c", "First_Meeting_Date__c"] },
  { key: "pre_qualified", label: "Pre-Qualified", subtitle: "Prequalified", target: "1 hour", triggerFrom: "Previous Milestone", phase: "lead", status: "active", suggestedSF: ["Pre_Qualified_Date__c", "Prequalification_Date__c", "PQ_Date__c"] },
  { key: "pre_approved", label: "Pre-Approved", subtitle: "Loan Pre Approval Date", target: "3 business days", triggerFrom: "Previous Milestone", phase: "lead", status: "active", suggestedSF: ["Loan_Pre_Approval_Date__c", "jungo__Loan_Pre_Approval_Date__c", "Pre_Approved_Date__c", "Preapproval_Date__c", "PA_Date__c"] },
  { key: "credit_only", label: "Credit Only Date", subtitle: "Credit Only Date", target: "1 business day", triggerFrom: "Application", phase: "lead", status: "active", suggestedSF: ["Credit_Only_Date__c", "jungo__Credit_Only_Date__c"] },

  // Processing Phase
  { key: "contract_received", label: "Contract Received", subtitle: "Contract Received", target: "3 business days", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["Contract_Received_Date__c", "Contract_Date__c", "Purchase_Contract_Date__c"] },
  { key: "le_pending", label: "LE Pending Date", subtitle: "LE Pending Date", target: "3 business days", triggerFrom: "Application", phase: "processing", status: "active", suggestedSF: ["LE_Pending_Date__c", "jungo__LE_Pending_Date__c", "Disclosure_Pending_Date__c"] },
  { key: "disclosure_sent", label: "Disclosure Sent", subtitle: "Loan Disc Ctrl TO", target: "3 business days", triggerFrom: "Application", phase: "processing", status: "active", suggestedSF: ["Loan_Disc_Ctrl_TO__c", "jungo__Loan_Disc_Ctrl_TO__c", "Disclosure_Sent_Date__c", "LE_Sent_Date__c", "GFE_Sent_Date__c"] },
  { key: "disclosed", label: "Disclosed Date", subtitle: "Disclosed Date", target: "3 business days", triggerFrom: "Disclosure Sent", phase: "processing", status: "active", suggestedSF: ["Disclosed_Date__c", "jungo__Disclosed_Date__c", "Disclosure_Received_Date__c", "jungo__Disclosure_Received_Date__c", "LE_Received_Date__c", "Disclosure_Acknowledged_Date__c", "Disclosure_Signed_Date__c"] },
  { key: "file_started", label: "File Started", subtitle: "File Started Date", target: "1 business day", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["File_Started_Date__c", "jungo__File_Started_Date__c", "File_Received_Date__c", "jungo__File_Received_Date__c"] },
  { key: "submitted_to_processing", label: "File Pending", subtitle: "File Pending Date", target: "3 business days", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["File_Pending_Date__c", "jungo__File_Pending_Date__c", "Submitted_To_Processing_Date__c", "Processing_Start_Date__c", "File_Submitted_Date__c"] },
  { key: "application_submission", label: "Application Submission", subtitle: "FHA Application Date", target: "3 business days", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["Application_Submission_Date__c", "App_Submitted_Date__c", "Application_Submitted__c", "FHA_Application_Date__c", "jungo__FHA_Application_Date__c"] },
  { key: "loan_date_1st_td", label: "Loan Date (1st TD)", subtitle: "Loan Date 1st Trust Deed", target: "N/A", triggerFrom: "Application", phase: "processing", status: "active", suggestedSF: ["Loan_Date_1st_TD__c", "jungo__Loan_Date_1st_TD__c", "Loan_Date__c", "jungo__Loan_Date__c"] },
  { key: "lock_in", label: "Lock-In Date", subtitle: "Rate Lock Date", target: "Per policy", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["Lock_In_Date__c", "jungo__Lock_In_Date__c", "Lock_Date__c", "Rate_Lock_Date__c"] },
  { key: "lock_expiration", label: "Lock Exp Date (1st TD)", subtitle: "Lock Expiration Date", target: "Per lock period", triggerFrom: "Lock-In", phase: "processing", status: "active", suggestedSF: ["Lock_Exp_Date_1st_TD__c", "jungo__Lock_Exp_Date_1st_TD__c", "Lock_Expiration_Date__c", "jungo__Lock_Expiration_Date__c", "Lock_Exp_Date__c"] },
  { key: "document_collection", label: "Document Collection", subtitle: null, target: "5 business days", triggerFrom: "Previous Milestone", phase: "processing", status: "active", suggestedSF: ["Document_Collection_Date__c", "Docs_Collected_Date__c", "Document_Package_Date__c"] },
  { key: "documents_requested", label: "Documents Requested", subtitle: null, target: "1 business day", triggerFrom: "Previous Milestone", phase: "processing", status: "inactive", suggestedSF: ["Documents_Requested_Date__c", "Doc_Request_Date__c", "Stips_Requested_Date__c"] },
  { key: "documents_received", label: "Documents Received", subtitle: "Documents Received", target: "5 business days", triggerFrom: "Documents Requested", phase: "processing", status: "active", suggestedSF: ["Documents_Received_Date__c", "Docs_Received_Date__c", "Doc_Package_Received__c"] },

  // Third Party Phase
  { key: "appraisal_ordered", label: "Appraisal Ordered", subtitle: "Appraisal Ordered", target: "1 business day", triggerFrom: "Disclosed", phase: "third_party", status: "active", suggestedSF: ["Appraisal_Ordered_Date__c", "Appraisal_Order_Date__c", "AMC_Order_Date__c"] },
  { key: "appraisal_payment", label: "Appraisal Payment", subtitle: "Appraisal Payment Date", target: "1 business day", triggerFrom: "Appraisal Ordered", phase: "third_party", status: "active", suggestedSF: ["Appraisal_Payment_Date__c", "jungo__Appraisal_Payment_Date__c", "Appraisal_Fee_Paid__c"] },
  { key: "appraisal_received", label: "Appraisal Received", subtitle: "Appraisal Received", target: "7 business days", triggerFrom: "Appraisal Ordered", phase: "third_party", status: "active", suggestedSF: ["Appraisal_Received_Date__c", "Appraisal_Complete_Date__c", "Appraisal_Report_Date__c", "jungo__Appraisal_Received_Date__c"] },
  { key: "appraisal_expires", label: "Appraisal Expires", subtitle: "Appraisal Expires Date", target: "Per guidelines", triggerFrom: "Appraisal Received", phase: "third_party", status: "active", suggestedSF: ["Appraisal_Expires_Date__c", "jungo__Appraisal_Expires_Date__c", "Appraisal_Expiration_Date__c"] },
  { key: "appraisal_docs_expire", label: "Appraisal Docs Expire", subtitle: "Appraisal Docs Expire Date", target: "Per guidelines", triggerFrom: "Appraisal Received", phase: "third_party", status: "active", suggestedSF: ["Appraisal_Docs_Expire_Date__c", "jungo__Appraisal_Docs_Expire_Date__c"] },
  { key: "insurance_ordered", label: "Insurance Ordered", subtitle: null, target: "10 business days", triggerFrom: "Disclosed", phase: "third_party", status: "active", suggestedSF: ["Insurance_Ordered_Date__c", "HOI_Ordered_Date__c", "Insurance_Order_Date__c"] },
  { key: "insurance_received", label: "Insurance Received", subtitle: "Insurance Received", target: "10 biz days before closing", triggerFrom: "Closing Date", phase: "third_party", status: "active", suggestedSF: ["Insurance_Received_Date__c", "HOI_Received_Date__c", "Insurance_Binder_Date__c"] },
  { key: "title_ordered", label: "Title Ordered", subtitle: "Title Ordered", target: "1 business day", triggerFrom: "Disclosed", phase: "third_party", status: "active", suggestedSF: ["Title_Ordered_Date__c", "Title_Order_Date__c", "Title_Request_Date__c"] },
  { key: "title_received", label: "Title Received", subtitle: null, target: "10 biz days before closing", triggerFrom: "Closing Date", phase: "third_party", status: "active", suggestedSF: ["Title_Received_Date__c", "Title_Report_Date__c", "Title_Commitment_Date__c"] },
  { key: "condo_cert", label: "Condo Cert", subtitle: "Condo Cert Date", target: "10 business days", triggerFrom: "Disclosed", phase: "third_party", status: "active", suggestedSF: ["Condo_Cert_Date__c", "jungo__Condo_Cert_Date__c", "Condo_Certification_Date__c", "HOA_Cert_Date__c"] },
  { key: "credit_docs_expire", label: "Credit Clock Expire", subtitle: "Credit Clock Expire Date", target: "Per guidelines", triggerFrom: "Credit Pull", phase: "third_party", status: "active", suggestedSF: ["Credit_Clock_Expire_Date__c", "jungo__Credit_Clock_Expire_Date__c", "Credit_Docs_Expire_Date__c", "jungo__Credit_Docs_Expire_Date__c", "Credit_Expiration_Date__c"] },

  // Underwriting Phase
  { key: "submit_to_underwriting", label: "Submit to Underwriting", subtitle: "UW Pending Date", target: "3 business days", triggerFrom: "Previous Milestone", phase: "underwriting", status: "active", suggestedSF: ["Submitted_To_UW_Date__c", "UW_Submit_Date__c", "Submit_To_UW__c", "UW_Pending_Date__c", "jungo__UW_Pending_Date__c"] },
  { key: "underwriting_decision", label: "Underwriting Decision", subtitle: "UW Decision", target: "3 business days", triggerFrom: "Previous Milestone", phase: "underwriting", status: "active", suggestedSF: ["UW_Decision_Date__c", "Underwriting_Decision_Date__c", "Decision_Date__c", "Underwriter_Initial_Open_Date__c", "jungo__Underwriter_Initial_Open_Date__c"] },
  { key: "approved", label: "Loan Approved", subtitle: "Loan Approved Date", target: "3 business days", triggerFrom: "Previous Milestone", phase: "underwriting", status: "active", suggestedSF: ["Loan_Approved_Date__c", "jungo__Loan_Approved_Date__c", "Approved_Date__c", "Approval_Date__c", "UW_Approved_Date__c", "Conditional_Approval_Date__c", "Approval_Received_Date__c", "jungo__Approval_Received_Date__c"] },
  { key: "ca_acknowledged", label: "CA Acknowledged", subtitle: "CA Acknowledged Date", target: "1 business day", triggerFrom: "Approval", phase: "underwriting", status: "active", suggestedSF: ["CA_Acknowledged_Date__c", "jungo__CA_Acknowledged_Date__c", "Conditional_Approval_Acknowledged_Date__c"] },
  { key: "conditions_review", label: "Conditions to Review", subtitle: "Conditions to Review Date", target: "1 business day", triggerFrom: "Approval", phase: "underwriting", status: "active", suggestedSF: ["Conditions_to_Review_Date__c", "jungo__Conditions_to_Review_Date__c", "Conditions_Sent_Review_Date__c", "jungo__Conditions_Sent_Review_Date__c", "Conditions_To_Borrower_Date__c"] },
  { key: "conditions_cleared", label: "Conditions Cleared", subtitle: "Conditions Cleared", target: "3 business days", triggerFrom: "Previous Milestone", phase: "underwriting", status: "active", suggestedSF: ["Conditions_Cleared_Date__c", "Conditions_Met_Date__c", "Stips_Cleared_Date__c"] },
  { key: "approval_not_accepted", label: "Approval Not Accepted", subtitle: "Approval Not Accepted Date", target: "N/A", triggerFrom: "Approval", phase: "underwriting", status: "inactive", suggestedSF: ["Approval_Not_Accepted_Date__c", "jungo__Approval_Not_Accepted_Date__c"] },
  { key: "loan_denied", label: "Loan Denied", subtitle: "Loan Denied Date", target: "N/A", triggerFrom: "Any stage", phase: "underwriting", status: "inactive", suggestedSF: ["Loan_Denied_Date__c", "jungo__Loan_Denied_Date__c", "Denied_Date__c"] },
  { key: "fha_endorsement", label: "FHA Endorsement", subtitle: "FHA Endorsement Date", target: "Per FHA timeline", triggerFrom: "Funding", phase: "underwriting", status: "active", suggestedSF: ["FHA_Endorsement_Date__c", "jungo__FHA_Endorsement_Date__c", "FHA_Case_Number_Date__c"] },

  // Closing Phase
  { key: "clear_to_close", label: "Clear to Close", subtitle: "Clear to Close Date", target: "3 business days", triggerFrom: "Conditions Cleared", phase: "closing", status: "active", suggestedSF: ["Clear_to_Close_Date__c", "jungo__Clear_to_Close_Date__c", "Clear_To_Close_Date__c", "CTC_Date__c", "CTC__c"] },
  { key: "cd_sent_to_borrower", label: "CD Sent to Borrower", subtitle: "CD Sent to Borrower Date", target: "3 days before closing", triggerFrom: "Clear to Close", phase: "closing", status: "active", suggestedSF: ["CD_Sent_to_Borrower_Date__c", "jungo__CD_Sent_to_Borrower_Date__c", "CD_Sent_Date__c", "jungo__CD_Sent_Date__c", "CD_Sent_to_Borrower__c"] },
  { key: "docs_ordered_out", label: "Docs Ordered Out", subtitle: "Docs Ordered Out Date", target: "1 business day", triggerFrom: "CTC", phase: "closing", status: "active", suggestedSF: ["Docs_Ordered_Out_Date__c", "jungo__Docs_Ordered_Out_Date__c", "Closing_Docs_Out_Date__c", "Docs_Out_Date__c", "Closing_Package_Sent__c"] },
  { key: "scheduled_closing", label: "Scheduled Closing", subtitle: "Scheduled Closing Date", target: "45 days", triggerFrom: "Application", phase: "closing", status: "active", suggestedSF: ["Scheduled_Closing_Date__c", "jungo__Scheduled_Closing_Date__c", "Closing_Date__c", "Close_Date__c", "CloseDate", "Settlement_Date__c"] },
  { key: "closing_date", label: "Closing Date", subtitle: "Close/Closed Date", target: "45 days", triggerFrom: "Clear To Close", phase: "closing", status: "active", suggestedSF: ["Close_Closed_Date__c", "jungo__Close_Closed_Date__c", "Closing_Date__c", "Close_Date__c", "CloseDate", "Settlement_Date__c"] },
  { key: "escrow_date", label: "Escrow Date", subtitle: "Escrow Date", target: "Per contract", triggerFrom: "Contract", phase: "closing", status: "active", suggestedSF: ["Escrow_Date__c", "jungo__Escrow_Date__c", "Escrow_Open_Date__c"] },
  { key: "funds_ordered", label: "Funds Ordered", subtitle: "Funds Ordered Date", target: "1 business day", triggerFrom: "Closing", phase: "closing", status: "active", suggestedSF: ["Funds_Ordered_Date__c", "jungo__Funds_Ordered_Date__c", "Wire_Ordered_Date__c"] },
  { key: "funds_state", label: "Funds State Date", subtitle: "Funds State Date", target: "1 business day", triggerFrom: "Funds Ordered", phase: "closing", status: "active", suggestedSF: ["Funds_State_Date__c", "jungo__Funds_State_Date__c"] },
  { key: "scheduled_funding", label: "Scheduled Funding", subtitle: "Scheduled Funding Date", target: "1 business day", triggerFrom: "Closing", phase: "closing", status: "active", suggestedSF: ["Scheduled_Funding_Date__c", "jungo__Scheduled_Funding_Date__c", "Expected_Funded_Date__c", "jungo__Expected_Funded_Date__c"] },
  { key: "loan_funded", label: "Funded Date", subtitle: "Funded Date", target: "1 business day", triggerFrom: "Previous Milestone", phase: "closing", status: "active", suggestedSF: ["Funded_Date__c", "jungo__Funded_Date__c", "Funding_Date__c", "Fund_Date__c", "Loan_Funded_Date__c"] },
  { key: "investor_purchased", label: "Investor Purchased", subtitle: "Investor Purchased Date", target: "Per investor", triggerFrom: "Funding", phase: "closing", status: "active", suggestedSF: ["Investor_Purchased_Date__c", "jungo__Investor_Purchased_Date__c", "Purchased_Date__c"] },
  { key: "first_payment", label: "First Payment", subtitle: "First Payment Date", target: "Per note", triggerFrom: "Funding", phase: "closing", status: "active", suggestedSF: ["First_Payment_Date__c", "jungo__First_Payment_Date__c", "First_Payment__c"] },
  { key: "withdrawn", label: "Withdrawn", subtitle: "Withdrawn Date", target: "N/A", triggerFrom: "Any stage", phase: "closing", status: "inactive", suggestedSF: ["Withdrawn_Date__c", "jungo__Withdrawn_Date__c", "Cancelled_Date__c", "Dead_Deal_Date__c", "Dead_Deal_Reason_Date__c", "jungo__Dead_Deal_Reason_Date__c"] },
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
          { key: "lead_status", label: "Lead Status", type: "picklist", required: true, suggestedSF: ["Status", "Lead_Status__c", "Loan_Lead_Status__c", "jungo__Loan_Lead_Status__c"] },
          { key: "referral_partner", label: "Referral Partner", type: "string", required: false, suggestedSF: ["Referral_Partner__c", "Referred_By__c"] },
          { key: "lead_state", label: "State", type: "string", required: false, suggestedSF: ["State", "State__c"] },
          { key: "lead_city", label: "City", type: "string", required: false, suggestedSF: ["City", "City__c"] },
        ],
      },
      {
        title: "Loan Details",
        fields: [
          { key: "lead_loan_amount", label: "Loan Amount", type: "currency", required: false, suggestedSF: ["Amount", "Loan_Amount__c", "S_Loan_Amount_1st_TD__c", "jungo__S_Loan_Amount_1st_TD__c", "S_Loan_Amount__c", "jungo__S_Loan_Amount__c"] },
          { key: "lead_loan_purpose", label: "Loan Purpose", type: "picklist", required: false, suggestedSF: ["Loan_Purpose__c", "Purpose__c"] },
          { key: "lead_loan_type", label: "Loan Type", type: "picklist", required: false, suggestedSF: ["Loan_Type__c", "Product_Type__c", "Lender_Type__c", "jungo__Lender_Type__c"] },
          { key: "lead_interest_rate", label: "Interest Rate", type: "decimal", required: false, suggestedSF: ["Interest_Rate__c", "Rate__c", "Note_Rate__c", "S_Rate_1st_TD__c", "jungo__S_Rate_1st_TD__c"] },
          { key: "lead_loan_term", label: "Loan Term", type: "integer", required: false, suggestedSF: ["Loan_Term__c", "Term__c", "jungo__Term__c", "jungo__Loan_Term__c", "S_Term__c", "jungo__S_Term__c", "Term_in_Months__c", "Loan_Term_Months__c"] },
          { key: "lead_ltv", label: "LTV", type: "decimal", required: false, suggestedSF: ["LTV__c", "S_LTV__c", "jungo__S_LTV__c", "jungo__LTV__c", "Loan_To_Value__c", "LTV_Ratio__c"] },
          { key: "lead_cltv", label: "CLTV", type: "decimal", required: false, suggestedSF: ["CLTV__c", "S_CLTV__c", "jungo__S_CLTV__c", "jungo__CLTV__c", "Combined_LTV__c", "Combined_Loan_To_Value__c"] },
          { key: "lead_dti", label: "DTI", type: "decimal", required: false, suggestedSF: ["DTI__c", "S_DTI__c", "jungo__S_DTI__c", "jungo__DTI__c", "Debt_To_Income__c", "DTI_Ratio__c", "Back_End_Ratio__c"] },
          { key: "lead_loan_stage", label: "Loan Stage", type: "picklist", required: false, suggestedSF: ["StageName", "Stage__c"] },
          { key: "lead_assigned_lo", label: "Assigned LO", type: "user", required: false, suggestedSF: ["OwnerId", "Loan_Officer__c"] },
          { key: "lead_processor", label: "Processor", type: "user", required: false, suggestedSF: ["Processor__c"] },
          { key: "lead_loan_number", label: "Loan Number", type: "string", required: false, suggestedSF: ["Loan_Number__c", "jungo__Loan_Number__c", "LOS_Loan_Number__c"] },
          { key: "lead_preapproval_amount", label: "Preapproval Amount", type: "currency", required: false, suggestedSF: ["Preapproval_Amount__c", "Pre_Approval_Amount__c"] },
          { key: "lead_credit_score", label: "Credit Score", type: "integer", required: false, suggestedSF: ["Credit_Score__c", "FICO__c", "FICO_Score__c", "jungo__FICO__c"] },
        ],
      },
      {
        title: "Property",
        fields: [
          { key: "lead_property_address", label: "Property Address", type: "string", required: false, suggestedSF: ["Street", "Property_Address__c", "jungo__Property_Address__c"] },
          { key: "lead_property_city", label: "City", type: "string", required: false, suggestedSF: ["City", "Property_City__c", "jungo__Property_City__c"] },
          { key: "lead_property_state", label: "State", type: "string", required: false, suggestedSF: ["State", "Property_State__c", "jungo__Property_State__c"] },
          { key: "lead_property_zip", label: "Zip", type: "string", required: false, suggestedSF: ["PostalCode", "Property_Zip__c", "Property_Postal_Code__c", "jungo__Property_Postal_Code__c"] },
          { key: "lead_property_type", label: "Property Type", type: "picklist", required: false, suggestedSF: ["Property_Type__c"] },
          { key: "lead_occupancy", label: "Occupancy", type: "picklist", required: false, suggestedSF: ["Occupancy_Type__c", "jungo__Occupancy_Type__c", "Occupancy__c", "jungo__Occupancy__c", "MtgPlanner_CRM__Occupancy__c", "MtgPlanner_CRM__Occupancy_Type__c", "Property_Occupancy__c"] },
          { key: "lead_property_value", label: "Property Value", type: "currency", required: false, suggestedSF: ["Estimated_Value__c", "Purchase_Price__c", "Property_Value__c"] },
          { key: "lead_appraisal_value", label: "Appraisal Value", type: "currency", required: false, suggestedSF: ["Appraisal_Value__c"] },
          { key: "lead_down_payment", label: "Down Payment", type: "currency", required: false, suggestedSF: ["Down_Payment__c", "Down_Payment_Amount__c"] },
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
          { key: "borrower_ssn", label: "SSN", type: "sensitive", required: true, suggestedSF: ["SSN__c", "Social__c", "Social_Security_Number__c", "Social_Security__c", "Borrower_SSN__c", "SSN_Encrypted__c", "Tax_ID__c", "SocialSecurityNumber", "jungo__SSN__c"] },
          { key: "borrower_dob", label: "Date of Birth", type: "date", required: true, suggestedSF: ["Birthdate", "DOB__c", "Date_of_Birth__c", "jungo__DOB__c"] },
          { key: "mailing_address", label: "Mailing Address", type: "string", required: false, suggestedSF: ["MailingStreet"] },
          { key: "mailing_city", label: "Mailing City", type: "string", required: false, suggestedSF: ["MailingCity"] },
          { key: "mailing_state", label: "Mailing State", type: "string", required: false, suggestedSF: ["MailingState"] },
          { key: "mailing_zip", label: "Mailing Zip", type: "string", required: false, suggestedSF: ["MailingPostalCode"] },
        ],
      },
      {
        title: "Loan Details",
        fields: [
          { key: "loan_amount", label: "Loan Amount", type: "currency", required: true, suggestedSF: ["Amount", "Loan_Amount__c", "S_Loan_Amount_1st_TD__c", "jungo__S_Loan_Amount_1st_TD__c", "S_Loan_Amount__c", "jungo__S_Loan_Amount__c"] },
          { key: "loan_purpose", label: "Loan Purpose", type: "picklist", required: true, suggestedSF: ["Loan_Purpose__c", "Purpose__c"] },
          { key: "loan_type", label: "Loan Type", type: "picklist", required: true, suggestedSF: ["Loan_Type__c", "Product_Type__c", "Lender_Type__c", "jungo__Lender_Type__c"] },
          { key: "interest_rate", label: "Interest Rate", type: "decimal", required: false, suggestedSF: ["Interest_Rate__c", "Rate__c", "Note_Rate__c", "S_Rate_1st_TD__c", "jungo__S_Rate_1st_TD__c"] },
          { key: "loan_term", label: "Loan Term", type: "integer", required: false, suggestedSF: ["Loan_Term__c", "Term__c", "jungo__Term__c", "jungo__Loan_Term__c", "S_Term__c", "jungo__S_Term__c", "Term_in_Months__c", "Loan_Term_Months__c"] },
          { key: "ltv", label: "LTV", type: "decimal", required: false, suggestedSF: ["LTV__c", "S_LTV__c", "jungo__S_LTV__c", "jungo__LTV__c", "Loan_To_Value__c", "LTV_Ratio__c"] },
          { key: "cltv", label: "CLTV", type: "decimal", required: false, suggestedSF: ["CLTV__c", "S_CLTV__c", "jungo__S_CLTV__c", "jungo__CLTV__c", "Combined_LTV__c", "Combined_Loan_To_Value__c"] },
          { key: "dti", label: "DTI", type: "decimal", required: false, suggestedSF: ["DTI__c", "S_DTI__c", "jungo__S_DTI__c", "jungo__DTI__c", "Debt_To_Income__c", "DTI_Ratio__c", "Back_End_Ratio__c"] },
          { key: "loan_lead_status", label: "Loan Lead Status", type: "picklist", required: false, suggestedSF: ["Loan_Lead_Status__c", "jungo__Loan_Lead_Status__c"] },
          { key: "loan_stage", label: "Loan Stage", type: "picklist", required: true, suggestedSF: ["StageName", "Stage__c"] },
          { key: "assigned_lo", label: "Assigned LO", type: "user", required: true, suggestedSF: ["OwnerId", "Loan_Officer__c"] },
          { key: "assigned_processor", label: "Processor", type: "user", required: false, suggestedSF: ["Processor__c"] },
        ],
      },
      {
        title: "Property",
        fields: [
          { key: "property_address", label: "Property Address", type: "string", required: true, suggestedSF: ["Property_Address__c", "jungo__Property_Address__c"] },
          { key: "property_city", label: "City", type: "string", required: true, suggestedSF: ["Property_City__c", "jungo__Property_City__c"] },
          { key: "property_state", label: "State", type: "string", required: true, suggestedSF: ["Property_State__c", "jungo__Property_State__c"] },
          { key: "property_zip", label: "Zip", type: "string", required: true, suggestedSF: ["Property_Zip__c", "Property_Postal_Code__c", "jungo__Property_Postal_Code__c", "jungo__Property_Zip__c"] },
          { key: "property_type", label: "Property Type", type: "picklist", required: true, suggestedSF: ["Property_Type__c"] },
          { key: "occupancy_type", label: "Occupancy", type: "picklist", required: true, suggestedSF: ["Occupancy_Type__c", "jungo__Occupancy_Type__c", "Occupancy__c", "jungo__Occupancy__c", "MtgPlanner_CRM__Occupancy__c", "MtgPlanner_CRM__Occupancy_Type__c", "Property_Occupancy__c"] },
          { key: "estimated_value", label: "Estimated Value", type: "currency", required: false, suggestedSF: ["Estimated_Value__c", "Purchase_Price__c"] },
          { key: "appraisal_value", label: "Appraisal Value", type: "currency", required: false, suggestedSF: ["Appraisal_Value__c"] },
        ],
      },
      {
        title: "Servicing",
        fields: [
          { key: "lender_type", label: "Lender Type", type: "picklist", required: false, suggestedSF: ["Lender_Type__c", "jungo__Lender_Type__c", "Investor__c"] },
          { key: "lender_credit", label: "Lender Credit", type: "currency", required: false, suggestedSF: ["Lender_Credit__c", "jungo__Lender_Credit__c"] },
          { key: "servicer", label: "Servicer", type: "string", required: false, suggestedSF: ["Servicer__c", "jungo__Servicer__c", "Loan_Servicer__c"] },
          { key: "servicer_loan_number", label: "Servicer Loan Number", type: "string", required: false, suggestedSF: ["Servicer_Loan_Number__c", "jungo__Servicer_Loan_Number__c", "Servicing_Loan_Number__c"] },
          { key: "loan_number", label: "Loan Number", type: "string", required: false, suggestedSF: ["Loan_Number__c", "jungo__Loan_Number__c", "LOS_Loan_Number__c"] },
          { key: "estimated_completion", label: "Est. Completion Date", type: "date", required: false, suggestedSF: ["Estimated_Sold_Completion_Date__c", "jungo__Estimated_Sold_Completion_Date__c", "Estimated_Completion_Date__c"] },
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
          { key: "mum_property_address", label: "Property Address", type: "string", required: true, suggestedSF: ["Property_Address__c", "MailingStreet", "jungo__Property_Address__c"] },
        ],
      },
      {
        title: "Loan Summary",
        fields: [
          { key: "original_loan_amount", label: "Original Loan Amount", type: "currency", required: true, suggestedSF: ["Amount", "Original_Loan_Amount__c", "S_Loan_Amount__c", "jungo__S_Loan_Amount__c"] },
          { key: "current_rate", label: "Current Rate", type: "decimal", required: false, suggestedSF: ["Interest_Rate__c", "Current_Rate__c"] },
          { key: "mum_loan_type", label: "Loan Type", type: "picklist", required: true, suggestedSF: ["Loan_Type__c"] },
          { key: "mum_servicer", label: "Servicer", type: "string", required: false, suggestedSF: ["Servicer__c", "jungo__Servicer__c"] },
          { key: "mum_servicer_loan_number", label: "Servicer Loan Number", type: "string", required: false, suggestedSF: ["Servicer_Loan_Number__c", "jungo__Servicer_Loan_Number__c"] },
          { key: "maturity_date", label: "Maturity Date", type: "date", required: false, suggestedSF: ["Maturity_Date__c"] },
        ],
      },
      {
        title: "Retention & Monitoring",
        fields: [
          { key: "estimated_home_value", label: "Est. Home Value", type: "currency", calculated: true, calculatedDesc: "Compound appreciation from original value" },
          { key: "estimated_equity", label: "Est. Equity", type: "currency", calculated: true, calculatedDesc: "Home value minus amortized balance" },
          { key: "current_ltv", label: "Current LTV", type: "decimal", calculated: true, calculatedDesc: "Amortized balance / current home value" },
          { key: "current_cltv", label: "Current CLTV", type: "decimal", calculated: true, calculatedDesc: "Combined loan balances / current home value" },
          { key: "refi_score", label: "Refi Opportunity Score", type: "integer", calculated: true, calculatedDesc: "0-100 score based on rate, equity, loan age" },
        ],
      },
    ],
  },
};

// ---------------------------------------------------------------
// INHERITANCE: Lead → Active Loan → MUM Clients
// ---------------------------------------------------------------
const LEAD_TO_ACTIVE_LOAN = {
  lead_first_name: 'borrower_first_name',
  lead_last_name: 'borrower_last_name',
  lead_email: 'borrower_email',
  lead_phone: 'borrower_phone',
  lead_loan_amount: 'loan_amount',
  lead_loan_purpose: 'loan_purpose',
  lead_loan_type: 'loan_type',
  lead_interest_rate: 'interest_rate',
  lead_loan_term: 'loan_term',
  lead_ltv: 'ltv',
  lead_cltv: 'cltv',
  lead_dti: 'dti',
  lead_loan_stage: 'loan_stage',
  lead_assigned_lo: 'assigned_lo',
  lead_processor: 'assigned_processor',
  lead_loan_number: 'loan_number',
  lead_property_address: 'property_address',
  lead_property_city: 'property_city',
  lead_property_state: 'property_state',
  lead_property_zip: 'property_zip',
  lead_property_type: 'property_type',
  lead_occupancy: 'occupancy_type',
  lead_property_value: 'estimated_value',
  lead_appraisal_value: 'appraisal_value',
};
const ACTIVE_TO_LEAD = Object.fromEntries(
  Object.entries(LEAD_TO_ACTIVE_LOAN).map(([k, v]) => [v, k])
);

// Active Loan → MUM Clients inheritance
const ACTIVE_LOAN_TO_MUM = {
  borrower_first_name: 'mum_first_name',
  borrower_last_name: 'mum_last_name',
  borrower_email: 'mum_email',
  borrower_phone: 'mum_phone',
  property_address: 'mum_property_address',
  loan_amount: 'original_loan_amount',
  interest_rate: 'current_rate',
  loan_type: 'mum_loan_type',
  servicer: 'mum_servicer',
  servicer_loan_number: 'mum_servicer_loan_number',
  // estimated_home_value, current_ltv, current_cltv, estimated_equity, refi_score
  // are calculated fields — not inherited from Active Loan Salesforce mappings
};
const MUM_TO_ACTIVE = Object.fromEntries(
  Object.entries(ACTIVE_LOAN_TO_MUM).map(([k, v]) => [v, k])
);

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
  const [openUp, setOpenUp] = useState(false);
  const ref = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    const handler = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);
  useEffect(() => {
    if (open && inputRef.current) inputRef.current.focus();
    if (open && ref.current) {
      const rect = ref.current.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      setOpenUp(spaceBelow < 360);
    }
  }, [open]);

  const filtered = useMemo(() => {
    const fields = sfFields || [];
    const q = search.toLowerCase();
    let res = q
      ? fields.filter(f =>
          f.apiName.toLowerCase().includes(q) ||
          f.label.toLowerCase().includes(q) ||
          f.object.toLowerCase().includes(q) ||
          // Also match with underscores/spaces removed so "ssn" finds "Social_Security_Number__c"
          f.apiName.toLowerCase().replace(/[_\s]/g, '').includes(q.replace(/[_\s]/g, '')) ||
          f.label.toLowerCase().replace(/[_\s]/g, '').includes(q.replace(/[_\s]/g, ''))
        )
      : fields;
    const sugSet = new Set((suggestedSF || []).map(s => s.toLowerCase()));
    res.sort((a, b) => {
      const aS = sugSet.has(a.apiName.toLowerCase()) ? 0 : 1;
      const bS = sugSet.has(b.apiName.toLowerCase()) ? 0 : 1;
      if (aS !== bS) return aS - bS;
      // Sort custom fields after standard when not searching
      if (!q && a.custom !== b.custom) return a.custom ? 1 : -1;
      return a.apiName.localeCompare(b.apiName);
    });
    return res.slice(0, 60);
  }, [search, suggestedSF, sfFields]);

  const sel = value ? (sfFields || []).find(f => `${f.object}.${f.apiName}` === value) : null;

  return (
    <div ref={ref} style={{ position: "relative", flex: 1, minWidth: 0, zIndex: open ? 1001 : "auto" }}>
      <button onClick={() => !disabled && setOpen(!open)} disabled={disabled} style={{
        width: "100%", padding: "7px 10px", border: value ? "1.5px solid #059669" : "1.5px solid #d1d5db",
        borderRadius: 6, background: value ? "#f0fdf4" : "#fff", cursor: disabled ? "not-allowed" : "pointer",
        display: "flex", alignItems: "center", justifyContent: "space-between",
        fontSize: 13, color: value ? "#065f46" : "#9ca3af", fontFamily: "inherit", minHeight: 34, transition: "all 0.15s",
        opacity: disabled ? 0.5 : 1,
      }}>
        <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {sel ? (<><span style={{ color: "#9ca3af", fontSize: 11 }}>{sel.object}.</span><span style={{ fontWeight: 600, color: "#065f46" }}>{sel.apiName}</span>{sel.label && sel.label !== sel.apiName && <span style={{ color: "#6b7280", fontSize: 10, marginLeft: 4 }}>({sel.label})</span>}</>) : (disabled ? (placeholderText || "Loading fields...") : "Select Salesforce field...")}
        </span>
        <span style={{ fontSize: 9, marginLeft: 4, flexShrink: 0, color: "#9ca3af" }}>{open ? "\u25B2" : "\u25BC"}</span>
      </button>

      {open && (
        <div style={{ position: "absolute", ...(openUp ? { bottom: "calc(100% + 3px)" } : { top: "calc(100% + 3px)" }), left: 0, right: 0, background: "#fff", border: "1px solid #e5e7eb", borderRadius: 8, boxShadow: "0 12px 40px rgba(0,0,0,0.15)", zIndex: 1000, maxHeight: 340, display: "flex", flexDirection: "column" }}>
          <div style={{ padding: 6, borderBottom: "1px solid #f3f4f6" }}>
            <input ref={inputRef} type="text" placeholder="Search by name, label, or object... (e.g. ssn, social, phone)" value={search} onChange={e => setSearch(e.target.value)}
              style={{ width: "100%", padding: "7px 10px", border: "1.5px solid #e5e7eb", borderRadius: 6, fontSize: 12, outline: "none", fontFamily: "inherit", boxSizing: "border-box" }}
              onFocus={e => { e.target.style.borderColor = "#6366f1"; }} onBlur={e => { e.target.style.borderColor = "#e5e7eb"; }} />
            {search && <div style={{ fontSize: 10, color: "#9ca3af", padding: "2px 4px" }}>{filtered.length} result{filtered.length !== 1 ? "s" : ""}</div>}
          </div>
          <div style={{ overflowY: "auto", flex: 1 }}>
            {filtered.length === 0 && <div style={{ padding: 14, textAlign: "center", color: "#9ca3af", fontSize: 12 }}>No fields found — try a different search term or refresh schema</div>}
            {filtered.map(f => {
              const k = `${f.object}.${f.apiName}`;
              const isSug = (suggestedSF || []).some(s => s.toLowerCase() === f.apiName.toLowerCase());
              const showLabel = f.label && f.label !== f.apiName;
              return (
                <button key={k} onClick={() => { onChange(k); setOpen(false); setSearch(""); }}
                  style={{ width: "100%", padding: "7px 10px", border: "none", background: value === k ? "#ede9fe" : isSug && !search ? "#f0fdf4" : "transparent", cursor: "pointer", display: "flex", alignItems: "center", gap: 6, fontSize: 12, textAlign: "left", fontFamily: "inherit", borderBottom: "1px solid #f9fafb" }}
                  onMouseEnter={e => { if (value !== k) e.currentTarget.style.background = "#f3f4f6"; }}
                  onMouseLeave={e => { if (value !== k) e.currentTarget.style.background = isSug && !search ? "#f0fdf4" : "transparent"; }}>
                  <span style={{ color: "#9ca3af", fontSize: 10, minWidth: 72, flexShrink: 0 }}>{f.object}</span>
                  <span style={{ fontWeight: 500, color: "#111827", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.apiName}</span>
                  {showLabel && <span style={{ color: "#6b7280", fontSize: 10, flexShrink: 0, maxWidth: 160, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>({f.label})</span>}
                  {f.custom && <span style={{ fontSize: 7, fontWeight: 700, color: "#7c3aed", background: "#f5f3ff", padding: "1px 4px", borderRadius: 3, flexShrink: 0 }}>CUSTOM</span>}
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
  const [refreshingSchema, setRefreshingSchema] = useState(false);

  // Fetch Salesforce schema fields from cached discovery
  const fetchSchemaFields = useCallback(async () => {
    setLoadingSfFields(true);
    try {
      const token = localStorage.getItem('token');
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 15000);

      let objectsRes;
      try {
        objectsRes = await fetch(`${API_URL}/api/integrations/salesforce/schema/objects`, {
          headers: { 'Authorization': `Bearer ${token}` },
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeout);
      }
      if (!objectsRes.ok) {
        const errData = await objectsRes.json().catch(() => ({}));
        throw new Error(errData.detail || `Failed to load SF objects (${objectsRes.status})`);
      }
      const objectsData = await objectsRes.json();
      const relevantObjects = objectsData.objects || objectsData.relevant_objects || [];

      if (relevantObjects.length === 0) {
        console.log('No SF objects discovered yet — schema discovery may be needed');
        setSfFields([]);
        return;
      }

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
      if (err.name === 'AbortError') {
        console.error('SF schema fetch timed out after 15s');
        toast.error('Salesforce field loading timed out — try Refresh Schema');
      } else {
        console.error('Failed to load Salesforce schema:', err);
        toast.error(err.message || 'Failed to load Salesforce fields');
      }
    } finally {
      setLoadingSfFields(false);
    }
  }, []);

  // Refresh schema from Salesforce (re-discover all fields)
  const refreshSchema = useCallback(async () => {
    setRefreshingSchema(true);
    try {
      const token = localStorage.getItem('token');
      const res = await fetch(`${API_URL}/api/integrations/salesforce/schema/discover`, {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      if (res.ok) {
        const data = await res.json();
        toast.success(`Schema refreshed: ${data.objects_discovered || 0} objects discovered`);
        // Re-fetch the fields from the updated schema
        await fetchSchemaFields();
      } else {
        const err = await res.json().catch(() => ({}));
        toast.error(err.detail || 'Failed to refresh schema');
      }
    } catch (err) {
      console.error('Schema refresh failed:', err);
      toast.error('Failed to refresh schema from Salesforce');
    } finally {
      setRefreshingSchema(false);
    }
  }, [fetchSchemaFields]);

  // Fetch schema fields on mount
  useEffect(() => {
    if (!isConnected) return;
    fetchSchemaFields();
  }, [isConnected, fetchSchemaFields]);

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

  // Effective mappings: Lead → Active Loan → MUM inheritance chain
  const effectiveMappings = useMemo(() => {
    const eff = { ...mappings };
    // Step 1: Active Loan inherits from Lead
    for (const [leadKey, activeKey] of Object.entries(LEAD_TO_ACTIVE_LOAN)) {
      if (!eff[activeKey] && eff[leadKey]) {
        eff[activeKey] = eff[leadKey];
      }
    }
    // Step 2: MUM inherits from Active Loan (which may itself be inherited from Lead)
    for (const [activeKey, mumKey] of Object.entries(ACTIVE_LOAN_TO_MUM)) {
      if (!eff[mumKey] && eff[activeKey]) {
        eff[mumKey] = eff[activeKey];
      }
    }
    return eff;
  }, [mappings]);

  // Track which fields are inherited (not directly mapped)
  const inheritedFields = useMemo(() => {
    const inherited = new Set();
    for (const [leadKey, activeKey] of Object.entries(LEAD_TO_ACTIVE_LOAN)) {
      if (!mappings[activeKey] && mappings[leadKey]) {
        inherited.add(activeKey);
      }
    }
    // MUM fields: inherited if not directly mapped but Active Loan equivalent has a value (direct or inherited)
    for (const [activeKey, mumKey] of Object.entries(ACTIVE_LOAN_TO_MUM)) {
      if (!mappings[mumKey] && (mappings[activeKey] || inherited.has(activeKey) && mappings[ACTIVE_TO_LEAD[activeKey]])) {
        inherited.add(mumKey);
      }
    }
    return inherited;
  }, [mappings]);

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
        body: JSON.stringify({ mappings: effectiveMappings })
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
  }, [effectiveMappings, onMappingSaved]);

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

  // Field Stats per stage (uses effectiveMappings so Active Loan counts include inherited)
  const fieldStats = useMemo(() => {
    const stats = {};
    for (const [key, stage] of Object.entries(CRM_FIELDS)) {
      let total = 0, mapped = 0, req = 0, reqMapped = 0;
      for (const sec of stage.sections) for (const f of sec.fields) {
        if (f.calculated) continue;
        total++; if (effectiveMappings[f.key]) mapped++;
        if (f.required) { req++; if (effectiveMappings[f.key]) reqMapped++; }
      }
      stats[key] = { total, mapped, req, reqMapped };
    }
    return stats;
  }, [effectiveMappings]);

  const totalMapped = slaStats.mapped + Object.values(fieldStats).reduce((s, v) => s + v.mapped, 0);
  const totalFields = slaStats.total + Object.values(fieldStats).reduce((s, v) => s + v.total, 0);

  // Auto-map helpers (includes Lead→Active Loan→MUM inheritance chain)
  const autoMap = useCallback((fields, prefix = "") => {
    setMappings(prev => {
      const n = { ...prev };
      for (const f of fields) {
        const k = prefix ? `${prefix}${f.key}` : f.key;
        if (n[k]) continue;
        // For CRM fields (not SLA), try inheriting from parent stage first
        if (!prefix) {
          // Active Loan inherits from Lead
          const leadKey = ACTIVE_TO_LEAD[f.key];
          if (leadKey && n[leadKey]) { n[k] = n[leadKey]; continue; }
          // MUM inherits from Active Loan
          const activeKey = MUM_TO_ACTIVE[f.key];
          if (activeKey && n[activeKey]) { n[k] = n[activeKey]; continue; }
          // MUM also chains through: if Active Loan inherited from Lead
          if (activeKey && ACTIVE_TO_LEAD[activeKey] && n[ACTIVE_TO_LEAD[activeKey]]) { n[k] = n[ACTIVE_TO_LEAD[activeKey]]; continue; }
        }
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

  const fieldsDisabled = loadingSfFields || refreshingSchema || sfFields.length === 0;
  const fieldsPlaceholder = loadingSfFields ? "Loading fields..." : refreshingSchema ? "Refreshing schema..." : (sfFields.length === 0 ? "No fields — click Refresh Schema above" : "Select Salesforce field...");

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
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {loadingSfFields && <span style={{ color: "#fbbf24", fontSize: 11 }}>Loading SF fields...</span>}
            {refreshingSchema && <span style={{ color: "#fbbf24", fontSize: 11 }}>Refreshing from Salesforce...</span>}
            <div style={{ textAlign: "right", marginRight: 4 }}>
              <div style={{ color: "#94a3b8", fontSize: 10 }}>{sfFields.length} SF fields loaded</div>
              <div style={{ color: "#64748b", fontSize: 9 }}>{sfFields.filter(f => f.custom).length} custom</div>
            </div>
            <button onClick={refreshSchema} disabled={refreshingSchema || loadingSfFields}
              style={{ padding: "7px 14px", borderRadius: 7, border: "1.5px solid #6366f1", background: "transparent", color: "#818cf8", fontSize: 11, fontWeight: 700, cursor: (refreshingSchema || loadingSfFields) ? "not-allowed" : "pointer", fontFamily: "inherit", opacity: (refreshingSchema || loadingSfFields) ? 0.5 : 1, whiteSpace: "nowrap" }}>
              {refreshingSchema ? "\u21BB Refreshing..." : "\u21BB Refresh Schema"}
            </button>
            <div style={{ width: 1, height: 28, background: "#334155" }} />
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

      {/* Schema alert */}
      {!loadingSfFields && !refreshingSchema && sfFields.length > 0 && sfFields.filter(f => f.custom).length === 0 && (
        <div style={{ margin: "0 24px", padding: "10px 16px", background: "#fffbeb", border: "1px solid #fbbf24", borderRadius: 8, display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
          <span style={{ fontSize: 16, flexShrink: 0 }}>{"\u26A0\uFE0F"}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#92400e" }}>No custom fields found in Salesforce</div>
            <div style={{ fontSize: 11, color: "#a16207" }}>SSN, loan fields, and other custom fields may be missing. Click <strong>Refresh Schema</strong> above to re-scan your Salesforce org.</div>
          </div>
        </div>
      )}
      {!loadingSfFields && !refreshingSchema && sfFields.length === 0 && (
        <div style={{ margin: "0 24px", padding: "10px 16px", background: "#fef2f2", border: "1px solid #fca5a5", borderRadius: 8, display: "flex", alignItems: "center", gap: 10, marginTop: 8 }}>
          <span style={{ fontSize: 16, flexShrink: 0 }}>{"\u274C"}</span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: "#991b1b" }}>No Salesforce fields loaded</div>
            <div style={{ fontSize: 11, color: "#b91c1c" }}>Click <strong>Refresh Schema</strong> to discover fields from your connected Salesforce org.</div>
          </div>
          <button onClick={refreshSchema} disabled={refreshingSchema}
            style={{ padding: "6px 14px", borderRadius: 6, border: "none", background: "#dc2626", color: "#fff", fontSize: 11, fontWeight: 700, cursor: "pointer", fontFamily: "inherit", whiteSpace: "nowrap" }}>
            Refresh Now
          </button>
        </div>
      )}

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
                <div key={phase} style={{ marginBottom: 6, background: "#fff", borderRadius: 8, border: "1px solid #e2e8f0" }}>
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
              if (filterUnmapped) fields = fields.filter(f => !f.calculated && !effectiveMappings[f.key]);
              if (fields.length === 0 && filterUnmapped) return null;
              if (fields.length === 0) return null;
              const expanded = expandedSections[section.title] !== false;
              const mappableFields = section.fields.filter(f => !f.calculated);
              const calculatedCount = section.fields.length - mappableFields.length;
              const mapped = mappableFields.filter(f => effectiveMappings[f.key]).length;
              const allCalculated = calculatedCount === section.fields.length;
              return (
                <div key={section.title} style={{ marginBottom: 6, background: "#fff", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <button onClick={() => toggle(section.title)} style={{
                    width: "100%", padding: "10px 14px", border: "none", background: "#fafafa", cursor: "pointer",
                    display: "flex", alignItems: "center", justifyContent: "space-between", fontFamily: "inherit",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontSize: 11, color: "#9ca3af" }}>{expanded ? "\u25BE" : "\u25B8"}</span>
                      <span style={{ fontWeight: 700, fontSize: 13, color: "#374151" }}>{section.title}</span>
                      {calculatedCount > 0 && <span style={{ fontSize: 9, fontWeight: 700, color: "#0369a1", background: "#e0f2fe", padding: "1px 6px", borderRadius: 3 }}>{calculatedCount} calculated</span>}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {!allCalculated && (
                        <span style={{ fontSize: 11, fontWeight: 700, color: mapped === mappableFields.length ? "#059669" : "#6b7280", background: mapped === mappableFields.length ? "#d1fae5" : "#f3f4f6", padding: "2px 8px", borderRadius: 100 }}>
                          {mapped}/{mappableFields.length}
                        </span>
                      )}
                      {!allCalculated && mapped < mappableFields.length && !fieldsDisabled && (
                        <button onClick={e => { e.stopPropagation(); autoMapSection(mappableFields); }}
                          style={{ padding: "3px 8px", borderRadius: 4, border: "1px solid #d1d5db", background: "#fff", fontSize: 10, fontWeight: 700, color: "#6366f1", cursor: "pointer", fontFamily: "inherit" }}>
                          Accept All
                        </button>
                      )}
                    </div>
                  </button>
                  {expanded && fields.map((f) => {
                    if (f.calculated) {
                      return (
                        <div key={f.key} style={{
                          display: "flex", alignItems: "center", gap: 10, padding: "9px 14px",
                          borderTop: "1px solid #f3f4f6",
                          background: "#f0f9ff",
                        }}>
                          <div style={{
                            width: 7, height: 7, borderRadius: 100, flexShrink: 0,
                            background: "#0ea5e9", boxShadow: "0 0 0 3px #e0f2fe",
                          }} />
                          <div style={{ width: 170, flexShrink: 0 }}>
                            <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
                              <span style={{ fontWeight: 600, fontSize: 13, color: "#111827" }}>{f.label}</span>
                              <span style={{ fontSize: 7, fontWeight: 800, color: "#0369a1", background: "#e0f2fe", padding: "1px 5px", borderRadius: 3, letterSpacing: "0.03em" }}>CALCULATED</span>
                            </div>
                            <TypeBadge type={f.type} />
                          </div>
                          <div style={{ color: "#0ea5e9", fontSize: 13, flexShrink: 0 }}>=</div>
                          <div style={{ flex: 1, padding: "7px 10px", borderRadius: 6, background: "#e0f2fe", border: "1.5px solid #7dd3fc", fontSize: 12, color: "#0c4a6e" }}>
                            {f.calculatedDesc}
                          </div>
                        </div>
                      );
                    }
                    const isInherited = inheritedFields.has(f.key);
                    const hasEffective = !!effectiveMappings[f.key];
                    const isMapped = hasEffective;
                    return (
                      <div key={f.key} style={{
                        display: "flex", alignItems: "center", gap: 10, padding: "9px 14px",
                        borderTop: "1px solid #f3f4f6",
                        background: isInherited ? "#f5f3ff" : isMapped ? "#fafffe" : f.required && !isMapped ? "#fffbeb" : "transparent",
                      }}>
                        <div style={{
                          width: 7, height: 7, borderRadius: 100, flexShrink: 0,
                          background: isMapped ? (isInherited ? "#6366f1" : "#059669") : f.required ? "#f59e0b" : "#d1d5db",
                          boxShadow: isMapped ? (isInherited ? "0 0 0 3px #e0e7ff" : "0 0 0 3px #d1fae5") : f.required && !isMapped ? "0 0 0 3px #fef3c7" : "none",
                        }} />
                        <div style={{ width: 170, flexShrink: 0 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 5, flexWrap: "wrap" }}>
                            <span style={{ fontWeight: 600, fontSize: 13, color: "#111827" }}>{f.label}</span>
                            {f.required && <span style={{ fontSize: 8, fontWeight: 800, color: "#dc2626" }}>REQ</span>}
                            {isInherited && <span style={{ fontSize: 7, fontWeight: 700, color: "#6366f1", background: "#eef2ff", padding: "1px 5px", borderRadius: 3 }}>{MUM_TO_ACTIVE[f.key] ? "FROM ACTIVE" : "FROM LEAD"}</span>}
                          </div>
                          <TypeBadge type={f.type} />
                        </div>
                        <div style={{ color: isMapped ? (isInherited ? "#6366f1" : "#059669") : "#d1d5db", fontSize: 13, flexShrink: 0 }}>{"\u2192"}</div>
                        <SearchableSelect value={effectiveMappings[f.key] || null} onChange={val => setMapping(f.key, val)} suggestedSF={f.suggestedSF} sfFields={sfFields} disabled={fieldsDisabled} placeholderText={fieldsPlaceholder} />
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

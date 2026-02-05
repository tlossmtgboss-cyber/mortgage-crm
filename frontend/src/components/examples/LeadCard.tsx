/**
 * LeadCard - Sample TypeScript component
 *
 * This component demonstrates TypeScript integration with the mortgage CRM types.
 * It can be used as a reference for migrating other components to TypeScript.
 */

import React from 'react';
import type { Lead, LeadStage } from '@/types';

// ============================================================================
// TYPE DEFINITIONS
// ============================================================================

interface LeadCardProps {
  lead: Lead;
  onStageChange?: (leadId: number, newStage: LeadStage) => void;
  onEdit?: (lead: Lead) => void;
  isSelected?: boolean;
  showScore?: boolean;
}

interface StageInfo {
  label: string;
  color: string;
  bgColor: string;
}

// ============================================================================
// CONSTANTS
// ============================================================================

const STAGE_STYLES: Record<LeadStage, StageInfo> = {
  'New': { label: 'New', color: '#1976d2', bgColor: '#e3f2fd' },
  'Attempted Contact': { label: 'Attempted', color: '#ed6c02', bgColor: '#fff3e0' },
  'Prospect': { label: 'Prospect', color: '#9c27b0', bgColor: '#f3e5f5' },
  'Application': { label: 'Application', color: '#0288d1', bgColor: '#e1f5fe' },
  'APPLICATION_STARTED': { label: 'App Started', color: '#0288d1', bgColor: '#e1f5fe' },
  'Document Fulfillment': { label: 'Docs', color: '#00838f', bgColor: '#e0f7fa' },
  'Pre-Qualified': { label: 'Pre-Qual', color: '#2e7d32', bgColor: '#e8f5e9' },
  'Pre-Approved': { label: 'Pre-Approved', color: '#1b5e20', bgColor: '#c8e6c9' },
  'Under Contract': { label: 'Contract', color: '#4527a0', bgColor: '#ede7f6' },
  'Long-Term Nurture': { label: 'Nurture', color: '#6d4c41', bgColor: '#efebe9' },
  'Closed': { label: 'Closed', color: '#388e3c', bgColor: '#c8e6c9' },
  'AMR': { label: 'AMR', color: '#5d4037', bgColor: '#d7ccc8' },
  'Referral Source': { label: 'Referral', color: '#00695c', bgColor: '#e0f2f1' },
  'Withdrawn': { label: 'Withdrawn', color: '#757575', bgColor: '#eeeeee' },
  'Does Not Qualify': { label: 'DNQ', color: '#c62828', bgColor: '#ffebee' },
  'Disclosed': { label: 'Disclosed', color: '#283593', bgColor: '#e8eaf6' },
};

// ============================================================================
// HELPER FUNCTIONS
// ============================================================================

function formatPhoneNumber(phone: string | null): string {
  if (!phone) return '';
  const cleaned = phone.replace(/\D/g, '');
  if (cleaned.length === 10) {
    return `(${cleaned.slice(0, 3)}) ${cleaned.slice(3, 6)}-${cleaned.slice(6)}`;
  }
  return phone;
}

function formatCurrency(amount: number | null): string {
  if (amount === null || amount === undefined) return '';
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount);
}

function getScoreColor(score: number): string {
  if (score >= 80) return '#2e7d32';
  if (score >= 60) return '#ed6c02';
  if (score >= 40) return '#f57c00';
  return '#d32f2f';
}

// ============================================================================
// COMPONENT
// ============================================================================

export const LeadCard: React.FC<LeadCardProps> = ({
  lead,
  onStageChange,
  onEdit,
  isSelected = false,
  showScore = true,
}) => {
  const stageInfo = STAGE_STYLES[lead.stage] || STAGE_STYLES['New'];

  const handleStageClick = (newStage: LeadStage): void => {
    if (onStageChange) {
      onStageChange(lead.id, newStage);
    }
  };

  const handleEditClick = (): void => {
    if (onEdit) {
      onEdit(lead);
    }
  };

  return (
    <div
      style={{
        border: isSelected ? '2px solid #1976d2' : '1px solid #e0e0e0',
        borderRadius: '8px',
        padding: '16px',
        backgroundColor: isSelected ? '#f5f5f5' : '#ffffff',
        transition: 'all 0.2s ease',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
        <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 600 }}>
          {lead.name}
        </h3>
        {showScore && (
          <span
            style={{
              fontSize: '14px',
              fontWeight: 600,
              color: getScoreColor(lead.ai_score),
            }}
          >
            Score: {lead.ai_score}
          </span>
        )}
      </div>

      {/* Stage Badge */}
      <div style={{ marginBottom: '12px' }}>
        <span
          style={{
            display: 'inline-block',
            padding: '4px 12px',
            borderRadius: '16px',
            fontSize: '12px',
            fontWeight: 500,
            color: stageInfo.color,
            backgroundColor: stageInfo.bgColor,
          }}
        >
          {stageInfo.label}
        </span>
      </div>

      {/* Contact Info */}
      <div style={{ fontSize: '14px', color: '#666', marginBottom: '12px' }}>
        {lead.email && (
          <div style={{ marginBottom: '4px' }}>
            <a href={`mailto:${lead.email}`} style={{ color: '#1976d2', textDecoration: 'none' }}>
              {lead.email}
            </a>
          </div>
        )}
        {lead.phone && (
          <div>
            <a href={`tel:${lead.phone}`} style={{ color: '#1976d2', textDecoration: 'none' }}>
              {formatPhoneNumber(lead.phone)}
            </a>
          </div>
        )}
      </div>

      {/* Loan Info */}
      {(lead.loan_amount || lead.loan_type) && (
        <div style={{ fontSize: '13px', color: '#888', marginBottom: '12px' }}>
          {lead.loan_type && <span>{lead.loan_type}</span>}
          {lead.loan_type && lead.loan_amount && <span> - </span>}
          {lead.loan_amount && <span>{formatCurrency(lead.loan_amount)}</span>}
        </div>
      )}

      {/* Actions */}
      <div style={{ display: 'flex', gap: '8px', marginTop: '16px' }}>
        <button
          onClick={handleEditClick}
          style={{
            flex: 1,
            padding: '8px 16px',
            border: '1px solid #1976d2',
            borderRadius: '4px',
            backgroundColor: 'transparent',
            color: '#1976d2',
            cursor: 'pointer',
            fontSize: '14px',
          }}
        >
          Edit
        </button>
        <button
          onClick={() => handleStageClick('Prospect')}
          style={{
            flex: 1,
            padding: '8px 16px',
            border: 'none',
            borderRadius: '4px',
            backgroundColor: '#1976d2',
            color: '#ffffff',
            cursor: 'pointer',
            fontSize: '14px',
          }}
        >
          Move to Prospect
        </button>
      </div>
    </div>
  );
};

export default LeadCard;

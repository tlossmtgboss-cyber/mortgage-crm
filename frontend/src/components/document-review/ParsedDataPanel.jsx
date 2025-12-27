/**
 * ParsedDataPanel
 *
 * Right-side panel showing extracted data with comparison to existing profile.
 * Groups fields by category and highlights conflicts.
 */

import React, { useMemo } from 'react';
import DataComparisonRow from './DataComparisonRow';
import './ParsedDataPanel.css';

// Field display labels and categories
const FIELD_CONFIG = {
  // Identity
  full_name: { label: 'Full Name', category: 'Identity' },
  first_name: { label: 'First Name', category: 'Identity' },
  last_name: { label: 'Last Name', category: 'Identity' },
  middle_name: { label: 'Middle Name', category: 'Identity' },
  date_of_birth: { label: 'Date of Birth', category: 'Identity' },
  ssn_last_4: { label: 'SSN (Last 4)', category: 'Identity' },

  // Address
  address: { label: 'Street Address', category: 'Address' },
  city: { label: 'City', category: 'Address' },
  state: { label: 'State', category: 'Address' },
  zip: { label: 'ZIP Code', category: 'Address' },
  zip_code: { label: 'ZIP Code', category: 'Address' },

  // Income/Employment
  employer_name: { label: 'Employer', category: 'Employment' },
  employee_name: { label: 'Employee Name', category: 'Employment' },
  gross_pay: { label: 'Gross Pay', category: 'Income' },
  net_pay: { label: 'Net Pay', category: 'Income' },
  ytd_gross: { label: 'YTD Gross', category: 'Income' },
  ytd_net: { label: 'YTD Net', category: 'Income' },
  pay_date: { label: 'Pay Date', category: 'Income' },
  pay_period_start: { label: 'Pay Period Start', category: 'Income' },
  pay_period_end: { label: 'Pay Period End', category: 'Income' },
  pay_frequency: { label: 'Pay Frequency', category: 'Income' },
  wages: { label: 'Wages', category: 'Income' },
  federal_wages: { label: 'Federal Wages', category: 'Income' },
  tax_year: { label: 'Tax Year', category: 'Income' },
  annual_income: { label: 'Annual Income', category: 'Income' },
  adjusted_gross_income: { label: 'AGI', category: 'Income' },
  filing_status: { label: 'Filing Status', category: 'Income' },

  // Banking/Assets
  bank_name: { label: 'Bank Name', category: 'Assets' },
  account_holder: { label: 'Account Holder', category: 'Assets' },
  account_number: { label: 'Account Number', category: 'Assets' },
  account_type: { label: 'Account Type', category: 'Assets' },
  ending_balance: { label: 'Ending Balance', category: 'Assets' },
  average_balance: { label: 'Average Balance', category: 'Assets' },
  statement_date: { label: 'Statement Date', category: 'Assets' },
  statement_period_start: { label: 'Period Start', category: 'Assets' },
  statement_period_end: { label: 'Period End', category: 'Assets' },

  // Document Info
  document_date: { label: 'Document Date', category: 'Document' },
  issue_date: { label: 'Issue Date', category: 'Document' },
  expiration_date: { label: 'Expiration Date', category: 'Document' },
};

const ParsedDataPanel = ({
  extraction,
  comparison,
  fieldSelections,
  onFieldAction,
}) => {
  // Group fields by category
  const groupedFields = useMemo(() => {
    if (!extraction?.extracted_fields) return {};

    const groups = {};
    const extractedFields = extraction.extracted_fields;
    const comparisonFields = comparison?.comparisons || {};

    Object.entries(extractedFields).forEach(([fieldName, extractedValue]) => {
      // Skip empty values
      if (extractedValue === null || extractedValue === undefined || extractedValue === '') {
        return;
      }

      const config = FIELD_CONFIG[fieldName] || {
        label: formatFieldLabel(fieldName),
        category: 'Other',
      };

      const category = config.category;
      if (!groups[category]) {
        groups[category] = [];
      }

      const comparisonData = comparisonFields[fieldName] || {};

      groups[category].push({
        fieldName,
        label: config.label,
        extractedValue,
        currentValue: comparisonData.current_value,
        confidence: extraction.confidence_scores?.[fieldName],
        provenance: extraction.provenance?.[fieldName],
        isConflict: comparisonData.status === 'conflict',
        isNew: comparisonData.status === 'new' ||
               (extractedValue && !comparisonData.current_value),
        isMatch: comparisonData.status === 'match',
      });
    });

    return groups;
  }, [extraction, comparison]);

  // Count stats
  const stats = useMemo(() => {
    let conflicts = 0;
    let newFields = 0;
    let matches = 0;

    Object.values(groupedFields).flat().forEach(field => {
      if (field.isConflict) conflicts++;
      else if (field.isNew) newFields++;
      else if (field.isMatch) matches++;
    });

    return { conflicts, newFields, matches };
  }, [groupedFields]);

  // Sort categories by importance
  const categoryOrder = ['Identity', 'Address', 'Employment', 'Income', 'Assets', 'Document', 'Other'];
  const sortedCategories = Object.keys(groupedFields).sort(
    (a, b) => categoryOrder.indexOf(a) - categoryOrder.indexOf(b)
  );

  if (!extraction) {
    return (
      <div className="parsed-data-panel empty">
        <p>No extraction data available</p>
      </div>
    );
  }

  return (
    <div className="parsed-data-panel">
      {/* Summary Header */}
      <div className="panel-header">
        <h3>Extracted Data</h3>
        <div className="extraction-stats">
          {stats.conflicts > 0 && (
            <span className="stat conflict">
              <span className="stat-count">{stats.conflicts}</span>
              <span className="stat-label">Conflicts</span>
            </span>
          )}
          {stats.newFields > 0 && (
            <span className="stat new">
              <span className="stat-count">{stats.newFields}</span>
              <span className="stat-label">New</span>
            </span>
          )}
          {stats.matches > 0 && (
            <span className="stat match">
              <span className="stat-count">{stats.matches}</span>
              <span className="stat-label">Matches</span>
            </span>
          )}
        </div>
      </div>

      {/* Field Groups */}
      <div className="field-groups">
        {sortedCategories.map(category => (
          <div key={category} className="field-group">
            <div className="group-header">
              <h4>{category}</h4>
              <span className="field-count">
                {groupedFields[category].length} fields
              </span>
            </div>
            <div className="group-fields">
              {groupedFields[category].map(field => (
                <DataComparisonRow
                  key={field.fieldName}
                  fieldName={field.fieldName}
                  label={field.label}
                  extractedValue={field.extractedValue}
                  currentValue={field.currentValue}
                  confidence={field.confidence}
                  provenance={field.provenance}
                  selectedAction={fieldSelections[field.fieldName]}
                  onActionSelect={onFieldAction}
                  isConflict={field.isConflict}
                  isNew={field.isNew}
                />
              ))}
            </div>
          </div>
        ))}
      </div>

      {/* Empty State */}
      {sortedCategories.length === 0 && (
        <div className="no-fields">
          <p>No data could be extracted from this document.</p>
        </div>
      )}
    </div>
  );
};

// Helper to format field names as labels
function formatFieldLabel(fieldName) {
  return fieldName
    .replace(/_/g, ' ')
    .replace(/\b\w/g, c => c.toUpperCase());
}

export default ParsedDataPanel;

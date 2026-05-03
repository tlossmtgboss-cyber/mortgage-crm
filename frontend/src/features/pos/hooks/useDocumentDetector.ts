/**
 * Real-time document detector — mirrors the backend DocumentChecklistService
 * rules engine. Evaluates all POS section data and returns which documents
 * the borrower will need to provide.
 *
 * Fires on every section data change so the Documents tab updates live as
 * the applicant fills out the form.
 */
import { useMemo } from 'react';

import type { SectionResponse } from '../types';

export type DocCategory = 'income' | 'assets' | 'identity' | 'property' | 'credit' | 'compliance';
export type DocPriority = 'required' | 'conditional';

export interface DetectedDocument {
  id: string;
  name: string;
  category: DocCategory;
  priority: DocPriority;
  description: string;
  reason: string;
  triggeredBy: string;
}

function sec(sections: Partial<Record<string, SectionResponse>>, key: string): Record<string, unknown> {
  return (sections[key]?.data as Record<string, unknown>) || {};
}

function nested(data: Record<string, unknown>, key: string): Record<string, unknown> {
  return (data[key] as Record<string, unknown>) || {};
}

export function useDocumentDetector(
  sections: Partial<Record<string, SectionResponse>>,
): DetectedDocument[] {
  return useMemo(() => {
    const docs: DetectedDocument[] = [];
    const added = new Set<string>();

    const add = (doc: Omit<DetectedDocument, 'id'>) => {
      const id = doc.name.toLowerCase().replace(/\s+/g, '_');
      if (added.has(id)) return;
      added.add(id);
      docs.push({ ...doc, id });
    };

    const employment = sec(sections, 'employment');
    const assets = sec(sections, 'assets');
    const loan = sec(sections, 'loan');
    const declarations = sec(sections, 'declarations');
    const reo = sec(sections, 'reo');
    const liabilities = sec(sections, 'liabilities');
    const employer = nested(employment, 'employer');

    // ---- BASE DOCUMENTS (always required once any section has data) ----
    const hasAnyData = Object.values(sections).some(s => s && Object.keys(s.data || {}).length > 0);
    if (hasAnyData) {
      add({
        name: 'Government-issued photo ID',
        category: 'identity',
        priority: 'required',
        description: "Valid driver's license, passport, or state ID",
        reason: 'Identity verification',
        triggeredBy: 'Application started',
      });
      add({
        name: 'Pay stubs (30 days)',
        category: 'income',
        priority: 'required',
        description: 'Most recent 30 days of pay stubs',
        reason: 'Verify current employment and income',
        triggeredBy: 'Application started',
      });
      add({
        name: 'W-2 forms (2 years)',
        category: 'income',
        priority: 'required',
        description: 'W-2 forms for the past 2 years',
        reason: 'Verify employment history and income',
        triggeredBy: 'Application started',
      });
      add({
        name: 'Federal tax returns (2 years)',
        category: 'income',
        priority: 'required',
        description: 'Federal tax returns with all schedules',
        reason: 'Verify reported income',
        triggeredBy: 'Application started',
      });
      add({
        name: 'Bank statements (2 months)',
        category: 'assets',
        priority: 'required',
        description: 'Bank statements for all accounts (all pages)',
        reason: 'Verify funds for down payment and closing costs',
        triggeredBy: 'Application started',
      });
    }

    // ---- SELF-EMPLOYED ----
    const empType = employment.employment_type as string;
    const isSelfEmployed = empType === 'self_employed' || empType === 'contractor' || employer.is_self_employed === true;
    if (isSelfEmployed) {
      add({
        name: 'Business tax returns (2 years)',
        category: 'income',
        priority: 'required',
        description: 'Business tax returns for the past 2 years',
        reason: 'Verify business income',
        triggeredBy: 'Self-employment indicated',
      });
      add({
        name: 'Profit & loss statement (YTD)',
        category: 'income',
        priority: 'required',
        description: 'Year-to-date profit and loss statement',
        reason: 'Verify current business performance',
        triggeredBy: 'Self-employment indicated',
      });
      add({
        name: 'Business license',
        category: 'income',
        priority: 'conditional',
        description: 'Current business license',
        reason: 'Verify business legitimacy',
        triggeredBy: 'Self-employment indicated',
      });
    }

    // ---- GIFT FUNDS ----
    if (assets.receiving_gift === true) {
      add({
        name: 'Gift letter',
        category: 'assets',
        priority: 'required',
        description: 'Signed gift letter from donor stating amount, relationship, and no repayment required',
        reason: 'Verify gift funds are a true gift',
        triggeredBy: 'Gift funds indicated in Assets',
      });
      add({
        name: "Donor's bank statement",
        category: 'assets',
        priority: 'required',
        description: "Donor's bank statement showing ability to give gift",
        reason: 'Verify donor has available funds',
        triggeredBy: 'Gift funds indicated in Assets',
      });
    }

    // ---- PURCHASE ----
    const loanPurpose = loan.loan_purpose as string;
    if (loanPurpose === 'purchase') {
      add({
        name: 'Purchase contract',
        category: 'property',
        priority: 'required',
        description: 'Signed purchase agreement/contract',
        reason: 'Verify property details and purchase price',
        triggeredBy: 'Purchase loan selected',
      });
      add({
        name: 'Earnest money receipt',
        category: 'property',
        priority: 'required',
        description: 'Earnest money deposit receipt',
        reason: 'Verify deposit amount and source',
        triggeredBy: 'Purchase loan selected',
      });
    }

    // ---- REFINANCE ----
    if (loanPurpose === 'refinance') {
      add({
        name: 'Current mortgage statement',
        category: 'property',
        priority: 'required',
        description: 'Most recent mortgage statement',
        reason: 'Verify current loan balance and payment history',
        triggeredBy: 'Refinance selected',
      });
      add({
        name: 'Homeowners insurance policy',
        category: 'property',
        priority: 'required',
        description: 'Current homeowners insurance declarations page',
        reason: 'Verify adequate coverage',
        triggeredBy: 'Refinance selected',
      });
    }

    // ---- OWNS OTHER PROPERTY ----
    if (reo.owns_other_property === true) {
      add({
        name: 'Mortgage statements (all properties)',
        category: 'property',
        priority: 'required',
        description: 'Current mortgage statements for each property owned',
        reason: 'Verify existing obligations',
        triggeredBy: 'Other real estate indicated',
      });
      add({
        name: 'Property insurance (all properties)',
        category: 'property',
        priority: 'conditional',
        description: 'Insurance declarations pages for each owned property',
        reason: 'Verify coverage on owned properties',
        triggeredBy: 'Other real estate indicated',
      });

      const properties = (reo.properties as Array<Record<string, unknown>>) || [];
      const hasRental = properties.some(p => p.monthly_rental_income && Number(p.monthly_rental_income) > 0);
      if (hasRental) {
        add({
          name: 'Lease agreements',
          category: 'income',
          priority: 'required',
          description: 'Current signed lease agreements for rental properties',
          reason: 'Verify rental income',
          triggeredBy: 'Rental income reported on owned property',
        });
      }
    }

    // ---- BANKRUPTCY ----
    if (declarations.bankruptcy_7_years === true) {
      add({
        name: 'Bankruptcy discharge papers',
        category: 'credit',
        priority: 'required',
        description: 'Bankruptcy discharge documentation',
        reason: 'Verify bankruptcy was discharged and waiting period met',
        triggeredBy: 'Bankruptcy declared',
      });
    }

    // ---- FORECLOSURE ----
    if (declarations.foreclosure_7_years === true) {
      add({
        name: 'Foreclosure documentation',
        category: 'credit',
        priority: 'required',
        description: 'Documents showing foreclosure date and resolution',
        reason: 'Verify waiting period compliance',
        triggeredBy: 'Foreclosure declared',
      });
    }

    // ---- NON-REPORTING DEBTS (child support, alimony) ----
    if (liabilities.has_non_reporting_debts === true) {
      const liabs = (liabilities.liabilities as Array<Record<string, unknown>>) || [];
      const hasChildSupport = liabs.some(l => l.type === 'child_support' || l.type === 'alimony' || l.type === 'separate_maintenance');
      if (hasChildSupport) {
        add({
          name: 'Court order / divorce decree',
          category: 'compliance',
          priority: 'required',
          description: 'Court order or divorce decree showing obligation amount',
          reason: 'Verify court-ordered payment obligations',
          triggeredBy: 'Child support / alimony indicated',
        });
      }
      const hasGarnishment = liabs.some(l => l.type === 'garnishment');
      if (hasGarnishment) {
        add({
          name: 'Garnishment order',
          category: 'compliance',
          priority: 'required',
          description: 'Court order showing garnishment details',
          reason: 'Verify garnishment terms',
          triggeredBy: 'Wage garnishment indicated',
        });
      }
    }

    // ---- MILITARY ----
    if (empType === 'military') {
      add({
        name: 'Leave & Earnings Statement (LES)',
        category: 'income',
        priority: 'required',
        description: 'Most recent Leave & Earnings Statement',
        reason: 'Verify military income and allowances',
        triggeredBy: 'Military employment selected',
      });
    }

    // ---- RETIRED ----
    if (empType === 'retired') {
      add({
        name: 'Retirement/pension award letter',
        category: 'income',
        priority: 'required',
        description: 'Award letter showing monthly benefit amount',
        reason: 'Verify retirement income',
        triggeredBy: 'Retired employment selected',
      });
      add({
        name: 'Social Security award letter',
        category: 'income',
        priority: 'conditional',
        description: 'SSA-1099 or benefit verification letter',
        reason: 'Verify Social Security income if applicable',
        triggeredBy: 'Retired employment selected',
      });
    }

    // ---- OUTSTANDING JUDGMENTS ----
    if (declarations.outstanding_judgments === true) {
      add({
        name: 'Judgment documentation',
        category: 'credit',
        priority: 'required',
        description: 'Court records showing judgment details and payment status',
        reason: 'Verify judgment status for underwriting',
        triggeredBy: 'Outstanding judgments declared',
      });
    }

    // ---- LAWSUIT ----
    if (declarations.party_to_lawsuit === true) {
      add({
        name: 'Lawsuit documentation',
        category: 'credit',
        priority: 'conditional',
        description: 'Details of pending litigation',
        reason: 'Assess potential financial liability',
        triggeredBy: 'Pending lawsuit declared',
      });
    }

    return docs;
  }, [sections]);
}

export const CATEGORY_LABELS: Record<DocCategory, string> = {
  income: 'Income',
  assets: 'Assets',
  identity: 'Identity',
  property: 'Property',
  credit: 'Credit',
  compliance: 'Compliance',
};

export const CATEGORY_ORDER: DocCategory[] = ['identity', 'income', 'assets', 'property', 'credit', 'compliance'];

// Core mortgage types for gradual TypeScript migration

export interface Lead {
  id: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  stage: string;
  ai_score: number;
  source: string;
  /* ... */
}

export interface Loan {
  id: string;
  loan_number: string;
  amount: number;
  rate: number;
  stage: LoanStage;
  borrower_name: string;
  /* ... */
}

export type LoanStage =
  | 'APPLICATION'
  | 'DISCLOSED'
  | 'PROCESSING'
  | 'SUBMITTED'
  | 'UNDERWRITING'
  | 'UW_RECEIVED'
  | 'CONDITIONAL_APPROVAL'
  | 'APPROVED'
  | 'SUSPENDED'
  | 'CTC'
  | 'CLEAR_TO_CLOSE'
  | 'CLOSING'
  | 'DOCS'
  | 'DOCS_OUT'
  | 'FUNDED'
  | 'CANCELLED'
  | 'DENIED'
  | 'DEAD'
  | 'NURTURE'
  | 'WITHDRAWN'
  | 'DOES_NOT_QUALIFY';

export type LoanType =
  | 'conventional'
  | 'fha'
  | 'va'
  | 'usda'
  | 'jumbo'
  | 'non_qm';

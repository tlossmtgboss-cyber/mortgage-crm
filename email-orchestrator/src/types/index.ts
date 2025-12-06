/**
 * Perennia AI Email Orchestrator - Type Definitions
 */

export interface Email {
  id: string;
  messageId: string;
  conversationId?: string;
  subject: string;
  body: string;
  bodyPreview: string;
  from: EmailAddress;
  to: EmailAddress[];
  cc?: EmailAddress[];
  receivedDateTime: Date;
  sentDateTime?: Date;
  hasAttachments: boolean;
  attachments?: Attachment[];
  importance: 'low' | 'normal' | 'high';
  isRead: boolean;
  webLink?: string;
  categories?: string[];
}

export interface EmailAddress {
  name?: string;
  address: string;
}

export interface Attachment {
  id: string;
  name: string;
  contentType: string;
  size: number;
  isInline: boolean;
  contentBytes?: string;
}

export interface ProcessingContext {
  userId: number;
  userEmail: string;
  timestamp: Date;
  correlationId: string;
  retryCount: number;
  metadata: Record<string, any>;
}

export interface ProcessingResult {
  success: boolean;
  processor: string;
  action: string;
  timeSaved: number;
  createdRecords?: CreatedRecord[];
  sentEmails?: SentEmail[];
  createdTasks?: CreatedTask[];
  error?: string;
  metadata?: Record<string, any>;
}

export interface CreatedRecord {
  type: 'loan' | 'lead' | 'contact' | 'task' | 'note';
  id: number | string;
  description: string;
}

export interface SentEmail {
  to: string;
  subject: string;
  templateName: string;
}

export interface CreatedTask {
  id: number;
  title: string;
  dueDate?: Date;
  priority: 'low' | 'medium' | 'high' | 'critical';
}

export interface EmailTemplate {
  id: number;
  name: string;
  subject: string;
  body: string;
  isHtml: boolean;
  variables: string[];
  category?: string;
  createdAt: Date;
  updatedAt: Date;
}

export interface QueuedEmail {
  id: number;
  emailId: string;
  messageId: string;
  priority: number;
  status: 'pending' | 'processing' | 'completed' | 'failed' | 'retry';
  retryCount: number;
  lastError?: string;
  createdAt: Date;
  processedAt?: Date;
}

export interface SLAConfig {
  critical: number;  // hours
  high: number;
  medium: number;
  low: number;
}

export interface SLAStatus {
  emailId: string;
  priority: 'critical' | 'high' | 'medium' | 'low';
  receivedAt: Date;
  slaDeadline: Date;
  hoursRemaining: number;
  status: 'ok' | 'warning' | 'breached';
  respondedAt?: Date;
}

export interface ProcessorStats {
  name: string;
  totalRuns: number;
  successCount: number;
  failureCount: number;
  avgProcessingTimeMs: number;
  totalTimeSavedMinutes: number;
  lastRunAt?: Date;
}

export interface DailySummary {
  date: Date;
  totalEmailsReceived: number;
  totalEmailsProcessed: number;
  totalEmailsAutoResponded: number;
  totalTimeSavedMinutes: number;
  processorBreakdown: ProcessorStats[];
  slaCompliance: {
    total: number;
    onTime: number;
    breached: number;
    complianceRate: number;
  };
  topSenders: Array<{
    email: string;
    count: number;
  }>;
  pendingItems: number;
}

export interface LoanApplicationData {
  borrowerName: string;
  borrowerEmail: string;
  borrowerPhone?: string;
  coBorrowerName?: string;
  coBorrowerEmail?: string;
  loanType: 'purchase' | 'refinance' | 'cash_out' | 'heloc';
  loanAmount?: number;
  propertyAddress?: string;
  propertyType?: string;
  estimatedValue?: number;
  creditScore?: number;
  employmentType?: string;
  annualIncome?: number;
  source?: string;
}

export interface ClientInquiryData {
  clientId?: number;
  loanId?: number;
  leadId?: number;
  inquiryType: 'status' | 'document' | 'rate' | 'general' | 'complaint';
  urgency: 'low' | 'medium' | 'high' | 'critical';
  sentiment: 'positive' | 'neutral' | 'negative';
  summary: string;
  suggestedResponse?: string;
  autoRespondEligible: boolean;
}

export interface InvoiceData {
  vendorName: string;
  vendorEmail: string;
  invoiceNumber?: string;
  amount?: number;
  dueDate?: Date;
  category: 'appraisal' | 'title' | 'credit' | 'legal' | 'other';
  loanNumber?: string;
}

export interface DocumentData {
  documentType: string;
  category: 'income' | 'asset' | 'property' | 'identity' | 'credit' | 'other';
  associatedLoanId?: number;
  associatedLeadId?: number;
  fileName?: string;
  fileSize?: number;
  extractedData?: Record<string, any>;
}

export interface WebhookPayload {
  value: WebhookNotification[];
}

export interface WebhookNotification {
  subscriptionId: string;
  clientState: string;
  changeType: 'created' | 'updated' | 'deleted';
  resource: string;
  resourceData: {
    '@odata.type': string;
    '@odata.id': string;
    id: string;
  };
  tenantId: string;
}

export interface RetryConfig {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
  backoffMultiplier: number;
}

export type LogLevel = 'error' | 'warn' | 'info' | 'debug';

export interface OrchestratorConfig {
  graphAccessToken: string;
  senderEmail: string;
  anthropicApiKey: string;
  internalDomains: string[];
  slaConfig: SLAConfig;
  retryConfig: RetryConfig;
  enableAutoResponses: boolean;
  enableLoanCreation: boolean;
  enableInvoiceProcessing: boolean;
  enableSlaMonitoring: boolean;
}

/**
 * Email Orchestrator Initialization
 * Sets up all components and returns configured orchestrator
 */

import { Pool } from 'pg';
import { Logger } from 'winston';
import Anthropic from '@anthropic-ai/sdk';

import { EmailOrchestrator } from './core/EmailOrchestrator';
import { GraphEmailService } from './services/GraphEmailService';
import { EmailTemplateService } from './services/EmailTemplateService';
import { QueueManager } from './services/QueueManager';
import { DailySummaryBot } from './services/DailySummaryBot';

import {
  LoanApplicationProcessor,
  ClientInquiryProcessor,
  InvoiceProcessor,
  DocumentProcessor,
  SLAMonitorProcessor
} from './processors';

import { OrchestratorConfig, SLAConfig, RetryConfig } from './types';
import { DEFAULT_RETRY_CONFIG } from './utils/RetryManager';

export interface InitializationConfig {
  // Required
  graphAccessToken: string;
  senderEmail: string;
  anthropicApiKey: string;

  // Optional with defaults
  internalDomains?: string[];
  slaConfig?: Partial<SLAConfig>;
  retryConfig?: Partial<RetryConfig>;

  // Feature flags
  enableAutoResponses?: boolean;
  enableLoanCreation?: boolean;
  enableInvoiceProcessing?: boolean;
  enableSlaMonitoring?: boolean;

  // Accounting email for invoice forwarding
  accountingEmail?: string;
}

export interface InitializationResult {
  orchestrator: EmailOrchestrator;
  graphService: GraphEmailService;
  templateService: EmailTemplateService;
  queueManager: QueueManager;
  summaryBot: DailySummaryBot;
}

/**
 * Initialize the email orchestrator with all components
 */
export async function initializeEmailOrchestrator(
  config: InitializationConfig,
  pool: Pool,
  logger: Logger
): Promise<InitializationResult> {
  logger.info('Initializing Email Orchestrator...');

  // Build full config with defaults
  const slaConfig: SLAConfig = {
    critical: config.slaConfig?.critical ?? 1,
    high: config.slaConfig?.high ?? 4,
    medium: config.slaConfig?.medium ?? 24,
    low: config.slaConfig?.low ?? 48
  };

  const retryConfig: RetryConfig = {
    ...DEFAULT_RETRY_CONFIG,
    ...config.retryConfig
  };

  const orchestratorConfig: OrchestratorConfig = {
    graphAccessToken: config.graphAccessToken,
    senderEmail: config.senderEmail,
    anthropicApiKey: config.anthropicApiKey,
    internalDomains: config.internalDomains ?? [],
    slaConfig,
    retryConfig,
    enableAutoResponses: config.enableAutoResponses ?? true,
    enableLoanCreation: config.enableLoanCreation ?? true,
    enableInvoiceProcessing: config.enableInvoiceProcessing ?? true,
    enableSlaMonitoring: config.enableSlaMonitoring ?? true
  };

  // Initialize services
  const graphService = new GraphEmailService(
    config.graphAccessToken,
    logger
  );

  const templateService = new EmailTemplateService(
    pool,
    graphService,
    logger,
    config.senderEmail
  );

  // Load email templates
  await templateService.loadTemplates();
  logger.info('Email templates loaded');

  const queueManager = new QueueManager(pool, logger);
  const summaryBot = new DailySummaryBot(pool, templateService, logger);

  // Initialize Anthropic client
  const anthropic = new Anthropic({
    apiKey: config.anthropicApiKey
  });

  // Create orchestrator
  const orchestrator = new EmailOrchestrator(pool, logger, orchestratorConfig);

  // Register processors
  if (orchestratorConfig.enableSlaMonitoring) {
    orchestrator.registerProcessor(
      'SLAMonitorProcessor',
      new SLAMonitorProcessor(pool, logger, anthropic, templateService, slaConfig)
    );
    logger.info('SLA Monitor Processor registered');
  }

  if (orchestratorConfig.enableLoanCreation) {
    orchestrator.registerProcessor(
      'LoanApplicationProcessor',
      new LoanApplicationProcessor(pool, logger, anthropic, templateService, true)
    );
    logger.info('Loan Application Processor registered');
  }

  if (orchestratorConfig.enableInvoiceProcessing) {
    orchestrator.registerProcessor(
      'InvoiceProcessor',
      new InvoiceProcessor(
        pool,
        logger,
        anthropic,
        templateService,
        config.accountingEmail ?? 'accounting@company.com'
      )
    );
    logger.info('Invoice Processor registered');
  }

  // Always register document processor
  orchestrator.registerProcessor(
    'DocumentProcessor',
    new DocumentProcessor(pool, logger, anthropic, templateService)
  );
  logger.info('Document Processor registered');

  // Register client inquiry processor
  orchestrator.registerProcessor(
    'ClientInquiryProcessor',
    new ClientInquiryProcessor(
      pool,
      logger,
      anthropic,
      templateService,
      orchestratorConfig.enableAutoResponses
    )
  );
  logger.info('Client Inquiry Processor registered');

  logger.info('Email Orchestrator initialized successfully', {
    processors: orchestrator.getProcessors().map(p => p.name),
    features: {
      autoResponses: orchestratorConfig.enableAutoResponses,
      loanCreation: orchestratorConfig.enableLoanCreation,
      invoiceProcessing: orchestratorConfig.enableInvoiceProcessing,
      slaMonitoring: orchestratorConfig.enableSlaMonitoring
    }
  });

  return {
    orchestrator,
    graphService,
    templateService,
    queueManager,
    summaryBot
  };
}

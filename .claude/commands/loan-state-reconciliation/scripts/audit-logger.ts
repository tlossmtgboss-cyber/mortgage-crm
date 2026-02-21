// ─────────────────────────────────────────────────────────────────────────────
// Audit Logger for Loan State Transitions
// Captures every pipeline transition and status change for compliance
// ─────────────────────────────────────────────────────────────────────────────

interface AuditEntry {
  event: string;
  from_pipeline?: string;
  to_pipeline?: string;
  from_milestone?: string;
  to_milestone?: string;
  trigger: string;
  trigger_type: string;
  salesforce_opportunity_id: string;
  crm_record_id: string;
  user_id: string;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

interface AuditLogRecord {
  id: string;
  entry: AuditEntry;
  created_at: string;
  sync_batch_id: string;
}

// ─── Database Schema ────────────────────────────────────────────────────────

/*
  CREATE TABLE loan_state_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event VARCHAR(100) NOT NULL,
    from_pipeline VARCHAR(50),
    to_pipeline VARCHAR(50),
    from_milestone VARCHAR(100),
    to_milestone VARCHAR(100),
    trigger_value VARCHAR(200) NOT NULL,
    trigger_type VARCHAR(50) NOT NULL,
    salesforce_opportunity_id VARCHAR(50) NOT NULL,
    crm_record_id UUID NOT NULL,
    user_id UUID NOT NULL,
    sync_batch_id UUID NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Indexes for common queries
    INDEX idx_audit_crm_record (crm_record_id, created_at DESC),
    INDEX idx_audit_user (user_id, created_at DESC),
    INDEX idx_audit_event (event, created_at DESC),
    INDEX idx_audit_sf_opp (salesforce_opportunity_id),
    INDEX idx_audit_batch (sync_batch_id)
  );
*/

// ─── Logger Class ───────────────────────────────────────────────────────────

export class TransitionAuditLogger {
  private batchId: string;
  private pendingEntries: AuditEntry[] = [];

  constructor(batchId: string) {
    this.batchId = batchId;
  }

  /**
   * Queue an audit entry for batch insert
   */
  log(entry: AuditEntry): void {
    this.pendingEntries.push(entry);
  }

  /**
   * Check if a specific transition already occurred (idempotency guard)
   * Call this before executing a transition to prevent duplicates
   */
  async hasTransitionOccurred(
    db: any, // Your database client
    crmRecordId: string,
    fromPipeline: string,
    toPipeline: string,
    toMilestone: string,
    withinSeconds: number = 300 // 5-minute window
  ): Promise<boolean> {
    const cutoff = new Date(Date.now() - withinSeconds * 1000).toISOString();

    const result = await db.query(
      `SELECT EXISTS(
        SELECT 1 FROM loan_state_audit_log
        WHERE crm_record_id = $1
          AND from_pipeline = $2
          AND to_pipeline = $3
          AND to_milestone = $4
          AND created_at > $5
          AND event = 'pipeline_transition'
      ) as already_transitioned`,
      [crmRecordId, fromPipeline, toPipeline, toMilestone, cutoff]
    );

    return result.rows[0]?.already_transitioned ?? false;
  }

  /**
   * Flush all pending entries to the database in a single batch insert
   */
  async flush(db: any): Promise<number> {
    if (this.pendingEntries.length === 0) return 0;

    const values: any[] = [];
    const placeholders: string[] = [];
    let paramIndex = 1;

    for (const entry of this.pendingEntries) {
      placeholders.push(
        `($${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, ` +
        `$${paramIndex++}, $${paramIndex++}, $${paramIndex++}, $${paramIndex++}, ` +
        `$${paramIndex++}, $${paramIndex++}, $${paramIndex++})`
      );
      values.push(
        entry.event,
        entry.from_pipeline || null,
        entry.to_pipeline || null,
        entry.from_milestone || null,
        entry.to_milestone || null,
        entry.trigger,
        entry.trigger_type,
        entry.salesforce_opportunity_id,
        entry.crm_record_id,
        entry.user_id,
        this.batchId,
      );
    }

    await db.query(
      `INSERT INTO loan_state_audit_log
        (event, from_pipeline, to_pipeline, from_milestone, to_milestone,
         trigger_value, trigger_type, salesforce_opportunity_id, crm_record_id,
         user_id, sync_batch_id)
       VALUES ${placeholders.join(', ')}`,
      values
    );

    const count = this.pendingEntries.length;
    this.pendingEntries = [];
    return count;
  }

  /**
   * Query transition history for a specific loan record
   */
  static async getRecordHistory(
    db: any,
    crmRecordId: string,
    limit: number = 50
  ): Promise<AuditLogRecord[]> {
    const result = await db.query(
      `SELECT * FROM loan_state_audit_log
       WHERE crm_record_id = $1
       ORDER BY created_at DESC
       LIMIT $2`,
      [crmRecordId, limit]
    );
    return result.rows;
  }

  /**
   * Get transition metrics for monitoring dashboard
   */
  static async getTransitionMetrics(
    db: any,
    userId: string,
    sinceDaysAgo: number = 30
  ): Promise<{
    total_transitions: number;
    leads_to_active: number;
    active_to_mum: number;
    flagged_for_review: number;
    reactivations: number;
    unmapped_stages: number;
    backward_movements: number;
  }> {
    const since = new Date(Date.now() - sinceDaysAgo * 24 * 60 * 60 * 1000).toISOString();

    const result = await db.query(
      `SELECT
        COUNT(*) FILTER (WHERE event = 'pipeline_transition') as total_transitions,
        COUNT(*) FILTER (WHERE from_pipeline = 'leads' AND to_pipeline = 'active_loans') as leads_to_active,
        COUNT(*) FILTER (WHERE from_pipeline = 'active_loans' AND to_pipeline = 'mum') as active_to_mum,
        COUNT(*) FILTER (WHERE event LIKE '%blocked%' OR event LIKE '%flag%') as flagged_for_review,
        COUNT(*) FILTER (WHERE event = 'reactivation') as reactivations,
        COUNT(*) FILTER (WHERE event = 'unmapped_stage') as unmapped_stages,
        COUNT(*) FILTER (WHERE event = 'milestone_updated' AND metadata->>'backward' = 'true') as backward_movements
       FROM loan_state_audit_log
       WHERE user_id = $1 AND created_at > $2`,
      [userId, since]
    );

    return result.rows[0];
  }
}

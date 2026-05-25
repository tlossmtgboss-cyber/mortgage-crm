import React, { useState, useEffect, useRef } from 'react';
import { workflowGraphApi } from '../../services/workflowGraphApi';
import './NodeDetailDrawer.css';

const ROLES = ['LO', 'Processor', 'Concierge', 'AI', 'Manager', 'System'];

const CHANNELS = [
  { key: 'phone', label: 'Phone', icon: '📞' },
  { key: 'text', label: 'Text', icon: '📱' },
  { key: 'voicemail_drop', label: 'Voicemail Drop', icon: '📩' },
  { key: 'text_process', label: 'Text Process', icon: '💬' },
  { key: 'email', label: 'Email', icon: '✉️' },
  { key: 'referral_partner', label: 'Referral Partner', icon: '🤝' },
];

const DELAY_UNITS = [
  { value: 'minutes', label: 'Minutes' },
  { value: 'hours', label: 'Hours' },
  { value: 'days', label: 'Days' },
  { value: 'weeks', label: 'Weeks' },
];

const ACTION_TYPES = [
  { value: 'send_sms', label: 'Send SMS', icon: '📱' },
  { value: 'send_email', label: 'Send Email', icon: '✉️' },
  { value: 'send_voicemail', label: 'Voicemail Drop', icon: '📩' },
  { value: 'create_task', label: 'Create Task', icon: '☑️' },
  { value: 'make_call', label: 'Make Call', icon: '📞' },
  { value: 'update_field', label: 'Update Field', icon: '✏️' },
  { value: 'change_stage', label: 'Change Stage', icon: '📊' },
  { value: 'assign_owner', label: 'Assign Owner', icon: '👤' },
  { value: 'add_note', label: 'Add Note', icon: '📝' },
  { value: 'add_tag', label: 'Add Tag', icon: '🏷️' },
  { value: 'start_workflow', label: 'Start Workflow', icon: '🔄' },
  { value: 'webhook', label: 'Send Webhook', icon: '🔗' },
];

const TRIGGER_TYPES = [
  { value: 'stage_change', label: 'Stage Changes' },
  { value: 'new_lead', label: 'New Lead Created' },
  { value: 'field_change', label: 'Field Changes' },
  { value: 'date_trigger', label: 'Date-Based' },
  { value: 'manual', label: 'Manual Entry' },
];

const LEAD_STAGES = [
  'New', 'Contacted', 'Qualified', 'Pre-Qualified', 'Pre-Approved',
  'Application', 'Nurture', 'Dead', 'Does Not Qualify',
];

const LOAN_STAGES = [
  'APPLICATION', 'DISCLOSED', 'PROCESSING', 'SUBMITTED', 'UNDERWRITING',
  'UW_RECEIVED', 'CONDITIONAL_APPROVAL', 'APPROVED', 'SUSPENDED',
  'CTC', 'CLEAR_TO_CLOSE', 'CLOSING', 'DOCS', 'DOCS_OUT', 'FUNDED',
];

const CONDITION_FIELDS = [
  { value: 'lead.stage', label: 'Lead Stage', type: 'select', options: LEAD_STAGES },
  { value: 'loan.stage', label: 'Loan Stage', type: 'select', options: LOAN_STAGES },
  { value: 'lead.source', label: 'Lead Source', type: 'text' },
  { value: 'lead.days_since_contact', label: 'Days Since Last Contact', type: 'number' },
  { value: 'lead.has_email', label: 'Has Email', type: 'boolean' },
  { value: 'lead.has_phone', label: 'Has Phone', type: 'boolean' },
  { value: 'loan.loan_amount', label: 'Loan Amount', type: 'number' },
  { value: 'loan.loan_type', label: 'Loan Type', type: 'text' },
  { value: 'loan.credit_score', label: 'Credit Score', type: 'number' },
  { value: 'loan.has_appraisal', label: 'Has Appraisal', type: 'boolean' },
  { value: 'loan.days_until_closing', label: 'Days Until Closing', type: 'number' },
  { value: 'contact.responded', label: 'Contact Responded', type: 'boolean' },
  { value: 'contact.opened_email', label: 'Opened Email', type: 'boolean' },
  { value: 'task.completed', label: 'Previous Task Completed', type: 'boolean' },
];

const OPERATORS = {
  text: [
    { value: 'equals', label: 'equals' },
    { value: 'not_equals', label: 'does not equal' },
    { value: 'contains', label: 'contains' },
    { value: 'starts_with', label: 'starts with' },
    { value: 'is_empty', label: 'is empty' },
    { value: 'is_not_empty', label: 'is not empty' },
  ],
  number: [
    { value: 'equals', label: '=' },
    { value: 'not_equals', label: '!=' },
    { value: 'greater_than', label: '>' },
    { value: 'less_than', label: '<' },
    { value: 'greater_or_equal', label: '>=' },
    { value: 'less_or_equal', label: '<=' },
    { value: 'between', label: 'between' },
  ],
  select: [
    { value: 'equals', label: 'is' },
    { value: 'not_equals', label: 'is not' },
    { value: 'in', label: 'is any of' },
  ],
  boolean: [
    { value: 'equals', label: 'is' },
  ],
};

const NOTIFY_RECIPIENTS = [
  { value: 'record_owner', label: 'Record Owner (LO)' },
  { value: 'processor', label: 'Processor' },
  { value: 'manager', label: 'Manager' },
  { value: 'team', label: 'Entire Team' },
  { value: 'specific_user', label: 'Specific User' },
];


function StartConfig({ config, onChange }) {
  const c = config || {};
  const update = (key, val) => onChange({ ...c, [key]: val });
  const updateTrigger = (key, val) => onChange({ ...c, trigger: { ...(c.trigger || {}), [key]: val } });

  return (
    <div className="wf-type-config">
      <h4>Trigger Configuration</h4>
      <div className="wf-field">
        <label>Trigger Type</label>
        <select value={c.trigger_type || 'manual'} onChange={e => update('trigger_type', e.target.value)}>
          {TRIGGER_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
        </select>
      </div>

      {c.trigger_type === 'stage_change' && (
        <>
          <div className="wf-field">
            <label>From Stage</label>
            <select value={c.trigger?.from_stage || 'any'} onChange={e => updateTrigger('from_stage', e.target.value)}>
              <option value="any">Any Stage</option>
              {[...LEAD_STAGES, ...LOAN_STAGES].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="wf-field">
            <label>To Stage</label>
            <select value={c.trigger?.to_stage || ''} onChange={e => updateTrigger('to_stage', e.target.value)}>
              <option value="">Select stage...</option>
              {[...LEAD_STAGES, ...LOAN_STAGES].map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
        </>
      )}

      {c.trigger_type === 'new_lead' && (
        <div className="wf-field">
          <label>Lead Source Filter</label>
          <input
            placeholder="Any source (leave blank for all)"
            value={c.trigger?.source_filter || ''}
            onChange={e => updateTrigger('source_filter', e.target.value)}
          />
        </div>
      )}

      {c.trigger_type === 'field_change' && (
        <>
          <div className="wf-field">
            <label>Watch Field</label>
            <select value={c.trigger?.field || ''} onChange={e => updateTrigger('field', e.target.value)}>
              <option value="">Select field...</option>
              {CONDITION_FIELDS.map(f => <option key={f.value} value={f.value}>{f.label}</option>)}
            </select>
          </div>
          <div className="wf-field">
            <label>New Value</label>
            <input
              placeholder="Trigger when field changes to..."
              value={c.trigger?.new_value || ''}
              onChange={e => updateTrigger('new_value', e.target.value)}
            />
          </div>
        </>
      )}

      {c.trigger_type === 'date_trigger' && (
        <>
          <div className="wf-field">
            <label>Date Field</label>
            <select value={c.trigger?.date_field || ''} onChange={e => updateTrigger('date_field', e.target.value)}>
              <option value="">Select field...</option>
              <option value="loan.closing_date">Closing Date</option>
              <option value="loan.lock_expiration">Lock Expiration</option>
              <option value="lead.created_at">Lead Created Date</option>
              <option value="lead.birthday">Birthday</option>
              <option value="loan.funded_date">Funded Date</option>
            </select>
          </div>
          <div className="wf-field-row">
            <div className="wf-field">
              <label>Offset</label>
              <input
                type="number"
                value={c.trigger?.offset_days || 0}
                onChange={e => updateTrigger('offset_days', parseInt(e.target.value) || 0)}
              />
            </div>
            <div className="wf-field">
              <label>Direction</label>
              <select value={c.trigger?.offset_direction || 'before'} onChange={e => updateTrigger('offset_direction', e.target.value)}>
                <option value="before">Days Before</option>
                <option value="after">Days After</option>
                <option value="on">On the Day</option>
              </select>
            </div>
          </div>
        </>
      )}

      <div className="wf-field" style={{ marginTop: 12 }}>
        <label className="wf-channel-toggle">
          <input
            type="checkbox"
            checked={c.re_enrollment || false}
            onChange={e => update('re_enrollment', e.target.checked)}
          />
          <span>Allow re-enrollment</span>
        </label>
      </div>
    </div>
  );
}


function DelayConfig({ config, onChange }) {
  const c = config || {};
  const update = (key, val) => onChange({ ...c, [key]: val });
  const updateDuration = (key, val) => onChange({ ...c, duration: { ...(c.duration || {}), [key]: val } });

  return (
    <div className="wf-type-config">
      <h4>Wait Configuration</h4>
      <div className="wf-field">
        <label>Wait Type</label>
        <select value={c.delay_type || 'fixed_duration'} onChange={e => update('delay_type', e.target.value)}>
          <option value="fixed_duration">Wait a set amount of time</option>
          <option value="until_time">Wait until a specific day/time</option>
          <option value="until_date_field">Wait until a date field</option>
          <option value="until_event">Wait for a response</option>
        </select>
      </div>

      {(c.delay_type || 'fixed_duration') === 'fixed_duration' && (
        <div className="wf-field-row">
          <div className="wf-field">
            <label>Amount</label>
            <input
              type="number"
              min="1"
              value={c.duration?.amount || 1}
              onChange={e => updateDuration('amount', parseInt(e.target.value) || 1)}
            />
          </div>
          <div className="wf-field">
            <label>Unit</label>
            <select value={c.duration?.unit || 'days'} onChange={e => updateDuration('unit', e.target.value)}>
              {DELAY_UNITS.map(u => <option key={u.value} value={u.value}>{u.label}</option>)}
            </select>
          </div>
        </div>
      )}

      {c.delay_type === 'until_time' && (
        <>
          <div className="wf-field">
            <label>Day of Week</label>
            <select value={c.until_time?.day || 'any'} onChange={e => update('until_time', { ...(c.until_time || {}), day: e.target.value })}>
              <option value="any">Next occurrence</option>
              <option value="monday">Monday</option>
              <option value="tuesday">Tuesday</option>
              <option value="wednesday">Wednesday</option>
              <option value="thursday">Thursday</option>
              <option value="friday">Friday</option>
            </select>
          </div>
          <div className="wf-field">
            <label>Time</label>
            <input
              type="time"
              value={c.until_time?.time || '09:00'}
              onChange={e => update('until_time', { ...(c.until_time || {}), time: e.target.value })}
            />
          </div>
        </>
      )}

      {c.delay_type === 'until_date_field' && (
        <>
          <div className="wf-field">
            <label>Date Field</label>
            <select value={c.until_field?.field || ''} onChange={e => update('until_field', { ...(c.until_field || {}), field: e.target.value })}>
              <option value="">Select field...</option>
              <option value="loan.closing_date">Closing Date</option>
              <option value="loan.lock_expiration">Lock Expiration</option>
              <option value="lead.created_at">Lead Created Date</option>
              <option value="loan.funded_date">Funded Date</option>
            </select>
          </div>
          <div className="wf-field-row">
            <div className="wf-field">
              <label>Offset</label>
              <input
                type="number"
                value={c.until_field?.offset || 0}
                onChange={e => update('until_field', { ...(c.until_field || {}), offset: parseInt(e.target.value) || 0 })}
              />
            </div>
            <div className="wf-field">
              <label>Direction</label>
              <select
                value={c.until_field?.direction || 'before'}
                onChange={e => update('until_field', { ...(c.until_field || {}), direction: e.target.value })}
              >
                <option value="before">Days Before</option>
                <option value="after">Days After</option>
              </select>
            </div>
          </div>
        </>
      )}

      {c.delay_type === 'until_event' && (
        <>
          <div className="wf-field">
            <label>Wait For</label>
            <select value={c.until_event?.event || 'any_reply'} onChange={e => update('until_event', { ...(c.until_event || {}), event: e.target.value })}>
              <option value="any_reply">Any Response (SMS, Email, or Call)</option>
              <option value="sms_reply">SMS Reply</option>
              <option value="email_reply">Email Reply</option>
              <option value="call_answer">Call Answered</option>
              <option value="form_submit">Form Submitted</option>
              <option value="doc_uploaded">Document Uploaded</option>
            </select>
          </div>
          <div className="wf-field">
            <label>Timeout (hours) — continue if no response</label>
            <input
              type="number"
              min="1"
              value={c.until_event?.timeout_hours || 48}
              onChange={e => update('until_event', { ...(c.until_event || {}), timeout_hours: parseInt(e.target.value) || 48 })}
            />
          </div>
        </>
      )}
    </div>
  );
}


function ConditionConfig({ config, onChange }) {
  const c = config || {};
  const conditions = c.conditions || [{ field: '', operator: 'equals', value: '' }];

  const updateCondition = (index, key, val) => {
    const updated = conditions.map((cond, i) => i === index ? { ...cond, [key]: val } : cond);
    onChange({ ...c, conditions: updated });
  };

  const addCondition = () => {
    onChange({ ...c, conditions: [...conditions, { field: '', operator: 'equals', value: '' }] });
  };

  const removeCondition = (index) => {
    if (conditions.length <= 1) return;
    onChange({ ...c, conditions: conditions.filter((_, i) => i !== index) });
  };

  const getFieldDef = (fieldValue) => CONDITION_FIELDS.find(f => f.value === fieldValue);
  const getOperators = (fieldValue) => {
    const def = getFieldDef(fieldValue);
    return OPERATORS[def?.type || 'text'] || OPERATORS.text;
  };

  return (
    <div className="wf-type-config">
      <h4>Branch Conditions</h4>
      <p className="wf-config-hint">Leads matching these conditions follow the "Yes" path. Others follow "No".</p>

      {conditions.length > 1 && (
        <div className="wf-field">
          <label>Match</label>
          <select value={c.logic || 'and'} onChange={e => onChange({ ...c, logic: e.target.value })}>
            <option value="and">ALL conditions (AND)</option>
            <option value="or">ANY condition (OR)</option>
          </select>
        </div>
      )}

      {conditions.map((cond, i) => {
        const fieldDef = getFieldDef(cond.field);
        const operators = getOperators(cond.field);
        const needsValue = !['is_empty', 'is_not_empty'].includes(cond.operator);

        return (
          <div key={i} className="wf-condition-row">
            {conditions.length > 1 && (
              <button className="wf-condition-remove" onClick={() => removeCondition(i)} title="Remove">×</button>
            )}
            <div className="wf-field">
              <label>Field</label>
              <select value={cond.field || ''} onChange={e => updateCondition(i, 'field', e.target.value)}>
                <option value="">Select field...</option>
                <optgroup label="Lead">
                  {CONDITION_FIELDS.filter(f => f.value.startsWith('lead.')).map(f =>
                    <option key={f.value} value={f.value}>{f.label}</option>
                  )}
                </optgroup>
                <optgroup label="Loan">
                  {CONDITION_FIELDS.filter(f => f.value.startsWith('loan.')).map(f =>
                    <option key={f.value} value={f.value}>{f.label}</option>
                  )}
                </optgroup>
                <optgroup label="Activity">
                  {CONDITION_FIELDS.filter(f => f.value.startsWith('contact.') || f.value.startsWith('task.')).map(f =>
                    <option key={f.value} value={f.value}>{f.label}</option>
                  )}
                </optgroup>
              </select>
            </div>
            <div className="wf-field">
              <label>Operator</label>
              <select value={cond.operator || 'equals'} onChange={e => updateCondition(i, 'operator', e.target.value)}>
                {operators.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            {needsValue && (
              <div className="wf-field">
                <label>Value</label>
                {fieldDef?.type === 'select' ? (
                  <select value={cond.value || ''} onChange={e => updateCondition(i, 'value', e.target.value)}>
                    <option value="">Select...</option>
                    {fieldDef.options.map(o => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : fieldDef?.type === 'boolean' ? (
                  <select value={cond.value || 'true'} onChange={e => updateCondition(i, 'value', e.target.value)}>
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                  </select>
                ) : (
                  <input
                    type={fieldDef?.type === 'number' ? 'number' : 'text'}
                    value={cond.value || ''}
                    onChange={e => updateCondition(i, 'value', e.target.value)}
                    placeholder="Enter value..."
                  />
                )}
              </div>
            )}
            {i < conditions.length - 1 && conditions.length > 1 && (
              <div className="wf-condition-logic-label">{c.logic === 'or' ? 'OR' : 'AND'}</div>
            )}
          </div>
        );
      })}

      <button className="wf-add-condition-btn" onClick={addCondition}>+ Add Condition</button>
    </div>
  );
}


function TaskActionConfig({ config, onChange }) {
  const c = config || {};
  const update = (key, val) => onChange({ ...c, [key]: val });
  const updateAction = (key, val) => onChange({ ...c, action: { ...(c.action || {}), [key]: val } });
  const actionType = c.action_type || '';

  return (
    <div className="wf-type-config">
      <h4>Action Configuration</h4>
      <div className="wf-field">
        <label>Action Type</label>
        <select value={actionType} onChange={e => update('action_type', e.target.value)}>
          <option value="">Select action...</option>
          {ACTION_TYPES.map(a => (
            <option key={a.value} value={a.value}>{a.icon} {a.label}</option>
          ))}
        </select>
      </div>

      {actionType === 'send_sms' && (
        <>
          <div className="wf-field">
            <label>Message</label>
            <textarea
              rows={4}
              value={c.action?.message || ''}
              onChange={e => updateAction('message', e.target.value)}
              placeholder="Hi {{first_name}}, ..."
            />
          </div>
          <p className="wf-config-hint">Use {'{{first_name}}'}, {'{{last_name}}'}, {'{{lo_name}}'}, {'{{loan_stage}}'} for merge fields</p>
        </>
      )}

      {actionType === 'send_email' && (
        <>
          <div className="wf-field">
            <label>Subject</label>
            <input
              value={c.action?.subject || ''}
              onChange={e => updateAction('subject', e.target.value)}
              placeholder="Email subject line..."
            />
          </div>
          <div className="wf-field">
            <label>Body</label>
            <textarea
              rows={5}
              value={c.action?.body || ''}
              onChange={e => updateAction('body', e.target.value)}
              placeholder="Email body with {{merge_fields}}..."
            />
          </div>
          <div className="wf-field">
            <label className="wf-channel-toggle">
              <input
                type="checkbox"
                checked={c.action?.track_opens !== false}
                onChange={e => updateAction('track_opens', e.target.checked)}
              />
              <span>Track opens & clicks</span>
            </label>
          </div>
        </>
      )}

      {actionType === 'send_voicemail' && (
        <>
          <div className="wf-field">
            <label>Voicemail Script</label>
            <textarea
              rows={4}
              value={c.action?.script || ''}
              onChange={e => updateAction('script', e.target.value)}
              placeholder="Hi {{first_name}}, this is {{lo_name}} calling about your loan..."
            />
          </div>
          <div className="wf-field">
            <label>Audio File ID (optional)</label>
            <input
              value={c.action?.audio_file_id || ''}
              onChange={e => updateAction('audio_file_id', e.target.value)}
              placeholder="Pre-recorded audio file ID"
            />
          </div>
        </>
      )}

      {actionType === 'make_call' && (
        <>
          <div className="wf-field">
            <label>Call Type</label>
            <select value={c.action?.call_type || 'manual'} onChange={e => updateAction('call_type', e.target.value)}>
              <option value="manual">Manual (create task to call)</option>
              <option value="ai_call">AI Call (Aria)</option>
            </select>
          </div>
          {c.action?.call_type === 'ai_call' && (
            <div className="wf-field">
              <label>Call Script / Objective</label>
              <textarea
                rows={3}
                value={c.action?.script || ''}
                onChange={e => updateAction('script', e.target.value)}
                placeholder="Aria should call to schedule an appointment..."
              />
            </div>
          )}
        </>
      )}

      {actionType === 'create_task' && (
        <>
          <div className="wf-field">
            <label>Task Title</label>
            <input
              value={c.action?.title || ''}
              onChange={e => updateAction('title', e.target.value)}
              placeholder="Follow up with {{first_name}}"
            />
          </div>
          <div className="wf-field">
            <label>Description</label>
            <textarea
              rows={2}
              value={c.action?.description || ''}
              onChange={e => updateAction('description', e.target.value)}
            />
          </div>
          <div className="wf-field-row">
            <div className="wf-field">
              <label>Due In</label>
              <input
                type="number"
                min="0"
                value={c.action?.due_offset || 0}
                onChange={e => updateAction('due_offset', parseInt(e.target.value) || 0)}
              />
            </div>
            <div className="wf-field">
              <label>Unit</label>
              <select value={c.action?.due_unit || 'days'} onChange={e => updateAction('due_unit', e.target.value)}>
                <option value="hours">Hours</option>
                <option value="days">Days</option>
              </select>
            </div>
          </div>
          <div className="wf-field-row">
            <div className="wf-field">
              <label>Priority</label>
              <select value={c.action?.priority || 'normal'} onChange={e => updateAction('priority', e.target.value)}>
                <option value="low">Low</option>
                <option value="normal">Normal</option>
                <option value="high">High</option>
                <option value="urgent">Urgent</option>
              </select>
            </div>
            <div className="wf-field">
              <label>Assign To</label>
              <select value={c.action?.assign_to || 'record_owner'} onChange={e => updateAction('assign_to', e.target.value)}>
                <option value="record_owner">Record Owner</option>
                <option value="processor">Processor</option>
                <option value="manager">Manager</option>
                <option value="round_robin">Round Robin</option>
              </select>
            </div>
          </div>
        </>
      )}

      {actionType === 'update_field' && (
        <>
          <div className="wf-field">
            <label>Field</label>
            <select value={c.action?.field || ''} onChange={e => updateAction('field', e.target.value)}>
              <option value="">Select field...</option>
              {CONDITION_FIELDS.filter(f => !f.value.startsWith('contact.') && !f.value.startsWith('task.')).map(f =>
                <option key={f.value} value={f.value}>{f.label}</option>
              )}
            </select>
          </div>
          <div className="wf-field">
            <label>New Value</label>
            <input
              value={c.action?.new_value || ''}
              onChange={e => updateAction('new_value', e.target.value)}
              placeholder="Set field to this value"
            />
          </div>
        </>
      )}

      {actionType === 'change_stage' && (
        <div className="wf-field">
          <label>New Stage</label>
          <select value={c.action?.new_stage || ''} onChange={e => updateAction('new_stage', e.target.value)}>
            <option value="">Select stage...</option>
            <optgroup label="Lead Stages">
              {LEAD_STAGES.map(s => <option key={s} value={s}>{s}</option>)}
            </optgroup>
            <optgroup label="Loan Stages">
              {LOAN_STAGES.map(s => <option key={s} value={s}>{s}</option>)}
            </optgroup>
          </select>
        </div>
      )}

      {actionType === 'assign_owner' && (
        <div className="wf-field">
          <label>Assignment Mode</label>
          <select value={c.action?.mode || 'record_owner'} onChange={e => updateAction('mode', e.target.value)}>
            <option value="record_owner">Keep Current Owner</option>
            <option value="round_robin">Round Robin</option>
            <option value="manager">Assign to Manager</option>
            <option value="processor">Assign to Processor</option>
          </select>
        </div>
      )}

      {actionType === 'add_note' && (
        <div className="wf-field">
          <label>Note Text</label>
          <textarea
            rows={3}
            value={c.action?.note || ''}
            onChange={e => updateAction('note', e.target.value)}
            placeholder="Automated workflow note: {{merge_fields}}"
          />
        </div>
      )}

      {actionType === 'add_tag' && (
        <div className="wf-field">
          <label>Tag</label>
          <input
            value={c.action?.tag || ''}
            onChange={e => updateAction('tag', e.target.value)}
            placeholder="e.g. hot-lead, needs-docs, rate-shopper"
          />
        </div>
      )}

      {actionType === 'webhook' && (
        <>
          <div className="wf-field">
            <label>URL</label>
            <input
              value={c.action?.url || ''}
              onChange={e => updateAction('url', e.target.value)}
              placeholder="https://..."
            />
          </div>
          <div className="wf-field">
            <label>Method</label>
            <select value={c.action?.method || 'POST'} onChange={e => updateAction('method', e.target.value)}>
              <option value="POST">POST</option>
              <option value="GET">GET</option>
              <option value="PUT">PUT</option>
            </select>
          </div>
        </>
      )}
    </div>
  );
}


function NotificationConfig({ config, onChange }) {
  const c = config || {};
  const update = (key, val) => onChange({ ...c, [key]: val });

  return (
    <div className="wf-type-config">
      <h4>Notification Configuration</h4>
      <div className="wf-field">
        <label>Notify Via</label>
        <select value={c.notify_type || 'in_app'} onChange={e => update('notify_type', e.target.value)}>
          <option value="in_app">In-App Notification</option>
          <option value="email">Email</option>
          <option value="sms">SMS</option>
          <option value="all">All Channels</option>
        </select>
      </div>
      <div className="wf-field">
        <label>Send To</label>
        <select value={c.recipient || 'record_owner'} onChange={e => update('recipient', e.target.value)}>
          {NOTIFY_RECIPIENTS.map(r => <option key={r.value} value={r.value}>{r.label}</option>)}
        </select>
      </div>
      <div className="wf-field">
        <label>Urgency</label>
        <select value={c.urgency || 'normal'} onChange={e => update('urgency', e.target.value)}>
          <option value="low">Low</option>
          <option value="normal">Normal</option>
          <option value="high">High</option>
          <option value="urgent">Urgent</option>
        </select>
      </div>
      <div className="wf-field">
        <label>Message</label>
        <textarea
          rows={3}
          value={c.message || ''}
          onChange={e => update('message', e.target.value)}
          placeholder="{{first_name}} {{last_name}} requires attention — {{reason}}"
        />
      </div>
    </div>
  );
}


export default function NodeDetailDrawer({ workflowKey, node, onUpdate, onDelete, onClose }) {
  const [activeTab, setActiveTab] = useState('config');
  const [leads, setLeads] = useState(null);
  const [history, setHistory] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const debounceRef = useRef(null);

  const handleChange = (field, value) => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onUpdate({ [field]: value });
    }, 400);
  };

  const handleConfigChange = (newConfig) => {
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      onUpdate({ config: newConfig });
    }, 400);
  };

  const handleChannelToggle = (channelKey) => {
    const updated = { ...(node.channels || {}), [channelKey]: !node.channels?.[channelKey] };
    onUpdate({ channels: updated });
  };

  useEffect(() => {
    if (activeTab === 'leads' && !leads) {
      workflowGraphApi.getNodeLeads(workflowKey, node.id).then(r => setLeads(r.data));
    }
    if (activeTab === 'history' && !history) {
      workflowGraphApi.getNodeHistory(workflowKey, node.id).then(r => setHistory(r.data.history));
    }
    if (activeTab === 'metrics' && !metrics) {
      workflowGraphApi.getNodeMetrics(workflowKey, node.id).then(r => setMetrics(r.data));
    }
  }, [activeTab, node.id, workflowKey, leads, history, metrics]);

  useEffect(() => {
    setLeads(null);
    setHistory(null);
    setMetrics(null);
  }, [node.id]);

  const tabs = [
    { key: 'config', label: 'Config' },
    { key: 'leads', label: `Leads (${node.lead_count || 0})` },
    { key: 'history', label: 'History' },
    { key: 'metrics', label: 'Metrics' },
  ];

  const isTerminal = node.type === 'start' || node.type === 'end';

  return (
    <div className="wf-drawer">
      <div className="wf-drawer-header">
        <span className="wf-drawer-title">{node.label}</span>
        <button className="wf-drawer-close" onClick={onClose}>&times;</button>
      </div>

      <div className="wf-drawer-tabs">
        {tabs.map(t => (
          <button
            key={t.key}
            className={`wf-drawer-tab ${activeTab === t.key ? 'active' : ''}`}
            onClick={() => setActiveTab(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>

      <div className="wf-drawer-body">
        {activeTab === 'config' && (
          <div className="wf-drawer-config">
            {/* Common fields */}
            <div className="wf-field">
              <label>Label</label>
              <input defaultValue={node.label} onChange={e => handleChange('label', e.target.value)} key={`label-${node.id}`} />
            </div>
            {!isTerminal && (
              <div className="wf-field">
                <label>Description</label>
                <textarea defaultValue={node.description || ''} onChange={e => handleChange('description', e.target.value)} key={`desc-${node.id}`} />
              </div>
            )}

            {/* Type-specific configuration */}
            {node.type === 'start' && (
              <StartConfig config={node.config} onChange={handleConfigChange} />
            )}

            {node.type === 'delay' && (
              <DelayConfig config={node.config} onChange={handleConfigChange} />
            )}

            {node.type === 'condition' && (
              <ConditionConfig config={node.config} onChange={handleConfigChange} />
            )}

            {node.type === 'task' && (
              <TaskActionConfig config={node.config} onChange={handleConfigChange} />
            )}

            {node.type === 'notification' && (
              <NotificationConfig config={node.config} onChange={handleConfigChange} />
            )}

            {/* Channels — for task and notification */}
            {(node.type === 'task' || node.type === 'notification') && (
              <div className="wf-field">
                <label>Channels</label>
                <div className="wf-channel-grid">
                  {CHANNELS.map(ch => (
                    <label key={ch.key} className="wf-channel-toggle">
                      <input
                        type="checkbox"
                        checked={!!node.channels?.[ch.key]}
                        onChange={() => handleChannelToggle(ch.key)}
                      />
                      <span>{ch.icon} {ch.label}</span>
                    </label>
                  ))}
                </div>
              </div>
            )}

            {/* Role / Day / Time — for task nodes */}
            {node.type === 'task' && (
              <>
                <div className="wf-field-row">
                  <div className="wf-field">
                    <label>Role</label>
                    <select defaultValue={node.role || ''} onChange={e => handleChange('role', e.target.value)} key={`role-${node.id}`}>
                      <option value="">None</option>
                      {ROLES.map(r => <option key={r} value={r}>{r}</option>)}
                    </select>
                  </div>
                  <div className="wf-field">
                    <label>Day</label>
                    <input defaultValue={node.day_label || ''} onChange={e => handleChange('day_label', e.target.value)} key={`day-${node.id}`} />
                  </div>
                </div>
                <div className="wf-field-row">
                  <div className="wf-field">
                    <label>Time of Day</label>
                    <select defaultValue={node.time_of_day || ''} onChange={e => handleChange('time_of_day', e.target.value)} key={`tod-${node.id}`}>
                      <option value="">Any</option>
                      <option value="AM">AM</option>
                      <option value="PM">PM</option>
                    </select>
                  </div>
                  <div className="wf-field">
                    <label>Repeat Weekly</label>
                    <input type="checkbox" checked={node.repeat_weekly || false} onChange={e => onUpdate({ repeat_weekly: e.target.checked })} />
                  </div>
                </div>
              </>
            )}

            {/* AI Guidance — shown when role is AI */}
            {node.role === 'AI' && (
              <div className="wf-ai-guidance">
                <h4>AI Guidance</h4>
                <div className="wf-field">
                  <label>Objective</label>
                  <input
                    defaultValue={node.ai_guidance?.objective || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), objective: e.target.value })}
                    key={`aio-${node.id}`}
                  />
                </div>
                <div className="wf-field">
                  <label>Talking Points / Script</label>
                  <textarea
                    defaultValue={node.ai_guidance?.talking_points || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), talking_points: e.target.value })}
                    rows={4}
                    key={`ait-${node.id}`}
                  />
                </div>
                <div className="wf-field">
                  <label>Success Criteria</label>
                  <input
                    defaultValue={node.ai_guidance?.success_criteria || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), success_criteria: e.target.value })}
                    key={`ais-${node.id}`}
                  />
                </div>
                <div className="wf-field">
                  <label>Escalation Rules</label>
                  <textarea
                    defaultValue={node.ai_guidance?.escalation_rules || ''}
                    onChange={e => handleChange('ai_guidance', { ...(node.ai_guidance || {}), escalation_rules: e.target.value })}
                    rows={3}
                    key={`aie-${node.id}`}
                  />
                </div>
              </div>
            )}

            {node.type !== 'start' && (
              <button className="wf-delete-btn" onClick={onDelete}>Delete Node</button>
            )}
          </div>
        )}

        {activeTab === 'leads' && (
          <div className="wf-drawer-leads">
            {!leads ? <div className="wf-drawer-loading">Loading...</div> :
            leads.leads?.length === 0 ? <div className="wf-drawer-empty">No leads at this step</div> :
            leads.leads.map(l => (
              <div key={l.id} className="wf-lead-row">
                <span className="wf-lead-name">{l.first_name} {l.last_name}</span>
                <span className="wf-lead-detail">{l.email}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'history' && (
          <div className="wf-drawer-history">
            {!history ? <div className="wf-drawer-loading">Loading...</div> :
            history.length === 0 ? <div className="wf-drawer-empty">No movement history</div> :
            history.map(h => (
              <div key={h.id} className="wf-history-row">
                <span className="wf-history-name">{h.lead_name}</span>
                <span className="wf-history-detail">
                  {h.direction === 'in' ? `from ${h.from_node_label || 'entry'}` : `to ${h.to_node_label}`}
                </span>
                <span className="wf-history-time">{new Date(h.moved_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'metrics' && (
          <div className="wf-drawer-metrics">
            {!metrics ? <div className="wf-drawer-loading">Loading...</div> : (
              <div className="wf-metrics-grid">
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.current_leads}</div>
                  <div className="wf-metric-label">Current Leads</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.total_entered}</div>
                  <div className="wf-metric-label">Total Entered</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.total_exited}</div>
                  <div className="wf-metric-label">Total Exited</div>
                </div>
                <div className="wf-metric-card">
                  <div className="wf-metric-value">{metrics.completion_rate}%</div>
                  <div className="wf-metric-label">Completion Rate</div>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

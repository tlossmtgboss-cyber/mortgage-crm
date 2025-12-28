import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { teamAPI, tasksAPI, reconciliationAPI, aiAPI, leadsAPI, loansAPI, API_BASE_URL } from '../services/api';
import MergeCenter from './MergeCenter';
import { useLayoutFix } from '../hooks/useLayoutFix';
import TaskDetailPanel from '../components/shared/TaskDetailPanel';
import ReconciliationDetailPanel from '../components/shared/ReconciliationDetailPanel';
import CallDetailPanel from '../components/shared/CallDetailPanel';
import TasksSkeleton from '../components/shared/TasksSkeleton';
import { TASK_EVENTS, emitTaskCompleted, subscribeToTaskEvent } from '../utils/taskEvents';
import { getAuthHeaders } from '../utils/auth';
import './Tasks.css';

const API_BASE = process.env.REACT_APP_API_URL || '';

// Lead status options
const LEAD_STAGES = [
  { value: 'new', label: 'New', color: '#6366f1' },
  { value: 'attempted_contact', label: 'Attempted Contact', color: '#8b5cf6' },
  { value: 'contact_made', label: 'Contact Made', color: '#06b6d4' },
  { value: 'needs_analysis', label: 'Needs Analysis', color: '#0ea5e9' },
  { value: 'pre_approved', label: 'Pre-Approved', color: '#10b981' },
  { value: 'application', label: 'Application', color: '#f59e0b' },
  { value: 'processing', label: 'Processing', color: '#f97316' },
  { value: 'closing', label: 'Closing', color: '#22c55e' },
  { value: 'funded', label: 'Funded', color: '#16a34a' },
  { value: 'not_qualified', label: 'Does Not Qualify', color: '#ef4444' },
  { value: 'withdrawn', label: 'Withdrawn', color: '#6b7280' }
];

// Mock data functions
const mockPrioritizedTasks = () => [
  {
    title: 'Follow up on pre-approval',
    borrower: 'Sarah Johnson',
    stage: 'Pre-Approved',
    urgency: 'high',
    ai_action: 'AI can send follow-up email — approve?',
    owner: 'Loan Officer',
    date_created: '2025-11-09T10:30:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi Sarah,

I hope this message finds you well! I wanted to follow up on your pre-approval that we completed last week.

Your pre-approval is valid for 90 days, expiring on February 8, 2025. I wanted to check in and see if you've had a chance to view any properties or if you have any questions about next steps.

If you'd like to discuss your home search or need any assistance, I'm here to help. Feel free to reply to this email or give me a call at (555) 123-4567.

Looking forward to hearing from you!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-08', type: 'Email', subject: 'Pre-approval completed', status: 'Sent', message: 'Sent pre-approval letter and next steps' },
      { date: '2025-11-05', type: 'Phone', subject: 'Initial consultation', status: 'Completed', message: '30-minute call discussing loan options and requirements' },
      { date: '2025-11-03', type: 'Email', subject: 'Welcome email', status: 'Sent', message: 'Introduced myself and requested initial documents' }
    ]
  },
  {
    title: 'Upload missing documents',
    borrower: 'Mike Chen',
    stage: 'Processing',
    urgency: 'critical',
    ai_action: 'AI detected missing documents from email analysis',
    owner: 'Loan Processor',
    date_created: '2025-11-10T14:20:00',
    preferred_contact_method: 'Text',
    missing_documents: [
      '2024 W-2 forms (both employers)',
      'Last 2 pay stubs from current job',
      '2 months recent bank statements (checking account)'
    ],
    ai_message: `Hi Mike,

Hope you're doing well! I've been reviewing your loan file and noticed we're still missing a few documents to move forward with processing:

📄 Still Needed:
• 2024 W-2 forms (both employers)
• Last 2 pay stubs from current job
• 2 months recent bank statements (checking)

Can you upload these through the portal? Or you can reply with photos and I'll handle the upload for you.

Once we have these, we can move to the next stage! Let me know if you have any questions.

Thanks!
[Your Name]
Loan Processor`,
    communication_history: [
      { date: '2025-11-10', type: 'Email', subject: 'Re: Document checklist', status: 'Received', message: 'Mike replied: "I uploaded the tax returns and my W-2 from my main job. Will send the other W-2 tomorrow."' },
      { date: '2025-11-09', type: 'Text', subject: 'Quick check-in', status: 'Sent', message: 'Asked Mike about document upload progress' },
      { date: '2025-11-08', type: 'Email', subject: 'Document checklist', status: 'Sent', message: 'Sent comprehensive list of all required documents for loan processing' },
      { date: '2025-11-07', type: 'Email', subject: 'Welcome to processing', status: 'Sent', message: 'Introduced loan processing phase and set expectations' }
    ]
  },
  {
    title: 'Schedule appraisal',
    borrower: 'Emily Davis',
    stage: 'Application Complete',
    urgency: 'medium',
    ai_action: 'AI can schedule appraisal — approve?',
    owner: 'Loan Officer',
    date_created: '2025-11-10T09:15:00',
    preferred_contact_method: 'Phone',
    ai_message: `Hi Emily,

Great news! Your loan application has been approved and we're ready to move forward with the appraisal.

I have availability with our preferred appraiser for the following dates:
- Thursday, November 14th at 10:00 AM
- Friday, November 15th at 2:00 PM
- Monday, November 18th at 9:00 AM

The appraisal typically takes 45-60 minutes. Please let me know which time works best for you, and I'll get it scheduled right away.

Thanks!
[Your Name]`,
    communication_history: [
      { date: '2025-11-09', type: 'Email', subject: 'Application approved', status: 'Sent', message: 'Congratulations email sent with next steps' },
      { date: '2025-11-07', type: 'Phone', subject: 'Application review', status: 'Completed', message: 'Reviewed application details' }
    ]
  }
];

const mockLoanIssues = () => [
  {
    borrower: 'John Smith',
    issue: 'Appraisal delay',
    time_remaining: '2 days',
    time_color: '#f59e0b',
    action: 'Follow up with appraiser',
    owner: 'Loan Officer',
    stage: 'Underwriting',
    urgency: 'high',
    date_created: '2025-11-12T09:15:00',
    preferred_contact_method: 'Phone',
    ai_message: `Hi John,

I wanted to give you a quick update on your loan application. We're currently waiting on the appraisal, which has been slightly delayed by 2 days.

I've reached out to the appraiser this morning and they confirmed they'll complete the inspection by end of day Thursday. Once we receive the appraisal report, we can move forward to final underwriting approval.

I know waiting can be frustrating, but we're doing everything we can to keep things moving quickly. I'll keep you posted on any updates.

If you have any questions in the meantime, please don't hesitate to reach out!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-12', type: 'Phone', subject: 'Appraisal status update', status: 'Completed', message: 'Called appraiser to check on timeline' },
      { date: '2025-11-10', type: 'Email', subject: 'Appraisal scheduled', status: 'Sent', message: 'Sent confirmation of appraisal appointment' },
      { date: '2025-11-08', type: 'Email', subject: 'Moving to underwriting', status: 'Sent', message: 'Notified client that file is being sent to underwriting' }
    ]
  },
  {
    borrower: 'Jane Doe',
    issue: 'Insurance missing',
    time_remaining: '5 hours',
    time_color: '#dc2626',
    action: 'Send urgent reminder',
    owner: 'Loan Processor',
    stage: 'Clear to Close',
    urgency: 'critical',
    date_created: '2025-11-13T08:00:00',
    preferred_contact_method: 'Text',
    ai_message: `Hi Jane,

URGENT: We need your homeowner's insurance binder by 5 PM today to close on schedule tomorrow.

📋 What we need:
• Homeowner's insurance binder
• Proof of paid first year premium
• Lender named as mortgagee

Your insurance agent can email this directly to us at docs@mortgagecrm.com or you can upload it to the portal.

This is the last item we need before closing! Please let me know if you need help contacting your insurance agent.

Thanks!
[Your Name]
Loan Processor`,
    communication_history: [
      { date: '2025-11-13', type: 'Text', subject: 'Insurance reminder', status: 'Sent', message: 'Sent text reminder about insurance deadline' },
      { date: '2025-11-12', type: 'Email', subject: 'Closing checklist', status: 'Sent', message: 'Sent final items needed for closing' },
      { date: '2025-11-11', type: 'Phone', subject: 'Closing date confirmed', status: 'Completed', message: '15-minute call confirming closing details' }
    ]
  }
];

const mockAiTasks = () => ({
  pending: [
    {
      id: 1,
      task: 'Draft follow-up email to Sarah Johnson',
      borrower: 'Sarah Johnson',
      confidence: 94,
      what_ai_did: 'Composed personalized email based on last conversation',
      owner: 'Loan Officer',
      stage: 'Pre-Approved',
      urgency: 'medium',
      date_created: '2025-11-13T11:00:00',
      preferred_contact_method: 'Email',
      ai_message: `Hi Sarah,

I hope you're doing well! I wanted to reach out and see how your property search is going.

Your pre-approval is still active for another 75 days. If you've found a property you're interested in or have any questions about the home buying process, I'm here to help.

Also, if your financial situation has changed at all (new income, credit changes, etc.), please let me know so we can make sure your pre-approval stays accurate.

Looking forward to helping you find your dream home!

Best regards,
[Your Name]
Loan Officer`,
      communication_history: [
        { date: '2025-11-08', type: 'Email', subject: 'Pre-approval completed', status: 'Sent', message: 'Sent pre-approval letter and congratulations' },
        { date: '2025-11-05', type: 'Phone', subject: 'Pre-approval interview', status: 'Completed', message: 'Discussed loan options and gathered documentation' }
      ]
    },
    {
      id: 2,
      task: 'Schedule appointment with Mike Chen',
      borrower: 'Mike Chen',
      confidence: 87,
      what_ai_did: 'Found mutual availability on calendar for Thursday 2pm',
      owner: 'Loan Officer',
      stage: 'Processing',
      urgency: 'medium',
      date_created: '2025-11-13T13:30:00',
      preferred_contact_method: 'Phone',
      ai_message: `Hi Mike,

I wanted to schedule a quick check-in call to review your loan application progress and answer any questions you might have.

I have the following times available this week:
• Thursday, Nov 14 at 2:00 PM
• Thursday, Nov 14 at 4:00 PM
• Friday, Nov 15 at 10:00 AM

The call should only take about 15-20 minutes. We'll review your current status, discuss next steps, and I can answer any questions.

Which time works best for you?

Thanks!
[Your Name]
Loan Officer`,
      communication_history: [
        { date: '2025-11-10', type: 'Email', subject: 'Document status update', status: 'Sent', message: 'Confirmed receipt of W-2s and requested bank statements' },
        { date: '2025-11-08', type: 'Text', subject: 'Quick question', status: 'Received', message: 'Mike asked about processing timeline' }
      ]
    }
  ],
  waiting: [
    {
      task: 'Approve rate lock for Emily Davis file',
      borrower: 'Emily Davis',
      owner: 'Loan Officer',
      stage: 'Application Complete',
      urgency: 'high',
      date_created: '2025-11-12T16:00:00',
      preferred_contact_method: 'Email',
      ai_message: `Hi Emily,

Good news! Interest rates have dropped slightly since we started your application.

Current Rate Options:
• 30-year fixed: 6.875% (down from 7.00%)
• 15-year fixed: 6.125% (down from 6.25%)

I recommend locking your rate today to secure this lower rate. The lock is good for 45 days, which gives us plenty of time to close.

Would you like me to proceed with the rate lock? Please confirm and I'll lock it in right away.

Best regards,
[Your Name]
Loan Officer`,
      communication_history: [
        { date: '2025-11-11', type: 'Email', subject: 'Application received', status: 'Sent', message: 'Confirmed application submission' },
        { date: '2025-11-09', type: 'Phone', subject: 'Rate options discussion', status: 'Completed', message: 'Discussed rate lock strategy' }
      ]
    },
    {
      task: 'Review updated credit report for John Smith',
      borrower: 'John Smith',
      owner: 'Underwriter',
      stage: 'Underwriting',
      urgency: 'medium',
      date_created: '2025-11-13T10:00:00',
      preferred_contact_method: 'Email',
      ai_message: `Hi John,

I noticed your credit score has improved by 15 points since we pulled your initial credit report! This is great news.

Your new score (735) may qualify you for a better interest rate. I'd like to re-run the numbers to see if we can save you money.

Would you authorize me to pull an updated credit report? This will be a soft pull and won't affect your score.

Let me know and I can have updated numbers for you within an hour!

Best regards,
[Your Name]
Loan Officer`,
      communication_history: [
        { date: '2025-11-12', type: 'Email', subject: 'Credit report received', status: 'Sent', message: 'Sent initial credit report results' },
        { date: '2025-11-10', type: 'Phone', subject: 'Credit discussion', status: 'Completed', message: 'Reviewed credit history and tradelines' }
      ]
    }
  ]
});

const mockMumAlerts = () => [
  {
    icon: '📅',
    title: 'Annual review due',
    client: 'Tom Wilson',
    borrower: 'Tom Wilson',
    action: 'Schedule annual mortgage review',
    owner: 'Loan Officer',
    stage: 'Client Retention',
    urgency: 'medium',
    date_created: '2025-11-13T09:00:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi Tom,

It's been a year since we closed on your home - congratulations on your home anniversary!

I'd love to schedule a quick 15-minute call to review your mortgage and see if there are any opportunities to save you money:

✅ Current interest rates (they may be lower now!)
✅ Your home equity position
✅ Refinance opportunities
✅ Any questions you have

I have the following times available:
• Tuesday, Nov 19 at 10:00 AM
• Wednesday, Nov 20 at 2:00 PM
• Thursday, Nov 21 at 11:00 AM

Which works best for you?

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2024-11-13', type: 'Email', subject: 'Closing completed!', status: 'Sent', message: 'Sent congratulations on successful closing' },
      { date: '2024-11-01', type: 'Phone', subject: 'Final walkthrough', status: 'Completed', message: 'Confirmed closing date and details' }
    ]
  },
  {
    icon: '📉',
    title: 'Rate drop opportunity',
    client: 'Lisa Brown',
    borrower: 'Lisa Brown',
    action: 'Send rate drop alert',
    owner: 'Loan Officer',
    stage: 'Client Retention',
    urgency: 'high',
    date_created: '2025-11-13T14:00:00',
    preferred_contact_method: 'Phone',
    ai_message: `Hi Lisa,

Great news! Interest rates have dropped significantly since you closed on your mortgage.

Your Current Loan:
• Current Rate: 7.25%
• Current Payment: $2,850/month

Refinance Opportunity:
• New Rate: 6.50%
• New Payment: $2,540/month
• Potential Savings: $310/month ($3,720/year!)

You could break even on closing costs in just 18 months and start saving immediately.

Would you like me to run the detailed numbers for you? I can have a full analysis ready within 24 hours.

Let me know!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-06-15', type: 'Email', subject: '6-month check-in', status: 'Sent', message: 'Checked in on how home ownership is going' },
      { date: '2025-01-10', type: 'Email', subject: 'First payment reminder', status: 'Sent', message: 'Reminded about first mortgage payment' }
    ]
  },
  {
    icon: '🎂',
    title: 'Home anniversary',
    client: 'Mark Taylor',
    borrower: 'Mark Taylor',
    action: 'Send anniversary message',
    owner: 'Loan Officer',
    stage: 'Client Retention',
    urgency: 'low',
    date_created: '2025-11-13T08:30:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi Mark,

Happy Home Anniversary! 🎉

It's been exactly one year since you got the keys to your new home. I hope this past year has been filled with wonderful memories!

As your mortgage professional, I wanted to check in and see how everything is going:

• How's the home treating you?
• Any questions about your mortgage?
• Any friends or family looking to buy a home?

Also, you've built up some equity this year! If you're curious about your current home value or have any questions, I'm always here to help.

Wishing you many more happy years in your home!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2024-11-13', type: 'Email', subject: 'Welcome home!', status: 'Sent', message: 'Sent closing congratulations and next steps' },
      { date: '2024-11-12', type: 'Phone', subject: 'Closing day!', status: 'Completed', message: 'Closing call and final documents review' }
    ]
  }
];

const mockLeadMetrics = () => ({
  new_today: 3,
  avg_contact_time: 1.2,
  conversion_rate: 23,
  hot_leads: 5,
  alerts: [
    '3 leads haven\'t been contacted in 24 hours.',
    '2 leads showed high buying intent in email.',
    'A referral partner sent you a lead and you haven\'t responded.'
  ]
});

const mockMessages = () => [
  {
    id: 1,
    type: 'email',
    type_icon: '📧',
    from: 'Sarah Johnson',
    borrower: 'Sarah Johnson',
    client_type: 'Pre-Approved',
    source: 'Outlook',
    timestamp: '2 hours ago',
    preview: 'Quick question about my pre-approval...',
    ai_summary: 'Asking about pre-approval expiration date',
    read: false,
    requires_response: true,
    owner: 'Loan Officer',
    stage: 'Pre-Approved',
    urgency: 'medium',
    date_created: '2025-11-13T14:00:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi Sarah,

Great question! Your pre-approval is valid for 90 days from the date we completed it.

Here are the details:
• Approved Date: November 8, 2025
• Expiration Date: February 8, 2026
• Days Remaining: 87 days

This gives you plenty of time to find the right home! If you need more time or if your financial situation changes, we can update or extend your pre-approval.

Are you actively looking at properties? I'd love to hear how the search is going!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-08', type: 'Email', subject: 'Pre-approval completed', status: 'Sent', message: 'Sent pre-approval letter and congratulations' },
      { date: '2025-11-05', type: 'Phone', subject: 'Pre-approval interview', status: 'Completed', message: '45-minute call gathering financial information' }
    ]
  },
  {
    id: 2,
    type: 'text',
    type_icon: '💬',
    from: 'Mike Chen',
    borrower: 'Mike Chen',
    client_type: 'Processing',
    source: 'Teams',
    timestamp: '5 hours ago',
    preview: 'Thanks for the update!',
    ai_summary: 'Acknowledged document receipt',
    read: true,
    requires_response: false,
    owner: 'Loan Processor',
    stage: 'Processing',
    urgency: 'low',
    date_created: '2025-11-13T09:00:00',
    preferred_contact_method: 'Text',
    ai_message: `Hi Mike,

You're very welcome! I'm glad we received your documents.

Quick update on your loan:
✅ W-2s received
✅ Tax returns verified
⏳ Waiting on final bank statement (due Thursday)

We're on track for your target closing date of December 5th. I'll keep you posted on next steps!

Let me know if you have any questions.

Best,
[Your Name]
Loan Processor`,
    communication_history: [
      { date: '2025-11-13', type: 'Text', subject: 'Document confirmation', status: 'Sent', message: 'Confirmed receipt of W-2s' },
      { date: '2025-11-10', type: 'Email', subject: 'Document checklist', status: 'Sent', message: 'Sent list of required documents' }
    ]
  },
  {
    id: 3,
    type: 'voicemail',
    type_icon: '🎙️',
    from: 'Emily Davis',
    borrower: 'Emily Davis',
    client_type: 'Application Started',
    source: 'Voicemail',
    timestamp: '1 day ago',
    preview: 'Left voicemail about appraisal timing',
    ai_summary: 'Wants to know when appraisal will be scheduled',
    duration: '1:23',
    read: false,
    requires_response: true,
    owner: 'Loan Officer',
    stage: 'Application Complete',
    urgency: 'high',
    date_created: '2025-11-12T10:30:00',
    preferred_contact_method: 'Phone',
    ai_message: `Hi Emily,

I got your voicemail about the appraisal timing - thanks for reaching out!

Good news: The appraisal has been scheduled for this Thursday, November 14th at 2:00 PM. The appraiser will call you 30 minutes before arriving.

What to expect:
• The inspection takes about 30-45 minutes
• You don't need to be home, but it's helpful if you are
• Make sure they can access all areas (attic, basement, garage)
• We should have the report within 2-3 business days

I'll call you this afternoon to confirm you got this message and answer any questions!

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-12', type: 'Voicemail', subject: 'Appraisal question', status: 'Received', message: 'Emily asked about appraisal timing' },
      { date: '2025-11-10', type: 'Email', subject: 'Application received', status: 'Sent', message: 'Confirmed receipt of completed application' },
      { date: '2025-11-08', type: 'Phone', subject: 'Initial consultation', status: 'Completed', message: 'Discussed loan options and process timeline' }
    ]
  },
  {
    id: 4,
    type: 'email',
    type_icon: '📧',
    from: 'John Smith',
    borrower: 'John Smith',
    client_type: 'Prospect',
    source: 'Outlook',
    timestamp: '3 days ago',
    preview: 'Following up on our conversation...',
    ai_summary: 'Requesting rate quote for $450k loan',
    read: true,
    requires_response: false,
    task_created: true,
    task_id: 'TASK-123',
    owner: 'Loan Officer',
    stage: 'Lead',
    urgency: 'medium',
    date_created: '2025-11-10T11:00:00',
    preferred_contact_method: 'Email',
    ai_message: `Hi John,

Thanks for your email! I'd be happy to provide you with rate quotes for your $450,000 home purchase.

Based on today's rates, here are your options:

**30-Year Fixed:**
• Rate: 6.875%
• Monthly Payment: $2,960
• Total Interest: $615,600

**15-Year Fixed:**
• Rate: 6.125%
• Monthly Payment: $3,850
• Total Interest: $243,000

**5/1 ARM:**
• Rate: 6.250% (initial 5 years)
• Monthly Payment: $2,770
• Potential savings in first 5 years

These rates assume 20% down ($90,000) and excellent credit (740+). Rates can change daily, so I'd recommend locking in soon if you're ready.

Would you like to schedule a call to discuss which option is best for your situation?

Best regards,
[Your Name]
Loan Officer`,
    communication_history: [
      { date: '2025-11-10', type: 'Email', subject: 'Rate quote request', status: 'Received', message: 'John requested rate information for $450k purchase' },
      { date: '2025-11-05', type: 'Phone', subject: 'Initial inquiry', status: 'Completed', message: '20-minute call about home buying process' }
    ]
  }
];

function Tasks() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  // Load completed tasks from localStorage on initial render
  const [completedTasks, setCompletedTasks] = useState(() => {
    const saved = localStorage.getItem('completedTasks');
    return saved ? new Set(JSON.parse(saved)) : new Set();
  });
  const [activeTab, setActiveTab] = useState('outstanding');
  const [selectedTask, setSelectedTask] = useState(null);
  const [commModal, setCommModal] = useState(null);
  const [snoozedTasks, setSnoozedTasks] = useState(new Set());
  const [teamMembers, setTeamMembers] = useState([]);
  const [selectedTaskIds, setSelectedTaskIds] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [completingTask, setCompletingTask] = useState(false);

  // Layout fix hook
  const { containerRef, triggerRecalculation } = useLayoutFix([loading]);

  // Save completed tasks to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('completedTasks', JSON.stringify([...completedTasks]));
  }, [completedTasks]);

  // Dashboard data states
  const [prioritizedTasks, setPrioritizedTasks] = useState([]);
  const [loanIssues, setLoanIssues] = useState([]);
  const [aiTasks, setAiTasks] = useState({ pending: [], waiting: [] });
  const [mumAlerts, setMumAlerts] = useState([]);
  const [leadMetrics, setLeadMetrics] = useState({});
  const [messages, setMessages] = useState([]);

  // Reconciliation tab state
  const [emailQueue, setEmailQueue] = useState([]);
  const [emailQueueTotal, setEmailQueueTotal] = useState(0);
  const [reconciliationStats, setReconciliationStats] = useState({});
  const [selectedEmail, setSelectedEmail] = useState(null);
  const [showDispositionDialog, setShowDispositionDialog] = useState(false);
  const [dispositionEmail, setDispositionEmail] = useState(null);
  const [selectedDisposition, setSelectedDisposition] = useState('');
  const [createTask, setCreateTask] = useState(false);
  const [taskTitle, setTaskTitle] = useState('');
  const [processingEmailId, setProcessingEmailId] = useState(null);
  const [queueFilters, setQueueFilters] = useState({
    status: 'pending',
    disposition: '',
    hasMatch: ''
  });

  // Phone tab state (Power Dialer)
  const [phoneTasks, setPhoneTasks] = useState([]);
  const [phoneContacts, setPhoneContacts] = useState([]);
  const [selectedPhoneTask, setSelectedPhoneTask] = useState(null);
  const [dialerSession, setDialerSession] = useState(null);
  const [callStatus, setCallStatus] = useState('idle');
  const [selectedPhoneTaskIds, setSelectedPhoneTaskIds] = useState([]);
  const [callLogs, setCallLogs] = useState([]);
  const [dialerSettings, setDialerSettings] = useState(null);

  // Disposition options for reconciliation
  const dispositionOptions = [
    { value: 'document_received', label: 'Document Received', icon: '📄' },
    { value: 'document_request', label: 'Document Request', icon: '📋' },
    { value: 'action_required', label: 'Action Required', icon: '⚡' },
    { value: 'general_correspondence', label: 'General Correspondence', icon: '💬' },
    { value: 'status_update', label: 'Status Update', icon: '📊' },
    { value: 'rate_lock_request', label: 'Rate Lock Request', icon: '🔒' },
    { value: 'closing_related', label: 'Closing Related', icon: '🏠' },
    { value: 'skip', label: 'Skip/Archive', icon: '⏭️' }
  ];

  useEffect(() => {
    loadTasks();
    loadTeamMembers();

    // Subscribe to task events from other components (e.g., ActionSidebar)
    const unsubscribeCompleted = subscribeToTaskEvent(TASK_EVENTS.TASK_COMPLETED, (detail) => {
      // If task was completed elsewhere, add to local completedTasks set
      if (detail.source !== 'tasks-page') {
        console.log('[Tasks] Task completed elsewhere, updating...', detail.taskId);
        setCompletedTasks(prev => {
          const newCompleted = new Set(prev);
          newCompleted.add(detail.taskId);
          return newCompleted;
        });
        // Also reload to get fresh data
        loadTasks();
      }
    });

    const unsubscribeRefresh = subscribeToTaskEvent(TASK_EVENTS.TASKS_REFRESH, (detail) => {
      if (detail.source !== 'tasks-page') {
        console.log('[Tasks] Refresh requested, reloading...');
        loadTasks();
      }
    });

    return () => {
      unsubscribeCompleted();
      unsubscribeRefresh();
    };
  }, []);

  // Auto-select first task when tasks load or tab changes
  useEffect(() => {
    if (!loading) {
      const tasksForTab = getTasksForTab();
      if (tasksForTab.length > 0) {
        // Only auto-select if no task is currently selected or if switching tabs
        if (!selectedTask || !tasksForTab.find(t => t.id === selectedTask.id)) {
          setSelectedTask(tasksForTab[0]);
        }
      } else {
        setSelectedTask(null);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [loading, activeTab, prioritizedTasks, aiTasks, loanIssues]);

  // Note: Task state (draft message, communication method, etc.) is now managed
  // inside the shared TaskDetailPanel component

  // Force layout recalculation when content loads to fix scroll issues
  useEffect(() => {
    if (!loading) {
      // Small delay to ensure DOM has updated
      const timer = setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
      }, 100);
      return () => clearTimeout(timer);
    }
  }, [loading, activeTab, selectedTask]);

  // Load reconciliation data when tab is active
  const loadReconciliationData = useCallback(async () => {
    try {
      // Load stats
      const statsResponse = await fetch(`${API_BASE_URL}/api/v1/email-intelligence/stats`, {
        headers: getAuthHeaders()
      });
      if (statsResponse.ok) {
        const data = await statsResponse.json();
        setReconciliationStats(data);
      }

      // Load email queue
      let url = `${API_BASE_URL}/api/v1/email-intelligence/queue?limit=50`;
      if (queueFilters.status) url += `&status=${queueFilters.status}`;
      if (queueFilters.disposition) url += `&disposition=${queueFilters.disposition}`;
      if (queueFilters.hasMatch === 'yes') url += `&has_match=true`;
      if (queueFilters.hasMatch === 'no') url += `&has_match=false`;

      const queueResponse = await fetch(url, { headers: getAuthHeaders() });
      if (queueResponse.ok) {
        const data = await queueResponse.json();
        setEmailQueue(data.emails || []);
        setEmailQueueTotal(data.total || 0);
      }
    } catch (error) {
      console.error('Error loading reconciliation data:', error);
    }
  }, [getAuthHeaders, queueFilters]);

  // Load phone dialer data when tab is active
  const loadPhoneData = useCallback(async () => {
    try {
      // Fetch call tasks
      const tasksResponse = await fetch(`${API_BASE}/api/v1/dialer/call-tasks`, {
        headers: getAuthHeaders()
      });
      if (tasksResponse.ok) {
        const data = await tasksResponse.json();
        setPhoneTasks(data.tasks || []);
      }

      // Fetch callable contacts
      const contactsResponse = await fetch(`${API_BASE}/api/v1/dialer/callable-contacts`, {
        headers: getAuthHeaders()
      });
      if (contactsResponse.ok) {
        const data = await contactsResponse.json();
        setPhoneContacts(data.contacts || []);
      }

      // Fetch call logs
      const logsResponse = await fetch(`${API_BASE}/api/v1/dialer/call-logs?limit=20`, {
        headers: getAuthHeaders()
      });
      if (logsResponse.ok) {
        const data = await logsResponse.json();
        setCallLogs(data.call_logs || []);
      }

      // Fetch dialer settings
      const settingsResponse = await fetch(`${API_BASE}/api/v1/dialer/settings`, {
        headers: getAuthHeaders()
      });
      if (settingsResponse.ok) {
        const data = await settingsResponse.json();
        setDialerSettings(data);
      }
    } catch (error) {
      console.error('Error loading phone data:', error);
    }
  }, [getAuthHeaders]);

  // Load tab-specific data when tab changes
  useEffect(() => {
    if (activeTab === 'reconciliation') {
      loadReconciliationData();
    } else if (activeTab === 'phone') {
      loadPhoneData();
    }
  }, [activeTab, loadReconciliationData, loadPhoneData]);

  // Reconciliation handlers
  const handleViewEmail = (email) => {
    setSelectedEmail(email);
  };

  const handleOpenDisposition = (email) => {
    setDispositionEmail(email);
    setSelectedDisposition(email.ai_analysis?.disposition || '');
    setCreateTask(false);
    setTaskTitle('');
    setShowDispositionDialog(true);
  };

  const handleProcessDisposition = async () => {
    if (!dispositionEmail || !selectedDisposition) return;

    setProcessingEmailId(dispositionEmail.id);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/email-intelligence/queue/${dispositionEmail.id}/process`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          disposition: selectedDisposition,
          create_task: createTask,
          task_title: createTask ? taskTitle : undefined
        })
      });

      if (response.ok) {
        setShowDispositionDialog(false);
        setDispositionEmail(null);
        loadReconciliationData();
      }
    } catch (error) {
      console.error('Error processing disposition:', error);
    } finally {
      setProcessingEmailId(null);
    }
  };

  const formatEmailDate = (dateStr) => {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
    if (diffDays === 0) return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    if (diffDays === 1) return 'Yesterday';
    if (diffDays < 7) return date.toLocaleDateString([], { weekday: 'short' });
    return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
  };

  const getEmailUrgencyLabel = (level) => {
    if (level >= 5) return { label: 'Critical', color: '#dc2626' };
    if (level >= 4) return { label: 'Urgent', color: '#f59e0b' };
    if (level >= 3) return { label: 'Normal', color: '#3b82f6' };
    return { label: 'Low', color: '#6b7280' };
  };

  // Phone dialer handlers
  const handleClickToDial = async (task) => {
    if (!task?.contact_phone) return;

    setCallStatus('dialing');
    try {
      const response = await fetch(`${API_BASE}/api/v1/dialer/click-to-dial`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          phone_number: task.contact_phone,
          lead_id: task.lead_id,
          loan_id: task.loan_id,
          task_id: task.id
        })
      });

      if (response.ok) {
        setCallStatus('in-progress');
      } else {
        setCallStatus('idle');
      }
    } catch (error) {
      console.error('Error initiating call:', error);
      setCallStatus('idle');
    }
  };

  const handleEndCall = async () => {
    setCallStatus('idle');
    // Refresh data after call
    loadPhoneData();
  };

  const togglePhoneTaskSelection = (taskId) => {
    setSelectedPhoneTaskIds(prev => {
      if (prev.includes(taskId)) {
        return prev.filter(id => id !== taskId);
      }
      return [...prev, taskId];
    });
  };

  // Select all phone tasks for power dialing
  const selectAllPhoneTasks = () => {
    if (selectedPhoneTaskIds.length === phoneTasks.length) {
      // If all selected, deselect all
      setSelectedPhoneTaskIds([]);
    } else {
      // Select all
      setSelectedPhoneTaskIds(phoneTasks.map(task => task.id));
    }
  };

  // Power dial state
  const [powerDialActive, setPowerDialActive] = useState(false);
  const [powerDialIndex, setPowerDialIndex] = useState(0);
  const [powerDialQueue, setPowerDialQueue] = useState([]);

  // Start power dial session with selected tasks (or all if none selected)
  const startPowerDial = () => {
    const tasksToDialIds = selectedPhoneTaskIds.length > 0
      ? selectedPhoneTaskIds
      : phoneTasks.map(t => t.id);

    const tasksToDial = phoneTasks.filter(t => tasksToDialIds.includes(t.id));

    if (tasksToDial.length === 0) {
      alert('No tasks to dial');
      return;
    }

    setPowerDialQueue(tasksToDial);
    setPowerDialIndex(0);
    setPowerDialActive(true);
    setSelectedPhoneTask(tasksToDial[0]);

    // Auto-dial the first contact
    handleClickToDial(tasksToDial[0]);
  };

  // Move to next contact in power dial queue
  const nextPowerDialContact = () => {
    const nextIndex = powerDialIndex + 1;
    if (nextIndex < powerDialQueue.length) {
      setPowerDialIndex(nextIndex);
      setSelectedPhoneTask(powerDialQueue[nextIndex]);
      handleClickToDial(powerDialQueue[nextIndex]);
    } else {
      // End of queue
      stopPowerDial();
    }
  };

  // Skip current contact and move to next
  const skipPowerDialContact = () => {
    nextPowerDialContact();
  };

  // Stop power dial session
  const stopPowerDial = () => {
    setPowerDialActive(false);
    setPowerDialQueue([]);
    setPowerDialIndex(0);
    setCallStatus('idle');
  };

  const loadTasks = async () => {
    try {
      setLoading(true);

      // Fetch workflow tasks from all leads/loans
      const token = localStorage.getItem('token');
      const workflowResponse = await fetch(`${API_BASE_URL}/api/v1/workflow-config/all-workflow-tasks?days_ahead=14`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      let workflowTasks = [];
      if (workflowResponse.ok) {
        const workflowData = await workflowResponse.json();
        workflowTasks = (workflowData.tasks || []).map(task => ({
          id: task.id,
          title: task.title,
          borrower: task.client_name || 'Client',
          stage: task.stage,
          urgency: task.urgency || 'medium',
          ai_action: null,
          owner: 'Loan Officer',
          date_created: task.due_date,
          due_date: task.due_date,
          preferred_contact_method: task.communication_methods?.includes('phone') ? 'Phone'
            : task.communication_methods?.includes('text') ? 'Text' : 'Email',
          ai_message: `${task.description}\n\nWorkflow: ${task.workflow_name}\nDays until due: ${task.days_until_due}`,
          description: task.description,
          source: 'Workflow',
          entity_type: task.client_type,
          entity_id: task.client_id,
          lead_id: task.client_type === 'lead' ? task.client_id : null,
          loan_id: task.client_type === 'loan' ? task.client_id : null,
          workflow_name: task.workflow_name,
          workflow_color: task.workflow_color,
          communication_methods: task.communication_methods || [],
          days_until_due: task.days_until_due,
          communication_history: []
        }));
      }

      // Also fetch any manual tasks from unified-tasks endpoint
      const response = await tasksAPI.getUnified();
      const unifiedTasks = response?.tasks || [];

      // Transform unified tasks to match frontend format
      const transformedTasks = unifiedTasks.map(task => ({
        id: `${task.source}-${task.id}`,
        title: task.title,
        borrower: task.client_name || 'Client',
        stage: task.stage || task.source,
        urgency: task.priority === 'urgent' ? 'critical' : task.priority || 'medium',
        ai_action: task.ai_suggested_response ? 'AI has a suggested action — approve?' : null,
        owner: task.owner || 'Loan Officer',
        date_created: task.created_at,
        due_date: task.due_date,
        preferred_contact_method: 'Email',
        ai_message: task.ai_suggested_response || `Complete task: ${task.title}`,
        ai_confidence: task.ai_confidence,
        description: task.description,
        source: task.source === 'reconciliation' ? 'AI Engine'
              : task.source === 'workflow' ? 'Workflow'
              : task.source === 'task' ? 'Manual'
              : task.source,
        entity_type: task.entity_type,
        entity_id: task.entity_id,
        email_from: task.email_from,
        email_subject: task.email_subject,
        communication_history: [],
        // SLA task fields
        sla_milestone_id: task.sla_milestone_id,
        sla_milestone_type: task.sla_milestone_type,
        sla_date_field: task.sla_date_field,
        related_type: task.related_type
      }));

      // Filter manual tasks AND workflow tasks from unified-tasks
      // (workflow tasks from unified-tasks are actual linked tasks in the tasks table)
      const manualAndUnifiedWorkflowTasks = transformedTasks.filter(t =>
        (t.source === 'Manual' || t.source === 'Workflow') &&
        !t.email_from &&
        !t.email_subject
      );

      // Filter out phone-only workflow tasks - those go to Power Dialer
      // A task is "phone-only" if phone is the preferred contact method
      const nonPhoneWorkflowTasks = workflowTasks.filter(task =>
        task.preferred_contact_method !== 'Phone'
      );

      // Combine old-style workflow tasks with manual + new linked workflow tasks
      const allTasks = [...nonPhoneWorkflowTasks, ...manualAndUnifiedWorkflowTasks];

      // Deduplicate tasks by id
      const seen = new Set();
      const deduplicatedTasks = allTasks.filter(task => {
        if (seen.has(task.id)) {
          return false;
        }
        seen.add(task.id);
        return true;
      });

      // Tasks page shows workflow tasks from all leads/loans + manual tasks
      setPrioritizedTasks(deduplicatedTasks);
      setLoanIssues(mockLoanIssues());
      // AI tasks are EMPTY - reconciliation items handled on Reconciliation page only
      setAiTasks({
        pending: [],
        waiting: []
      });
      setMumAlerts(mockMumAlerts());
      setLeadMetrics(mockLeadMetrics());
      // Messages tab is empty - emails only on Reconciliation page
      setMessages([]);

    } catch (error) {
      console.error('Failed to load tasks:', error);
      // Load demo data on error - but NO emails (emails only on Reconciliation page)
      setPrioritizedTasks(mockPrioritizedTasks());
      setLoanIssues(mockLoanIssues());
      setAiTasks({ pending: [], waiting: [] });  // No AI Engine tasks - they go to Reconciliation
      setMumAlerts(mockMumAlerts());
      setLeadMetrics(mockLeadMetrics());
      setMessages([]);  // No emails - they go to Reconciliation page only
    } finally {
      setLoading(false);
    }
  };

  const loadTeamMembers = async () => {
    try {
      const data = await teamAPI.getMembers();
      setTeamMembers(Array.isArray(data) ? data : []);
    } catch (error) {
      console.error('Failed to load team members:', error);
      setTeamMembers([]);
    }
  };

  // Handler functions
  const handleSend = (taskId, method, message) => {
    // method and message are passed from the shared TaskDetailPanel component
    alert(`Task sent via ${method || 'Email'}!`);
    handleComplete(taskId);
  };

  const handleDelete = async (taskId) => {

    try {
      // Check if this is a mock/demo task
      // Mock tasks have IDs like 'priority-0', 'message-1', 'ai-pending-0', etc.
      const mockIdPatterns = ['priority-', 'issue-', 'ai-pending-', 'ai-waiting-', 'mum-', 'lead-', 'message-'];
      const isMockTask = typeof taskId === 'string' && mockIdPatterns.some(pattern => taskId.startsWith(pattern));

      if (!isMockTask && typeof taskId === 'string') {
        // Check if it's a reconciliation task (AI Engine)
        if (taskId.startsWith('reconciliation-')) {
          const numericId = taskId.replace('reconciliation-', '');
          await reconciliationAPI.delete(numericId);
        } else if (taskId.startsWith('task-')) {
          // Regular task from unified-tasks
          const numericId = taskId.replace('task-', '');
          await tasksAPI.delete(numericId);
        } else if (taskId.startsWith('workflow-')) {
          // Workflow task - these may not be deletable, just remove from UI
          console.log('Workflow task dismissed from UI:', taskId);
        } else {
          // Try as-is for numeric IDs
          await tasksAPI.delete(taskId);
        }
      } else if (!isMockTask && typeof taskId === 'number') {
        await tasksAPI.delete(taskId);
      }

      // Remove from local state
      setCompletedTasks(prev => {
        const newCompleted = new Set(prev);
        newCompleted.add(taskId);
        return newCompleted;
      });

      // Select next task from current tab only
      if (selectedTask && selectedTask.id === taskId) {
        const tabTasks = getTasksForTab();
        const currentIndex = tabTasks.findIndex(t => t.id === taskId);
        const nextTask = tabTasks[currentIndex + 1] || tabTasks[currentIndex - 1] || null;
        setSelectedTask(nextTask);
      }

      // Emit event so other components (like ActionSidebar) can update
      emitTaskCompleted(taskId, 'tasks-page');
    } catch (error) {
      console.error('Error deleting task:', error);
      alert('Failed to delete task. Please try again.');
    }
  };

  // Bulk delete selected tasks
  const handleBulkDelete = async () => {
    if (selectedTaskIds.size === 0) return;

    setBulkDeleting(true);
    let successCount = 0;
    let failCount = 0;

    for (const taskId of selectedTaskIds) {
      try {
        const mockIdPatterns = ['priority-', 'issue-', 'ai-pending-', 'ai-waiting-', 'mum-', 'lead-', 'message-'];
        const isMockTask = typeof taskId === 'string' && mockIdPatterns.some(pattern => taskId.startsWith(pattern));

        if (!isMockTask && typeof taskId === 'string') {
          if (taskId.startsWith('reconciliation-')) {
            const numericId = taskId.replace('reconciliation-', '');
            await reconciliationAPI.delete(numericId);
          } else if (taskId.startsWith('task-')) {
            const numericId = taskId.replace('task-', '');
            await tasksAPI.delete(numericId);
          } else if (taskId.startsWith('workflow-')) {
            // Workflow tasks - just mark as completed in UI
            console.log('Workflow task dismissed:', taskId);
          } else {
            await tasksAPI.delete(taskId);
          }
        } else if (!isMockTask && typeof taskId === 'number') {
          await tasksAPI.delete(taskId);
        }

        // Mark as completed locally
        setCompletedTasks(prev => new Set([...prev, taskId]));
        successCount++;
      } catch (error) {
        console.error(`Failed to delete task ${taskId}:`, error);
        failCount++;
      }
    }

    // Clear selection
    setSelectedTaskIds(new Set());
    setSelectedTask(null);
    setBulkDeleting(false);

    if (failCount > 0) {
      alert(`Deleted ${successCount} tasks. ${failCount} failed.`);
    }
  };

  // Toggle task selection
  const toggleTaskSelection = (taskId, e) => {
    e.stopPropagation();
    setSelectedTaskIds(prev => {
      const newSet = new Set(prev);
      if (newSet.has(taskId)) {
        newSet.delete(taskId);
      } else {
        newSet.add(taskId);
      }
      return newSet;
    });
  };

  // Select all visible tasks
  const handleSelectAll = (tasks) => {
    const allSelected = tasks.every(t => selectedTaskIds.has(t.id));
    if (allSelected) {
      // Deselect all
      setSelectedTaskIds(prev => {
        const newSet = new Set(prev);
        tasks.forEach(t => newSet.delete(t.id));
        return newSet;
      });
    } else {
      // Select all
      setSelectedTaskIds(prev => {
        const newSet = new Set(prev);
        tasks.forEach(t => newSet.add(t.id));
        return newSet;
      });
    }
  };

  const handleSnooze = (taskId) => {
    setSnoozedTasks(prev => {
      const newSnoozed = new Set(prev);
      newSnoozed.add(taskId);
      return newSnoozed;
    });

    // Remove from snoozed after 24 hours
    setTimeout(() => {
      setSnoozedTasks(prev => {
        const newSnoozed = new Set(prev);
        newSnoozed.delete(taskId);
        return newSnoozed;
      });
    }, 24 * 60 * 60 * 1000); // 24 hours

    // Select next task from current tab only
    if (selectedTask && selectedTask.id === taskId) {
      const tabTasks = getTasksForTab();
      const currentIndex = tabTasks.findIndex(t => t.id === taskId);
      const nextTask = tabTasks[currentIndex + 1] || tabTasks[currentIndex - 1] || null;
      setSelectedTask(nextTask);
    }
  };

  const handleDelegate = async (member) => {
    if (!selectedTask) return;

    const memberName = `${member.first_name} ${member.last_name}`;
    const taskId = selectedTask.id;
    const taskSource = selectedTask.source;

    // Optimistic UI: remove task from list immediately
    if (taskSource === 'AI Engine') {
      setAiTasks(prev => ({
        pending: prev.pending.filter(t => t.id !== taskId),
        waiting: prev.waiting.filter(t => t.id !== taskId)
      }));
    } else if (taskSource === 'Client for Life') {
      setMumAlerts(prev => prev.filter(t => t.id !== taskId));
    } else if (taskSource === 'Messages') {
      setMessages(prev => prev.filter(t => t.id !== taskId));
    } else {
      setPrioritizedTasks(prev => prev.filter(t => t.id !== taskId));
      setLoanIssues(prev => prev.filter(t => t.id !== taskId));
    }

    // Move to next task
    const tabTasks = getTasksForTab();
    const currentIndex = tabTasks.findIndex(t => t.id === taskId);
    const nextTask = tabTasks[currentIndex + 1] || tabTasks[currentIndex - 1] || null;
    setSelectedTask(nextTask);

    // Call API in background
    try {
      await tasksAPI.delegate(taskId, member.id);
      console.log(`Task ${taskId} delegated to ${memberName}`);
    } catch (error) {
      console.error('Failed to delegate task:', error);
    }
  };

  // Get tasks filtered by active tab
  const getTasksForTab = () => {
    if (activeTab === 'completed') {
      return getCompletedTasks();
    }

    const allTasks = getAggregatedTasks();

    switch (activeTab) {
      case 'outstanding':
        return allTasks.filter(task => !snoozedTasks.has(task.id));
      case 'mum':
        return allTasks.filter(task => task.source === 'Client for Life' && !snoozedTasks.has(task.id));
      default:
        return allTasks.filter(task => !snoozedTasks.has(task.id));
    }
  };

  // Get all completed tasks for the completed tab
  const getCompletedTasks = () => {
    const tasks = [];

    // Add completed manual prioritized tasks
    prioritizedTasks.forEach((task, idx) => {
      if (completedTasks.has(`priority-${idx}`)) {
        tasks.push({
          id: `priority-${idx}`,
          ...task,
          source: 'Manual Priority',
          sourceIcon: '🎯'
        });
      }
    });

    // Add completed loan issues
    loanIssues.forEach((issue, idx) => {
      if (completedTasks.has(`issue-${idx}`)) {
        tasks.push({
          id: `issue-${idx}`,
          ...issue,
          title: issue.issue,
          stage: 'Milestone Alert',
          urgency: 'critical',
          source: 'Milestone Risk',
          sourceIcon: '🔥'
        });
      }
    });

    // Add completed AI pending tasks
    aiTasks.pending.forEach((task, idx) => {
      const taskId = `ai-pending-${idx}`;
      if (completedTasks.has(taskId)) {
        const { id: _originalId, ...taskWithoutId } = task;
        tasks.push({
          ...taskWithoutId,
          id: taskId,
          title: task.task,
          stage: 'AI Suggested',
          urgency: task.urgency || 'medium',
          ai_action: `AI confidence: ${task.confidence}%`,
          source: 'AI Engine',
          sourceIcon: '🤖'
        });
      }
    });

    // Add completed AI waiting tasks
    aiTasks.waiting.forEach((task, idx) => {
      const taskId = `ai-waiting-${idx}`;
      if (completedTasks.has(taskId)) {
        const { id: _originalId, ...taskWithoutId } = task;
        tasks.push({
          ...taskWithoutId,
          id: taskId,
          title: task.task,
          stage: 'Needs Approval',
          urgency: task.urgency || 'low',
          source: 'AI Engine',
          sourceIcon: '🤖'
        });
      }
    });

    // Add completed MUM alerts
    mumAlerts.forEach((alert, idx) => {
      if (completedTasks.has(`mum-${idx}`)) {
        tasks.push({
          id: `mum-${idx}`,
          ...alert,
          borrower: alert.client,
          stage: 'Client Retention',
          urgency: alert.urgency || 'medium',
          source: 'Client for Life',
          sourceIcon: '💎'
        });
      }
    });

    // Add completed lead alerts
    if (leadMetrics.alerts) {
      leadMetrics.alerts.forEach((alert, idx) => {
        if (alert && completedTasks.has(`lead-${idx}`)) {
          tasks.push({
            id: `lead-${idx}`,
            title: alert,
            borrower: '',
            stage: 'Leads',
            urgency: 'high',
            ai_action: null,
            source: 'Leads Engine',
            sourceIcon: '🚀'
          });
        }
      });
    }

    // Add completed messages
    messages.filter(m => !m.read).forEach((msg, idx) => {
      const msgId = `message-${idx}`;
      if (completedTasks.has(msgId)) {
        const { id: _originalId, ...msgWithoutId } = msg;
        tasks.push({
          ...msgWithoutId,
          id: msgId,
          title: `Message from ${msg.from}`,
          borrower: msg.from,
          stage: 'Communication',
          urgency: msg.urgency || 'medium',
          ai_action: msg.ai_summary ? `AI Summary: ${msg.ai_summary}` : null,
          source: 'Messages',
          sourceIcon: '💬'
        });
      }
    });

    return tasks;
  };

  // Aggregate all tasks from different containers
  // IMPORTANT: NO emails or AI Engine/reconciliation tasks - those go to Reconciliation page ONLY
  const getAggregatedTasks = () => {
    const tasks = [];
    const addedTaskIds = new Set();

    // Add prioritized tasks - EXCLUDE any AI Engine or email-related tasks
    prioritizedTasks.forEach((task, idx) => {
      const taskId = task.id || `priority-${idx}`;
      // Skip AI Engine tasks and any tasks with email data
      if (task.source === 'AI Engine' || task.email_from || task.email_subject) {
        return;
      }
      if (!completedTasks.has(taskId) && !addedTaskIds.has(taskId)) {
        addedTaskIds.add(taskId);
        // Set sourceIcon based on source
        let sourceIcon = '🎯';
        if (task.source === 'Workflow') sourceIcon = '⚡';
        else if (task.source === 'Manual') sourceIcon = '🎯';

        tasks.push({
          ...task,
          id: taskId,
          source: task.source || 'Manual Priority',
          sourceIcon
        });
      }
    });

    // Add loan issues as critical tasks
    loanIssues.forEach((issue, idx) => {
      const taskId = `issue-${idx}`;
      if (!completedTasks.has(taskId) && !addedTaskIds.has(taskId)) {
        addedTaskIds.add(taskId);
        tasks.push({
          id: taskId,
          ...issue,
          title: issue.issue,
          stage: 'Milestone Alert',
          urgency: 'critical',
          source: 'Milestone Risk',
          sourceIcon: '🔥'
        });
      }
    });

    // AI Engine tasks (emails/reconciliation) are NOT added here
    // They belong ONLY on the Reconciliation page

    // Add MUM alerts
    mumAlerts.forEach((alert, idx) => {
      const taskId = `mum-${idx}`;
      if (!completedTasks.has(taskId) && !addedTaskIds.has(taskId)) {
        addedTaskIds.add(taskId);
        tasks.push({
          id: taskId,
          ...alert,
          borrower: alert.client,
          stage: 'Client Retention',
          urgency: alert.urgency || 'medium',
          source: 'Client for Life',
          sourceIcon: '💎'
        });
      }
    });

    // Add lead alerts as tasks
    if (leadMetrics.alerts) {
      leadMetrics.alerts.forEach((alert, idx) => {
        const taskId = `lead-${idx}`;
        if (alert && !completedTasks.has(taskId) && !addedTaskIds.has(taskId)) {
          addedTaskIds.add(taskId);
          tasks.push({
            id: taskId,
            title: alert,
            borrower: '',
            stage: 'Leads',
            urgency: 'high',
            ai_action: null,
            source: 'Leads Engine',
            sourceIcon: '🚀'
          });
        }
      });
    }

    // Add unread messages as tasks
    messages.filter(m => !m.read).forEach((msg, idx) => {
      const taskId = `message-${idx}`;
      if (!completedTasks.has(taskId) && !addedTaskIds.has(taskId)) {
        addedTaskIds.add(taskId);
        const { id: _originalId, ...msgWithoutId } = msg;
        tasks.push({
          ...msgWithoutId,
          id: taskId,
          title: `Message from ${msg.from}`,
          borrower: msg.from,
          stage: 'Communication',
          urgency: msg.urgency || 'medium',
          ai_action: msg.ai_summary ? `AI Summary: ${msg.ai_summary}` : null,
          source: 'Messages',
          sourceIcon: '💬'
        });
      }
    });

    return tasks;
  };

  const handleComplete = async (taskId) => {
    setCompletingTask(true);
    try {
      // Check task type and call appropriate API
      const mockIdPatterns = ['priority-', 'issue-', 'ai-pending-', 'ai-waiting-', 'mum-', 'lead-', 'message-'];
      const isMockTask = typeof taskId === 'string' && mockIdPatterns.some(pattern => taskId.startsWith(pattern));

      if (!isMockTask) {
        if (typeof taskId === 'string' && taskId.startsWith('task-')) {
          const numericId = taskId.replace('task-', '');
          await tasksAPI.update(numericId, { status: 'completed' });
        } else if (typeof taskId === 'string' && taskId.startsWith('workflow-')) {
          // Workflow tasks - mark completed in backend if possible
          const numericId = taskId.replace('workflow-', '');
          try {
            await tasksAPI.update(numericId, { status: 'completed' });
          } catch (e) {
            console.log('Workflow task completed locally:', taskId);
          }
        } else if (typeof taskId === 'number') {
          await tasksAPI.update(taskId, { status: 'completed' });
        }
      }

      // Update local state
      setCompletedTasks(prev => {
        const newCompleted = new Set(prev);
        newCompleted.add(taskId);
        return newCompleted;
      });

      // If the completed task is the selected one, select the next task from current tab only
      if (selectedTask && selectedTask.id === taskId) {
        const tabTasks = getTasksForTab();
        const currentIndex = tabTasks.findIndex(t => t.id === taskId);
        const nextTask = tabTasks[currentIndex + 1] || tabTasks[currentIndex - 1] || null;
        setSelectedTask(nextTask);
      }

      // Emit event so other components (like ActionSidebar) can update
      emitTaskCompleted(taskId, 'tasks-page');
    } catch (error) {
      console.error('Error completing task:', error);
      // Still mark as completed locally even if API fails
      setCompletedTasks(prev => {
        const newCompleted = new Set(prev);
        newCompleted.add(taskId);
        return newCompleted;
      });
      // Still emit event for local completion
      emitTaskCompleted(taskId, 'tasks-page');
    } finally {
      setCompletingTask(false);
    }
  };

  // Handle changing lead/loan status
  const handleChangeStatus = async (newStatus) => {
    if (!selectedTask) return;

    setUpdatingStatus(true);
    try {
      // Check if this task is associated with a lead or loan
      const leadId = selectedTask.lead_id || selectedTask.leadId;
      const loanId = selectedTask.loan_id || selectedTask.loanId;

      if (leadId) {
        await leadsAPI.update(leadId, { stage: newStatus });
        // Update the selected task's stage locally
        setSelectedTask(prev => ({ ...prev, stage: newStatus }));
        alert(`Lead status updated to "${LEAD_STAGES.find(s => s.value === newStatus)?.label || newStatus}"`);
      } else if (loanId) {
        await loansAPI.update(loanId, { stage: newStatus });
        setSelectedTask(prev => ({ ...prev, stage: newStatus }));
        alert(`Loan status updated to "${newStatus}"`);
      } else {
        alert('No lead or loan associated with this task');
      }
    } catch (error) {
      console.error('Error updating status:', error);
      alert('Failed to update status. Please try again.');
    } finally {
      setUpdatingStatus(false);
    }
  };

  const handleApproveAiTask = async (taskId, method = 'email') => {
    try {
      // Get the task details before completing
      const task = selectedTask;

      // If there's an AI message, log it as a sent email
      if (task && task.ai_message) {
        // Store the sent email in localStorage for now (will be API later)
        const sentEmails = JSON.parse(localStorage.getItem('sentEmails') || '[]');
        sentEmails.push({
          id: `email-${Date.now()}`,
          taskId: taskId,
          to: task.borrower,
          subject: task.title,
          body: task.ai_message,
          sentAt: new Date().toISOString(),
          sentVia: method,
          status: 'sent',
          loanId: task.loan_id || task.loanId || null
        });
        localStorage.setItem('sentEmails', JSON.stringify(sentEmails));
      }

      // Mark task as complete
      handleComplete(taskId);

      // Show success message
      alert('AI action approved and sent!');
    } catch (error) {
      console.error('Error approving AI task:', error);
      alert('Failed to approve task');
    }
  };

  const getUrgencyColor = (urgency) => {
    const colors = {
      critical: '#dc2626',
      high: '#f59e0b',
      medium: '#3b82f6',
      low: '#6b7280'
    };
    return colors[urgency] || '#6b7280';
  };

  const handleCommClick = (comm) => {
    // Generate detailed content based on type
    let detailedContent = null;

    if (comm.type === 'Email') {
      detailedContent = {
        type: 'Email',
        subject: comm.subject,
        thread: [
          {
            from: 'You',
            to: selectedTask?.borrower || 'Client',
            date: comm.date,
            body: comm.message
          },
          {
            from: selectedTask?.borrower || 'Client',
            to: 'You',
            date: comm.date,
            body: 'Thank you for reaching out! I appreciate the information. I have a few questions about the next steps...'
          }
        ]
      };
    } else if (comm.type === 'Phone') {
      detailedContent = {
        type: 'Phone',
        subject: comm.subject,
        duration: '30 minutes',
        date: comm.date,
        summary: comm.message,
        details: `Call started at 2:30 PM and lasted 30 minutes.

Key Discussion Points:
• Reviewed loan options and interest rates
• Discussed pre-qualification requirements
• Explained the application process timeline
• Answered questions about documentation needed
• Scheduled follow-up for next week

Next Steps:
• Client will gather employment verification documents
• Send detailed loan comparison email
• Schedule property search consultation

Client seemed very engaged and interested in moving forward with the pre-qualification process.`
      };
    } else if (comm.type === 'Text') {
      detailedContent = {
        type: 'Text',
        subject: comm.subject,
        messages: [
          { from: 'You', text: comm.message, time: '10:30 AM' },
          { from: selectedTask?.borrower || 'Client', text: 'Thanks for the reminder! I\'ll upload them today.', time: '10:45 AM' },
          { from: 'You', text: 'Perfect! Let me know if you need any help.', time: '10:46 AM' },
          { from: selectedTask?.borrower || 'Client', text: 'Will do 👍', time: '10:47 AM' }
        ]
      };
    }

    setCommModal(detailedContent);
  };

  // Use skeleton loader that matches the exact layout structure
  if (loading) return <TasksSkeleton />;

  const allTasks = getAggregatedTasks();
  const tabTasks = getTasksForTab();

  // Reusable Email Layout Component
  const TaskEmailLayout = ({ tasks, emptyMessage = "No tasks" }) => {
    const allSelected = tasks.length > 0 && tasks.every(t => selectedTaskIds.has(t.id));
    const someSelected = tasks.some(t => selectedTaskIds.has(t.id));

    return (
    <div className="email-layout">
      {/* Task List (Left Side) */}
      <div className="task-inbox">
        <div className="inbox-header">
          <div className="inbox-header-left">
            <input
              type="checkbox"
              className="task-checkbox select-all-checkbox"
              checked={allSelected}
              ref={(el) => {
                if (el) el.indeterminate = someSelected && !allSelected;
              }}
              onChange={() => handleSelectAll(tasks)}
              title="Select all"
            />
            <h3>Tasks</h3>
            <span className="task-count">{tasks.length}</span>
          </div>
          {selectedTaskIds.size > 0 && (
            <button
              className="btn-bulk-delete"
              onClick={handleBulkDelete}
              disabled={bulkDeleting}
            >
              {bulkDeleting ? 'Deleting...' : `🗑️ Delete (${selectedTaskIds.size})`}
            </button>
          )}
        </div>
        <div className="inbox-list">
          {tasks.map((task) => (
            <div
              key={task.id}
              className={`inbox-item ${selectedTask && selectedTask.id === task.id ? 'selected' : ''} ${selectedTaskIds.has(task.id) ? 'checked' : ''}`}
              onClick={() => setSelectedTask(task)}
            >
              <div className="inbox-item-header">
                <input
                  type="checkbox"
                  className="task-checkbox"
                  checked={selectedTaskIds.has(task.id)}
                  onChange={(e) => toggleTaskSelection(task.id, e)}
                  onClick={(e) => e.stopPropagation()}
                />
                <span className="source-icon">{task.sourceIcon}</span>
                <span className="task-title-compact">{task.title}</span>
                {task.ai_confidence && (
                  <span
                    className={`ai-confidence-meter ${task.ai_confidence >= 90 ? 'high' : task.ai_confidence >= 70 ? 'medium' : 'low'}`}
                    title={`AI Confidence: ${task.ai_confidence}%`}
                  >
                    🤖 {task.ai_confidence}%
                  </span>
                )}
              </div>
              <div className="inbox-item-meta">
                <span className="task-client-compact">{task.borrower || task.source}</span>
                <span
                  className="urgency-dot"
                  style={{ backgroundColor: getUrgencyColor(task.urgency) }}
                  title={task.urgency}
                ></span>
              </div>
              <div className="task-preview">{task.stage}</div>
            </div>
          ))}
          {tasks.length === 0 && (
            <div className="empty-inbox">
              <p>{emptyMessage}</p>
            </div>
          )}
        </div>
      </div>

      {/* Task Detail (Right Side) - Using Shared Component */}
      <TaskDetailPanel
        task={selectedTask}
        onComplete={handleComplete}
        onDelete={handleDelete}
        onSnooze={handleSnooze}
        onDelegate={handleDelegate}
        onSend={handleSend}
        onApproveAi={handleApproveAiTask}
        onChangeStatus={handleChangeStatus}
        completing={completingTask}
        updatingStatus={updatingStatus}
        teamMembers={teamMembers}
        statusOptions={LEAD_STAGES}
      />
    </div>
    );
  };

  // Reusable Email Layout for Reconciliation
  const ReconciliationEmailLayout = () => {
    return (
      <div className="email-layout">
        {/* Email List (Left Side) */}
        <div className="task-inbox">
          <div className="inbox-header">
            <div className="inbox-header-left">
              <h3>📧 Email Queue</h3>
              <span className="task-count">{emailQueue.length}</span>
            </div>
            <div className="inbox-filters">
              <select
                value={queueFilters.status}
                onChange={(e) => setQueueFilters({ ...queueFilters, status: e.target.value })}
                className="filter-select"
              >
                <option value="">All Status</option>
                <option value="pending">Pending</option>
                <option value="processed">Processed</option>
              </select>
            </div>
          </div>
          <div className="inbox-list">
            {emailQueue.map((email) => (
              <div
                key={email.id}
                className={`inbox-item ${selectedEmail && selectedEmail.id === email.id ? 'selected' : ''}`}
                onClick={() => setSelectedEmail(email)}
              >
                <div className="inbox-item-header">
                  <span className="source-icon">📧</span>
                  <span className="task-title-compact">{email.subject || '(No Subject)'}</span>
                </div>
                <div className="inbox-item-meta">
                  <span className="task-client-compact">{email.from_name || email.from_email}</span>
                  {email.ai_analysis?.urgency_level && (
                    <span
                      className="urgency-dot"
                      style={{ backgroundColor: getEmailUrgencyLabel(email.ai_analysis.urgency_level).color }}
                      title={getEmailUrgencyLabel(email.ai_analysis.urgency_level).label}
                    ></span>
                  )}
                </div>
                <div className="task-preview">
                  {email.matched_loan_id && <span className="match-tag">Loan #{email.matched_loan_id}</span>}
                  {email.matched_lead_id && <span className="match-tag lead">Lead #{email.matched_lead_id}</span>}
                  <span className="date-tag">{formatEmailDate(email.sent_date)}</span>
                </div>
              </div>
            ))}
            {emailQueue.length === 0 && (
              <div className="empty-inbox">
                <p>📭 No emails in queue</p>
              </div>
            )}
          </div>
        </div>

        {/* Email Detail (Right Side) - Using shared component */}
        <ReconciliationDetailPanel
          email={selectedEmail}
          onProcess={(email) => handleOpenDisposition(email)}
          onViewLoan={(loanId) => navigate(`/loans/${loanId}`)}
          onViewLead={(leadId) => navigate(`/leads/${leadId}`)}
          onClose={() => setSelectedEmail(null)}
        />
      </div>
    );
  };

  // Reusable Email Layout for Phone Dialer
  const PhoneEmailLayout = () => {
    return (
      <div className="email-layout">
        {/* Phone Task List (Left Side) */}
        <div className="task-inbox">
          <div className="inbox-header">
            <div className="inbox-header-left">
              <h3>📞 Call Tasks</h3>
              <span className="task-count">{phoneTasks.length}</span>
            </div>
            <div className="inbox-header-right">
              <button
                className="select-all-btn"
                onClick={selectAllPhoneTasks}
                title={selectedPhoneTaskIds.length === phoneTasks.length ? "Deselect All" : "Select All"}
              >
                {selectedPhoneTaskIds.length === phoneTasks.length ? '☑️ Deselect All' : '☐ Select All'}
              </button>
              {!powerDialActive ? (
                <button
                  className="power-dial-btn"
                  onClick={startPowerDial}
                  disabled={phoneTasks.length === 0}
                  title={selectedPhoneTaskIds.length > 0 ? `Power Dial ${selectedPhoneTaskIds.length} selected` : 'Power Dial All'}
                >
                  🚀 Power Dial {selectedPhoneTaskIds.length > 0 ? `(${selectedPhoneTaskIds.length})` : 'All'}
                </button>
              ) : (
                <button
                  className="power-dial-btn stop"
                  onClick={stopPowerDial}
                >
                  ⏹️ Stop Dialing
                </button>
              )}
            </div>
          </div>
          {/* Power Dial Progress Bar */}
          {powerDialActive && (
            <div className="power-dial-progress">
              <div className="progress-info">
                <span>📞 Power Dialing: {powerDialIndex + 1} of {powerDialQueue.length}</span>
                <span className="progress-contact">{powerDialQueue[powerDialIndex]?.contact_name}</span>
              </div>
              <div className="progress-bar">
                <div
                  className="progress-fill"
                  style={{ width: `${((powerDialIndex + 1) / powerDialQueue.length) * 100}%` }}
                />
              </div>
            </div>
          )}
          <div className="inbox-list">
            {phoneTasks.map((task) => (
              <div
                key={task.id}
                className={`inbox-item ${selectedPhoneTask && selectedPhoneTask.id === task.id ? 'selected' : ''}`}
                onClick={() => setSelectedPhoneTask(task)}
              >
                <div className="inbox-item-header">
                  <input
                    type="checkbox"
                    className="task-checkbox"
                    checked={selectedPhoneTaskIds.includes(task.id)}
                    onChange={() => togglePhoneTaskSelection(task.id)}
                    onClick={(e) => e.stopPropagation()}
                  />
                  <span className="source-icon">{task.task_type === 'workflow' ? '⚡' : '📞'}</span>
                  <span className="task-title-compact">{task.title}</span>
                </div>
                <div className="inbox-item-meta">
                  <span className="task-client-compact">{task.contact_name}</span>
                  <span
                    className="urgency-dot"
                    style={{ backgroundColor: task.priority === 'high' ? '#f59e0b' : '#6b7280' }}
                  ></span>
                </div>
                <div className="task-preview">
                  <span className="phone-tag">📱 {task.contact_phone}</span>
                  {task.entity_type && (
                    <span className={`match-tag ${task.entity_type}`}>
                      {task.entity_type === 'lead' ? 'Lead' : 'Loan'}
                    </span>
                  )}
                </div>
              </div>
            ))}
            {phoneTasks.length === 0 && (
              <div className="empty-inbox">
                <p>📞 No call tasks available</p>
                <p style={{ fontSize: '12px', color: '#888' }}>Phone tasks from workflows will appear here</p>
              </div>
            )}
          </div>
        </div>

        {/* Phone Task Detail (Right Side) - Using shared component */}
        <CallDetailPanel
          task={selectedPhoneTask}
          callStatus={callStatus}
          powerDialActive={powerDialActive}
          powerDialIndex={powerDialIndex}
          powerDialTotal={powerDialQueue.length}
          onClickToDial={handleClickToDial}
          onEndCall={handleEndCall}
          onNextContact={nextPowerDialContact}
          onSkipContact={skipPowerDialContact}
          onStopPowerDial={stopPowerDial}
          onViewEntity={(task) => {
            if (task.lead_id) {
              navigate(`/leads/${task.lead_id}`);
            } else if (task.loan_id) {
              navigate(`/loans/${task.loan_id}`);
            }
          }}
          onComplete={(taskId) => {
            setPhoneTasks(prev => prev.filter(t => t.id !== taskId));
            setSelectedPhoneTask(null);
          }}
          onClose={() => setSelectedPhoneTask(null)}
        />
      </div>
    );
  };

  return (
    <div className="tasks-page" ref={containerRef}>
      <div className="tasks-container">
        <div className="tasks-header">
          <div className="header-content">
            <h1>Tasks</h1>
            <p>Manage and complete your outstanding tasks</p>

            {/* Tab Navigation */}
            <div className="tab-navigation">
              <button
                className={`tab-button ${activeTab === 'outstanding' ? 'active' : ''}`}
                onClick={() => setActiveTab('outstanding')}
              >
                Outstanding ({allTasks.filter(t => !snoozedTasks.has(t.id)).length})
              </button>
              <button
                className={`tab-button ${activeTab === 'reconciliation' ? 'active' : ''}`}
                onClick={() => setActiveTab('reconciliation')}
              >
                Reconciliation ({reconciliationStats.pending_count || 0})
              </button>
              <button
                className={`tab-button ${activeTab === 'phone' ? 'active' : ''}`}
                onClick={() => setActiveTab('phone')}
              >
                Phone ({phoneTasks.length})
              </button>
              <button
                className={`tab-button ${activeTab === 'completed' ? 'active' : ''}`}
                onClick={() => setActiveTab('completed')}
              >
                Completed ({getCompletedTasks().length})
              </button>
            </div>
          </div>
          <div className="header-actions">
            {/* Action button placeholder - can be customized per tab */}
          </div>
        </div>

        {/* Outstanding Tasks Tab */}
        {activeTab === 'outstanding' && (
          <div className="tasks-content">
            <TaskEmailLayout tasks={tabTasks} emptyMessage="No outstanding tasks" />
          </div>
        )}

        {/* Reconciliation Tab */}
        {activeTab === 'reconciliation' && (
          <div className="tasks-content">
            <ReconciliationEmailLayout />
          </div>
        )}

        {/* Phone Tab */}
        {activeTab === 'phone' && (
          <div className="tasks-content">
            <PhoneEmailLayout />
          </div>
        )}

        {/* Completed Tasks Tab */}
        {activeTab === 'completed' && (
          <div className="tasks-content">
            <TaskEmailLayout tasks={tabTasks} emptyMessage="No completed tasks yet" />
          </div>
        )}
      </div>

      {/* Delete and Delegate modals are now handled inside TaskDetailPanel */}

      {/* Communication Detail Modal */}
      {commModal && (
        <div className="comm-modal-overlay" onClick={() => setCommModal(null)}>
          <div className="comm-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-comm-modal" onClick={() => setCommModal(null)}>×</button>

            <div className="comm-modal-header">
              <span className="comm-modal-icon">
                {commModal.type === 'Email' && '📧'}
                {commModal.type === 'Phone' && '📞'}
                {commModal.type === 'Text' && '💬'}
              </span>
              <h2>{commModal.subject}</h2>
            </div>

            <div className="comm-modal-body">
              {commModal.type === 'Email' && (
                <div className="email-thread">
                  {commModal.thread.map((email, idx) => (
                    <div key={idx} className="email-message">
                      <div className="email-message-header">
                        <div className="email-from-to">
                          <strong>From:</strong> {email.from}<br />
                          <strong>To:</strong> {email.to}
                        </div>
                        <div className="email-date">{new Date(email.date).toLocaleString()}</div>
                      </div>
                      <div className="email-message-body">{email.body}</div>
                    </div>
                  ))}
                </div>
              )}

              {commModal.type === 'Phone' && (
                <div className="phone-summary">
                  <div className="call-meta">
                    <div className="call-info-item">
                      <strong>Duration:</strong> {commModal.duration}
                    </div>
                    <div className="call-info-item">
                      <strong>Date:</strong> {new Date(commModal.date).toLocaleString()}
                    </div>
                  </div>
                  <div className="call-summary-section">
                    <h3>Summary</h3>
                    <p>{commModal.summary}</p>
                  </div>
                  <div className="call-details-section">
                    <h3>Call Notes</h3>
                    <pre className="call-notes">{commModal.details}</pre>
                  </div>
                </div>
              )}

              {commModal.type === 'Text' && (
                <div className="text-thread">
                  {commModal.messages.map((msg, idx) => (
                    <div key={idx} className={`text-message ${msg.from === 'You' ? 'sent' : 'received'}`}>
                      <div className="text-message-bubble">
                        <div className="text-message-sender">{msg.from}</div>
                        <div className="text-message-text">{msg.text}</div>
                        <div className="text-message-time">{msg.time}</div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* AI Acknowledgment is now shown inline inside TaskDetailPanel */}

      {/* Disposition Dialog Modal */}
      {showDispositionDialog && dispositionEmail && (
        <div className="modal-overlay" onClick={() => setShowDispositionDialog(false)}>
          <div className="modal-content disposition-modal" onClick={(e) => e.stopPropagation()}>
            <h2>Process Email</h2>
            <p className="disposition-email-subject">
              <strong>Subject:</strong> {dispositionEmail.subject || '(No Subject)'}
            </p>
            <p className="disposition-email-from">
              <strong>From:</strong> {dispositionEmail.from_name || dispositionEmail.from_email}
            </p>

            <div className="disposition-options-grid">
              {dispositionOptions.map((option) => (
                <button
                  key={option.value}
                  className={`disposition-option ${selectedDisposition === option.value ? 'selected' : ''}`}
                  onClick={() => setSelectedDisposition(option.value)}
                >
                  <span className="disposition-icon">{option.icon}</span>
                  <span className="disposition-label">{option.label}</span>
                </button>
              ))}
            </div>

            <label className="create-task-checkbox">
              <input
                type="checkbox"
                checked={createTask}
                onChange={(e) => setCreateTask(e.target.checked)}
              />
              <span>Create a follow-up task</span>
            </label>

            {createTask && (
              <input
                type="text"
                className="task-title-input"
                placeholder="Task title..."
                value={taskTitle}
                onChange={(e) => setTaskTitle(e.target.value)}
              />
            )}

            <div className="modal-buttons">
              <button
                className="btn-modal-primary"
                onClick={handleProcessDisposition}
                disabled={!selectedDisposition || processingEmailId === dispositionEmail.id}
              >
                {processingEmailId === dispositionEmail.id ? 'Processing...' : 'Process Email'}
              </button>
              <button
                className="btn-modal-cancel"
                onClick={() => setShowDispositionDialog(false)}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default Tasks;

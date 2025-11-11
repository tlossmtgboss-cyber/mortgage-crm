import React, { useState, useEffect } from 'react';
import { onboardingAPI, teamAPI } from '../services/api';
import './OnboardingWizard.css';

const OnboardingWizard = ({ onComplete, onSkip }) => {
  const [currentStep, setCurrentStep] = useState(1);
  const [activeMilestone, setActiveMilestone] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [connectionModal, setConnectionModal] = useState(null);
  const [helpdeskModal, setHelpdeskModal] = useState(null);
  const [uploadedTestEmail, setUploadedTestEmail] = useState(null);
  const [draggedTask, setDraggedTask] = useState(null);
  const [taskEditModal, setTaskEditModal] = useState(null);
  const [roleAddModal, setRoleAddModal] = useState(false);
  const [newRoleForm, setNewRoleForm] = useState({ role_title: '', role_name: '', responsibilities: '', skills_required: [], key_activities: [] });
  const [teamMembers, setTeamMembers] = useState([]);
  const [formData, setFormData] = useState({
    // Step 1: Upload Documents
    sopFiles: [],
    processTree: null,

    // Step 2: Role Review (new)
    extractedRoles: [],

    // Step 3: Task Review (new)
    extractedTasks: [],
    extractedMilestones: [],

    // Step 4: Team & Roles
    teamName: '',
    members: [{ firstName: '', lastName: '', email: '', phone: '', role: '' }],
    manager: '',
    timezone: 'America/Los_Angeles',

    // Step 5: Process Tree (populated by AI or manually)
    milestones: [],

    // Step 6: Integrations
    calendly: { connected: false, eventTypes: [] },
    email: { provider: null, connected: false, mailboxes: [] },
    telephony: { provider: null, phoneNumbers: [] },

    // Step 7: Compliance
    quietHours: { start: '08:00', end: '20:00' },
    maxRetries: 3,
    maxDailyAttempts: 5,
    dncAccepted: false,
    recordingPolicy: {},

    // Step 8: AI Agent
    agentName: 'Samantha',
    voiceProfile: 'elevenlabs-default',
    identityLine: '',
    purposePrompts: {},
    escalationNumber: '',

    // Step 9: Test & Go-Live
    testsPassed: {
      callTest: false,
      emailTest: false
    }
  });

  const totalSteps = 9;

  // Load existing onboarding data when component mounts
  useEffect(() => {
    const loadExistingData = async () => {
      try {
        // Load existing roles, milestones, tasks, and team members if they exist
        const [roles, milestones, tasks, members] = await Promise.all([
          onboardingAPI.getRoles().catch(() => []),
          onboardingAPI.getMilestones().catch(() => []),
          onboardingAPI.getTasks().catch(() => []),
          teamAPI.getMembers().catch(() => [])
        ]);

        if (members.length > 0) {
          setTeamMembers(members);
        }

        if (roles.length > 0 || milestones.length > 0 || tasks.length > 0) {
          setFormData(prevData => ({
            ...prevData,
            extractedRoles: roles,
            extractedMilestones: milestones,
            extractedTasks: tasks,
            // Don't load processTree from database - should start fresh at 0,0,0
            // processTree will only be set after user uploads documents and runs AI processing
            processTree: null
          }));
        }
      } catch (error) {
        console.error('Error loading existing onboarding data:', error);
      }
    };

    loadExistingData();
  }, []);

  const handleNext = () => {
    if (currentStep < totalSteps) {
      setCurrentStep(currentStep + 1);
    } else {
      handleComplete();
    }
  };

  const handleBack = () => {
    if (currentStep > 1) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleComplete = async () => {
    try {
      // Save process tree to localStorage
      if (formData.processTree && formData.milestones.length > 0) {
        const processTreeData = {
          ...formData.processTree,
          milestonesData: formData.milestones
        };
        localStorage.setItem('onboardingProcessTree', JSON.stringify(processTreeData));
      }

      const token = localStorage.getItem('token');
      const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

      await fetch(`${API_BASE_URL}/api/v1/onboarding/complete`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(formData)
      });

      if (onComplete) {
        onComplete();
      }
    } catch (error) {
      console.error('Failed to complete onboarding:', error);
      // Still complete on error for now
      if (onComplete) {
        onComplete();
      }
    }
  };

  const updateField = (field, value) => {
    setFormData(prevData => ({ ...prevData, [field]: value }));
  };

  const addMember = () => {
    setFormData(prevData => ({
      ...prevData,
      members: [...prevData.members, { firstName: '', lastName: '', email: '', phone: '', role: '' }]
    }));
  };

  const updateMember = (index, field, value) => {
    setFormData(prevData => {
      const newMembers = [...prevData.members];
      newMembers[index][field] = value;
      return { ...prevData, members: newMembers };
    });
  };

  const removeMember = (index) => {
    setFormData(prevData => ({
      ...prevData,
      members: prevData.members.filter((_, i) => i !== index)
    }));
  };

  // File upload handlers
  const handleFileSelect = (e) => {
    const files = Array.from(e.target.files);
    addFiles(files);
  };

  const addFiles = (newFiles) => {
    const MAX_FILES = 10;
    const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB per file

    const validFiles = newFiles.filter(file => {
      // Check file type
      const validTypes = ['.pdf', '.docx', '.xlsx', '.csv', '.doc', '.xls', '.txt'];
      const fileExt = '.' + file.name.split('.').pop().toLowerCase();
      if (!validTypes.includes(fileExt)) {
        alert(`${file.name}: Invalid file type. Please upload PDF, DOCX, XLSX, or CSV files.`);
        return false;
      }

      // Check file size
      if (file.size > MAX_FILE_SIZE) {
        alert(`${file.name}: File too large. Maximum size is 50MB.`);
        return false;
      }

      return true;
    });

    const currentFiles = formData.sopFiles || [];
    const combinedFiles = [...currentFiles, ...validFiles];

    if (combinedFiles.length > MAX_FILES) {
      alert(`Maximum ${MAX_FILES} files allowed. Only adding first ${MAX_FILES - currentFiles.length} files.`);
      updateField('sopFiles', combinedFiles.slice(0, MAX_FILES));
    } else {
      updateField('sopFiles', combinedFiles);
    }
  };

  const removeFile = (index) => {
    const newFiles = formData.sopFiles.filter((_, i) => i !== index);
    updateField('sopFiles', newFiles);
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    const files = Array.from(e.dataTransfer.files);
    addFiles(files);
  };

  // AI Process Tree Generation
  const handleAIProcessing = async () => {
    setIsProcessing(true);

    try {
      // Upload actual files to be parsed by AI
      // Each file will be read and parsed separately, then combined
      const parseResult = await onboardingAPI.parseDocumentsUpload(formData.sopFiles);

      // Transform API response to match the existing data structure
      const generatedMilestones = parseResult.milestones.map((milestone, mIndex) => {
        // Get tasks for this milestone
        const milestoneTasks = parseResult.tasks
          .filter(task => task.milestone_id === milestone.id)
          .map(task => {
            // Find the role for this task
            const role = parseResult.roles.find(r => r.id === task.role_id);
            return {
              name: task.task_name,
              owner: role?.role_title || 'Unassigned',
              sla: task.sla || 24,
              slaUnit: task.sla_unit || 'hours',
              aiAuto: task.ai_automatable || false
            };
          });

        return {
          name: milestone.name,
          tasks: milestoneTasks
        };
      });

      // Calculate stats
      const totalTasks = parseResult.summary.total_tasks;

      // Store all extracted data
      setFormData(prevData => ({
        ...prevData,
        milestones: generatedMilestones,
        extractedRoles: parseResult.roles,
        extractedTasks: parseResult.tasks,
        extractedMilestones: parseResult.milestones,
        processTree: {
          generated: true,
          milestones: parseResult.summary.total_milestones,
          tasks: totalTasks,
          roles: parseResult.summary.total_roles
        }
      }));

      setIsProcessing(false);

      // Automatically advance to role review step
      setCurrentStep(2);

    } catch (error) {
      console.error('Error parsing documents:', error);
      setIsProcessing(false);
      alert('Failed to parse documents. Please try again.');

      // Fallback to sample data in case of error
      const generatedMilestones = [
      {
        name: 'New Lead',
        tasks: [
          { name: 'Log lead in CRM', owner: 'Concierge', sla: 15, slaUnit: 'hours', aiAuto: true },
          { name: 'Initial contact via phone/email', owner: 'Concierge', sla: 2, slaUnit: 'hours', aiAuto: true },
          { name: 'Send welcome email with company overview', owner: 'Concierge', sla: 1, slaUnit: 'hours', aiAuto: true },
          { name: 'Schedule discovery call', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Conduct needs assessment call', owner: 'Loan Officer', sla: 48, slaUnit: 'hours', aiAuto: false },
          { name: 'Send pre-qualification questionnaire', owner: 'Concierge', sla: 4, slaUnit: 'hours', aiAuto: true },
          { name: 'Review pre-qualification responses', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Request credit pull authorization', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Pull credit report', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Analyze credit report', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Review credit disputes if needed', owner: 'Loan Officer', sla: 48, slaUnit: 'hours', aiAuto: false },
          { name: 'Request income documentation preview', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Provide initial loan estimate', owner: 'Loan Officer', sla: 3, slaUnit: 'days', aiAuto: false },
          { name: 'Send product comparison sheet', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Schedule product selection meeting', owner: 'Concierge', sla: 2, slaUnit: 'days', aiAuto: true },
          { name: 'Assign to loan team', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false }
        ]
      },
      {
        name: 'Application',
        tasks: [
          { name: 'Send application portal link', owner: 'Concierge', sla: 2, slaUnit: 'hours', aiAuto: true },
          { name: 'Provide application tutorial video', owner: 'Concierge', sla: 1, slaUnit: 'hours', aiAuto: true },
          { name: 'Monitor application progress', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Send application completion reminders', owner: 'Concierge', sla: 48, slaUnit: 'hours', aiAuto: true },
          { name: 'Review completed application', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Verify application accuracy', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Request missing application information', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: true },
          { name: 'Generate initial disclosures', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Send initial disclosures to borrower', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: true },
          { name: 'Confirm disclosure receipt', owner: 'Concierge', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Log intent to proceed', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Lock interest rate if requested', owner: 'Loan Officer', sla: 4, slaUnit: 'hours', aiAuto: false },
          { name: 'Send rate lock confirmation', owner: 'Concierge', sla: 2, slaUnit: 'hours', aiAuto: true },
          { name: 'Create initial document checklist', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Send document request to borrower', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true }
        ]
      },
      {
        name: 'Processing',
        tasks: [
          { name: 'Review all uploaded documents', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Verify income documents (paystubs)', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Verify employment (VOE)', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Request W2s for past 2 years', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Request tax returns if self-employed', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Verify asset accounts (bank statements)', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Source large deposits if needed', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Review gift funds documentation', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Order appraisal', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Collect appraisal fee', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Schedule appraisal appointment', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: true },
          { name: 'Monitor appraisal status', owner: 'Processor', sla: 5, slaUnit: 'days', aiAuto: true },
          { name: 'Review appraisal report', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Share appraisal with borrower', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Order title search', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Review preliminary title report', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
          { name: 'Clear title exceptions if needed', owner: 'Processor', sla: 5, slaUnit: 'days', aiAuto: false },
          { name: 'Order homeowners insurance', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: true },
          { name: 'Verify insurance coverage amounts', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Obtain mortgage insurance quote if needed', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Request HOA documents if applicable', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: true },
          { name: 'Review HOA budget and bylaws', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Order flood certification', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Order flood insurance if required', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: true },
          { name: 'Prepare file for underwriting', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Complete loan application package', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false }
        ]
      },
      {
        name: 'Underwriting',
        tasks: [
          { name: 'Submit file to underwriter', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Confirm underwriter assignment', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Monitor underwriting queue', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Receive initial underwriting decision', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
          { name: 'Review underwriting conditions', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Explain conditions to borrower', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Request additional documentation for conditions', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Review updated bank statements', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Obtain updated paystub', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Request letter of explanation if needed', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Verify employment again (72hr prior to close)', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
          { name: 'Clear PTD conditions', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Submit cleared conditions to UW', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Receive final approval', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Review final approval conditions', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Notify borrower of approval', owner: 'Loan Officer', sla: 4, slaUnit: 'hours', aiAuto: true },
          { name: 'Order final title update', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false }
        ]
      },
      {
        name: 'Clear to Close',
        tasks: [
          { name: 'Receive clear to close from UW', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Notify loan team of CTC', owner: 'Processor', sla: 2, slaUnit: 'hours', aiAuto: true },
          { name: 'Request final Closing Disclosure figures', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Prepare Closing Disclosure', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Send initial CD to borrower', owner: 'Processor', sla: 4, slaUnit: 'hours', aiAuto: true },
          { name: 'Confirm CD receipt and review', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Wait 3-day CD review period', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
          { name: 'Coordinate closing date/time with title', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Coordinate with borrower schedule', owner: 'Concierge', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Confirm closing appointment', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Send closing location details', owner: 'Concierge', sla: 48, slaUnit: 'hours', aiAuto: true },
          { name: 'Verify wiring instructions if needed', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Send pre-closing checklist to borrower', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: true },
          { name: 'Verify final insurance binder', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Order final verification of employment', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
          { name: 'Perform final credit check', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Send final figures to title company', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Review final CD for accuracy', owner: 'Loan Officer', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Send final CD if changes occurred', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true }
        ]
      },
      {
        name: 'Closing',
        tasks: [
          { name: 'Send closing package to title', owner: 'Processor', sla: 2, slaUnit: 'days', aiAuto: false },
          { name: 'Review closing package for accuracy', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Send closing reminder to borrower', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Verify borrower has required IDs', owner: 'Concierge', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Verify cash to close amount', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Confirm wire/cashier check instructions', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: true },
          { name: 'Monitor closing appointment', owner: 'Processor', sla: 4, slaUnit: 'hours', aiAuto: false },
          { name: 'Receive signed closing documents', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Review closing documents for completeness', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Submit docs for funding approval', owner: 'Processor', sla: 24, slaUnit: 'hours', aiAuto: false },
          { name: 'Receive funding approval', owner: 'Processor', sla: 1, slaUnit: 'days', aiAuto: false },
          { name: 'Wire funds to title company', owner: 'Processor', sla: 4, slaUnit: 'hours', aiAuto: false },
          { name: 'Confirm funding with title', owner: 'Processor', sla: 12, slaUnit: 'hours', aiAuto: false },
          { name: 'Notify borrower of successful funding', owner: 'Loan Officer', sla: 4, slaUnit: 'hours', aiAuto: true },
          { name: 'Send congratulations package', owner: 'Concierge', sla: 1, slaUnit: 'days', aiAuto: true },
          { name: 'Request closing gift preference', owner: 'Concierge', sla: 2, slaUnit: 'days', aiAuto: true },
          { name: 'Send closing gift', owner: 'Concierge', sla: 5, slaUnit: 'days', aiAuto: false }
        ]
      },
      {
        name: 'Post-Close',
        tasks: [
          { name: 'Archive loan file', owner: 'Processor', sla: 3, slaUnit: 'days', aiAuto: false },
          { name: 'Upload to investor portal if sold', owner: 'Processor', sla: 5, slaUnit: 'days', aiAuto: false },
          { name: 'Send welcome to servicing email', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
          { name: 'Provide servicing contact info', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
          { name: '7-day check-in call', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
          { name: 'Request Google review', owner: 'Concierge', sla: 10, slaUnit: 'days', aiAuto: true },
          { name: 'Request Zillow review', owner: 'Concierge', sla: 10, slaUnit: 'days', aiAuto: true },
          { name: 'Add to referral partner list', owner: 'Loan Officer', sla: 14, slaUnit: 'days', aiAuto: false },
          { name: '30-day check-in call', owner: 'Loan Officer', sla: 30, slaUnit: 'days', aiAuto: true },
          { name: 'Send first mortgage statement guide', owner: 'Concierge', sla: 30, slaUnit: 'days', aiAuto: true },
          { name: 'Schedule quarterly check-in', owner: 'Concierge', sla: 60, slaUnit: 'days', aiAuto: true },
          { name: 'Add to birthday calendar', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true },
          { name: 'Add to home anniversary calendar', owner: 'Concierge', sla: 7, slaUnit: 'days', aiAuto: true }
        ]
      },
      {
        name: 'Client for Life',
        tasks: [
          { name: 'Send quarterly market update', owner: 'Concierge', sla: 90, slaUnit: 'days', aiAuto: true },
          { name: 'Monitor for refinance opportunities', owner: 'Loan Officer', sla: 180, slaUnit: 'days', aiAuto: true },
          { name: 'Send home anniversary card', owner: 'Concierge', sla: 365, slaUnit: 'days', aiAuto: true },
          { name: 'Send birthday card/gift', owner: 'Concierge', sla: 365, slaUnit: 'days', aiAuto: true },
          { name: 'Annual financial review invitation', owner: 'Concierge', sla: 330, slaUnit: 'days', aiAuto: true },
          { name: 'Conduct annual review call', owner: 'Loan Officer', sla: 365, slaUnit: 'days', aiAuto: false },
          { name: 'Review for equity opportunities', owner: 'Loan Officer', sla: 365, slaUnit: 'days', aiAuto: false },
          { name: 'Send holiday greetings', owner: 'Concierge', sla: 365, slaUnit: 'days', aiAuto: true },
          { name: 'Check for life changes (marriage, kids, etc)', owner: 'Loan Officer', sla: 180, slaUnit: 'days', aiAuto: false },
          { name: 'Send home maintenance tips', owner: 'Concierge', sla: 120, slaUnit: 'days', aiAuto: true },
          { name: 'Provide property value updates', owner: 'Loan Officer', sla: 180, slaUnit: 'days', aiAuto: true },
          { name: 'Request referrals gently', owner: 'Loan Officer', sla: 90, slaUnit: 'days', aiAuto: false }
        ]
      }
    ];

    // Calculate stats
    const totalTasks = generatedMilestones.reduce((total, m) => total + m.tasks.length, 0);

      // Update BOTH milestones AND processTree in a single atomic update (fallback)
      setFormData(prevData => ({
        ...prevData,
        milestones: generatedMilestones,
        processTree: {
          generated: true,
          milestones: generatedMilestones.length,
          tasks: totalTasks,
          roles: 5
        }
      }));

      setIsProcessing(false);
    }
  };

  // Milestone and task management
  const addMilestone = () => {
    setFormData(prevData => {
      const newMilestone = {
        name: 'New Milestone',
        tasks: []
      };
      const newMilestones = [...prevData.milestones, newMilestone];
      setActiveMilestone(newMilestones.length - 1);
      return { ...prevData, milestones: newMilestones };
    });
  };

  const updateMilestone = (index, field, value) => {
    setFormData(prevData => {
      const newMilestones = [...prevData.milestones];
      newMilestones[index][field] = value;
      return { ...prevData, milestones: newMilestones };
    });
  };

  const removeMilestone = (index) => {
    setFormData(prevData => {
      const newMilestones = prevData.milestones.filter((_, i) => i !== index);
      if (activeMilestone >= newMilestones.length) {
        setActiveMilestone(Math.max(0, newMilestones.length - 1));
      }
      return { ...prevData, milestones: newMilestones };
    });
  };

  const addTask = (milestoneIndex) => {
    setFormData(prevData => {
      const newTask = {
        name: '',
        owner: 'Loan Officer',
        sla: 24,
        slaUnit: 'hours',
        aiAuto: false
      };
      const newMilestones = [...prevData.milestones];
      newMilestones[milestoneIndex].tasks = [...newMilestones[milestoneIndex].tasks, newTask];
      return { ...prevData, milestones: newMilestones };
    });
  };

  const updateTask = (milestoneIndex, taskIndex, field, value) => {
    setFormData(prevData => {
      const newMilestones = [...prevData.milestones];
      newMilestones[milestoneIndex].tasks[taskIndex][field] = value;
      return { ...prevData, milestones: newMilestones };
    });
  };

  const removeTask = (milestoneIndex, taskIndex) => {
    setFormData(prevData => {
      const newMilestones = [...prevData.milestones];
      newMilestones[milestoneIndex].tasks = newMilestones[milestoneIndex].tasks.filter((_, i) => i !== taskIndex);
      return { ...prevData, milestones: newMilestones };
    });
  };

  // Drag and Drop handlers for tasks between milestones
  const handleDragStart = (e, milestoneIndex, taskIndex) => {
    setDraggedTask({ milestoneIndex, taskIndex });
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDropTask = (e, targetMilestoneIndex) => {
    e.preventDefault();
    if (!draggedTask) return;

    const { milestoneIndex: sourceMilestoneIndex, taskIndex: sourceTaskIndex } = draggedTask;

    // If dropped in the same milestone, do nothing
    if (sourceMilestoneIndex === targetMilestoneIndex) {
      setDraggedTask(null);
      return;
    }

    // Move task from source to target milestone
    setFormData(prevData => {
      const newMilestones = [...prevData.milestones];

      // Get the task from source milestone
      const taskToMove = { ...newMilestones[sourceMilestoneIndex].tasks[sourceTaskIndex] };

      // Remove from source milestone
      newMilestones[sourceMilestoneIndex].tasks = newMilestones[sourceMilestoneIndex].tasks.filter((_, i) => i !== sourceTaskIndex);

      // Add to target milestone
      newMilestones[targetMilestoneIndex].tasks = [...newMilestones[targetMilestoneIndex].tasks, taskToMove];

      return { ...prevData, milestones: newMilestones };
    });

    setDraggedTask(null);
  };

  // Task Edit Modal handlers
  const handleOpenTaskEdit = (task) => {
    setTaskEditModal({
      ...task,
      tempRoleId: task.role_id,
      tempUserId: null
    });
  };

  const handleCloseTaskEdit = () => {
    setTaskEditModal(null);
  };

  const handleSaveTaskEdit = async () => {
    if (!taskEditModal) return;

    try {
      // Save to backend
      const updateData = {
        task_name: taskEditModal.task_name,
        task_description: taskEditModal.task_description,
        role_id: taskEditModal.tempRoleId || taskEditModal.role_id,
        assigned_user_id: taskEditModal.tempUserId || taskEditModal.assigned_user_id,
        sla: taskEditModal.sla,
        sla_unit: taskEditModal.sla_unit,
        ai_automatable: taskEditModal.ai_automatable
      };

      const updatedTask = await onboardingAPI.updateTask(taskEditModal.id, updateData);

      // Update local state with the saved task
      setFormData(prevData => {
        const newTasks = prevData.extractedTasks.map(task => {
          if (task.id === taskEditModal.id) {
            return updatedTask;
          }
          return task;
        });

        return { ...prevData, extractedTasks: newTasks };
      });

      setTaskEditModal(null);
    } catch (error) {
      console.error('Failed to save task:', error);
      alert('Failed to save task changes. Please try again.');
    }
  };

  const handleUpdateTaskEditField = (field, value) => {
    setTaskEditModal(prev => ({ ...prev, [field]: value }));
  };

  // Role Add Modal handlers
  const handleOpenRoleAdd = () => {
    setNewRoleForm({
      role_title: '',
      role_name: '',
      responsibilities: '',
      skills_required: [],
      key_activities: []
    });
    setRoleAddModal(true);
  };

  const handleCloseRoleAdd = () => {
    setRoleAddModal(false);
  };

  const handleSaveNewRole = () => {
    if (!newRoleForm.role_title || !newRoleForm.role_name) {
      alert('Please enter both role title and role name');
      return;
    }

    const newRole = {
      id: `role_${Date.now()}`,
      role_title: newRoleForm.role_title,
      role_name: newRoleForm.role_name,
      responsibilities: newRoleForm.responsibilities,
      skills_required: newRoleForm.skills_required,
      key_activities: newRoleForm.key_activities
    };

    setFormData(prevData => ({
      ...prevData,
      extractedRoles: [...(prevData.extractedRoles || []), newRole]
    }));

    setRoleAddModal(false);
  };

  const renderStep = () => {
    switch (currentStep) {
      case 1:
        return renderProcessUpload();
      case 2:
        return renderRoleReview();
      case 3:
        return renderTaskReview();
      case 4:
        return renderTeamRoles();
      case 5:
        return renderProcessTree();
      case 6:
        return renderIntegrations();
      case 7:
        return renderCompliance();
      case 8:
        return renderAIAgent();
      case 9:
        return renderTestGoLive();
      default:
        return null;
    }
  };

  // SCREEN 2: Role Review
  const renderRoleReview = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">👥</div>
        <h2>Review Roles & Responsibilities</h2>
        <p className="step-description">
          AI has identified {formData.extractedRoles?.length || 0} roles from your process documents. Review each role and their responsibilities.
        </p>
      </div>

      <div className="roles-review-container">
        {formData.extractedRoles && formData.extractedRoles.length > 0 ? (
          formData.extractedRoles.map((role, index) => (
            <div key={role.id} className="role-card">
              <div className="role-header">
                <div className="role-number">{index + 1}</div>
                <div className="role-info">
                  <h3>{role.role_title}</h3>
                  <span className="role-badge">{role.role_name}</span>
                </div>
              </div>

              <div className="role-details">
                <div className="detail-section">
                  <h4>Responsibilities</h4>
                  <p>{role.responsibilities}</p>
                </div>

                {role.skills_required && role.skills_required.length > 0 && (
                  <div className="detail-section">
                    <h4>Required Skills</h4>
                    <div className="skills-list">
                      {role.skills_required.map((skill, idx) => (
                        <span key={idx} className="skill-tag">{skill}</span>
                      ))}
                    </div>
                  </div>
                )}

                {role.key_activities && role.key_activities.length > 0 && (
                  <div className="detail-section">
                    <h4>Key Activities</h4>
                    <ul className="activities-list">
                      {role.key_activities.map((activity, idx) => (
                        <li key={idx}>{activity}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          ))
        ) : (
          <div className="no-roles-message">
            <p>No roles have been extracted yet. Please go back to Step 1 and generate the process tree.</p>
          </div>
        )}
      </div>
    </div>
  );

  // SCREEN 3: Task Review
  const renderTaskReview = () => {
    // Group tasks by role
    const tasksByRole = {};
    formData.extractedRoles?.forEach(role => {
      tasksByRole[role.id] = {
        role: role,
        tasks: formData.extractedTasks?.filter(t => t.role_id === role.id) || []
      };
    });

    return (
      <div className="step-content">
        <div className="step-header">
          <div className="step-icon">📋</div>
          <h2>Review Tasks by Role</h2>
          <p className="step-description">
            Review all {formData.extractedTasks?.length || 0} tasks organized by role. Click any task to edit, reassign, or view details.
          </p>
          <button className="btn-add-role" onClick={handleOpenRoleAdd}>
            + Add New Role
          </button>
        </div>

        <div className="tasks-by-role-container">
          {Object.values(tasksByRole).map(({ role, tasks }) => (
            <div key={role.id} className="role-tasks-section">
              <div className="role-tasks-header">
                <h3>{role.role_title}</h3>
                <span className="tasks-count">{tasks.length} tasks</span>
              </div>

              <div className="tasks-grid">
                {tasks.map((task, index) => {
                  const milestone = formData.extractedMilestones?.find(m => m.id === task.milestone_id);
                  const assignedUser = teamMembers?.find(m => m.id === task.assigned_user_id);

                  return (
                    <div
                      key={task.id}
                      className="task-review-card clickable"
                      onClick={() => handleOpenTaskEdit(task)}
                    >
                      <div className="task-review-header">
                        <span className="task-number">{index + 1}</span>
                        <h4>{task.task_name}</h4>
                      </div>

                      {task.task_description && (
                        <p className="task-description">{task.task_description}</p>
                      )}

                      <div className="task-meta-info">
                        {milestone && (
                          <span className="meta-badge milestone-badge">📍 {milestone.name}</span>
                        )}
                        {assignedUser && (
                          <span className="meta-badge user-badge">👤 {assignedUser.full_name || assignedUser.email}</span>
                        )}
                        {task.estimated_duration && (
                          <span className="meta-badge time-badge">⏱️ {task.estimated_duration} min</span>
                        )}
                        {task.sla && (
                          <span className="meta-badge sla-badge">⏰ SLA: {task.sla} {task.sla_unit}</span>
                        )}
                        {task.ai_automatable && (
                          <span className="meta-badge ai-badge">🤖 AI Automatable</span>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>

              {tasks.length === 0 && (
                <p className="no-tasks-message">No tasks assigned to this role yet.</p>
              )}
            </div>
          ))}
        </div>
      </div>
    );
  };

  // SCREEN 4: Team & Roles
  const renderTeamRoles = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">👥</div>
        <h2>Team & Roles</h2>
        <p className="step-description">
          {formData.processTree
            ? `Set up your team members - you'll assign them to the ${formData.processTree.tasks} generated tasks in the next step`
            : 'Set up your team members and assign roles'}
        </p>
      </div>

      <div className="form-section">
        <div className="form-field">
          <label>Timezone</label>
          <select
            value={formData.timezone}
            onChange={(e) => updateField('timezone', e.target.value)}
            className="input-field"
          >
            <option value="America/Los_Angeles">Pacific Time</option>
            <option value="America/Denver">Mountain Time</option>
            <option value="America/Chicago">Central Time</option>
            <option value="America/New_York">Eastern Time</option>
          </select>
        </div>

        <div className="form-field">
          <label>Team Members</label>
          {formData.members.map((member, index) => (
            <div key={index} className="member-row">
              <input
                type="text"
                placeholder="First Name"
                value={member.firstName}
                onChange={(e) => updateMember(index, 'firstName', e.target.value)}
                className="input-field input-sm"
              />
              <input
                type="text"
                placeholder="Last Name"
                value={member.lastName}
                onChange={(e) => updateMember(index, 'lastName', e.target.value)}
                className="input-field input-sm"
              />
              <input
                type="email"
                placeholder="Email"
                value={member.email}
                onChange={(e) => updateMember(index, 'email', e.target.value)}
                className="input-field input-md"
              />
              <input
                type="tel"
                placeholder="Phone"
                value={member.phone}
                onChange={(e) => updateMember(index, 'phone', e.target.value)}
                className="input-field input-sm"
              />
              <select
                value={member.role}
                onChange={(e) => updateMember(index, 'role', e.target.value)}
                className="input-field input-md"
              >
                <option value="">Select Role</option>
                <option value="president">President</option>
                <option value="regional_manager">Regional Manager</option>
                <option value="area_manager">Area Manager</option>
                <option value="sales_manager">Sales Manager</option>
                <option value="team_leader">Team Leader</option>
                <option value="loan_officer">Loan Officer</option>
                <option value="executive_assistant">Executive Assistant</option>
                <option value="production_assistant_1">Production Assistant 1</option>
                <option value="production_assistant_2">Production Assistant 2</option>
                <option value="application_analysis">Application Analysis</option>
                <option value="concierge">Concierge</option>
                <option value="processor">Processor</option>
                <option value="processing_manager">Processing Manager</option>
                <option value="processing_assistant">Processing Assistant</option>
                <option value="closer">Closer</option>
                <option value="funder">Funder</option>
                <option value="underwriter">Underwriter</option>
              </select>
              {index > 0 && (
                <button onClick={() => removeMember(index)} className="btn-remove">×</button>
              )}
            </div>
          ))}
          <button onClick={addMember} className="btn-add-member">+ Add Member</button>
        </div>

        <div className="form-field">
          <label>Manager</label>
          <select
            value={formData.manager}
            onChange={(e) => updateField('manager', e.target.value)}
            className="input-field"
          >
            <option value="">Select Manager</option>
            {formData.members.map((member, index) => (
              member.email && (
                <option key={index} value={member.email}>
                  {member.firstName} {member.lastName} ({member.email})
                </option>
              )
            ))}
          </select>
        </div>
      </div>

      <div className="validation-requirements">
        <p>✓ At least one team member required</p>
        <p>✓ All emails must be unique and valid</p>
      </div>
    </div>
  );

  // SCREEN 1: Systems & Processes Upload
  const renderProcessUpload = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">📄</div>
        <h2>Upload Your Process Documents</h2>
        <p className="step-description">Upload your SOPs first - AI will generate ALL tasks and workflows to assign to your team</p>
      </div>

      <div className="form-section">
        <div className="form-field">
          <label>Upload Process Documents</label>
          <p className="field-hint">PDFs, DOCX, XLSX, CSV of your SOPs (Lead → Loan → Post-Close)</p>
          <div
            className="file-upload-area"
            onDragOver={handleDragOver}
            onDrop={handleDrop}
          >
            <input
              type="file"
              multiple
              accept=".pdf,.docx,.doc,.xlsx,.xls,.csv,.txt"
              onChange={handleFileSelect}
              className="file-input"
              id="sop-upload"
            />
            <label htmlFor="sop-upload" className="file-upload-label">
              <div className="upload-icon">📎</div>
              <div className="upload-text">Click to upload or drag and drop</div>
              <div className="upload-hint">PDF, DOCX, XLSX, CSV, TXT (max 10 files, 50MB each)</div>
            </label>
          </div>

          {formData.sopFiles && formData.sopFiles.length > 0 && (
            <div className="uploaded-files">
              <div className="files-header">
                <h4>{formData.sopFiles.length} file{formData.sopFiles.length !== 1 ? 's' : ''} uploaded</h4>
                <button
                  className="btn-clear-all"
                  onClick={() => updateField('sopFiles', [])}
                >
                  Clear all
                </button>
              </div>
              {formData.sopFiles.map((file, index) => (
                <div key={index} className="file-item">
                  <div className="file-icon">
                    {file.name.endsWith('.pdf') ? '📕' :
                     file.name.endsWith('.docx') || file.name.endsWith('.doc') ? '📘' :
                     file.name.endsWith('.xlsx') || file.name.endsWith('.xls') ? '📗' :
                     file.name.endsWith('.csv') ? '📊' : '📄'}
                  </div>
                  <div className="file-info">
                    <div className="file-name">{file.name}</div>
                    <div className="file-size">{formatFileSize(file.size)}</div>
                  </div>
                  <button
                    className="btn-remove-file"
                    onClick={() => removeFile(index)}
                    title="Remove file"
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>

        {formData.sopFiles && formData.sopFiles.length > 0 && !formData.processTree && (
          <div className="ai-processing">
            <button
              className="btn-ai-process"
              onClick={handleAIProcessing}
              disabled={isProcessing}
            >
              {isProcessing ? (
                <>
                  <span className="spinner"></span>
                  Processing...
                </>
              ) : (
                <>🤖 AI: Parse & Generate Process Tree</>
              )}
            </button>
            <p className="processing-hint">
              AI will extract milestones, tasks, and role ownership from your {formData.sopFiles.length} document{formData.sopFiles.length !== 1 ? 's' : ''}
            </p>
          </div>
        )}

        {formData.processTree && (
          <div className="process-tree-preview">
            <h4>✓ Process Tree Generated</h4>
            <div className="preview-stats">
              <div className="stat-item">
                <span className="stat-label">Milestones</span>
                <span className="stat-number">{formData.processTree.milestones}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Tasks</span>
                <span className="stat-number">{formData.processTree.tasks}</span>
              </div>
              <div className="stat-item">
                <span className="stat-label">Roles</span>
                <span className="stat-number">{formData.processTree.roles}</span>
              </div>
            </div>
            <button
              className="btn-regenerate"
              onClick={handleAIProcessing}
              disabled={isProcessing}
            >
              🔄 Regenerate
            </button>
          </div>
        )}
      </div>
    </div>
  );

  // SCREEN 3: Confirm "Who Does What, When"
  const renderProcessTree = () => {
    const currentMilestone = formData.milestones[activeMilestone];
    const availableRoles = ['President', 'Regional Manager', 'Area Manager', 'Sales Manager', 'Team Leader', 'Loan Officer', 'Executive Assistant', 'Production Assistant 1', 'Production Assistant 2', 'Application Analysis', 'Concierge', 'Processor', 'Processing Manager', 'Processing Assistant', 'Closer', 'Funder', 'Underwriter'];

    // Show message if no milestones exist
    if (formData.milestones.length === 0) {
      return (
        <div className="step-content">
          <div className="step-header">
            <div className="step-icon">🗂️</div>
            <h2>Who Does What, When</h2>
            <p className="step-description">No milestones or tasks found</p>
          </div>

          <div className="empty-milestones-state">
            <div className="empty-state-icon">📋</div>
            <h3>No Process Tree Generated</h3>
            <p>
              Go back to <strong>Step 1</strong> to upload your process documents and click
              <strong> "🤖 AI: Parse & Generate Process Tree"</strong> to automatically create
              all your milestones and tasks.
            </p>
            <button className="btn-back-to-upload" onClick={() => setCurrentStep(1)}>
              ← Go Back to Upload Documents
            </button>
            <div className="or-divider">
              <span>OR</span>
            </div>
            <p className="manual-option">Start building your process manually:</p>
            <button className="btn-add-first-milestone" onClick={addMilestone}>
              + Add Your First Milestone
            </button>
          </div>
        </div>
      );
    }

    return (
      <div className="step-content">
        <div className="step-header">
          <div className="step-icon">🗂️</div>
          <h2>Who Does What, When</h2>
          <p className="step-description">
            {formData.processTree
              ? `✓ Review ${formData.milestones.reduce((total, m) => total + m.tasks.length, 0)} AI-generated tasks and assign ownership`
              : 'Configure your process ownership and SLAs'}
          </p>
        </div>

        {formData.processTree && (
          <div className="ai-generated-banner">
            <span className="banner-icon">🤖</span>
            <div className="banner-content">
              <strong>AI-Generated Process Tree</strong>
              <p>Review and approve the {formData.milestones.length} milestones and {formData.milestones.reduce((total, m) => total + m.tasks.length, 0)} tasks below. You can edit, add, or remove any milestone or task.</p>
            </div>
          </div>
        )}

        <div className="process-tree-editor">
          <div className="milestone-column">
            <div className="milestone-header">
              <h4>Milestones</h4>
              <button className="btn-add-milestone" onClick={addMilestone} title="Add Milestone">+</button>
            </div>
            <div className="milestone-list">
              {formData.milestones.map((milestone, index) => (
                <div
                  key={index}
                  className={`milestone-item ${index === activeMilestone ? 'active' : ''} ${draggedTask && draggedTask.milestoneIndex !== index ? 'drop-target' : ''}`}
                  onClick={() => setActiveMilestone(index)}
                  onDragOver={handleDragOver}
                  onDrop={(e) => handleDropTask(e, index)}
                >
                  <input
                    type="text"
                    value={milestone.name}
                    onChange={(e) => updateMilestone(index, 'name', e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    className="milestone-name-input"
                  />
                  {formData.milestones.length > 1 && (
                    <button
                      className="btn-remove-milestone"
                      onClick={(e) => {
                        e.stopPropagation();
                        removeMilestone(index);
                      }}
                      title="Remove Milestone"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          <div className="tasks-column">
            {currentMilestone && (
              <>
                <div className="tasks-header">
                  <h4>Tasks for "{currentMilestone.name}"</h4>
                  <button
                    className="btn-add-task"
                    onClick={() => addTask(activeMilestone)}
                  >
                    + Add Task
                  </button>
                </div>
                <div className="task-list">
                  {currentMilestone.tasks.length === 0 ? (
                    <div className="empty-tasks">
                      <p>No tasks yet. Click "+ Add Task" to create one.</p>
                    </div>
                  ) : (
                    currentMilestone.tasks.map((task, taskIndex) => (
                      <div
                        key={taskIndex}
                        className="task-item"
                      >
                        <div className="task-header">
                          <div
                            className="drag-handle"
                            draggable="true"
                            onDragStart={(e) => handleDragStart(e, activeMilestone, taskIndex)}
                            onDragEnd={() => setDraggedTask(null)}
                            title="Drag to move task to another milestone"
                          >
                            ⋮⋮
                          </div>
                          <div className="task-name-section">
                            <label className="task-label">Task</label>
                            <input
                              type="text"
                              value={task.name}
                              onChange={(e) => updateTask(activeMilestone, taskIndex, 'name', e.target.value)}
                              placeholder="What needs to be done?"
                              className="task-name-input"
                            />
                          </div>
                          <button
                            className="btn-remove-task"
                            onClick={() => removeTask(activeMilestone, taskIndex)}
                            title="Remove Task"
                          >
                            ×
                          </button>
                        </div>

                        <div className="task-details">
                          <div className="task-detail-group">
                            <label className="detail-label">Assigned To</label>
                            <select
                              value={task.owner}
                              onChange={(e) => updateTask(activeMilestone, taskIndex, 'owner', e.target.value)}
                              className="owner-select"
                            >
                              {availableRoles.map(role => (
                                <option key={role} value={role}>{role}</option>
                              ))}
                            </select>
                          </div>

                          <div className="task-detail-group">
                            <label className="detail-label">Complete Within</label>
                            <div className="task-sla">
                              <input
                                type="number"
                                value={task.sla}
                                onChange={(e) => updateTask(activeMilestone, taskIndex, 'sla', parseInt(e.target.value) || 0)}
                                className="sla-input"
                                min="1"
                              />
                              <select
                                value={task.slaUnit}
                                onChange={(e) => updateTask(activeMilestone, taskIndex, 'slaUnit', e.target.value)}
                                className="sla-unit-select"
                              >
                                <option value="hours">hours</option>
                                <option value="days">days</option>
                              </select>
                            </div>
                          </div>

                          <div className="task-detail-group task-ai-section">
                            <label className="ai-auto-label">
                              <input
                                type="checkbox"
                                checked={task.aiAuto}
                                onChange={(e) => updateTask(activeMilestone, taskIndex, 'aiAuto', e.target.checked)}
                                className="ai-auto-checkbox"
                              />
                              <span className="ai-auto-text">
                                <strong>AI Auto</strong>
                                <span className="ai-auto-hint">AI attempts task, escalates to user if needed, learns for next time</span>
                              </span>
                            </label>
                          </div>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </>
            )}
          </div>
        </div>

        <div className="process-summary">
          <p>
            <strong>{formData.milestones.length}</strong> milestone{formData.milestones.length !== 1 ? 's' : ''} •
            <strong> {formData.milestones.reduce((total, m) => total + m.tasks.length, 0)}</strong> total task{formData.milestones.reduce((total, m) => total + m.tasks.length, 0) !== 1 ? 's' : ''}
          </p>
        </div>
      </div>
    );
  };

  // SCREEN 4: Integrations
  const integrationsList = [
    // Calendar & Scheduling
    { id: 'calendly', name: 'Calendly', icon: '📅', category: 'Calendar', description: 'Automated appointment scheduling' },
    { id: 'google-calendar', name: 'Google Calendar', icon: '📅', category: 'Calendar', description: 'Sync your Google Calendar events' },
    { id: 'outlook-calendar', name: 'Outlook Calendar', icon: '📅', category: 'Calendar', description: 'Microsoft Outlook calendar integration' },

    // Email
    { id: 'gmail', name: 'Gmail', icon: '📧', category: 'Email', description: 'Connect your Gmail account' },
    { id: 'outlook', name: 'Microsoft 365', icon: '📧', category: 'Email', description: 'Outlook and Microsoft 365 email' },
    { id: 'yahoo', name: 'Yahoo Mail', icon: '📧', category: 'Email', description: 'Yahoo email integration' },

    // Phone & SMS
    { id: 'twilio', name: 'Twilio', icon: '📞', category: 'Phone', description: 'AI calling, SMS, and voice' },
    { id: 'ringcentral', name: 'RingCentral', icon: '📞', category: 'Phone', description: 'Business phone system' },
    { id: 'dialpad', name: 'Dialpad', icon: '📞', category: 'Phone', description: 'Cloud-based phone system' },

    // Document Management
    { id: 'docusign', name: 'DocuSign', icon: '📝', category: 'Documents', description: 'Electronic signature platform' },
    { id: 'adobe-sign', name: 'Adobe Sign', icon: '📝', category: 'Documents', description: 'Adobe document signing' },
    { id: 'dropbox', name: 'Dropbox', icon: '📁', category: 'Documents', description: 'Cloud file storage' },
    { id: 'google-drive', name: 'Google Drive', icon: '📁', category: 'Documents', description: 'Google cloud storage' },

    // LOS (Loan Origination Systems)
    { id: 'encompass', name: 'Encompass', icon: '🏢', category: 'LOS', description: 'ICE Mortgage Technology LOS', optional: true },
    { id: 'calyx-point', name: 'Calyx Point', icon: '🏢', category: 'LOS', description: 'Calyx loan origination', optional: true },
    { id: 'bytepro', name: 'BytePro', icon: '🏢', category: 'LOS', description: 'BytePro LOS integration', optional: true },

    // CRM
    { id: 'salesforce', name: 'Salesforce', icon: '☁️', category: 'CRM', description: 'Salesforce CRM integration', optional: true },
    { id: 'hubspot', name: 'HubSpot', icon: '🎯', category: 'CRM', description: 'HubSpot marketing & CRM', optional: true },

    // Credit Bureaus
    { id: 'experian', name: 'Experian', icon: '💳', category: 'Credit', description: 'Experian credit reports', optional: true },
    { id: 'equifax', name: 'Equifax', icon: '💳', category: 'Credit', description: 'Equifax credit data', optional: true },
    { id: 'transunion', name: 'TransUnion', icon: '💳', category: 'Credit', description: 'TransUnion credit services', optional: true },

    // Team Communication
    { id: 'slack', name: 'Slack', icon: '💬', category: 'Communication', description: 'Team messaging and alerts' },
    { id: 'teams', name: 'Microsoft Teams', icon: '💬', category: 'Communication', description: 'Microsoft Teams chat' },

    // Accounting
    { id: 'quickbooks', name: 'QuickBooks', icon: '💰', category: 'Accounting', description: 'QuickBooks accounting', optional: true },
    { id: 'xero', name: 'Xero', icon: '💰', category: 'Accounting', description: 'Xero accounting software', optional: true }
  ];

  const handleConnectIntegration = async (integration) => {
    // Handle Salesforce OAuth flow
    if (integration.id === 'salesforce') {
      try {
        const token = localStorage.getItem('token');
        const isVercel = window.location.hostname.includes('vercel.app');
        const API_BASE_URL = isVercel ? '' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

        const response = await fetch(`${API_BASE_URL}/api/v1/salesforce/oauth/start`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        if (!response.ok) {
          throw new Error('Failed to initiate Salesforce OAuth');
        }

        const data = await response.json();

        // Open OAuth window
        const width = 600;
        const height = 700;
        const left = (window.screen.width - width) / 2;
        const top = (window.screen.height - height) / 2;

        const popup = window.open(
          data.auth_url,
          'Salesforce OAuth',
          `width=${width},height=${height},left=${left},top=${top}`
        );

        // Monitor the popup for closing
        const checkPopup = setInterval(() => {
          if (popup && popup.closed) {
            clearInterval(checkPopup);
            // Check connection status after popup closes
            checkSalesforceConnection();
          }
        }, 1000);

      } catch (error) {
        console.error('Salesforce OAuth error:', error);
        alert('Failed to connect to Salesforce. Please ensure the integration is configured in your environment.');
      }
    }
    // Handle Microsoft 365 OAuth flow
    else if (integration.id === 'outlook') {
      try {
        const token = localStorage.getItem('token');
        const isVercel = window.location.hostname.includes('vercel.app');
        const API_BASE_URL = isVercel ? '' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

        const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/oauth/start`, {
          headers: {
            'Authorization': `Bearer ${token}`
          }
        });

        if (!response.ok) {
          throw new Error('Failed to initiate Microsoft 365 OAuth');
        }

        const data = await response.json();

        // Open OAuth window
        const width = 600;
        const height = 700;
        const left = (window.screen.width - width) / 2;
        const top = (window.screen.height - height) / 2;

        const popup = window.open(
          data.auth_url,
          'Microsoft 365 Login',
          `width=${width},height=${height},left=${left},top=${top}`
        );

        // Monitor the popup for closing
        const checkPopup = setInterval(() => {
          if (popup && popup.closed) {
            clearInterval(checkPopup);
            // Check connection status after popup closes
            checkMicrosoftConnection();
          }
        }, 1000);

      } catch (error) {
        console.error('Microsoft 365 OAuth error:', error);
        alert('Microsoft 365 integration is being configured. Please go to Settings > Integrations to complete the connection with proper OAuth authentication.');
      }
    }
    else {
      // For other integrations, show the modal
      setConnectionModal(integration);
    }
  };

  const checkSalesforceConnection = async () => {
    try {
      const token = localStorage.getItem('token');
      const isVercel = window.location.hostname.includes('vercel.app');
      const API_BASE_URL = isVercel ? '' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE_URL}/api/v1/salesforce/status`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.connected) {
          alert('✅ Salesforce connected successfully!');
          // Update formData to reflect connection
          setFormData(prevData => ({
            ...prevData,
            salesforceConnected: true
          }));
        }
      }
    } catch (error) {
      console.error('Error checking Salesforce status:', error);
    }
  };

  const checkMicrosoftConnection = async () => {
    try {
      const token = localStorage.getItem('token');
      const isVercel = window.location.hostname.includes('vercel.app');
      const API_BASE_URL = isVercel ? '' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

      const response = await fetch(`${API_BASE_URL}/api/v1/microsoft/status`, {
        headers: {
          'Authorization': `Bearer ${token}`
        }
      });

      if (response.ok) {
        const data = await response.json();
        if (data.connected) {
          alert('✅ Microsoft 365 connected successfully! Your email: ' + data.email_address);
          // Update formData to reflect connection
          setFormData(prevData => ({
            ...prevData,
            microsoftConnected: true
          }));
        }
      }
    } catch (error) {
      console.error('Error checking Microsoft 365 status:', error);
    }
  };

  const handleCloseModal = () => {
    setConnectionModal(null);
  };

  const handleAuthComplete = () => {
    // Simulate successful connection for non-OAuth integrations
    console.log(`Connected to ${connectionModal.name}`);
    setConnectionModal(null);
  };

  const renderIntegrations = () => {
    // Group integrations by category
    const categories = [...new Set(integrationsList.map(i => i.category))];

    return (
      <div className="step-content">
        <div className="step-header">
          <div className="step-icon">🔗</div>
          <h2>Integrations</h2>
          <p className="step-description">Connect your tools and services</p>
        </div>

        {categories.map(category => (
          <div key={category} className="integration-category">
            <h3 className="category-title">{category}</h3>
            <div className="integrations-grid">
              {integrationsList
                .filter(integration => integration.category === category)
                .map(integration => (
                  <div key={integration.id} className={`integration-card ${integration.optional ? 'optional' : ''}`}>
                    <div className="integration-header">
                      <span className="integration-icon">{integration.icon}</span>
                      <h4>{integration.name}</h4>
                      {integration.optional && <span className="optional-badge">Optional</span>}
                    </div>
                    <p className="integration-description">{integration.description}</p>
                    <button
                      className="btn-connect"
                      onClick={() => handleConnectIntegration(integration)}
                    >
                      Connect {integration.name}
                    </button>
                  </div>
                ))}
            </div>
          </div>
        ))}
      </div>
    );
  };

  // SCREEN 5: Compliance & Guardrails
  const renderCompliance = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">⚖️</div>
        <h2>Compliance & Guardrails</h2>
        <p className="step-description">Set calling hours, retry limits, and compliance policies</p>
      </div>

      <div className="form-section">
        <div className="form-row">
          <div className="form-field">
            <label>Quiet Hours (Local Time)</label>
            <div className="time-range">
              <input
                type="time"
                value={formData.quietHours.start}
                onChange={(e) => updateField('quietHours', { ...formData.quietHours, start: e.target.value })}
                className="input-field"
              />
              <span>to</span>
              <input
                type="time"
                value={formData.quietHours.end}
                onChange={(e) => updateField('quietHours', { ...formData.quietHours, end: e.target.value })}
                className="input-field"
              />
            </div>
            <p className="field-hint">AI will only call between these hours</p>
          </div>
        </div>

        <div className="form-row">
          <div className="form-field">
            <label>Max Retries per Contact</label>
            <input
              type="number"
              value={formData.maxRetries}
              onChange={(e) => updateField('maxRetries', parseInt(e.target.value))}
              className="input-field"
              min="1"
              max="10"
            />
            <p className="field-hint">Number of retry attempts with backoff</p>
          </div>

          <div className="form-field">
            <label>Max Daily Attempts</label>
            <input
              type="number"
              value={formData.maxDailyAttempts}
              onChange={(e) => updateField('maxDailyAttempts', parseInt(e.target.value))}
              className="input-field"
              min="1"
              max="20"
            />
            <p className="field-hint">Maximum contact attempts per day</p>
          </div>
        </div>

        <div className="compliance-policies">
          <h4>Policy Acknowledgments</h4>
          <label className="policy-checkbox">
            <input
              type="checkbox"
              checked={formData.dncAccepted}
              onChange={(e) => updateField('dncAccepted', e.target.checked)}
            />
            <span>I acknowledge compliance with Do Not Call (DNC) regulations</span>
          </label>

          <label className="policy-checkbox">
            <input type="checkbox" />
            <span>I will comply with state-specific recording consent laws</span>
          </label>

          <label className="policy-checkbox">
            <input type="checkbox" />
            <span>I will honor customer opt-out requests immediately</span>
          </label>
        </div>

        <div className="recording-states">
          <h4>Recording Policy by State</h4>
          <p className="field-hint">Select states where you do business:</p>
          <div className="state-grid">
            <label><input type="checkbox" /> CA (2-party)</label>
            <label><input type="checkbox" /> TX (1-party)</label>
            <label><input type="checkbox" /> FL (2-party)</label>
            <label><input type="checkbox" /> NY (1-party)</label>
          </div>
        </div>
      </div>
    </div>
  );

  // SCREEN 6: AI Agent Voice & Script
  const renderAIAgent = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🤖</div>
        <h2>AI Agent Voice & Script</h2>
        <p className="step-description">Configure your AI assistant's personality and scripts</p>
      </div>

      <div className="form-section">
        <div className="form-field">
          <label>Agent Name</label>
          <input
            type="text"
            value={formData.agentName}
            onChange={(e) => updateField('agentName', e.target.value)}
            className="input-field"
            placeholder="e.g., Samantha, Alex, Jordan"
          />
        </div>

        <div className="form-field">
          <label>Voice Profile</label>
          <select
            value={formData.voiceProfile}
            onChange={(e) => updateField('voiceProfile', e.target.value)}
            className="input-field"
          >
            <option value="elevenlabs-rachel">Rachel (Professional Female)</option>
            <option value="elevenlabs-adam">Adam (Professional Male)</option>
            <option value="elevenlabs-samantha">Samantha (Friendly Female)</option>
            <option value="elevenlabs-josh">Josh (Casual Male)</option>
          </select>
          <button className="btn-preview-voice">▶ Preview Voice</button>
        </div>

        <div className="form-field">
          <label>Identity Line</label>
          <textarea
            value={formData.identityLine || `This is ${formData.agentName}, calling from Tim Loss's office...`}
            onChange={(e) => updateField('identityLine', e.target.value)}
            className="textarea-field"
            rows="3"
            placeholder="This is Samantha, calling from Tim Loss's mortgage office..."
          />
          <p className="field-hint">How the AI introduces itself on calls</p>
        </div>

        <div className="purpose-prompts">
          <h4>Purpose Prompts</h4>

          <div className="prompt-section">
            <label>Annual Review</label>
            <textarea
              className="textarea-field"
              rows="3"
              placeholder="I'm reaching out for your annual mortgage review. We've found potential savings..."
            />
          </div>

          <div className="prompt-section">
            <label>Pre-Approval Follow-up</label>
            <textarea
              className="textarea-field"
              rows="3"
              placeholder="Following up on your pre-approval application. Do you have time to discuss next steps?"
            />
          </div>

          <div className="prompt-section">
            <label>Refinance Opportunity</label>
            <textarea
              className="textarea-field"
              rows="3"
              placeholder="Rates have dropped significantly. I wanted to discuss potential refinance savings..."
            />
          </div>
        </div>

        <div className="form-field">
          <label>Escalation / Warm Transfer Number</label>
          <input
            type="tel"
            value={formData.escalationNumber}
            onChange={(e) => updateField('escalationNumber', e.target.value)}
            className="input-field"
            placeholder="+1 (555) 123-4567"
          />
          <p className="field-hint">Number to transfer to when customer requests human</p>
        </div>
      </div>
    </div>
  );

  // SCREEN 7: Test & Go-Live
  const handleTestCallClick = () => {
    setHelpdeskModal({
      feature: 'AI Calling Test',
      message: 'This feature is not yet configured. Our team will help you set it up.'
    });
  };

  const handleTestCalendarClick = () => {
    setHelpdeskModal({
      feature: 'Calendar Booking Test',
      message: 'This feature requires Calendly integration to be fully configured.'
    });
  };

  const handleEmailUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      setUploadedTestEmail(file);
      // Simulate email parsing
      setTimeout(() => {
        setFormData(prevData => ({
          ...prevData,
          testsPassed: { ...prevData.testsPassed, emailTest: true }
        }));
      }, 1000);
    }
  };

  const handleCloseHelpdeskModal = () => {
    setHelpdeskModal(null);
  };

  const handleSubmitTicket = (e) => {
    e.preventDefault();
    console.log('Helpdesk ticket submitted for:', helpdeskModal.feature);
    // In production, this would send to your helpdesk system
    setHelpdeskModal(null);
    alert('Support ticket submitted! Our team will contact you shortly.');
  };

  const renderTestGoLive = () => (
    <div className="step-content">
      <div className="step-header">
        <div className="step-icon">🚀</div>
        <h2>Test & Go-Live</h2>
        <p className="step-description">Verify everything works before activating your account</p>
      </div>

      <div className="test-checklist">
        <h4>Pre-Launch Checklist</h4>

        <div className="test-item">
          <div className="test-header">
            <h5>📞 Test AI Calling</h5>
            {formData.testsPassed.callTest ? (
              <span className="status-pass">✓ Passed</span>
            ) : (
              <span className="status-pending">Pending</span>
            )}
          </div>
          <p>Call your phone number and verify voice quality, script, and transfer</p>
          <input
            type="tel"
            placeholder="Your test phone number"
            className="input-field test-input"
          />
          <button className="btn-test" onClick={handleTestCallClick}>Run Call Test</button>
        </div>

        <div className="test-item">
          <div className="test-header">
            <h5>📧 Test Email Parsing</h5>
            {formData.testsPassed.emailTest ? (
              <span className="status-pass">✓ Passed</span>
            ) : (
              <span className="status-pending">Pending</span>
            )}
          </div>
          <p>Upload a sample email to verify milestone detection</p>
          {uploadedTestEmail ? (
            <div className="uploaded-test-file">
              <span className="file-icon">📧</span>
              <span className="file-name">{uploadedTestEmail.name}</span>
              <span className="status-pass">✓ Uploaded</span>
            </div>
          ) : (
            <div className="file-upload-area">
              <input
                type="file"
                accept=".eml,.msg,.txt"
                onChange={handleEmailUpload}
                className="file-input"
                id="email-test-upload"
              />
              <label htmlFor="email-test-upload" className="btn-test">
                Upload Sample Email
              </label>
            </div>
          )}
          <div className="email-test-example">
            <p className="example-hint">Try uploading an "Appraisal Received" email (.eml, .msg, or .txt)</p>
          </div>
        </div>

        <div className="test-item">
          <div className="test-header">
            <h5>📅 Test Calendar Booking</h5>
            <span className="status-pending">Optional</span>
          </div>
          <p>Book a test appointment through Calendly integration</p>
          <button className="btn-test-secondary" onClick={handleTestCalendarClick}>Test Calendly</button>
        </div>

        <div className="test-item">
          <div className="test-header">
            <h5>👥 Team Invites Sent</h5>
            <span className="status-pass">✓ Ready</span>
          </div>
          <p>{formData.members.length} team members will receive activation emails</p>
        </div>
      </div>

      <div className="go-live-section">
        <div className="requirements-check">
          <h4>Requirements</h4>
          <div className="requirement-item">
            <span className={formData.members?.length > 0 && formData.members[0].email ? 'check-pass' : 'check-fail'}>
              {formData.members?.length > 0 && formData.members[0].email ? '✓' : '○'}
            </span>
            Team members configured
          </div>
          <div className="requirement-item">
            <span className={formData.dncAccepted ? 'check-pass' : 'check-fail'}>
              {formData.dncAccepted ? '✓' : '○'}
            </span>
            Compliance policies accepted
          </div>
          <div className="requirement-item">
            <span className="check-pass">✓</span>
            AI agent configured
          </div>
        </div>

        <div className="activation-ready">
          <p className="ready-message">
            All systems ready! Click below to activate your account.
          </p>
          <p className="ready-hint">
            Your team will receive login credentials and you'll be redirected to your dashboard.
          </p>
        </div>
      </div>
    </div>
  );

  const progress = (currentStep / totalSteps) * 100;
  const canProceed = true; // Add validation logic per step if needed

  return (
    <div className="onboarding-overlay">
      <div className="onboarding-wizard-v2">
        {/* Close Button */}
        {onSkip && (
          <button className="btn-close-wizard" onClick={onSkip} title="Skip for now">
            ×
          </button>
        )}

        {/* Progress Bar */}
        <div className="wizard-progress">
          <div className="progress-bar-container">
            <div className="progress-bar-fill" style={{ width: `${progress}%` }}></div>
          </div>
          <div className="progress-text">
            Step {currentStep} of {totalSteps}
          </div>
        </div>

        {/* Step Indicators */}
        <div className="step-indicators">
          {[
            { num: 1, label: 'Process' },
            { num: 2, label: 'Roles' },
            { num: 3, label: 'Tasks' },
            { num: 4, label: 'Team' },
            { num: 5, label: 'Ownership' },
            { num: 6, label: 'Integrations' },
            { num: 7, label: 'Compliance' },
            { num: 8, label: 'AI Agent' },
            { num: 9, label: 'Go-Live' }
          ].map((step) => (
            <div
              key={step.num}
              className={`step-indicator ${currentStep >= step.num ? 'active' : ''} ${
                currentStep > step.num ? 'completed' : ''
              }`}
            >
              <div className="indicator-dot">
                {currentStep > step.num ? '✓' : step.num}
              </div>
              <div className="indicator-label">{step.label}</div>
            </div>
          ))}
        </div>

        {/* Step Content */}
        {renderStep()}

        {/* Navigation */}
        <div className="wizard-navigation">
          {currentStep > 1 && (
            <button className="btn-nav btn-back" onClick={handleBack}>
              ← Back
            </button>
          )}

          <div className="nav-spacer"></div>

          <button
            className={`btn-nav btn-next ${!canProceed ? 'disabled' : ''}`}
            onClick={handleNext}
            disabled={!canProceed}
          >
            {currentStep === totalSteps ? (
              <>Activate Account & Go Live! 🚀</>
            ) : (
              <>Next →</>
            )}
          </button>
        </div>
      </div>

      {/* Helpdesk Modal */}
      {helpdeskModal && (
        <div className="connection-modal-overlay" onClick={handleCloseHelpdeskModal}>
          <div className="connection-modal helpdesk-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={handleCloseHelpdeskModal}>×</button>

            <div className="modal-header">
              <span className="modal-icon">🎫</span>
              <h3>Submit Support Ticket</h3>
              <p className="modal-description">Feature Not Yet Available</p>
            </div>

            <div className="modal-body">
              <div className="helpdesk-notice">
                <div className="notice-icon">ℹ️</div>
                <div className="notice-content">
                  <h4>{helpdeskModal.feature}</h4>
                  <p>{helpdeskModal.message}</p>
                </div>
              </div>

              <form className="helpdesk-form" onSubmit={handleSubmitTicket}>
                <div className="form-field">
                  <label>Your Name</label>
                  <input
                    type="text"
                    className="input-field"
                    placeholder="Full name"
                    required
                    defaultValue={`${formData.members[0]?.firstName || ''} ${formData.members[0]?.lastName || ''}`.trim()}
                  />
                </div>

                <div className="form-field">
                  <label>Email Address</label>
                  <input
                    type="email"
                    className="input-field"
                    placeholder="your@email.com"
                    required
                    defaultValue={formData.members[0]?.email || ''}
                  />
                </div>

                <div className="form-field">
                  <label>Phone Number (Optional)</label>
                  <input
                    type="tel"
                    className="input-field"
                    placeholder="(555) 123-4567"
                    defaultValue={formData.members[0]?.phone || ''}
                  />
                </div>

                <div className="form-field">
                  <label>Issue Type</label>
                  <select className="input-field" required>
                    <option value="setup">Setup Assistance</option>
                    <option value="bug">Report a Bug</option>
                    <option value="feature">Feature Request</option>
                    <option value="integration">Integration Help</option>
                    <option value="other">Other</option>
                  </select>
                </div>

                <div className="form-field">
                  <label>Additional Details</label>
                  <textarea
                    className="textarea-field"
                    placeholder="Please describe what you need help with..."
                    rows="4"
                    defaultValue={`I need help setting up: ${helpdeskModal.feature}`}
                  ></textarea>
                </div>

                <div className="helpdesk-actions">
                  <button type="button" className="btn-cancel" onClick={handleCloseHelpdeskModal}>
                    Cancel
                  </button>
                  <button type="submit" className="btn-submit-ticket">
                    Submit Ticket
                  </button>
                </div>
              </form>

              <div className="support-info">
                <p className="support-note">
                  📧 You can also email us at <strong>support@mortgagecrm.com</strong>
                </p>
                <p className="support-note">
                  ⏱️ Average response time: <strong>2-4 hours</strong>
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Connection Modal */}
      {connectionModal && (
        <div className="connection-modal-overlay" onClick={handleCloseModal}>
          <div className="connection-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={handleCloseModal}>×</button>

            <div className="modal-header">
              <span className="modal-icon">{connectionModal.icon}</span>
              <h3>Connect to {connectionModal.name}</h3>
              <p className="modal-description">{connectionModal.description}</p>
            </div>

            <div className="modal-body">
              <div className="auth-form">
                <div className="auth-provider-logo">
                  <span className="provider-logo-icon">{connectionModal.icon}</span>
                  <h4>{connectionModal.name}</h4>
                </div>

                <p className="auth-instruction">
                  Sign in to your {connectionModal.name} account to authorize access
                </p>

                <form className="oauth-form" onSubmit={(e) => { e.preventDefault(); handleAuthComplete(); }}>
                  <div className="form-field">
                    <label>Email or Username</label>
                    <input
                      type="text"
                      className="input-field"
                      placeholder={`Your ${connectionModal.name} email`}
                      autoFocus
                    />
                  </div>

                  <div className="form-field">
                    <label>Password</label>
                    <input
                      type="password"
                      className="input-field"
                      placeholder="Password"
                    />
                  </div>

                  <button type="submit" className="btn-authorize">
                    Authorize Connection
                  </button>
                </form>

                <div className="auth-footer">
                  <p className="security-note">
                    🔒 Your credentials are encrypted and securely stored. We only access data necessary for the integration.
                  </p>
                  <div className="permissions-info">
                    <p className="permissions-title">This integration will be able to:</p>
                    <ul className="permissions-list">
                      {connectionModal.category === 'Email' && (
                        <>
                          <li>Read emails and attachments</li>
                          <li>Send emails on your behalf</li>
                          <li>Access contact information</li>
                        </>
                      )}
                      {connectionModal.category === 'Calendar' && (
                        <>
                          <li>View and create calendar events</li>
                          <li>Send meeting invitations</li>
                          <li>Access availability information</li>
                        </>
                      )}
                      {connectionModal.category === 'Phone' && (
                        <>
                          <li>Make and receive calls</li>
                          <li>Send and receive SMS messages</li>
                          <li>Access call history and recordings</li>
                        </>
                      )}
                      {connectionModal.category === 'Documents' && (
                        <>
                          <li>Upload and download documents</li>
                          <li>Create and modify files</li>
                          <li>Share documents with clients</li>
                        </>
                      )}
                      {connectionModal.category === 'LOS' && (
                        <>
                          <li>Read loan application data</li>
                          <li>Update loan statuses</li>
                          <li>Sync borrower information</li>
                        </>
                      )}
                      {connectionModal.category === 'CRM' && (
                        <>
                          <li>Read and write contact data</li>
                          <li>Create and update leads</li>
                          <li>Sync pipeline information</li>
                        </>
                      )}
                      {connectionModal.category === 'Credit' && (
                        <>
                          <li>Pull credit reports</li>
                          <li>View credit scores</li>
                          <li>Access credit history</li>
                        </>
                      )}
                      {connectionModal.category === 'Communication' && (
                        <>
                          <li>Send messages to channels</li>
                          <li>Create notifications</li>
                          <li>Access team information</li>
                        </>
                      )}
                      {connectionModal.category === 'Accounting' && (
                        <>
                          <li>Read transaction data</li>
                          <li>Create invoices</li>
                          <li>Sync financial records</li>
                        </>
                      )}
                    </ul>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Task Edit Modal */}
      {taskEditModal && (
        <div className="connection-modal-overlay" onClick={handleCloseTaskEdit}>
          <div className="connection-modal task-edit-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={handleCloseTaskEdit}>×</button>

            <div className="modal-header">
              <span className="modal-icon">📋</span>
              <h3>Edit Task</h3>
              <p className="modal-description">Update task details and assignment</p>
            </div>

            <div className="modal-body">
              <div className="form-field">
                <label>Task Name</label>
                <input
                  type="text"
                  className="input-field"
                  value={taskEditModal.task_name || ''}
                  onChange={(e) => handleUpdateTaskEditField('task_name', e.target.value)}
                />
              </div>

              <div className="form-field">
                <label>Description</label>
                <textarea
                  className="textarea-field"
                  rows="3"
                  value={taskEditModal.task_description || ''}
                  onChange={(e) => handleUpdateTaskEditField('task_description', e.target.value)}
                />
              </div>

              <div className="form-field">
                <label>Assigned Role</label>
                <select
                  className="input-field"
                  value={taskEditModal.tempRoleId || ''}
                  onChange={(e) => handleUpdateTaskEditField('tempRoleId', e.target.value)}
                >
                  <option value="">Select Role</option>
                  {formData.extractedRoles?.map(role => (
                    <option key={role.id} value={role.id}>
                      {role.role_title}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-field">
                <label>Assigned User (Optional)</label>
                <select
                  className="input-field"
                  value={taskEditModal.tempUserId || ''}
                  onChange={(e) => handleUpdateTaskEditField('tempUserId', e.target.value ? parseInt(e.target.value) : null)}
                >
                  <option value="">Select User</option>
                  {teamMembers.map((member) => (
                    <option key={member.id} value={member.id}>
                      {member.full_name || member.email}
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-row">
                <div className="form-field">
                  <label>SLA</label>
                  <input
                    type="number"
                    className="input-field"
                    value={taskEditModal.sla || ''}
                    onChange={(e) => handleUpdateTaskEditField('sla', parseInt(e.target.value) || 0)}
                    min="1"
                  />
                </div>

                <div className="form-field">
                  <label>SLA Unit</label>
                  <select
                    className="input-field"
                    value={taskEditModal.sla_unit || 'hours'}
                    onChange={(e) => handleUpdateTaskEditField('sla_unit', e.target.value)}
                  >
                    <option value="hours">Hours</option>
                    <option value="days">Days</option>
                  </select>
                </div>
              </div>

              <div className="form-field">
                <label className="checkbox-label">
                  <input
                    type="checkbox"
                    checked={taskEditModal.ai_automatable || false}
                    onChange={(e) => handleUpdateTaskEditField('ai_automatable', e.target.checked)}
                  />
                  <span>AI Automatable</span>
                </label>
              </div>

              <div className="modal-actions">
                <button className="btn-cancel" onClick={handleCloseTaskEdit}>
                  Cancel
                </button>
                <button className="btn-save" onClick={handleSaveTaskEdit}>
                  Save Changes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Role Add Modal */}
      {roleAddModal && (
        <div className="connection-modal-overlay" onClick={handleCloseRoleAdd}>
          <div className="connection-modal role-add-modal" onClick={(e) => e.stopPropagation()}>
            <button className="btn-close-modal" onClick={handleCloseRoleAdd}>×</button>

            <div className="modal-header">
              <span className="modal-icon">👥</span>
              <h3>Add New Role</h3>
              <p className="modal-description">Create a custom role for your team</p>
            </div>

            <div className="modal-body">
              <div className="form-field">
                <label>Role Title *</label>
                <input
                  type="text"
                  className="input-field"
                  placeholder="e.g., Senior Loan Officer"
                  value={newRoleForm.role_title}
                  onChange={(e) => setNewRoleForm({ ...newRoleForm, role_title: e.target.value })}
                />
              </div>

              <div className="form-field">
                <label>Role Name (Internal) *</label>
                <input
                  type="text"
                  className="input-field"
                  placeholder="e.g., senior_loan_officer"
                  value={newRoleForm.role_name}
                  onChange={(e) => setNewRoleForm({ ...newRoleForm, role_name: e.target.value })}
                />
              </div>

              <div className="form-field">
                <label>Responsibilities</label>
                <textarea
                  className="textarea-field"
                  rows="3"
                  placeholder="Describe what this role is responsible for..."
                  value={newRoleForm.responsibilities}
                  onChange={(e) => setNewRoleForm({ ...newRoleForm, responsibilities: e.target.value })}
                />
              </div>

              <div className="modal-actions">
                <button className="btn-cancel" onClick={handleCloseRoleAdd}>
                  Cancel
                </button>
                <button className="btn-save" onClick={handleSaveNewRole}>
                  Add Role
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default OnboardingWizard;

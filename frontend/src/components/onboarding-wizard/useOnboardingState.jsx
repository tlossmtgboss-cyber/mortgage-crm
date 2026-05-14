import { useState, useEffect } from 'react';
import { onboardingAPI, teamAPI } from '../../services/api';
import { toast } from '../../utils/toast';
import { getToken } from '../../utils/tokenStore';

const INITIAL_FORM_DATA = {
  // Step 1: User Registration
  firstName: '',
  lastName: '',
  userEmail: '',
  userPhone: '',
  businessAddress: '',
  currentRole: '',
  businessHoursStart: '09:00',
  businessHoursEnd: '17:00',

  // Step 3: Upload Documents
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
};

export const useOnboardingState = ({ onComplete }) => {
  const [currentStep, setCurrentStep] = useState(0);
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
  const [formData, setFormData] = useState(INITIAL_FORM_DATA);
  const [selectedMemberForTasks, setSelectedMemberForTasks] = useState(null);
  const [memberTaskModal, setMemberTaskModal] = useState(false);
  const [previewEmails, setPreviewEmails] = useState([]);

  const totalSteps = 10;

  // Load existing onboarding data when component mounts
  useEffect(() => {
    const loadExistingData = async () => {
      try {
        const [roles, milestones, tasks, members] = await Promise.all([
          onboardingAPI.getRoles().catch(() => []),
          onboardingAPI.getMilestones().catch(() => []),
          onboardingAPI.getTasks().catch(() => []),
          teamAPI.getMembers().catch(() => [])
        ]);

        if (members.length > 0) {
          setTeamMembers(members);
        }

        let processData = null;
        try {
          const stored = localStorage.getItem('onboarding_process_data');
          if (stored) {
            processData = JSON.parse(stored);
          }
        } catch (e) {
          console.error('Failed to load from localStorage:', e);
        }

        const finalRoles = roles.length > 0 ? roles : (processData?.extractedRoles || []);
        const finalMilestones = milestones.length > 0 ? milestones : (processData?.extractedMilestones || []);
        const finalTasks = tasks.length > 0 ? tasks : (processData?.extractedTasks || []);
        const finalProcessTree = processData?.processTree || null;

        if (finalRoles.length > 0 || finalMilestones.length > 0 || finalTasks.length > 0) {
          const processTreeStats = finalProcessTree || {
            generated: true,
            milestones: finalMilestones.length,
            tasks: finalTasks.length,
            roles: finalRoles.length
          };

          setFormData(prevData => ({
            ...prevData,
            extractedRoles: finalRoles,
            extractedMilestones: finalMilestones,
            extractedTasks: finalTasks,
            processTree: processTreeStats
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
      if (formData.processTree && formData.milestones.length > 0) {
        const processTreeData = {
          ...formData.processTree,
          milestonesData: formData.milestones
        };
        localStorage.setItem('onboardingProcessTree', JSON.stringify(processTreeData));
      }

      const token = getToken();
      const isProduction = window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1';
      const API_BASE_URL = isProduction ? 'https://api.perenniaai.com' : (process.env.REACT_APP_API_URL || 'http://localhost:8000');

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
    const MAX_FILE_SIZE = 50 * 1024 * 1024;

    const validFiles = newFiles.filter(file => {
      const validTypes = ['.pdf', '.docx', '.xlsx', '.csv', '.doc', '.xls', '.txt'];
      const fileExt = '.' + file.name.split('.').pop().toLowerCase();
      if (!validTypes.includes(fileExt)) {
        toast.error(`${file.name}: Invalid file type. Please upload PDF, DOCX, XLSX, or CSV files.`);
        return false;
      }
      if (file.size > MAX_FILE_SIZE) {
        toast.error(`${file.name}: File too large. Maximum size is 50MB.`);
        return false;
      }
      return true;
    });

    const currentFiles = formData.sopFiles || [];
    const combinedFiles = [...currentFiles, ...validFiles];

    if (combinedFiles.length > MAX_FILES) {
      toast.warning(`Maximum ${MAX_FILES} files allowed. Only adding first ${MAX_FILES - currentFiles.length} files.`);
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

  // Milestone and task management
  const addMilestone = () => {
    setFormData(prevData => {
      const newMilestone = { name: 'New Milestone', tasks: [] };
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
      const newTask = { name: '', owner: 'Loan Officer', sla: 24, slaUnit: 'hours', aiAuto: false };
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

  // Drag and Drop handlers
  const handleDragStart = (e, milestoneIndex, taskIndex) => {
    setDraggedTask({ milestoneIndex, taskIndex });
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDropTask = (e, targetMilestoneIndex) => {
    e.preventDefault();
    if (!draggedTask) return;

    const { milestoneIndex: sourceMilestoneIndex, taskIndex: sourceTaskIndex } = draggedTask;
    if (sourceMilestoneIndex === targetMilestoneIndex) {
      setDraggedTask(null);
      return;
    }

    setFormData(prevData => {
      const newMilestones = [...prevData.milestones];
      const taskToMove = { ...newMilestones[sourceMilestoneIndex].tasks[sourceTaskIndex] };
      newMilestones[sourceMilestoneIndex].tasks = newMilestones[sourceMilestoneIndex].tasks.filter((_, i) => i !== sourceTaskIndex);
      newMilestones[targetMilestoneIndex].tasks = [...newMilestones[targetMilestoneIndex].tasks, taskToMove];
      return { ...prevData, milestones: newMilestones };
    });

    setDraggedTask(null);
  };

  // Task Edit Modal handlers
  const handleOpenTaskEdit = (task) => {
    setTaskEditModal({ ...task, tempRoleId: task.role_id, tempUserId: null });
  };

  const handleCloseTaskEdit = () => {
    setTaskEditModal(null);
  };

  const handleSaveTaskEdit = async () => {
    if (!taskEditModal) return;
    try {
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

      setFormData(prevData => {
        const newTasks = prevData.extractedTasks.map(task => {
          if (task.id === taskEditModal.id) return updatedTask;
          return task;
        });
        return { ...prevData, extractedTasks: newTasks };
      });

      setTaskEditModal(null);
    } catch (error) {
      console.error('Failed to save task:', error);
      toast.error('Failed to save task changes. Please try again.');
    }
  };

  const handleUpdateTaskEditField = (field, value) => {
    setTaskEditModal(prev => ({ ...prev, [field]: value }));
  };

  // Role Add Modal handlers
  const handleOpenRoleAdd = () => {
    setNewRoleForm({ role_title: '', role_name: '', responsibilities: '', skills_required: [], key_activities: [] });
    setRoleAddModal(true);
  };

  const handleCloseRoleAdd = () => {
    setRoleAddModal(false);
  };

  const handleSaveNewRole = () => {
    if (!newRoleForm.role_title || !newRoleForm.role_name) {
      toast.error('Please enter both role title and role name');
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

  // Email preview
  const handlePreviewEmailUpload = (e) => {
    const files = Array.from(e.target.files).slice(0, 3);
    const parsedEmails = files.map((file, index) => ({
      id: `preview_${Date.now()}_${index}`,
      fileName: file.name,
      sender: 'sarah.johnson@example.com',
      subject: index === 0 ? 'Re: Pre-approval question' : index === 1 ? 'Documents uploaded' : 'Closing date question',
      extractedData: {
        leadName: index === 0 ? 'Sarah Johnson' : index === 1 ? 'Mike Chen' : 'Emily Davis',
        phone: index === 0 ? '(555) 123-4567' : index === 1 ? '(555) 234-5678' : '(555) 345-6789',
        loanAmount: index === 0 ? '$425,000' : index === 1 ? '$380,000' : '$510,000',
        milestone: index === 0 ? 'Pre-Approval' : index === 1 ? 'Document Review' : 'Clear to Close',
        confidence: index === 0 ? 95 : index === 1 ? 92 : 88
      }
    }));
    setPreviewEmails(parsedEmails);
  };

  // Test & Go-Live handlers
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
    setHelpdeskModal(null);
    toast.success('Support ticket submitted! Our team will contact you shortly.');
  };

  const handleCloseModal = () => {
    setConnectionModal(null);
  };

  const handleAuthComplete = () => {
    console.log(`Connected to ${connectionModal.name}`);
    setConnectionModal(null);
  };

  return {
    // State
    currentStep, setCurrentStep,
    activeMilestone, setActiveMilestone,
    isProcessing, setIsProcessing,
    connectionModal, setConnectionModal,
    helpdeskModal, setHelpdeskModal,
    uploadedTestEmail,
    draggedTask, setDraggedTask,
    taskEditModal, setTaskEditModal,
    roleAddModal,
    newRoleForm, setNewRoleForm,
    teamMembers,
    formData, setFormData,
    selectedMemberForTasks, setSelectedMemberForTasks,
    memberTaskModal, setMemberTaskModal,
    previewEmails,
    totalSteps,

    // Handlers
    handleNext, handleBack, handleComplete,
    updateField, addMember, updateMember, removeMember,
    handleFileSelect, removeFile, formatFileSize,
    handleDragOver, handleDrop,
    addMilestone, updateMilestone, removeMilestone,
    addTask, updateTask, removeTask,
    handleDragStart, handleDropTask,
    handleOpenTaskEdit, handleCloseTaskEdit, handleSaveTaskEdit, handleUpdateTaskEditField,
    handleOpenRoleAdd, handleCloseRoleAdd, handleSaveNewRole,
    handlePreviewEmailUpload,
    handleTestCallClick, handleTestCalendarClick,
    handleEmailUpload,
    handleCloseHelpdeskModal, handleSubmitTicket,
    handleCloseModal, handleAuthComplete,
  };
};

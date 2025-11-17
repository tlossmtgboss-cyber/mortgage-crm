import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './PipelineEfficiency.css';

function PipelineEfficiency() {
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState('30days'); // 7days, 30days, 90days, year
  const [selectedBottleneck, setSelectedBottleneck] = useState(null);
  const [showDrilldownModal, setShowDrilldownModal] = useState(false);
  const [selectedTeamMember, setSelectedTeamMember] = useState(null);
  const [showTeamDrilldown, setShowTeamDrilldown] = useState(false);
  const [selectedStage, setSelectedStage] = useState(null);
  const [showStageDrilldown, setShowStageDrilldown] = useState(false);

  // Mock stage loans data - keyed by stage name
  const stageLoansData = {
    'Lead Generation': [
      { id: 4001, borrowerName: 'Sarah Chen', loanNumber: 'L-2024-201', loanAmount: 420000, source: 'Website', assignedTo: 'Mike Johnson', daysInStage: 1, status: 'New Lead', lastActivity: 'Form submitted' },
      { id: 4002, borrowerName: 'Robert Martinez', loanNumber: 'L-2024-202', loanAmount: 385000, source: 'Referral', assignedTo: 'Sarah Mitchell', daysInStage: 2, status: 'Contacted', lastActivity: 'Initial call completed' },
      { id: 4003, borrowerName: 'Emily Taylor', loanNumber: 'L-2024-203', loanAmount: 510000, source: 'Facebook Ad', assignedTo: 'Mike Johnson', daysInStage: 1, status: 'New Lead', lastActivity: 'Waiting for callback' },
      { id: 4004, borrowerName: 'James Wilson', loanNumber: 'L-2024-204', loanAmount: 295000, source: 'Zillow', assignedTo: 'Sarah Mitchell', daysInStage: 3, status: 'Needs Follow-up', lastActivity: 'Voicemail left' }
    ],
    'Pre-Qualification': [
      { id: 4005, borrowerName: 'Linda Brown', loanNumber: 'L-2024-205', loanAmount: 475000, assignedTo: 'Mike Johnson', creditScore: 740, daysInStage: 2, status: 'Documents Pending', lastActivity: 'Waiting for paystubs' },
      { id: 4006, borrowerName: 'David Garcia', loanNumber: 'L-2024-206', loanAmount: 550000, assignedTo: 'Sarah Mitchell', creditScore: 780, daysInStage: 5, status: 'Needs Attention', lastActivity: 'Missing bank statements' },
      { id: 4007, borrowerName: 'Patricia Lee', loanNumber: 'L-2024-207', loanAmount: 325000, assignedTo: 'Mike Johnson', creditScore: 720, daysInStage: 1, status: 'On Track', lastActivity: 'All docs received' }
    ],
    'Application': [
      { id: 4008, borrowerName: 'Michael Anderson', loanNumber: 'L-2024-208', loanAmount: 680000, assignedTo: 'Jennifer Lopez', creditScore: 760, daysInStage: 4, status: 'In Review', lastActivity: 'Credit pulled' },
      { id: 4009, borrowerName: 'Jennifer Thomas', loanNumber: 'L-2024-209', loanAmount: 445000, assignedTo: 'Jennifer Lopez', creditScore: 710, daysInStage: 6, status: 'Needs Attention', lastActivity: 'Waiting for employment verification' },
      { id: 4010, borrowerName: 'Christopher Moore', loanNumber: 'L-2024-210', loanAmount: 390000, assignedTo: 'Maria Garcia', creditScore: 795, daysInStage: 3, status: 'On Track', lastActivity: 'Application complete' }
    ],
    'Processing': [
      { id: 4011, borrowerName: 'Jessica White', loanNumber: 'L-2024-211', loanAmount: 520000, processor: 'Jennifer Lopez', daysInStage: 8, status: 'Delayed', missingDocs: 'Tax returns, HOA docs', lastActivity: 'Requested docs 3 days ago' },
      { id: 4012, borrowerName: 'Daniel Harris', loanNumber: 'L-2024-212', loanAmount: 415000, processor: 'Maria Garcia', daysInStage: 15, status: 'Critical', missingDocs: 'Gift letter, appraisal', lastActivity: 'Escalated to manager' },
      { id: 4013, borrowerName: 'Ashley Clark', loanNumber: 'L-2024-213', loanAmount: 365000, processor: 'Jennifer Lopez', daysInStage: 10, status: 'Needs Attention', missingDocs: 'Insurance binder', lastActivity: 'Follow-up scheduled' }
    ],
    'Underwriting': [
      { id: 4014, borrowerName: 'Matthew Lewis', loanNumber: 'L-2024-214', loanAmount: 595000, underwriter: 'David Chen', daysInStage: 7, status: 'In Review', conditions: '2', lastActivity: 'Submitted to underwriter' },
      { id: 4015, borrowerName: 'Amanda Walker', loanNumber: 'L-2024-215', loanAmount: 725000, underwriter: 'David Chen', daysInStage: 9, status: 'Suspended', conditions: '5', lastActivity: 'Waiting for appraisal review' },
      { id: 4016, borrowerName: 'Joshua Hall', loanNumber: 'L-2024-216', loanAmount: 455000, underwriter: 'Rachel Kim', daysInStage: 5, status: 'On Track', conditions: '1', lastActivity: 'Conditional approval issued' }
    ],
    'Clear to Close': [
      { id: 4017, borrowerName: 'Nicole Young', loanNumber: 'L-2024-217', loanAmount: 485000, closer: 'Tom Wilson', daysInStage: 2, status: 'Ready to Close', closingDate: '2024-01-25', lastActivity: 'Docs sent to title' },
      { id: 4018, borrowerName: 'Ryan King', loanNumber: 'L-2024-218', loanAmount: 540000, closer: 'Tom Wilson', daysInStage: 4, status: 'Pending Final Review', closingDate: '2024-01-27', lastActivity: 'Final walkthrough complete' },
      { id: 4019, borrowerName: 'Stephanie Scott', loanNumber: 'L-2024-219', loanAmount: 395000, closer: 'Tom Wilson', daysInStage: 1, status: 'Ready to Close', closingDate: '2024-01-24', lastActivity: 'Wire instructions sent' }
    ],
    'Closing': [
      { id: 4020, borrowerName: 'Brandon Green', loanNumber: 'L-2024-220', loanAmount: 625000, closer: 'Tom Wilson', daysInStage: 1, status: 'Scheduled', closingDate: '2024-01-23', lastActivity: 'Closing scheduled' },
      { id: 4021, borrowerName: 'Michelle Adams', loanNumber: 'L-2024-221', loanAmount: 475000, closer: 'Tom Wilson', daysInStage: 2, status: 'In Progress', closingDate: '2024-01-24', lastActivity: 'Waiting for funds' }
    ]
  };

  // Mock team member loans data - keyed by role
  const teamMemberLoansData = {
    'Loan Officers': [
      { id: 3001, borrowerName: 'Alex Thompson', loanNumber: 'L-2024-101', loanAmount: 450000, currentStage: 'Application', assignedTo: 'Sarah Mitchell', daysInStage: 3, status: 'On Track' },
      { id: 3002, borrowerName: 'Maria Garcia', loanNumber: 'L-2024-102', loanAmount: 325000, currentStage: 'Pre-Approval', assignedTo: 'Mike Johnson', daysInStage: 2, status: 'On Track' },
      { id: 3003, borrowerName: 'David Chen', loanNumber: 'L-2024-103', loanAmount: 580000, currentStage: 'Application', assignedTo: 'Sarah Mitchell', daysInStage: 5, status: 'Needs Attention' },
      { id: 3004, borrowerName: 'Jennifer Lopez', loanNumber: 'L-2024-104', loanAmount: 395000, currentStage: 'Pre-Qualification', assignedTo: 'Mike Johnson', daysInStage: 1, status: 'On Track' },
      { id: 3005, borrowerName: 'Robert Taylor', loanNumber: 'L-2024-105', loanAmount: 670000, currentStage: 'Application', assignedTo: 'Sarah Mitchell', daysInStage: 4, status: 'On Track' },
      { id: 3006, borrowerName: 'Lisa Anderson', loanNumber: 'L-2024-106', loanAmount: 410000, currentStage: 'Pre-Approval', assignedTo: 'Mike Johnson', daysInStage: 2, status: 'On Track' },
      { id: 3007, borrowerName: 'James Wilson', loanNumber: 'L-2024-107', loanAmount: 525000, currentStage: 'Application', assignedTo: 'Sarah Mitchell', daysInStage: 6, status: 'Delayed' },
      { id: 3008, borrowerName: 'Patricia Moore', loanNumber: 'L-2024-108', loanAmount: 360000, currentStage: 'Pre-Qualification', assignedTo: 'Mike Johnson', daysInStage: 1, status: 'On Track' },
      { id: 3009, borrowerName: 'Christopher Lee', loanNumber: 'L-2024-109', loanAmount: 495000, currentStage: 'Application', assignedTo: 'Sarah Mitchell', daysInStage: 3, status: 'On Track' },
      { id: 3010, borrowerName: 'Barbara Martinez', loanNumber: 'L-2024-110', loanAmount: 425000, currentStage: 'Pre-Approval', assignedTo: 'Mike Johnson', daysInStage: 2, status: 'On Track' },
      { id: 3011, borrowerName: 'Daniel White', loanNumber: 'L-2024-111', loanAmount: 550000, currentStage: 'Application', assignedTo: 'Sarah Mitchell', daysInStage: 4, status: 'On Track' },
      { id: 3012, borrowerName: 'Nancy Jackson', loanNumber: 'L-2024-112', loanAmount: 385000, currentStage: 'Pre-Qualification', assignedTo: 'Mike Johnson', daysInStage: 1, status: 'On Track' },
      { id: 3013, borrowerName: 'Kevin Brown', loanNumber: 'L-2024-113', loanAmount: 615000, currentStage: 'Application', assignedTo: 'Sarah Mitchell', daysInStage: 5, status: 'Needs Attention' },
      { id: 3014, borrowerName: 'Michelle Davis', loanNumber: 'L-2024-114', loanAmount: 440000, currentStage: 'Pre-Approval', assignedTo: 'Mike Johnson', daysInStage: 2, status: 'On Track' },
      { id: 3015, borrowerName: 'Steven Johnson', loanNumber: 'L-2024-115', loanAmount: 375000, currentStage: 'Application', assignedTo: 'Sarah Mitchell', daysInStage: 3, status: 'On Track' }
    ],
    'Processors': [
      { id: 4001, borrowerName: 'Emily Roberts', loanNumber: 'L-2024-201', loanAmount: 465000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 8, status: 'On Track' },
      { id: 4002, borrowerName: 'Michael Green', loanNumber: 'L-2024-202', loanAmount: 390000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 12, status: 'Needs Attention' },
      { id: 4003, borrowerName: 'Amanda Clark', loanNumber: 'L-2024-203', loanAmount: 520000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 6, status: 'On Track' },
      { id: 4004, borrowerName: 'Thomas Hill', loanNumber: 'L-2024-204', loanAmount: 435000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 15, status: 'Delayed' },
      { id: 4005, borrowerName: 'Rachel Adams', loanNumber: 'L-2024-205', loanAmount: 585000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 7, status: 'On Track' },
      { id: 4006, borrowerName: 'Brandon Scott', loanNumber: 'L-2024-206', loanAmount: 410000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 10, status: 'On Track' },
      { id: 4007, borrowerName: 'Stephanie King', loanNumber: 'L-2024-207', loanAmount: 495000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 9, status: 'On Track' },
      { id: 4008, borrowerName: 'Jason Wright', loanNumber: 'L-2024-208', loanAmount: 375000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 11, status: 'Needs Attention' },
      { id: 4009, borrowerName: 'Angela Lopez', loanNumber: 'L-2024-209', loanAmount: 540000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 8, status: 'On Track' },
      { id: 4010, borrowerName: 'Brian Hall', loanNumber: 'L-2024-210', loanAmount: 420000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 13, status: 'Delayed' },
      { id: 4011, borrowerName: 'Rebecca Allen', loanNumber: 'L-2024-211', loanAmount: 475000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 7, status: 'On Track' },
      { id: 4012, borrowerName: 'Justin Young', loanNumber: 'L-2024-212', loanAmount: 405000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 9, status: 'On Track' },
      { id: 4013, borrowerName: 'Melissa King', loanNumber: 'L-2024-213', loanAmount: 560000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 10, status: 'On Track' },
      { id: 4014, borrowerName: 'Gary Wright', loanNumber: 'L-2024-214', loanAmount: 385000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 14, status: 'Needs Attention' },
      { id: 4015, borrowerName: 'Laura Scott', loanNumber: 'L-2024-215', loanAmount: 510000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 6, status: 'On Track' },
      { id: 4016, borrowerName: 'Ryan Turner', loanNumber: 'L-2024-216', loanAmount: 445000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 11, status: 'On Track' },
      { id: 4017, borrowerName: 'Kimberly Baker', loanNumber: 'L-2024-217', loanAmount: 395000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 8, status: 'On Track' },
      { id: 4018, borrowerName: 'Eric Nelson', loanNumber: 'L-2024-218', loanAmount: 525000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 12, status: 'Needs Attention' },
      { id: 4019, borrowerName: 'Sharon Carter', loanNumber: 'L-2024-219', loanAmount: 430000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 7, status: 'On Track' },
      { id: 4020, borrowerName: 'Dennis Mitchell', loanNumber: 'L-2024-220', loanAmount: 490000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 9, status: 'On Track' },
      { id: 4021, borrowerName: 'Cynthia Perez', loanNumber: 'L-2024-221', loanAmount: 455000, currentStage: 'Processing', assignedTo: 'John Smith', daysInStage: 10, status: 'On Track' },
      { id: 4022, borrowerName: 'Raymond Roberts', loanNumber: 'L-2024-222', loanAmount: 370000, currentStage: 'Processing', assignedTo: 'Jane Doe', daysInStage: 15, status: 'Delayed' }
    ],
    'Underwriters': [
      { id: 5001, borrowerName: 'Gregory Turner', loanNumber: 'L-2024-301', loanAmount: 515000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 5, status: 'On Track' },
      { id: 5002, borrowerName: 'Deborah Phillips', loanNumber: 'L-2024-302', loanAmount: 445000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 9, status: 'Needs Review' },
      { id: 5003, borrowerName: 'Frank Campbell', loanNumber: 'L-2024-303', loanAmount: 590000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 4, status: 'On Track' },
      { id: 5004, borrowerName: 'Ruth Parker', loanNumber: 'L-2024-304', loanAmount: 425000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 7, status: 'On Track' },
      { id: 5005, borrowerName: 'Harold Evans', loanNumber: 'L-2024-305', loanAmount: 555000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 6, status: 'On Track' },
      { id: 5006, borrowerName: 'Catherine Edwards', loanNumber: 'L-2024-306', loanAmount: 395000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 8, status: 'Needs Review' },
      { id: 5007, borrowerName: 'Peter Collins', loanNumber: 'L-2024-307', loanAmount: 620000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 5, status: 'On Track' },
      { id: 5008, borrowerName: 'Donna Stewart', loanNumber: 'L-2024-308', loanAmount: 465000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 10, status: 'Suspended' },
      { id: 5009, borrowerName: 'Arthur Morris', loanNumber: 'L-2024-309', loanAmount: 535000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 4, status: 'On Track' },
      { id: 5010, borrowerName: 'Carol Rogers', loanNumber: 'L-2024-310', loanAmount: 480000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 6, status: 'On Track' },
      { id: 5011, borrowerName: 'Henry Reed', loanNumber: 'L-2024-311', loanAmount: 425000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 5, status: 'On Track' },
      { id: 5012, borrowerName: 'Frances Cook', loanNumber: 'L-2024-312', loanAmount: 560000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 7, status: 'On Track' },
      { id: 5013, borrowerName: 'Carl Morgan', loanNumber: 'L-2024-313', loanAmount: 410000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 8, status: 'Needs Review' },
      { id: 5014, borrowerName: 'Janet Bell', loanNumber: 'L-2024-314', loanAmount: 495000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 5, status: 'On Track' },
      { id: 5015, borrowerName: 'Roger Murphy', loanNumber: 'L-2024-315', loanAmount: 445000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 6, status: 'On Track' },
      { id: 5016, borrowerName: 'Diane Bailey', loanNumber: 'L-2024-316', loanAmount: 525000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 9, status: 'Needs Review' },
      { id: 5017, borrowerName: 'Keith Rivera', loanNumber: 'L-2024-317', loanAmount: 475000, currentStage: 'Underwriting', assignedTo: 'Tom Wilson', daysInStage: 4, status: 'On Track' },
      { id: 5018, borrowerName: 'Alice Cooper', loanNumber: 'L-2024-318', loanAmount: 580000, currentStage: 'Underwriting', assignedTo: 'Susan Davis', daysInStage: 7, status: 'On Track' }
    ],
    'Closers': [
      { id: 6001, borrowerName: 'Willie Richardson', loanNumber: 'L-2024-401', loanAmount: 485000, currentStage: 'Clear to Close', assignedTo: 'Linda Martinez', daysInStage: 2, status: 'Ready to Close' },
      { id: 6002, borrowerName: 'Teresa Cox', loanNumber: 'L-2024-402', loanAmount: 420000, currentStage: 'Clear to Close', assignedTo: 'Robert Chen', daysInStage: 1, status: 'Ready to Close' },
      { id: 6003, borrowerName: 'Lawrence Howard', loanNumber: 'L-2024-403', loanAmount: 545000, currentStage: 'Closing', assignedTo: 'Linda Martinez', daysInStage: 1, status: 'Scheduled' },
      { id: 6004, borrowerName: 'Evelyn Ward', loanNumber: 'L-2024-404', loanAmount: 395000, currentStage: 'Clear to Close', assignedTo: 'Robert Chen', daysInStage: 2, status: 'Ready to Close' },
      { id: 6005, borrowerName: 'Russell Torres', loanNumber: 'L-2024-405', loanAmount: 615000, currentStage: 'Closing', assignedTo: 'Linda Martinez', daysInStage: 1, status: 'Scheduled' },
      { id: 6006, borrowerName: 'Ann Peterson', loanNumber: 'L-2024-406', loanAmount: 455000, currentStage: 'Clear to Close', assignedTo: 'Robert Chen', daysInStage: 2, status: 'Ready to Close' },
      { id: 6007, borrowerName: 'Philip Gray', loanNumber: 'L-2024-407', loanAmount: 530000, currentStage: 'Closing', assignedTo: 'Linda Martinez', daysInStage: 1, status: 'Scheduled' },
      { id: 6008, borrowerName: 'Judith Ramirez', loanNumber: 'L-2024-408', loanAmount: 475000, currentStage: 'Clear to Close', assignedTo: 'Robert Chen', daysInStage: 1, status: 'Ready to Close' }
    ]
  };

  // Mock affected loans data - keyed by bottleneck ID
  const affectedLoansData = {
    1: [ // Missing Documents
      {
        id: 1001,
        borrowerName: 'Sarah Johnson',
        loanNumber: 'L-2024-001',
        loanAmount: 425000,
        currentStage: 'Processing',
        processor: 'John Smith',
        missingItems: ['Pay Stubs (last 2 months)', 'Bank Statements', 'W-2 Forms (2023)'],
        daysDelayed: 5
      },
      {
        id: 1002,
        borrowerName: 'Michael Chen',
        loanNumber: 'L-2024-012',
        loanAmount: 380000,
        currentStage: 'Processing',
        processor: 'Jane Doe',
        missingItems: ['Tax Returns (2022-2023)', 'Proof of Assets'],
        daysDelayed: 4
      },
      {
        id: 1003,
        borrowerName: 'Emily Rodriguez',
        loanNumber: 'L-2024-018',
        loanAmount: 295000,
        currentStage: 'Processing',
        processor: 'John Smith',
        missingItems: ['Employment Verification', 'HOA Documents'],
        daysDelayed: 3
      },
      {
        id: 1004,
        borrowerName: 'David Martinez',
        loanNumber: 'L-2024-023',
        loanAmount: 550000,
        currentStage: 'Processing',
        processor: 'Jane Doe',
        missingItems: ['Gift Letter', 'Source of Funds Documentation'],
        daysDelayed: 6
      },
      {
        id: 1005,
        borrowerName: 'Jennifer Lee',
        loanNumber: 'L-2024-029',
        loanAmount: 340000,
        currentStage: 'Processing',
        processor: 'John Smith',
        missingItems: ['Divorce Decree', 'Child Support Documentation'],
        daysDelayed: 4
      },
      {
        id: 1006,
        borrowerName: 'Robert Taylor',
        loanNumber: 'L-2024-031',
        loanAmount: 620000,
        currentStage: 'Processing',
        processor: 'Jane Doe',
        missingItems: ['Business Tax Returns', 'Profit & Loss Statement'],
        daysDelayed: 5
      },
      {
        id: 1007,
        borrowerName: 'Amanda Wilson',
        loanNumber: 'L-2024-035',
        loanAmount: 475000,
        currentStage: 'Processing',
        processor: 'John Smith',
        missingItems: ['Homeowners Insurance', 'Property Appraisal'],
        daysDelayed: 3
      },
      {
        id: 1008,
        borrowerName: 'James Brown',
        loanNumber: 'L-2024-037',
        loanAmount: 410000,
        currentStage: 'Processing',
        processor: 'Jane Doe',
        missingItems: ['Retirement Account Statements', 'Investment Documentation'],
        daysDelayed: 7
      }
    ],
    2: [ // Income Verification Delays
      {
        id: 2001,
        borrowerName: 'Lisa Anderson',
        loanNumber: 'L-2024-008',
        loanAmount: 385000,
        currentStage: 'Pre-Qualification',
        processor: 'John Smith',
        missingItems: ['Employer Verification Response'],
        daysDelayed: 4
      },
      {
        id: 2002,
        borrowerName: 'Christopher Garcia',
        loanNumber: 'L-2024-015',
        loanAmount: 290000,
        currentStage: 'Pre-Qualification',
        processor: 'Jane Doe',
        missingItems: ['Employment Letter', 'Salary Confirmation'],
        daysDelayed: 3
      },
      {
        id: 2003,
        borrowerName: 'Patricia Moore',
        loanNumber: 'L-2024-022',
        loanAmount: 445000,
        currentStage: 'Pre-Qualification',
        processor: 'John Smith',
        missingItems: ['Commission Income Verification'],
        daysDelayed: 5
      },
      {
        id: 2004,
        borrowerName: 'Daniel Thomas',
        loanNumber: 'L-2024-026',
        loanAmount: 315000,
        currentStage: 'Pre-Qualification',
        processor: 'Jane Doe',
        missingItems: ['Self-Employment Verification'],
        daysDelayed: 2
      },
      {
        id: 2005,
        borrowerName: 'Nancy Jackson',
        loanNumber: 'L-2024-033',
        loanAmount: 520000,
        currentStage: 'Pre-Qualification',
        processor: 'John Smith',
        missingItems: ['Bonus Income Documentation'],
        daysDelayed: 3
      },
      {
        id: 2006,
        borrowerName: 'Kevin White',
        loanNumber: 'L-2024-039',
        loanAmount: 360000,
        currentStage: 'Pre-Qualification',
        processor: 'Jane Doe',
        missingItems: ['Overtime Income Verification'],
        daysDelayed: 4
      }
    ]
  };

  // Mock data - in production this would come from API
  const [efficiencyData, setEfficiencyData] = useState({
    overallScore: 78,
    trend: 5.2,
    lastUpdated: new Date().toISOString(),

    // Stage metrics
    stageMetrics: [
      {
        name: 'Lead Generation',
        efficiency: 85,
        avgTime: '2.3 days',
        conversionRate: 42,
        bottlenecks: 1,
        volume: 45,
        trend: 8
      },
      {
        name: 'Pre-Qualification',
        efficiency: 72,
        avgTime: '4.1 days',
        conversionRate: 68,
        bottlenecks: 3,
        volume: 19,
        trend: -3
      },
      {
        name: 'Application',
        efficiency: 81,
        avgTime: '5.2 days',
        conversionRate: 78,
        bottlenecks: 2,
        volume: 13,
        trend: 12
      },
      {
        name: 'Processing',
        efficiency: 65,
        avgTime: '12.5 days',
        conversionRate: 85,
        bottlenecks: 5,
        volume: 10,
        trend: -8
      },
      {
        name: 'Underwriting',
        efficiency: 70,
        avgTime: '8.7 days',
        conversionRate: 92,
        bottlenecks: 4,
        volume: 8,
        trend: 2
      },
      {
        name: 'Clear to Close',
        efficiency: 88,
        avgTime: '3.2 days',
        conversionRate: 96,
        bottlenecks: 1,
        volume: 7,
        trend: 15
      },
      {
        name: 'Closing',
        efficiency: 92,
        avgTime: '1.8 days',
        conversionRate: 98,
        bottlenecks: 0,
        volume: 7,
        trend: 10
      }
    ],

    // Team performance
    teamMetrics: [
      {
        role: 'Loan Officers',
        efficiency: 82,
        activeLoans: 15,
        avgResponseTime: '2.3 hrs',
        taskCompletionRate: 89,
        trend: 6
      },
      {
        role: 'Processors',
        efficiency: 68,
        activeLoans: 22,
        avgResponseTime: '5.1 hrs',
        taskCompletionRate: 72,
        trend: -4
      },
      {
        role: 'Underwriters',
        efficiency: 75,
        activeLoans: 18,
        avgResponseTime: '4.2 hrs',
        taskCompletionRate: 81,
        trend: 3
      },
      {
        role: 'Closers',
        efficiency: 91,
        activeLoans: 8,
        avgResponseTime: '1.5 hrs',
        taskCompletionRate: 95,
        trend: 12
      }
    ],

    // Active bottlenecks
    bottlenecks: [
      {
        id: 1,
        stage: 'Processing',
        issue: 'Missing Documents',
        affectedLoans: 8,
        avgDelay: '4.5 days',
        severity: 'high',
        suggestedAction: 'Send automated document reminder emails'
      },
      {
        id: 2,
        stage: 'Pre-Qualification',
        issue: 'Income Verification Delays',
        affectedLoans: 6,
        avgDelay: '3.2 days',
        severity: 'high',
        suggestedAction: 'Follow up with employers directly'
      },
      {
        id: 3,
        stage: 'Underwriting',
        issue: 'Appraisal Review Backlog',
        affectedLoans: 5,
        avgDelay: '2.8 days',
        severity: 'medium',
        suggestedAction: 'Escalate to senior underwriters'
      },
      {
        id: 4,
        stage: 'Processing',
        issue: 'Credit Report Disputes',
        affectedLoans: 4,
        avgDelay: '5.1 days',
        severity: 'medium',
        suggestedAction: 'Expedite credit bureau responses'
      },
      {
        id: 5,
        stage: 'Application',
        issue: 'Incomplete Applications',
        affectedLoans: 7,
        avgDelay: '2.1 days',
        severity: 'low',
        suggestedAction: 'Improve application form validation'
      },
      {
        id: 6,
        stage: 'Underwriting',
        issue: 'Title Search Delays',
        affectedLoans: 3,
        avgDelay: '3.5 days',
        severity: 'low',
        suggestedAction: 'Switch to faster title company'
      }
    ],

    // Key metrics
    keyMetrics: {
      avgTimeToClose: 35.2,
      avgTimeToCloseChange: -2.3,
      pullThroughRate: 68,
      pullThroughRateChange: 4.1,
      loansFallingBehind: 12,
      loansFallingBehindChange: -3,
      automationRate: 42,
      automationRateChange: 8.5,
      customerSatisfaction: 4.6,
      customerSatisfactionChange: 0.3
    },

    // Performance trends (last 12 weeks)
    trends: [
      { week: 'Week 1', score: 65, volume: 32 },
      { week: 'Week 2', score: 67, volume: 35 },
      { week: 'Week 3', score: 69, volume: 38 },
      { week: 'Week 4', score: 71, volume: 36 },
      { week: 'Week 5', score: 68, volume: 34 },
      { week: 'Week 6', score: 72, volume: 40 },
      { week: 'Week 7', score: 74, volume: 42 },
      { week: 'Week 8', score: 73, volume: 39 },
      { week: 'Week 9', score: 75, volume: 43 },
      { week: 'Week 10', score: 76, volume: 45 },
      { week: 'Week 11', score: 77, volume: 44 },
      { week: 'Week 12', score: 78, volume: 45 }
    ]
  });

  useEffect(() => {
    loadEfficiencyData();
  }, [timeRange]);

  const loadEfficiencyData = () => {
    setLoading(true);
    // Simulate API call
    setTimeout(() => {
      setLoading(false);
    }, 500);
  };

  const getStatusColor = (efficiency) => {
    if (efficiency >= 80) return 'high';
    if (efficiency >= 60) return 'medium';
    return 'low';
  };

  const getSeverityIcon = (severity) => {
    switch (severity) {
      case 'high': return '🔴';
      case 'medium': return '🟡';
      case 'low': return '🟢';
      default: return '⚪';
    }
  };

  const handleBottleneckClick = (bottleneck) => {
    setSelectedBottleneck(bottleneck);
    setShowDrilldownModal(true);
  };

  const handleCloseDrilldown = () => {
    setShowDrilldownModal(false);
    setSelectedBottleneck(null);
  };

  const handleCreateTask = (loan) => {
    const assignee = loan.processor || loan.assignedTo;
    alert(`Creating task for ${assignee} to follow up on loan ${loan.loanNumber} for borrower ${loan.borrowerName}`);
    // In production, this would call the AI task creation API
  };

  const handleTeamMemberClick = (member) => {
    setSelectedTeamMember(member);
    setShowTeamDrilldown(true);
  };

  const handleCloseTeamDrilldown = () => {
    setShowTeamDrilldown(false);
    setSelectedTeamMember(null);
  };

  const handleStageClick = (stage) => {
    setSelectedStage(stage);
    setShowStageDrilldown(true);
  };

  const handleCloseStageDrilldown = () => {
    setShowStageDrilldown(false);
    setSelectedStage(null);
  };

  const getStatusColorClass = (status) => {
    switch (status) {
      case 'On Track': return 'status-on-track';
      case 'Ready to Close': return 'status-on-track';
      case 'Scheduled': return 'status-scheduled';
      case 'Needs Attention': return 'status-warning';
      case 'Needs Review': return 'status-warning';
      case 'Delayed': return 'status-danger';
      case 'Suspended': return 'status-danger';
      default: return 'status-default';
    }
  };

  const formatCurrency = (amount) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0
    }).format(amount);
  };

  if (loading) {
    return (
      <div className="efficiency-page">
        <div className="loading-spinner">Loading efficiency data...</div>
      </div>
    );
  }

  return (
    <div className="efficiency-page">
      {/* Header */}
      <div className="efficiency-header">
        <div className="header-left">
          <button className="btn-back" onClick={() => navigate('/dashboard')}>
            ← Back to Dashboard
          </button>
          <h1>Pipeline Efficiency Report</h1>
          <p className="last-updated">Last updated: {new Date(efficiencyData.lastUpdated).toLocaleString()}</p>
        </div>
        <div className="header-right">
          <select
            className="time-range-selector"
            value={timeRange}
            onChange={(e) => setTimeRange(e.target.value)}
          >
            <option value="7days">Last 7 Days</option>
            <option value="30days">Last 30 Days</option>
            <option value="90days">Last 90 Days</option>
            <option value="year">Last Year</option>
          </select>
          <button className="btn-export">Export Report</button>
        </div>
      </div>

      {/* Overall Score Card */}
      <div className="efficiency-score-card">
        <div className="score-display">
          <div className="score-number-large">{efficiencyData.overallScore}</div>
          <div className="score-label-large">Overall Pipeline Efficiency</div>
          <div className={`score-trend-large ${efficiencyData.trend >= 0 ? 'up' : 'down'}`}>
            {efficiencyData.trend >= 0 ? '↑' : '↓'} {Math.abs(efficiencyData.trend)}% vs. last period
          </div>
        </div>

        {/* Key Metrics Row */}
        <div className="key-metrics-grid">
          <div className="metric-card">
            <div className="metric-label">Avg. Time to Close</div>
            <div className="metric-value">{efficiencyData.keyMetrics.avgTimeToClose} days</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.avgTimeToCloseChange < 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.avgTimeToCloseChange < 0 ? '↓' : '↑'} {Math.abs(efficiencyData.keyMetrics.avgTimeToCloseChange)} days
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Pull-Through Rate</div>
            <div className="metric-value">{efficiencyData.keyMetrics.pullThroughRate}%</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.pullThroughRateChange >= 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.pullThroughRateChange >= 0 ? '↑' : '↓'} {Math.abs(efficiencyData.keyMetrics.pullThroughRateChange)}%
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Loans Falling Behind</div>
            <div className="metric-value">{efficiencyData.keyMetrics.loansFallingBehind}</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.loansFallingBehindChange < 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.loansFallingBehindChange < 0 ? '↓' : '↑'} {Math.abs(efficiencyData.keyMetrics.loansFallingBehindChange)}
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Automation Rate</div>
            <div className="metric-value">{efficiencyData.keyMetrics.automationRate}%</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.automationRateChange >= 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.automationRateChange >= 0 ? '↑' : '↓'} {Math.abs(efficiencyData.keyMetrics.automationRateChange)}%
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-label">Customer Satisfaction</div>
            <div className="metric-value">{efficiencyData.keyMetrics.customerSatisfaction}/5.0</div>
            <div className={`metric-change ${efficiencyData.keyMetrics.customerSatisfactionChange >= 0 ? 'positive' : 'negative'}`}>
              {efficiencyData.keyMetrics.customerSatisfactionChange >= 0 ? '↑' : '↓'} {Math.abs(efficiencyData.keyMetrics.customerSatisfactionChange)}
            </div>
          </div>
        </div>
      </div>

      {/* Main Content Grid */}
      <div className="efficiency-content-grid">

        {/* Stage Performance Section */}
        <div className="efficiency-section stage-performance">
          <h2>Stage Performance Analysis</h2>
          <div className="stage-table">
            <table>
              <thead>
                <tr>
                  <th>Stage</th>
                  <th>Efficiency</th>
                  <th>Avg. Time</th>
                  <th>Conv. Rate</th>
                  <th>Volume</th>
                  <th>Bottlenecks</th>
                  <th>Trend</th>
                </tr>
              </thead>
              <tbody>
                {efficiencyData.stageMetrics.map((stage, idx) => (
                  <tr
                    key={idx}
                    className="stage-row clickable"
                    onClick={() => handleStageClick(stage)}
                    style={{ cursor: 'pointer' }}
                  >
                    <td className="stage-name">{stage.name}</td>
                    <td>
                      <div className="efficiency-cell">
                        <div className={`efficiency-badge ${getStatusColor(stage.efficiency)}`}>
                          {stage.efficiency}%
                        </div>
                      </div>
                    </td>
                    <td>{stage.avgTime}</td>
                    <td>{stage.conversionRate}%</td>
                    <td>{stage.volume}</td>
                    <td>
                      <span className={`bottleneck-count ${stage.bottlenecks > 0 ? 'has-issues' : 'no-issues'}`}>
                        {stage.bottlenecks}
                      </span>
                    </td>
                    <td>
                      <span className={`trend-indicator ${stage.trend >= 0 ? 'positive' : 'negative'}`}>
                        {stage.trend >= 0 ? '↑' : '↓'} {Math.abs(stage.trend)}%
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Team Performance Section */}
        <div className="efficiency-section team-performance">
          <h2>Team Performance Metrics</h2>
          <div className="team-cards">
            {efficiencyData.teamMetrics.map((member, idx) => (
              <div
                key={idx}
                className="team-performance-card clickable"
                onClick={() => handleTeamMemberClick(member)}
                style={{ cursor: 'pointer' }}
              >
                <div className="team-card-header">
                  <h3>{member.role}</h3>
                  <div className={`efficiency-score ${getStatusColor(member.efficiency)}`}>
                    {member.efficiency}%
                  </div>
                </div>
                <div className="team-card-metrics">
                  <div className="team-metric">
                    <span className="team-metric-label">Active Loans:</span>
                    <span className="team-metric-value">{member.activeLoans}</span>
                  </div>
                  <div className="team-metric">
                    <span className="team-metric-label">Avg Response:</span>
                    <span className="team-metric-value">{member.avgResponseTime}</span>
                  </div>
                  <div className="team-metric">
                    <span className="team-metric-label">Task Completion:</span>
                    <span className="team-metric-value">{member.taskCompletionRate}%</span>
                  </div>
                </div>
                <div className={`team-trend ${member.trend >= 0 ? 'positive' : 'negative'}`}>
                  {member.trend >= 0 ? '↑' : '↓'} {Math.abs(member.trend)}% vs. last period
                </div>
                <div className="click-to-view-team">
                  Click to view active loans →
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Bottlenecks Section */}
        <div className="efficiency-section bottlenecks-section">
          <h2>Active Bottlenecks & Recommendations</h2>
          <div className="bottlenecks-list">
            {efficiencyData.bottlenecks.map((bottleneck) => (
              <div
                key={bottleneck.id}
                className={`bottleneck-card severity-${bottleneck.severity} clickable`}
                onClick={() => handleBottleneckClick(bottleneck)}
                style={{ cursor: 'pointer' }}
              >
                <div className="bottleneck-header">
                  <div className="bottleneck-title">
                    <span className="severity-icon">{getSeverityIcon(bottleneck.severity)}</span>
                    <h3>{bottleneck.issue}</h3>
                  </div>
                  <div className="bottleneck-stage">{bottleneck.stage}</div>
                </div>
                <div className="bottleneck-details">
                  <div className="bottleneck-stat">
                    <span className="stat-label">Affected Loans:</span>
                    <span className="stat-value">{bottleneck.affectedLoans}</span>
                  </div>
                  <div className="bottleneck-stat">
                    <span className="stat-label">Avg. Delay:</span>
                    <span className="stat-value">{bottleneck.avgDelay}</span>
                  </div>
                </div>
                <div className="bottleneck-action">
                  <strong>Suggested Action:</strong> {bottleneck.suggestedAction}
                </div>
                <div className="click-to-view">
                  Click to view affected loans →
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Performance Trends Chart */}
        <div className="efficiency-section trends-section">
          <h2>Efficiency Trends (Last 12 Weeks)</h2>
          <div className="trends-chart">
            <div className="chart-container">
              {efficiencyData.trends.map((trend, idx) => (
                <div key={idx} className="chart-bar-group">
                  <div className="chart-bars">
                    <div
                      className="chart-bar score-bar"
                      style={{ height: `${trend.score}%` }}
                      title={`Efficiency: ${trend.score}%`}
                    ></div>
                    <div
                      className="chart-bar volume-bar"
                      style={{ height: `${(trend.volume / 50) * 100}%` }}
                      title={`Volume: ${trend.volume}`}
                    ></div>
                  </div>
                  <div className="chart-label">{trend.week.replace('Week ', 'W')}</div>
                </div>
              ))}
            </div>
            <div className="chart-legend">
              <div className="legend-item">
                <div className="legend-color score-color"></div>
                <span>Efficiency Score</span>
              </div>
              <div className="legend-item">
                <div className="legend-color volume-color"></div>
                <span>Loan Volume</span>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Drill-down Modal */}
      {showDrilldownModal && selectedBottleneck && (
        <div className="drilldown-modal-overlay" onClick={handleCloseDrilldown}>
          <div className="drilldown-modal" onClick={(e) => e.stopPropagation()}>
            <div className="drilldown-header">
              <div>
                <h2>{selectedBottleneck.issue}</h2>
                <p className="drilldown-subtitle">
                  {selectedBottleneck.stage} • {selectedBottleneck.affectedLoans} Affected Loans
                </p>
              </div>
              <button className="btn-close-modal" onClick={handleCloseDrilldown}>
                ✕
              </button>
            </div>

            <div className="drilldown-content">
              {affectedLoansData[selectedBottleneck.id] ? (
                <div className="affected-loans-list">
                  {affectedLoansData[selectedBottleneck.id].map((loan) => (
                    <div key={loan.id} className="affected-loan-card">
                      <div className="loan-card-header">
                        <div>
                          <h3>{loan.borrowerName}</h3>
                          <p className="loan-number">{loan.loanNumber}</p>
                        </div>
                        <div className="loan-amount">{formatCurrency(loan.loanAmount)}</div>
                      </div>

                      <div className="loan-card-info">
                        <div className="loan-info-row">
                          <span className="info-label">Current Stage:</span>
                          <span className="info-value">{loan.currentStage}</span>
                        </div>
                        <div className="loan-info-row">
                          <span className="info-label">Assigned Processor:</span>
                          <span className="info-value">{loan.processor}</span>
                        </div>
                        <div className="loan-info-row">
                          <span className="info-label">Days Delayed:</span>
                          <span className="info-value delay-warning">{loan.daysDelayed} days</span>
                        </div>
                      </div>

                      <div className="missing-items-section">
                        <h4>Missing Items:</h4>
                        <ul className="missing-items-list">
                          {loan.missingItems.map((item, idx) => (
                            <li key={idx}>{item}</li>
                          ))}
                        </ul>
                      </div>

                      <div className="loan-card-actions">
                        <button
                          className="btn-create-task"
                          onClick={() => handleCreateTask(loan)}
                        >
                          🤖 Create AI Task for {loan.processor}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-data">
                  <p>No detailed loan data available for this bottleneck.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Team Member Drill-down Modal */}
      {showTeamDrilldown && selectedTeamMember && (
        <div className="drilldown-modal-overlay" onClick={handleCloseTeamDrilldown}>
          <div className="drilldown-modal" onClick={(e) => e.stopPropagation()}>
            <div className="drilldown-header">
              <div>
                <h2>{selectedTeamMember.role} - Active Loans</h2>
                <p className="drilldown-subtitle">
                  {selectedTeamMember.activeLoans} Active Loans • {selectedTeamMember.efficiency}% Efficiency
                </p>
              </div>
              <button className="btn-close-modal" onClick={handleCloseTeamDrilldown}>
                ✕
              </button>
            </div>

            <div className="drilldown-content">
              {teamMemberLoansData[selectedTeamMember.role] ? (
                <div className="affected-loans-list">
                  {teamMemberLoansData[selectedTeamMember.role].map((loan) => (
                    <div key={loan.id} className="affected-loan-card team-loan-card">
                      <div className="loan-card-header">
                        <div>
                          <h3>{loan.borrowerName}</h3>
                          <p className="loan-number">{loan.loanNumber}</p>
                        </div>
                        <div className="loan-amount">{formatCurrency(loan.loanAmount)}</div>
                      </div>

                      <div className="loan-card-info">
                        <div className="loan-info-row">
                          <span className="info-label">Current Stage:</span>
                          <span className="info-value">{loan.currentStage}</span>
                        </div>
                        <div className="loan-info-row">
                          <span className="info-label">Assigned To:</span>
                          <span className="info-value">{loan.assignedTo}</span>
                        </div>
                        <div className="loan-info-row">
                          <span className="info-label">Days in Stage:</span>
                          <span className="info-value">{loan.daysInStage} days</span>
                        </div>
                        <div className="loan-info-row">
                          <span className="info-label">Status:</span>
                          <span className={`info-value loan-status ${getStatusColorClass(loan.status)}`}>
                            {loan.status}
                          </span>
                        </div>
                      </div>

                      <div className="loan-card-actions">
                        <button
                          className="btn-create-task"
                          onClick={() => handleCreateTask(loan)}
                        >
                          🤖 Create AI Task for {loan.assignedTo}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-data">
                  <p>No active loans data available for {selectedTeamMember.role}.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Stage Drill-down Modal */}
      {showStageDrilldown && selectedStage && stageLoansData[selectedStage.name] && (
        <div className="drilldown-modal-overlay" onClick={handleCloseStageDrilldown}>
          <div className="drilldown-modal stage-drilldown-modal" onClick={(e) => e.stopPropagation()}>
            <div className="drilldown-header">
              <div>
                <h2>{selectedStage.name}</h2>
                <p className="drilldown-subtitle">
                  {stageLoansData[selectedStage.name].length} Active Loans •
                  {selectedStage.efficiency}% Efficiency •
                  Avg. {selectedStage.avgTime}
                </p>
              </div>
              <button className="btn-close-modal" onClick={handleCloseStageDrilldown}>×</button>
            </div>
            <div className="drilldown-content">
              {stageLoansData[selectedStage.name] && stageLoansData[selectedStage.name].length > 0 ? (
                <div className="affected-loans-list">
                  {stageLoansData[selectedStage.name].map((loan) => (
                    <div key={loan.id} className="affected-loan-card stage-loan-card">
                      <div className="loan-card-header">
                        <div>
                          <h3>{loan.borrowerName}</h3>
                          <p className="loan-number">{loan.loanNumber}</p>
                        </div>
                        <div className="loan-amount">{formatCurrency(loan.loanAmount)}</div>
                      </div>

                      <div className="loan-card-info">
                        <div className="loan-info-row">
                          <span className="info-label">Assigned To:</span>
                          <span className="info-value">
                            {loan.assignedTo || loan.processor || loan.underwriter || loan.closer}
                          </span>
                        </div>
                        <div className="loan-info-row">
                          <span className="info-label">Days in Stage:</span>
                          <span className={`info-value ${loan.daysInStage > 7 ? 'delay-warning' : ''}`}>
                            {loan.daysInStage} days
                          </span>
                        </div>
                        <div className="loan-info-row">
                          <span className="info-label">Status:</span>
                          <span className={`info-value loan-status ${getStatusColorClass(loan.status)}`}>
                            {loan.status}
                          </span>
                        </div>

                        {/* Stage-specific fields */}
                        {loan.source && (
                          <div className="loan-info-row">
                            <span className="info-label">Source:</span>
                            <span className="info-value">{loan.source}</span>
                          </div>
                        )}
                        {loan.creditScore && (
                          <div className="loan-info-row">
                            <span className="info-label">Credit Score:</span>
                            <span className="info-value">{loan.creditScore}</span>
                          </div>
                        )}
                        {loan.conditions && (
                          <div className="loan-info-row">
                            <span className="info-label">Conditions:</span>
                            <span className="info-value">{loan.conditions} outstanding</span>
                          </div>
                        )}
                        {loan.closingDate && (
                          <div className="loan-info-row">
                            <span className="info-label">Closing Date:</span>
                            <span className="info-value">{loan.closingDate}</span>
                          </div>
                        )}
                      </div>

                      {/* Missing docs or last activity */}
                      {loan.missingDocs && (
                        <div className="missing-items-section">
                          <h4>Missing Documents</h4>
                          <p style={{ margin: 0, color: '#e53e3e', fontSize: '14px' }}>{loan.missingDocs}</p>
                        </div>
                      )}

                      <div style={{
                        marginTop: '12px',
                        padding: '12px',
                        background: '#f7fafc',
                        borderRadius: '6px',
                        fontSize: '13px',
                        color: '#4a5568'
                      }}>
                        <strong>Last Activity:</strong> {loan.lastActivity}
                      </div>

                      <div className="loan-card-actions">
                        <button
                          className="btn-create-task"
                          onClick={() => handleCreateTask(loan)}
                        >
                          🤖 Create AI Task for {loan.assignedTo || loan.processor || loan.underwriter || loan.closer}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="no-data">
                  <p>No active loans in {selectedStage.name} stage.</p>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default PipelineEfficiency;

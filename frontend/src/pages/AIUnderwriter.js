import React, { useState, useRef, useEffect, useCallback } from 'react';
import { aiAPI, API_BASE_URL } from '../services/api';
import { getCurrentUserId } from '../utils/auth';
import GuidelineUpdatesSidebar from '../components/GuidelineUpdatesSidebar';
import GuidelineNotificationBadge from '../components/GuidelineNotificationBadge';
import EscalationPanel from '../components/EscalationPanel';
import './AIUnderwriter.css';
import { toast } from '../utils/toast';

// View modes
const VIEW_MODES = [
  { id: 'chat', label: 'AI Chat', icon: '💬' },
  { id: 'file-analysis', label: 'Smart File Analysis', icon: '📁' },
  { id: 'applicants', label: 'Applicants', icon: '👥' },
];

// Guideline categories
const GUIDELINE_CATEGORIES = [
  { id: 'all', label: 'All Guidelines', icon: '📋' },
  { id: 'conventional', label: 'Conventional', icon: '🏠' },
  { id: 'fha', label: 'FHA', icon: '🏛️' },
  { id: 'va', label: 'VA', icon: '🎖️' },
  { id: 'usda', label: 'USDA', icon: '🌾' },
  { id: 'jumbo', label: 'Jumbo', icon: '💎' },
  { id: 'non-qm', label: 'Non-QM', icon: '📊' },
];

function AIUnderwriter() {
  // View mode state
  const [viewMode, setViewMode] = useState('chat');

  // File analysis state
  const [loanSearchQuery, setLoanSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [selectedLoan, setSelectedLoan] = useState(null);
  const [fileAnalysis, setFileAnalysis] = useState(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [pipelineReadiness, setPipelineReadiness] = useState(null);
  const [isLoadingPipeline, setIsLoadingPipeline] = useState(false);

  // Applicants tab state
  const [applicants, setApplicants] = useState([]);
  const [selectedApplicant, setSelectedApplicant] = useState(null);
  const [isLoadingApplicants, setIsLoadingApplicants] = useState(false);
  const [applicantDetails, setApplicantDetails] = useState(null);
  const [isLoadingDetails, setIsLoadingDetails] = useState(false);
  const [applicantSearchQuery, setApplicantSearchQuery] = useState('');

  // Chat state
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: 'Hello! I\'m your Smart AI Underwriter with memory. I remember our previous conversations and can answer mortgage lending questions by searching current guidelines. I learn from our interactions to provide better answers over time. Just ask me anything!',
      timestamp: new Date(),
    },
  ]);
  const [inputMessage, setInputMessage] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [memoryStats, setMemoryStats] = useState(null);
  const [currentUserId, setCurrentUserId] = useState(null);
  const [isListening, setIsListening] = useState(false);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [showScenarioBuilder, setShowScenarioBuilder] = useState(false);
  const [scenario, setScenario] = useState({
    loanType: 'conventional',
    creditScore: '',
    ltv: '',
    dti: '',
    loanAmount: '',
    propertyValue: '',
    occupancy: 'primary',
    propertyType: 'single-family',
    incomeType: 'w2',
    reserves: '',
    // Calculator fields
    monthlyIncome: '',
    monthlyDebt: '',
    proposedPayment: '',
  });
  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);

  // File Analysis Functions
  const searchLoans = useCallback(async () => {
    if (!loanSearchQuery.trim()) return;
    setIsSearching(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/loans/search?q=${encodeURIComponent(loanSearchQuery)}&limit=10`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setSearchResults(data.loans || data || []);
      }
    } catch (error) {
      console.error('Error searching loans:', error);
    } finally {
      setIsSearching(false);
    }
  }, [loanSearchQuery]);

  const analyzeFile = useCallback(async (loanId) => {
    setIsAnalyzing(true);
    setFileAnalysis(null);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/ai-file-analysis/analyze/${loanId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setFileAnalysis(data);
      }
    } catch (error) {
      console.error('Error analyzing file:', error);
      setFileAnalysis({ error: 'Failed to analyze loan file. Please try again.' });
    } finally {
      setIsAnalyzing(false);
    }
  }, []);

  const loadPipelineReadiness = useCallback(async () => {
    setIsLoadingPipeline(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/ai-file-analysis/pipeline-readiness?limit=15`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setPipelineReadiness(data);
      }
    } catch (error) {
      console.error('Error loading pipeline readiness:', error);
    } finally {
      setIsLoadingPipeline(false);
    }
  }, []);

  // Applicants Functions
  const loadApplicants = useCallback(async () => {
    setIsLoadingApplicants(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/loans?limit=50&include_borrower=true`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setApplicants(data.loans || data || []);
      }
    } catch (error) {
      console.error('Error loading applicants:', error);
    } finally {
      setIsLoadingApplicants(false);
    }
  }, []);

  const loadApplicantDetails = useCallback(async (loanId) => {
    setIsLoadingDetails(true);
    setApplicantDetails(null);
    try {
      // Fetch loan details with all related data
      const response = await fetch(`${API_BASE_URL}/api/v1/loans/${loanId}`, {
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
        },
      });
      if (response.ok) {
        const data = await response.json();
        setApplicantDetails(data);
      }
    } catch (error) {
      console.error('Error loading applicant details:', error);
      setApplicantDetails({ error: 'Failed to load applicant details' });
    } finally {
      setIsLoadingDetails(false);
    }
  }, []);

  const handleApplicantSelect = (applicant) => {
    setSelectedApplicant(applicant);
    loadApplicantDetails(applicant.id);
  };

  const filteredApplicants = applicants.filter(applicant => {
    if (!applicantSearchQuery.trim()) return true;
    const query = applicantSearchQuery.toLowerCase();
    const name = (applicant.borrower_name || '').toLowerCase();
    const loanNumber = (applicant.loan_number || '').toLowerCase();
    const address = (applicant.property_address || '').toLowerCase();
    return name.includes(query) || loanNumber.includes(query) || address.includes(query);
  });

  // Load pipeline readiness when switching to file analysis mode
  useEffect(() => {
    if (viewMode === 'file-analysis' && !pipelineReadiness) {
      loadPipelineReadiness();
    }
  }, [viewMode, pipelineReadiness, loadPipelineReadiness]);

  // Load applicants when switching to applicants mode
  useEffect(() => {
    if (viewMode === 'applicants' && applicants.length === 0) {
      loadApplicants();
    }
  }, [viewMode, applicants.length, loadApplicants]);

  const handleLoanSelect = (loan) => {
    setSelectedLoan(loan);
    setFileAnalysis(null);
    analyzeFile(loan.id);
  };

  const getGradeColor = (grade) => {
    switch (grade) {
      case 'A': return '#10b981';
      case 'B': return '#3b82f6';
      case 'C': return '#f59e0b';
      case 'D': return '#ef4444';
      case 'F': return '#dc2626';
      default: return '#6b7280';
    }
  };

  const getSeverityColor = (severity) => {
    switch (severity) {
      case 'critical': return '#dc2626';
      case 'high': return '#ef4444';
      case 'medium': return '#f59e0b';
      default: return '#6b7280';
    }
  };

  // Initialize speech recognition
  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onresult = (event) => {
        const transcript = Array.from(event.results)
          .map(result => result[0].transcript)
          .join('');
        setInputMessage(transcript);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.onerror = (event) => {
        console.error('Speech recognition error:', event.error);
        setIsListening(false);
      };

      recognitionRef.current = recognition;
    }

    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      toast.error('Speech recognition is not supported in your browser. Please use Chrome or Edge.');
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      setInputMessage('');
      recognitionRef.current.start();
      setIsListening(true);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    loadMemoryStats();
    loadCurrentUser();
  }, []);

  const loadCurrentUser = () => {
    const userId = getCurrentUserId();
    setCurrentUserId(userId || 1);
  };

  const loadMemoryStats = async () => {
    try {
      const stats = await aiAPI.getMemoryStats();
      setMemoryStats(stats);
    } catch (error) {
      console.error('Failed to load memory stats:', error);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!inputMessage.trim() || isLoading) return;

    // Add category context to the question
    const categoryContext = selectedCategory !== 'all'
      ? `[${GUIDELINE_CATEGORIES.find(c => c.id === selectedCategory)?.label} Guidelines] `
      : '';

    const userMessage = {
      role: 'user',
      content: inputMessage,
      category: selectedCategory,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInputMessage('');
    setIsLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/ai-underwriter/ask`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          question: categoryContext + inputMessage,
          category: selectedCategory,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to get answer');
      }

      const data = await response.json();

      const assistantMessage = {
        role: 'assistant',
        content: data.answer,
        sources: data.sources || [],
        confidence: data.confidence,
        category: selectedCategory,
        timestamp: new Date(),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error('Error asking question:', error);
      const errorMessage = {
        role: 'assistant',
        content: 'Sorry, I encountered an error while searching for that information. Please try again.',
        timestamp: new Date(),
        isError: true,
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // Calculate DTI
  const calculateDTI = () => {
    const monthlyIncome = parseFloat(scenario.monthlyIncome) || 0;
    const monthlyDebt = parseFloat(scenario.monthlyDebt) || 0;
    const proposedPayment = parseFloat(scenario.proposedPayment) || 0;

    if (monthlyIncome === 0) return { frontEnd: 0, backEnd: 0 };

    const frontEnd = ((proposedPayment / monthlyIncome) * 100).toFixed(2);
    const backEnd = (((monthlyDebt + proposedPayment) / monthlyIncome) * 100).toFixed(2);

    return { frontEnd, backEnd };
  };

  // Calculate LTV
  const calculateLTV = () => {
    const loanAmount = parseFloat(scenario.loanAmount) || 0;
    const propertyValue = parseFloat(scenario.propertyValue) || 0;

    if (propertyValue === 0) return 0;
    return ((loanAmount / propertyValue) * 100).toFixed(2);
  };

  // Generate scenario question
  const generateScenarioQuestion = () => {
    const ltv = calculateLTV();
    const parts = [];

    parts.push(`I have a ${scenario.loanType.toUpperCase()} loan scenario:`);
    if (scenario.creditScore) parts.push(`Credit Score: ${scenario.creditScore}`);
    if (ltv > 0) parts.push(`LTV: ${ltv}%`);
    if (scenario.dti) parts.push(`DTI: ${scenario.dti}%`);
    if (scenario.loanAmount) parts.push(`Loan Amount: $${parseFloat(scenario.loanAmount).toLocaleString()}`);
    parts.push(`Occupancy: ${scenario.occupancy}`);
    parts.push(`Property Type: ${scenario.propertyType}`);
    if (scenario.incomeType) parts.push(`Income Type: ${scenario.incomeType}`);

    parts.push('\nDoes this scenario meet guidelines? What are the key requirements and any potential issues?');

    return parts.join('\n');
  };

  const handleScenarioSubmit = () => {
    const question = generateScenarioQuestion();
    setInputMessage(question);
    setSelectedCategory(scenario.loanType);
    setShowScenarioBuilder(false);
  };

  // Category-specific suggested questions
  const suggestedQuestionsByCategory = {
    all: [
      'What are the minimum credit score requirements for each loan type?',
      'Compare DTI limits across FHA, VA, and Conventional loans',
      'What documentation is required for self-employed borrowers?',
      'What are the reserve requirements for investment properties?',
      'What are the key differences between FHA and Conventional loans?',
    ],
    conventional: [
      'What are the minimum credit score requirements for conventional loans?',
      'What is the maximum DTI ratio for conventional loans?',
      'What are the LTV limits for conventional cash-out refinances?',
      'What are Fannie Mae reserve requirements?',
      'What are the income documentation requirements for conventional loans?',
    ],
    fha: [
      'What is the minimum credit score for FHA loans?',
      'What are FHA DTI limits and compensating factors?',
      'What is the FHA UFMIP and annual MIP?',
      'What are FHA property requirements?',
      'Can FHA loans be used for investment properties?',
    ],
    va: [
      'What are VA loan eligibility requirements?',
      'Does VA have a minimum credit score requirement?',
      'What is the VA funding fee structure?',
      'What are VA residual income requirements?',
      'Can VA loans be used for manufactured homes?',
    ],
    usda: [
      'What are USDA income limits?',
      'What areas are eligible for USDA loans?',
      'What is the USDA guarantee fee?',
      'What credit score is needed for USDA loans?',
      'What are USDA property requirements?',
    ],
    jumbo: [
      'What is the current jumbo loan limit?',
      'What credit score is needed for jumbo loans?',
      'What are typical jumbo loan reserve requirements?',
      'What DTI limits apply to jumbo loans?',
      'What are the LTV limits for jumbo loans?',
    ],
    'non-qm': [
      'What is a Non-QM loan?',
      'What are bank statement loan requirements?',
      'What is a DSCR loan and how does it qualify?',
      'What credit scores are accepted for Non-QM loans?',
      'What are asset depletion loan requirements?',
    ],
  };

  const suggestedQuestions = suggestedQuestionsByCategory[selectedCategory] || suggestedQuestionsByCategory.all;

  const handleSuggestedQuestion = (question) => {
    setInputMessage(question);
  };

  return (
    <div className="ai-underwriter-page">
      <div className="underwriter-header">
        <div className="header-content">
          <h1>
            🧠 Smart AI Underwriter
            <GuidelineNotificationBadge userId={currentUserId || 1} />
          </h1>
          <p className="subtitle">
            {viewMode === 'chat'
              ? 'Ask any mortgage lending question and get answers with sources'
              : 'AI-powered loan file analysis to catch issues before submission'}
          </p>
          {viewMode === 'chat' && memoryStats && (
            <div className="memory-stats-badge">
              💾 {memoryStats.total_memories} conversations remembered
            </div>
          )}
        </div>
      </div>

      {/* View Mode Toggle */}
      <div className="view-mode-container">
        <div className="view-mode-tabs">
          {VIEW_MODES.map((mode) => (
            <button
              key={mode.id}
              className={`view-mode-tab ${viewMode === mode.id ? 'active' : ''}`}
              onClick={() => setViewMode(mode.id)}
            >
              <span className="mode-icon">{mode.icon}</span>
              <span className="mode-label">{mode.label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* Chat View */}
      {viewMode === 'chat' && (
        <>
          {/* Category Tabs */}
          <div className="category-tabs-container">
            <div className="category-tabs">
              {GUIDELINE_CATEGORIES.map((category) => (
                <button
                  key={category.id}
                  className={`category-tab ${selectedCategory === category.id ? 'active' : ''}`}
                  onClick={() => setSelectedCategory(category.id)}
                >
                  <span className="category-icon">{category.icon}</span>
                  <span className="category-label">{category.label}</span>
                </button>
              ))}
            </div>
            <button
              className="scenario-builder-toggle"
              onClick={() => setShowScenarioBuilder(!showScenarioBuilder)}
            >
              {showScenarioBuilder ? '✕ Close' : '📝 Scenario Builder'}
            </button>
          </div>

      {/* Scenario Builder Modal */}
      {showScenarioBuilder && (
        <div className="scenario-builder-panel">
          <div className="scenario-builder-content">
            <h3>📝 Loan Scenario Builder</h3>
            <p className="scenario-description">
              Enter loan details to analyze against guidelines
            </p>

            <div className="scenario-form">
              <div className="scenario-row">
                <div className="scenario-field">
                  <label>Loan Type</label>
                  <select
                    value={scenario.loanType}
                    onChange={(e) => setScenario({ ...scenario, loanType: e.target.value })}
                  >
                    <option value="conventional">Conventional</option>
                    <option value="fha">FHA</option>
                    <option value="va">VA</option>
                    <option value="usda">USDA</option>
                    <option value="jumbo">Jumbo</option>
                    <option value="non-qm">Non-QM</option>
                  </select>
                </div>
                <div className="scenario-field">
                  <label>Credit Score</label>
                  <input
                    type="number"
                    placeholder="e.g., 720"
                    value={scenario.creditScore}
                    onChange={(e) => setScenario({ ...scenario, creditScore: e.target.value })}
                  />
                </div>
              </div>

              <div className="scenario-row">
                <div className="scenario-field">
                  <label>Loan Amount</label>
                  <input
                    type="number"
                    placeholder="e.g., 350000"
                    value={scenario.loanAmount}
                    onChange={(e) => setScenario({ ...scenario, loanAmount: e.target.value })}
                  />
                </div>
                <div className="scenario-field">
                  <label>Property Value</label>
                  <input
                    type="number"
                    placeholder="e.g., 400000"
                    value={scenario.propertyValue}
                    onChange={(e) => setScenario({ ...scenario, propertyValue: e.target.value })}
                  />
                </div>
              </div>

              <div className="scenario-row">
                <div className="scenario-field">
                  <label>DTI %</label>
                  <input
                    type="number"
                    placeholder="e.g., 43"
                    value={scenario.dti}
                    onChange={(e) => setScenario({ ...scenario, dti: e.target.value })}
                  />
                </div>
                <div className="scenario-field">
                  <label>Occupancy</label>
                  <select
                    value={scenario.occupancy}
                    onChange={(e) => setScenario({ ...scenario, occupancy: e.target.value })}
                  >
                    <option value="primary">Primary Residence</option>
                    <option value="second-home">Second Home</option>
                    <option value="investment">Investment Property</option>
                  </select>
                </div>
              </div>

              <div className="scenario-row">
                <div className="scenario-field">
                  <label>Property Type</label>
                  <select
                    value={scenario.propertyType}
                    onChange={(e) => setScenario({ ...scenario, propertyType: e.target.value })}
                  >
                    <option value="single-family">Single Family</option>
                    <option value="condo">Condo</option>
                    <option value="townhouse">Townhouse</option>
                    <option value="2-4-unit">2-4 Unit</option>
                    <option value="manufactured">Manufactured</option>
                  </select>
                </div>
                <div className="scenario-field">
                  <label>Income Type</label>
                  <select
                    value={scenario.incomeType}
                    onChange={(e) => setScenario({ ...scenario, incomeType: e.target.value })}
                  >
                    <option value="w2">W-2 Employee</option>
                    <option value="self-employed">Self-Employed</option>
                    <option value="commission">Commission</option>
                    <option value="pension">Pension/Retirement</option>
                    <option value="rental">Rental Income</option>
                  </select>
                </div>
              </div>

              {/* Live Calculations Display */}
              <div className="scenario-calculations">
                <div className="calc-item">
                  <span className="calc-label">Calculated LTV:</span>
                  <span className="calc-value">{calculateLTV()}%</span>
                </div>
                {scenario.dti && (
                  <div className="calc-item">
                    <span className="calc-label">DTI:</span>
                    <span className={`calc-value ${parseFloat(scenario.dti) > 50 ? 'warning' : ''}`}>
                      {scenario.dti}%
                    </span>
                  </div>
                )}
              </div>

              <div className="scenario-actions">
                <button
                  className="scenario-analyze-btn"
                  onClick={handleScenarioSubmit}
                >
                  🔍 Analyze Scenario
                </button>
                <button
                  className="scenario-clear-btn"
                  onClick={() => setScenario({
                    loanType: 'conventional',
                    creditScore: '',
                    ltv: '',
                    dti: '',
                    loanAmount: '',
                    propertyValue: '',
                    occupancy: 'primary',
                    propertyType: 'single-family',
                    incomeType: 'w2',
                    reserves: '',
                    monthlyIncome: '',
                    monthlyDebt: '',
                    proposedPayment: '',
                  })}
                >
                  Clear
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      <div className="underwriter-page-container">
        <div className="underwriter-container">
        <div className="messages-container">
          {messages.map((message, index) => (
            <div
              key={index}
              className={`message ${message.role} ${message.isError ? 'error' : ''}`}
            >
              <div className="message-header">
                <span className="message-role">
                  {message.role === 'user' ? 'You' : '🤖 AI Underwriter'}
                </span>
                <span className="message-time">
                  {message.timestamp.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </span>
              </div>
              <div className="message-content">{message.content}</div>
              {message.sources && message.sources.length > 0 && (
                <div className="message-sources">
                  <div className="sources-header">📚 Sources:</div>
                  {message.sources.map((source, idx) => (
                    <a
                      key={idx}
                      href={source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="source-link"
                    >
                      <span className="source-icon">🔗</span>
                      <span className="source-title">{source.title || source.url}</span>
                    </a>
                  ))}
                </div>
              )}
              {message.confidence && (
                <div className="message-confidence">
                  Confidence: {Math.round(message.confidence * 100)}%
                </div>
              )}
            </div>
          ))}
          {isLoading && (
            <div className="message assistant loading-message">
              <div className="message-header">
                <span className="message-role">🤖 AI Underwriter</span>
              </div>
              <div className="message-content">
                <div className="typing-indicator">
                  <span></span>
                  <span></span>
                  <span></span>
                </div>
                Searching guidelines...
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {messages.length === 1 && (
          <div className="suggested-questions">
            <h3>Suggested Questions:</h3>
            <div className="questions-grid">
              {suggestedQuestions.map((question, index) => (
                <button
                  key={index}
                  className="suggested-question-btn"
                  onClick={() => handleSuggestedQuestion(question)}
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        )}

        <form onSubmit={handleSubmit} className="input-form">
          <div className="input-container">
            <button
              type="button"
              className={`voice-button ${isListening ? 'listening' : ''}`}
              onClick={toggleListening}
              disabled={isLoading}
              title={isListening ? 'Stop listening' : 'Speak your question'}
            >
              {isListening ? '🔴' : '🎤'}
            </button>
            <input
              type="text"
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              placeholder={isListening ? 'Listening...' : 'Ask a mortgage lending question...'}
              className={`message-input ${isListening ? 'listening' : ''}`}
              disabled={isLoading}
            />
            <button type="submit" className="send-button" disabled={isLoading || !inputMessage.trim()}>
              {isLoading ? '...' : 'Ask'}
            </button>
          </div>
        </form>
        </div>

        <div className="sidebar-container">
          {/* Quick Calculator Panel */}
          <div className="calculator-panel">
            <h3 className="calculator-panel-title">🧮 Quick Calculators</h3>

            {/* DTI Calculator */}
            <div className="calculator-section">
              <h4>DTI Calculator</h4>
              <div className="calc-inputs">
                <div className="calc-input-group">
                  <label>Monthly Income</label>
                  <input
                    type="number"
                    placeholder="$0"
                    value={scenario.monthlyIncome || ''}
                    onChange={(e) => setScenario({ ...scenario, monthlyIncome: e.target.value })}
                  />
                </div>
                <div className="calc-input-group">
                  <label>Monthly Debts</label>
                  <input
                    type="number"
                    placeholder="$0"
                    value={scenario.monthlyDebt || ''}
                    onChange={(e) => setScenario({ ...scenario, monthlyDebt: e.target.value })}
                  />
                </div>
                <div className="calc-input-group">
                  <label>Proposed PITI</label>
                  <input
                    type="number"
                    placeholder="$0"
                    value={scenario.proposedPayment || ''}
                    onChange={(e) => setScenario({ ...scenario, proposedPayment: e.target.value })}
                  />
                </div>
              </div>
              <div className="calc-results">
                <div className="calc-result-item">
                  <span>Front-End DTI:</span>
                  <span className={`calc-result-value ${parseFloat(calculateDTI().frontEnd) > 31 ? 'warning' : ''}`}>
                    {calculateDTI().frontEnd}%
                  </span>
                </div>
                <div className="calc-result-item">
                  <span>Back-End DTI:</span>
                  <span className={`calc-result-value ${parseFloat(calculateDTI().backEnd) > 43 ? 'warning' : ''}`}>
                    {calculateDTI().backEnd}%
                  </span>
                </div>
              </div>
            </div>

            {/* LTV Calculator */}
            <div className="calculator-section">
              <h4>LTV Calculator</h4>
              <div className="calc-inputs">
                <div className="calc-input-group">
                  <label>Loan Amount</label>
                  <input
                    type="number"
                    placeholder="$0"
                    value={scenario.loanAmount || ''}
                    onChange={(e) => setScenario({ ...scenario, loanAmount: e.target.value })}
                  />
                </div>
                <div className="calc-input-group">
                  <label>Property Value</label>
                  <input
                    type="number"
                    placeholder="$0"
                    value={scenario.propertyValue || ''}
                    onChange={(e) => setScenario({ ...scenario, propertyValue: e.target.value })}
                  />
                </div>
              </div>
              <div className="calc-results">
                <div className="calc-result-item">
                  <span>LTV:</span>
                  <span className={`calc-result-value ${parseFloat(calculateLTV()) > 80 ? 'warning' : ''}`}>
                    {calculateLTV()}%
                  </span>
                </div>
                <div className="calc-result-item">
                  <span>Down Payment:</span>
                  <span className="calc-result-value">
                    ${((parseFloat(scenario.propertyValue) || 0) - (parseFloat(scenario.loanAmount) || 0)).toLocaleString()}
                  </span>
                </div>
              </div>
            </div>

            {/* Quick Reference */}
            <div className="quick-reference">
              <h4>Quick Reference</h4>
              <div className="reference-grid">
                <div className="reference-item">
                  <span className="ref-label">Conv. Max DTI</span>
                  <span className="ref-value">50%</span>
                </div>
                <div className="reference-item">
                  <span className="ref-label">FHA Max DTI</span>
                  <span className="ref-value">56.99%</span>
                </div>
                <div className="reference-item">
                  <span className="ref-label">VA Max DTI</span>
                  <span className="ref-value">None*</span>
                </div>
                <div className="reference-item">
                  <span className="ref-label">Conv. Min Credit</span>
                  <span className="ref-value">620</span>
                </div>
                <div className="reference-item">
                  <span className="ref-label">FHA Min Credit</span>
                  <span className="ref-value">500</span>
                </div>
                <div className="reference-item">
                  <span className="ref-label">Conforming Limit</span>
                  <span className="ref-value">$806,500</span>
                </div>
              </div>
            </div>
          </div>

          <GuidelineUpdatesSidebar userId={currentUserId || 1} />
          <EscalationPanel />
        </div>
      </div>
        </>
      )}

      {/* File Analysis View */}
      {viewMode === 'file-analysis' && (
        <div className="file-analysis-container">
          <div className="file-analysis-main">
            {/* Search and Select Loan */}
            <div className="loan-search-section">
              <h3>Search for a Loan to Analyze</h3>
              <div className="loan-search-form">
                <input
                  type="text"
                  placeholder="Enter loan number or borrower name..."
                  value={loanSearchQuery}
                  onChange={(e) => setLoanSearchQuery(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && searchLoans()}
                  className="loan-search-input"
                />
                <button
                  onClick={searchLoans}
                  disabled={isSearching}
                  className="loan-search-btn"
                >
                  {isSearching ? 'Searching...' : 'Search'}
                </button>
              </div>

              {searchResults.length > 0 && (
                <div className="search-results">
                  {searchResults.map((loan) => (
                    <div
                      key={loan.id}
                      className={`search-result-item ${selectedLoan?.id === loan.id ? 'selected' : ''}`}
                      onClick={() => handleLoanSelect(loan)}
                    >
                      <div className="result-loan-number">{loan.loan_number || `Loan #${loan.id}`}</div>
                      <div className="result-details">
                        <span>{loan.borrower_name || loan.property_address}</span>
                        <span className="result-amount">${(loan.amount || 0).toLocaleString()}</span>
                      </div>
                      <div className="result-stage">{loan.stage}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Analysis Results */}
            {isAnalyzing && (
              <div className="analysis-loading">
                <div className="analysis-spinner"></div>
                <p>Analyzing loan file with AI...</p>
                <p className="analysis-loading-sub">This may take a few moments</p>
              </div>
            )}

            {fileAnalysis && !fileAnalysis.error && (
              <div className="analysis-results">
                {/* Readiness Score */}
                <div className="readiness-header">
                  <div className="readiness-score-container">
                    <div
                      className="readiness-score"
                      style={{ borderColor: getGradeColor(fileAnalysis.readiness_grade) }}
                    >
                      <span className="score-value">{fileAnalysis.readiness_score}</span>
                      <span className="score-label">/ 100</span>
                    </div>
                    <div
                      className="readiness-grade"
                      style={{ backgroundColor: getGradeColor(fileAnalysis.readiness_grade) }}
                    >
                      Grade {fileAnalysis.readiness_grade}
                    </div>
                  </div>
                  <div className="readiness-summary">
                    <h2>File Analysis for {fileAnalysis.loan_number || `Loan #${fileAnalysis.loan_id}`}</h2>
                    <p className="loan-type-badge">{fileAnalysis.loan_type?.toUpperCase() || 'CONVENTIONAL'}</p>
                    <p className="summary-text">{fileAnalysis.summary}</p>
                  </div>
                </div>

                {/* Quick Stats */}
                <div className="analysis-stats">
                  <div className="stat-card">
                    <span className="stat-value">{fileAnalysis.documents_collected}</span>
                    <span className="stat-label">Docs Collected</span>
                  </div>
                  <div className="stat-card warning">
                    <span className="stat-value">{fileAnalysis.missing_documents?.length || 0}</span>
                    <span className="stat-label">Missing Docs</span>
                  </div>
                  <div className="stat-card error">
                    <span className="stat-value">{fileAnalysis.red_flags?.length || 0}</span>
                    <span className="stat-label">Red Flags</span>
                  </div>
                  <div className="stat-card">
                    <span className="stat-value">{fileAnalysis.open_conditions}</span>
                    <span className="stat-label">Open Conditions</span>
                  </div>
                </div>

                {/* Red Flags */}
                {fileAnalysis.red_flags?.length > 0 && (
                  <div className="analysis-section red-flags-section">
                    <h3>Red Flags</h3>
                    <div className="red-flags-list">
                      {fileAnalysis.red_flags.map((flag, index) => (
                        <div
                          key={index}
                          className="red-flag-item"
                          style={{ borderLeftColor: getSeverityColor(flag.severity) }}
                        >
                          <span className="flag-severity" style={{ backgroundColor: getSeverityColor(flag.severity) }}>
                            {flag.severity}
                          </span>
                          <span className="flag-issue">{flag.issue}</span>
                          {flag.recommendation && (
                            <p className="flag-recommendation">{flag.recommendation}</p>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Missing Documents */}
                {fileAnalysis.missing_documents?.length > 0 && (
                  <div className="analysis-section missing-docs-section">
                    <h3>Missing Documents</h3>
                    <div className="missing-docs-grid">
                      {fileAnalysis.missing_documents.map((doc, index) => (
                        <div key={index} className={`missing-doc-item priority-${doc.priority}`}>
                          <span className="doc-category">{doc.category}</span>
                          <span className="doc-name">{doc.document}</span>
                          <span className={`doc-priority priority-${doc.priority}`}>{doc.priority}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Compliance Issues */}
                {fileAnalysis.compliance_issues?.length > 0 && (
                  <div className="analysis-section compliance-section">
                    <h3>Compliance Issues</h3>
                    <div className="compliance-list">
                      {fileAnalysis.compliance_issues.map((issue, index) => (
                        <div key={index} className={`compliance-item severity-${issue.severity}`}>
                          <span className="compliance-type">{issue.type}</span>
                          <span className="compliance-message">{issue.message}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Recommendations */}
                {fileAnalysis.recommendations?.length > 0 && (
                  <div className="analysis-section recommendations-section">
                    <h3>Recommendations</h3>
                    <ul className="recommendations-list">
                      {fileAnalysis.recommendations.map((rec, index) => (
                        <li key={index}>{rec}</li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Next Steps */}
                {fileAnalysis.next_steps?.length > 0 && (
                  <div className="analysis-section next-steps-section">
                    <h3>Immediate Next Steps</h3>
                    <ol className="next-steps-list">
                      {fileAnalysis.next_steps.map((step, index) => (
                        <li key={index}>{step}</li>
                      ))}
                    </ol>
                  </div>
                )}
              </div>
            )}

            {fileAnalysis?.error && (
              <div className="analysis-error">
                <p>{fileAnalysis.error}</p>
              </div>
            )}
          </div>

          {/* Pipeline Readiness Sidebar */}
          <div className="pipeline-readiness-sidebar">
            <h3>Pipeline Readiness</h3>
            <button
              onClick={loadPipelineReadiness}
              disabled={isLoadingPipeline}
              className="refresh-pipeline-btn"
            >
              {isLoadingPipeline ? 'Loading...' : 'Refresh'}
            </button>

            {pipelineReadiness && (
              <>
                <div className="pipeline-summary">
                  <div className="pipeline-stat ready">
                    <span className="count">{pipelineReadiness.summary?.ready || 0}</span>
                    <span className="label">Ready</span>
                  </div>
                  <div className="pipeline-stat almost">
                    <span className="count">{pipelineReadiness.summary?.almost_ready || 0}</span>
                    <span className="label">Almost</span>
                  </div>
                  <div className="pipeline-stat needs-work">
                    <span className="count">{pipelineReadiness.summary?.needs_work || 0}</span>
                    <span className="label">Needs Work</span>
                  </div>
                  <div className="pipeline-stat critical">
                    <span className="count">{pipelineReadiness.summary?.critical || 0}</span>
                    <span className="label">Critical</span>
                  </div>
                </div>

                <div className="pipeline-loans">
                  <h4>Needs Attention</h4>
                  {[...(pipelineReadiness.by_status?.critical || []), ...(pipelineReadiness.by_status?.needs_work || [])].slice(0, 5).map((loan) => (
                    <div
                      key={loan.loan_id}
                      className="pipeline-loan-item"
                      onClick={() => {
                        setSelectedLoan({ id: loan.loan_id, loan_number: loan.loan_number });
                        analyzeFile(loan.loan_id);
                      }}
                    >
                      <div className="loan-info">
                        <span className="loan-num">{loan.loan_number || `#${loan.loan_id}`}</span>
                        <span className="loan-score" style={{ color: getGradeColor(loan.readiness_grade) }}>
                          {loan.readiness_score}
                        </span>
                      </div>
                      {loan.quick_issues?.length > 0 && (
                        <div className="loan-issues">
                          {loan.quick_issues.slice(0, 2).map((issue, i) => (
                            <span key={i} className="issue-chip">{issue}</span>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        </div>
      )}

      {/* Applicants View */}
      {viewMode === 'applicants' && (
        <div className="applicants-container">
          {/* Applicants List Panel */}
          <div className="applicants-list-panel">
            <div className="applicants-list-header">
              <h3>All Applicants</h3>
              <button
                onClick={loadApplicants}
                disabled={isLoadingApplicants}
                className="refresh-applicants-btn"
              >
                {isLoadingApplicants ? 'Loading...' : '🔄 Refresh'}
              </button>
            </div>

            <div className="applicants-search">
              <input
                type="text"
                placeholder="Search by name, loan number, or address..."
                value={applicantSearchQuery}
                onChange={(e) => setApplicantSearchQuery(e.target.value)}
                className="applicants-search-input"
              />
            </div>

            {isLoadingApplicants && (
              <div className="applicants-loading">
                <div className="loading-spinner"></div>
                <p>Loading applicants...</p>
              </div>
            )}

            {!isLoadingApplicants && filteredApplicants.length === 0 && (
              <div className="no-applicants">
                <p>No applicants found</p>
              </div>
            )}

            <div className="applicants-list">
              {filteredApplicants.map((applicant) => (
                <div
                  key={applicant.id}
                  className={`applicant-card ${selectedApplicant?.id === applicant.id ? 'selected' : ''}`}
                  onClick={() => handleApplicantSelect(applicant)}
                >
                  <div className="applicant-card-header">
                    <span className="applicant-name">{applicant.borrower_name || 'Unknown Borrower'}</span>
                    <span className={`applicant-status status-${(applicant.status || applicant.stage || 'unknown').toLowerCase().replace(/\s+/g, '-')}`}>
                      {applicant.status || applicant.stage || 'Unknown'}
                    </span>
                  </div>
                  <div className="applicant-card-body">
                    <div className="applicant-info-row">
                      <span className="info-label">Loan #:</span>
                      <span className="info-value">{applicant.loan_number || `#${applicant.id}`}</span>
                    </div>
                    <div className="applicant-info-row">
                      <span className="info-label">Amount:</span>
                      <span className="info-value">${(applicant.loan_amount || applicant.amount || 0).toLocaleString()}</span>
                    </div>
                    {applicant.property_address && (
                      <div className="applicant-info-row">
                        <span className="info-label">Property:</span>
                        <span className="info-value address">{applicant.property_address}</span>
                      </div>
                    )}
                    {applicant.loan_type && (
                      <div className="applicant-info-row">
                        <span className="info-label">Type:</span>
                        <span className="info-value loan-type">{applicant.loan_type.toUpperCase()}</span>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Applicant Details Panel */}
          <div className="applicant-details-panel">
            {!selectedApplicant && (
              <div className="no-selection">
                <div className="no-selection-icon">👥</div>
                <h3>Select an Applicant</h3>
                <p>Click on an applicant from the list to view their details</p>
              </div>
            )}

            {selectedApplicant && isLoadingDetails && (
              <div className="details-loading">
                <div className="loading-spinner"></div>
                <p>Loading applicant details...</p>
              </div>
            )}

            {selectedApplicant && applicantDetails && !applicantDetails.error && (
              <div className="applicant-details">
                <div className="details-header">
                  <h2>{applicantDetails.borrower_name || selectedApplicant.borrower_name || 'Applicant Details'}</h2>
                  <span className={`details-status status-${(applicantDetails.status || applicantDetails.stage || 'unknown').toLowerCase().replace(/\s+/g, '-')}`}>
                    {applicantDetails.status || applicantDetails.stage || 'Unknown Status'}
                  </span>
                </div>

                {/* Loan Overview Section */}
                <div className="details-section">
                  <h3>📋 Loan Overview</h3>
                  <div className="details-grid">
                    <div className="detail-item">
                      <span className="detail-label">Loan Number</span>
                      <span className="detail-value">{applicantDetails.loan_number || `#${applicantDetails.id}`}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Loan Amount</span>
                      <span className="detail-value">${(applicantDetails.loan_amount || applicantDetails.amount || 0).toLocaleString()}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Loan Type</span>
                      <span className="detail-value">{(applicantDetails.loan_type || 'N/A').toUpperCase()}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Loan Purpose</span>
                      <span className="detail-value">{applicantDetails.loan_purpose || applicantDetails.purpose || 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Interest Rate</span>
                      <span className="detail-value">{applicantDetails.rate || applicantDetails.interest_rate ? `${applicantDetails.rate || applicantDetails.interest_rate}%` : 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">LTV</span>
                      <span className="detail-value">{applicantDetails.ltv ? `${applicantDetails.ltv}%` : 'N/A'}</span>
                    </div>
                  </div>
                </div>

                {/* Borrower Information Section */}
                <div className="details-section">
                  <h3>👤 Borrower Information</h3>
                  <div className="details-grid">
                    <div className="detail-item">
                      <span className="detail-label">Name</span>
                      <span className="detail-value">{applicantDetails.borrower_name || 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Email</span>
                      <span className="detail-value">{applicantDetails.borrower_email || applicantDetails.email || 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Phone</span>
                      <span className="detail-value">{applicantDetails.borrower_phone || applicantDetails.phone || 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Credit Score</span>
                      <span className="detail-value">{applicantDetails.credit_score || 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">DTI</span>
                      <span className="detail-value">{applicantDetails.dti ? `${applicantDetails.dti}%` : 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Monthly Income</span>
                      <span className="detail-value">{applicantDetails.monthly_income ? `$${applicantDetails.monthly_income.toLocaleString()}` : 'N/A'}</span>
                    </div>
                  </div>
                </div>

                {/* Property Information Section */}
                <div className="details-section">
                  <h3>🏠 Property Information</h3>
                  <div className="details-grid">
                    <div className="detail-item full-width">
                      <span className="detail-label">Address</span>
                      <span className="detail-value">{applicantDetails.property_address || 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Property Type</span>
                      <span className="detail-value">{applicantDetails.property_type || 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Occupancy</span>
                      <span className="detail-value">{applicantDetails.occupancy_type || applicantDetails.occupancy || 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Property Value</span>
                      <span className="detail-value">{applicantDetails.appraisal_value || applicantDetails.property_value ? `$${(applicantDetails.appraisal_value || applicantDetails.property_value).toLocaleString()}` : 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">County</span>
                      <span className="detail-value">{applicantDetails.county || 'N/A'}</span>
                    </div>
                  </div>
                </div>

                {/* Dates Section */}
                <div className="details-section">
                  <h3>📅 Important Dates</h3>
                  <div className="details-grid">
                    <div className="detail-item">
                      <span className="detail-label">Application Date</span>
                      <span className="detail-value">{applicantDetails.application_date ? new Date(applicantDetails.application_date).toLocaleDateString() : 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Expected Close</span>
                      <span className="detail-value">{applicantDetails.expected_close_date ? new Date(applicantDetails.expected_close_date).toLocaleDateString() : 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Lock Expiration</span>
                      <span className="detail-value">{applicantDetails.lock_expiration_date ? new Date(applicantDetails.lock_expiration_date).toLocaleDateString() : 'N/A'}</span>
                    </div>
                    <div className="detail-item">
                      <span className="detail-label">Last Updated</span>
                      <span className="detail-value">{applicantDetails.updated_at ? new Date(applicantDetails.updated_at).toLocaleDateString() : 'N/A'}</span>
                    </div>
                  </div>
                </div>

                {/* Actions */}
                <div className="details-actions">
                  <button
                    className="action-btn primary"
                    onClick={() => {
                      setViewMode('file-analysis');
                      setSelectedLoan({ id: applicantDetails.id, loan_number: applicantDetails.loan_number });
                      analyzeFile(applicantDetails.id);
                    }}
                  >
                    📊 Run AI File Analysis
                  </button>
                </div>
              </div>
            )}

            {selectedApplicant && applicantDetails?.error && (
              <div className="details-error">
                <p>{applicantDetails.error}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default AIUnderwriter;

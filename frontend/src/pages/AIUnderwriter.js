import React, { useState, useRef, useEffect } from 'react';
import { aiAPI } from '../services/api';
import GuidelineUpdatesSidebar from '../components/GuidelineUpdatesSidebar';
import GuidelineNotificationBadge from '../components/GuidelineNotificationBadge';
import EscalationPanel from '../components/EscalationPanel';
import './AIUnderwriter.css';

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
      alert('Speech recognition is not supported in your browser. Please use Chrome or Edge.');
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
    try {
      const token = localStorage.getItem('token');
      if (token) {
        // Decode JWT to get user ID
        const payload = JSON.parse(atob(token.split('.')[1]));
        setCurrentUserId(payload.user_id || payload.sub || 1); // Fallback to 1 if not found
      } else {
        // No token, default to user ID 1
        setCurrentUserId(1);
      }
    } catch (error) {
      console.error('Failed to load user ID:', error);
      setCurrentUserId(1); // Fallback to user ID 1
    }
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
      const response = await fetch('/api/v1/ai-underwriter/ask', {
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
          <p className="subtitle">Ask any mortgage lending question and get answers with sources</p>
          {memoryStats && (
            <div className="memory-stats-badge">
              💾 {memoryStats.total_memories} conversations remembered
            </div>
          )}
        </div>
      </div>

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
                  <span className="ref-value">$766,550</span>
                </div>
              </div>
            </div>
          </div>

          <GuidelineUpdatesSidebar userId={currentUserId || 1} />
          <EscalationPanel />
        </div>
      </div>
    </div>
  );
}

export default AIUnderwriter;

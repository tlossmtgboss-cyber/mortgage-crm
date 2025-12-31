import React, { useState, useCallback, useRef, useEffect } from 'react';
import './EstimateComparison.css';
import { getCalendlySchedulingUrl } from '../services/schedulingService';

const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? (process.env.REACT_APP_API_URL || 'http://localhost:8000')
  : 'https://api.perenniaai.com';

// Default fallback URL if no Calendly integration is configured
const DEFAULT_CALENDLY_URL = "https://calendly.com/timlossteam/client-reengagement-clone?hide_event_type_details=1&hide_gdpr_banner=1";
const CUSTOM_QUOTE_URL = "https://www.perenniaai.com/apply/purchase";

function EstimateComparison() {
  // State for estimates A and B
  const [estimateA, setEstimateA] = useState(null);
  const [estimateB, setEstimateB] = useState(null);
  const [fileA, setFileA] = useState(null);
  const [fileB, setFileB] = useState(null);

  // Loading states
  const [loadingA, setLoadingA] = useState(false);
  const [loadingB, setLoadingB] = useState(false);
  const [comparing, setComparing] = useState(false);

  // Results
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState(null);

  // Provenance accordion state
  const [expandedProvenance, setExpandedProvenance] = useState({});

  // Calendly modal state
  const [showCalendly, setShowCalendly] = useState(false);
  const [calendlyUrl, setCalendlyUrl] = useState(DEFAULT_CALENDLY_URL);
  const [calendlyLoading, setCalendlyLoading] = useState(false);

  // AI Critique and Q&A state
  const [aiCritique, setAiCritique] = useState(null);
  const [critiqueLoading, setCritiqueLoading] = useState(false);
  const [qaMessages, setQaMessages] = useState([]);
  const [currentQuestion, setCurrentQuestion] = useState('');
  const [askingQuestion, setAskingQuestion] = useState(false);

  // === NEW ENHANCED FEATURES STATE ===

  // Batch comparison mode (3+ estimates)
  const [batchMode, setBatchMode] = useState(false);
  const [batchEstimates, setBatchEstimates] = useState([]);
  const [batchFiles, setBatchFiles] = useState([]);
  const [batchLoadingIndex, setBatchLoadingIndex] = useState(-1);
  const [batchComparison, setBatchComparison] = useState(null);

  // History sidebar
  const [showHistory, setShowHistory] = useState(false);
  const [comparisonHistory, setComparisonHistory] = useState([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyFilter, setHistoryFilter] = useState('all'); // 'all' or 'saved'

  // Share modal
  const [showShareModal, setShowShareModal] = useState(false);
  const [shareToken, setShareToken] = useState(null);
  const [shareCopied, setShareCopied] = useState(false);

  // Advanced analysis tabs
  const [analysisTab, setAnalysisTab] = useState('overview'); // 'overview', 'prepayment', 'tax'

  // Prepayment analysis
  const [prepaymentScenarios, setPrepaymentScenarios] = useState([
    { extra_monthly: 200, extra_yearly: 0, one_time: 0 },
    { extra_monthly: 0, extra_yearly: 1000, one_time: 0 },
    { extra_monthly: 100, extra_yearly: 500, one_time: 5000 },
  ]);
  const [prepaymentResults, setPrepaymentResults] = useState(null);
  const [prepaymentLoading, setPrepaymentLoading] = useState(false);

  // Tax impact analysis
  const [taxInputs, setTaxInputs] = useState({
    filing_status: 'single',
    annual_income: 100000,
    state_tax_rate: 5,
    property_tax_annual: 5000,
    other_itemized_deductions: 0,
  });
  const [taxResult, setTaxResult] = useState(null);
  const [taxLoading, setTaxLoading] = useState(false);

  // File input refs
  const fileInputA = useRef(null);
  const fileInputB = useRef(null);
  const batchFileInputRef = useRef(null);

  // Q&A refs
  const qaMessagesRef = useRef(null);
  const questionInputRef = useRef(null);

  // Preload Calendly script on component mount for faster loading
  useEffect(() => {
    if (!document.querySelector('script[src="https://assets.calendly.com/assets/external/widget.js"]')) {
      const script = document.createElement('script');
      script.src = 'https://assets.calendly.com/assets/external/widget.js';
      script.async = true;
      document.body.appendChild(script);
    }
  }, []);

  // Fetch dynamic Calendly URL from backend integration
  useEffect(() => {
    const fetchCalendlyUrl = async () => {
      try {
        // Try to get the user ID from localStorage or use a default
        const token = localStorage.getItem('token');
        if (token) {
          // Parse the user ID from the JWT token (basic parsing)
          const payload = JSON.parse(atob(token.split('.')[1]));
          const userId = payload.sub || payload.user_id;

          if (userId) {
            const result = await getCalendlySchedulingUrl(userId);
            if (result.success && result.schedulingUrl) {
              // Add params to hide event type details and GDPR banner
              const url = new URL(result.schedulingUrl);
              url.searchParams.set('hide_event_type_details', '1');
              url.searchParams.set('hide_gdpr_banner', '1');
              setCalendlyUrl(url.toString());
              console.log('[EstimateComparison] Using dynamic Calendly URL:', url.toString());
            }
          }
        }
      } catch (error) {
        console.log('[EstimateComparison] Using default Calendly URL (no integration found)');
        // Keep using the default URL
      }
    };

    fetchCalendlyUrl();
  }, []);

  // Handle body scroll when modal is open and initialize Calendly widget
  useEffect(() => {
    if (showCalendly) {
      document.body.style.overflow = 'hidden';

      // Initialize Calendly widget when modal opens
      const initCalendly = () => {
        if (window.Calendly) {
          const widgetContainer = document.querySelector('.calendly-inline-widget');
          if (widgetContainer) {
            // Clear any existing widget content
            widgetContainer.innerHTML = '';

            // Small delay to ensure container has proper dimensions
            setTimeout(() => {
              try {
                window.Calendly.initInlineWidget({
                  url: calendlyUrl,
                  parentElement: widgetContainer,
                  prefill: {},
                  utm: {}
                });
                console.log('[EstimateComparison] Calendly widget initialized with URL:', calendlyUrl);

                // Hide loading fallback after widget starts loading
                const fallback = document.querySelector('.calendly-loading-fallback');
                if (fallback) {
                  setTimeout(() => {
                    fallback.style.display = 'none';
                  }, 2000);
                }
              } catch (err) {
                console.error('[EstimateComparison] Calendly init error:', err);
              }
            }, 100);
          }
        }
      };

      // Wait for both script and DOM to be ready
      const attemptInit = () => {
        if (window.Calendly && document.querySelector('.calendly-inline-widget')) {
          initCalendly();
          return true;
        }
        return false;
      };

      // Try immediately, then poll if needed
      if (!attemptInit()) {
        const checkReady = setInterval(() => {
          if (attemptInit()) {
            clearInterval(checkReady);
          }
        }, 200);

        // Clean up interval after 10 seconds
        setTimeout(() => clearInterval(checkReady), 10000);
      }
    } else {
      document.body.style.overflow = 'unset';
      // Show loading fallback again when modal closes (for next open)
      const fallback = document.querySelector('.calendly-loading-fallback');
      if (fallback) {
        fallback.style.display = '';
      }
    }
    return () => {
      document.body.style.overflow = 'unset';
    };
  }, [showCalendly, calendlyUrl]);

  // Handle schedule call button click
  const handleScheduleCall = () => {
    if (comparison?.comparison_id) {
      // Track conversion
      fetch(`${API_BASE_URL}/api/v1/estimate-parser/compare/convert?comparison_id=${comparison.comparison_id}`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        }
      }).catch(err => console.error('Failed to track conversion:', err));
    }
    setShowCalendly(true);
  };

  // Generate AI critique when comparison is complete
  useEffect(() => {
    if (comparison && !aiCritique && !critiqueLoading) {
      generateCritique();
    }
  }, [comparison]);

  // Auto-scroll Q&A messages
  useEffect(() => {
    if (qaMessagesRef.current) {
      qaMessagesRef.current.scrollTop = qaMessagesRef.current.scrollHeight;
    }
  }, [qaMessages]);

  // Generate AI critique of the estimates
  const generateCritique = async () => {
    if (!comparison) return;

    setCritiqueLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/critique`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          comparison_id: comparison.comparison_id,
          estimate_a: comparison.estimate_a,
          estimate_b: comparison.estimate_b,
          winner: comparison.winner,
          savings_amount: comparison.savings_amount
        })
      });

      const data = await response.json();

      if (response.ok && data.critique) {
        setAiCritique(data.critique);
      } else {
        // Fallback critique if endpoint doesn't exist or fails
        setAiCritique(generateFallbackCritique());
      }
    } catch (err) {
      console.error('Failed to generate critique:', err);
      // Use fallback critique
      setAiCritique(generateFallbackCritique());
    } finally {
      setCritiqueLoading(false);
    }
  };

  // Generate fallback critique based on comparison data
  const generateFallbackCritique = () => {
    if (!comparison) return '';

    const a = comparison.estimate_a;
    const b = comparison.estimate_b;
    const winner = comparison.winner;
    const loser = winner === 'A' ? 'B' : 'A';

    let critique = `**Analysis Summary**\n\n`;

    // Cash to close analysis
    const cashDiff = Math.abs((a.cash_to_close || 0) - (b.cash_to_close || 0));
    if (cashDiff > 0) {
      critique += `**Cash to Close:** Estimate ${winner} requires ${formatCurrency(cashDiff)} less upfront, which means more money stays in your pocket at closing.\n\n`;
    }

    // Interest rate analysis
    const rateDiff = Math.abs((a.interest_rate || 0) - (b.interest_rate || 0));
    if (rateDiff > 0) {
      const lowerRate = (a.interest_rate || 0) < (b.interest_rate || 0) ? 'A' : 'B';
      critique += `**Interest Rate:** Estimate ${lowerRate} offers a lower rate (${formatPercent(lowerRate === 'A' ? a.interest_rate : b.interest_rate)}), which will save you money over the life of the loan.\n\n`;
    }

    // Closing costs analysis
    const closingDiff = Math.abs((a.total_closing_costs || 0) - (b.total_closing_costs || 0));
    if (closingDiff > 1000) {
      const lowerCosts = (a.total_closing_costs || 0) < (b.total_closing_costs || 0) ? 'A' : 'B';
      critique += `**Closing Costs:** There's a ${formatCurrency(closingDiff)} difference in closing costs. Estimate ${lowerCosts} has lower fees, but make sure to compare what services are included.\n\n`;
    }

    // Monthly payment analysis
    const monthlyDiff = Math.abs((a.monthly_principal_and_interest || 0) - (b.monthly_principal_and_interest || 0));
    if (monthlyDiff > 0) {
      const lowerMonthly = (a.monthly_principal_and_interest || 0) < (b.monthly_principal_and_interest || 0) ? 'A' : 'B';
      critique += `**Monthly Payment:** Estimate ${lowerMonthly} has a lower monthly P&I payment, saving you ${formatCurrency(monthlyDiff)} per month.\n\n`;
    }

    // Overall recommendation
    critique += `**Recommendation:** Based on the numbers, Estimate ${winner} appears to be the better option. However, consider factors like lender reputation, customer service, and any rate lock terms before making your final decision.`;

    return critique;
  };

  // Handle Q&A question submission
  const askQuestion = async (e) => {
    e.preventDefault();
    if (!currentQuestion.trim() || askingQuestion) return;

    const question = currentQuestion.trim();
    setCurrentQuestion('');

    // Add user question to messages
    setQaMessages(prev => [...prev, { type: 'user', text: question }]);
    setAskingQuestion(true);

    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/ask`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          question: question,
          comparison_id: comparison?.comparison_id,
          estimate_a: comparison?.estimate_a,
          estimate_b: comparison?.estimate_b,
          context: aiCritique
        })
      });

      const data = await response.json();

      if (response.ok && data.answer) {
        setQaMessages(prev => [...prev, { type: 'ai', text: data.answer }]);
      } else {
        // Fallback response
        setQaMessages(prev => [...prev, {
          type: 'ai',
          text: generateFallbackAnswer(question)
        }]);
      }
    } catch (err) {
      console.error('Failed to get answer:', err);
      setQaMessages(prev => [...prev, {
        type: 'ai',
        text: generateFallbackAnswer(question)
      }]);
    } finally {
      setAskingQuestion(false);
      questionInputRef.current?.focus();
    }
  };

  // Generate fallback answers for common questions
  const generateFallbackAnswer = (question) => {
    const q = question.toLowerCase();

    if (q.includes('rate') || q.includes('interest')) {
      const rateA = comparison?.estimate_a?.interest_rate;
      const rateB = comparison?.estimate_b?.interest_rate;
      return `Estimate A has an interest rate of ${formatPercent(rateA)} and Estimate B has ${formatPercent(rateB)}. The lower rate will save you money over the life of the loan, but also consider the closing costs and whether the rate is locked.`;
    }

    if (q.includes('closing cost') || q.includes('fees')) {
      const costsA = comparison?.estimate_a?.total_closing_costs;
      const costsB = comparison?.estimate_b?.total_closing_costs;
      return `Estimate A has ${formatCurrency(costsA)} in closing costs, while Estimate B has ${formatCurrency(costsB)}. Review the itemized fees to ensure you're comparing similar services.`;
    }

    if (q.includes('cash') || q.includes('upfront')) {
      const cashA = comparison?.estimate_a?.cash_to_close;
      const cashB = comparison?.estimate_b?.cash_to_close;
      return `You'll need ${formatCurrency(cashA)} for Estimate A and ${formatCurrency(cashB)} for Estimate B at closing. This includes your down payment, closing costs, and prepaid items.`;
    }

    if (q.includes('monthly') || q.includes('payment')) {
      const monthlyA = comparison?.estimate_a?.monthly_principal_and_interest;
      const monthlyB = comparison?.estimate_b?.monthly_principal_and_interest;
      return `The monthly P&I is ${formatCurrency(monthlyA)} for Estimate A and ${formatCurrency(monthlyB)} for Estimate B. Remember, your total monthly payment will also include taxes and insurance.`;
    }

    if (q.includes('better') || q.includes('recommend') || q.includes('which')) {
      return `Based on the comparison, Estimate ${comparison?.winner} appears to be the better option with potential savings of ${formatCurrency(comparison?.savings_amount)}. But here's the thing - we can likely beat both of these rates. Click "Get Instant Rate Quote" below to get a custom quote, or schedule a free consultation to see how much more we can save you.`;
    }

    return `That's a great question! Based on the estimates provided, I'd recommend getting a custom quote from our team. We can often beat these rates by 0.25-0.5%. Click "Get Instant Rate Quote" below or schedule a free consultation to discuss your options.`;
  };

  // Format currency
  const formatCurrency = (amount) => {
    if (amount === null || amount === undefined) return '—';
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(amount);
  };

  // Format percentage
  const formatPercent = (value) => {
    if (value === null || value === undefined) return '—';
    return `${parseFloat(value).toFixed(3)}%`;
  };

  // Parse estimate from file
  const parseEstimate = async (file, setEstimate, setLoading, label) => {
    setLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/parse`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || data.detail || 'Failed to parse estimate');
      }

      if (data.success && data.data) {
        // Generate a local ID if doc_hash is not provided by backend
        const localId = data.data.doc_hash || `local_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        setEstimate({
          ...data.data,
          doc_hash: localId,
          request_id: data.request_id
        });
      } else {
        throw new Error(data.error || 'Failed to parse estimate');
      }
    } catch (err) {
      console.error(`Parse error (${label}):`, err);
      setError(`Failed to parse ${label}: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  // Handle file selection
  const handleFileSelect = (e, side) => {
    const file = e.target.files[0];
    if (!file) return;

    // Validate file type
    const validTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/webp'];
    if (!validTypes.includes(file.type)) {
      setError('Please upload a PDF or image file (JPG, PNG, WebP)');
      return;
    }

    // Validate size (15MB max)
    if (file.size > 15 * 1024 * 1024) {
      setError('File size must be under 15MB');
      return;
    }

    if (side === 'A') {
      setFileA(file);
      setEstimateA(null);
      parseEstimate(file, setEstimateA, setLoadingA, 'Estimate A');
    } else {
      setFileB(file);
      setEstimateB(null);
      parseEstimate(file, setEstimateB, setLoadingB, 'Estimate B');
    }
  };

  // Handle drag and drop
  const handleDrop = useCallback((e, side) => {
    e.preventDefault();
    e.stopPropagation();

    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileSelect({ target: { files: [file] } }, side);
    }
  }, []);

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  // Compare estimates
  const compareEstimates = async () => {
    if (!estimateA || !estimateB) {
      setError('Please upload both estimates first');
      return;
    }

    setComparing(true);
    setError(null);

    try {
      // Try backend comparison first
      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/compare`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          estimate_a_hash: estimateA.doc_hash,
          estimate_b_hash: estimateB.doc_hash,
          estimate_a: estimateA,
          estimate_b: estimateB,
          session_id: `session_${Date.now()}`
        })
      });

      const data = await response.json();

      if (response.ok && data.success) {
        setComparison(data);
      } else {
        // Fall back to local comparison
        const localComparison = performLocalComparison();
        setComparison(localComparison);
      }
    } catch (err) {
      console.error('Compare error, using local comparison:', err);
      // Fall back to local comparison
      const localComparison = performLocalComparison();
      setComparison(localComparison);
    } finally {
      setComparing(false);
    }
  };

  // Perform local comparison when backend is unavailable
  const performLocalComparison = () => {
    const cashA = estimateA.cash_to_close || 0;
    const cashB = estimateB.cash_to_close || 0;
    const rateA = estimateA.interest_rate || 0;
    const rateB = estimateB.interest_rate || 0;

    // Determine winner based on cash to close (primary) and rate (secondary)
    let winner = 'A';
    let savings = 0;
    let reason = '';

    if (cashA < cashB) {
      winner = 'A';
      savings = cashB - cashA;
      reason = `Lower cash to close by ${formatCurrency(savings)}`;
    } else if (cashB < cashA) {
      winner = 'B';
      savings = cashA - cashB;
      reason = `Lower cash to close by ${formatCurrency(savings)}`;
    } else if (rateA < rateB) {
      winner = 'A';
      reason = 'Lower interest rate';
    } else if (rateB < rateA) {
      winner = 'B';
      reason = 'Lower interest rate';
    } else {
      reason = 'Both estimates are similar';
    }

    return {
      success: true,
      comparison_id: `local_${Date.now()}`,
      winner: winner,
      savings_amount: savings,
      savings_message: savings > 0 ? `You could save ${formatCurrency(savings)}` : null,
      reason: reason,
      estimate_a: estimateA,
      estimate_b: estimateB
    };
  };

  // Track conversion click - directs to custom quote application
  const handleCTAClick = async () => {
    if (comparison?.comparison_id) {
      try {
        await fetch(`${API_BASE_URL}/api/v1/estimate-parser/compare/convert?comparison_id=${comparison.comparison_id}`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        });
      } catch (err) {
        console.error('Failed to track conversion:', err);
      }
    }
    // Direct to custom quote application
    window.open(CUSTOM_QUOTE_URL, '_blank');
  };

  // Download PDF
  const handleDownloadPDF = async () => {
    if (!comparison?.comparison_id) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/estimate-parser/compare/${comparison.comparison_id}/pdf`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (!response.ok) {
        throw new Error('Failed to generate PDF');
      }

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `loan_comparison_${comparison.comparison_id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
    } catch (err) {
      console.error('PDF download error:', err);
      setError('Failed to download PDF. Please try again.');
    }
  };

  // Toggle provenance accordion
  const toggleProvenance = (key) => {
    setExpandedProvenance(prev => ({
      ...prev,
      [key]: !prev[key]
    }));
  };

  // Reset and start over
  const reset = () => {
    setEstimateA(null);
    setEstimateB(null);
    setFileA(null);
    setFileB(null);
    setComparison(null);
    setError(null);
    setExpandedProvenance({});
    setAiCritique(null);
    setQaMessages([]);
    setCurrentQuestion('');
    setBatchEstimates([]);
    setBatchFiles([]);
    setBatchComparison(null);
    setPrepaymentResults(null);
    setTaxResult(null);
    setAnalysisTab('overview');
    if (fileInputA.current) fileInputA.current.value = '';
    if (fileInputB.current) fileInputB.current.value = '';
    if (batchFileInputRef.current) batchFileInputRef.current.value = '';
  };

  // === NEW ENHANCED FEATURE FUNCTIONS ===

  // Fetch comparison history
  const fetchComparisonHistory = async () => {
    setHistoryLoading(true);
    try {
      const params = new URLSearchParams({ limit: 20 });
      if (historyFilter === 'saved') params.append('saved_only', 'true');

      const response = await fetch(
        `${API_BASE_URL}/api/v1/estimate-parser/history?${params}`,
        {
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setComparisonHistory(data.history || []);
      }
    } catch (err) {
      console.error('Failed to fetch history:', err);
    } finally {
      setHistoryLoading(false);
    }
  };

  // Load comparison from history
  const loadFromHistory = async (historyItem) => {
    // This would reload the comparison data - for now we just close the sidebar
    setShowHistory(false);
    // Could implement full reload logic here
  };

  // Save/unsave comparison
  const toggleSaveComparison = async (comparisonId, currentlySaved) => {
    try {
      const method = currentlySaved ? 'DELETE' : 'POST';
      await fetch(
        `${API_BASE_URL}/api/v1/estimate-parser/compare/${comparisonId}/save`,
        {
          method,
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`,
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({})
        }
      );
      // Refresh history
      fetchComparisonHistory();
    } catch (err) {
      console.error('Failed to toggle save:', err);
    }
  };

  // Create share link
  const createShareLink = async () => {
    if (!comparison?.comparison_id) return;

    try {
      const response = await fetch(
        `${API_BASE_URL}/api/v1/estimate-parser/compare/${comparison.comparison_id}/share`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );

      if (response.ok) {
        const data = await response.json();
        setShareToken(data.share_token);
        setShowShareModal(true);
      }
    } catch (err) {
      console.error('Failed to create share link:', err);
    }
  };

  // Copy share link
  const copyShareLink = () => {
    const shareUrl = `${window.location.origin}/shared/${shareToken}`;
    navigator.clipboard.writeText(shareUrl);
    setShareCopied(true);
    setTimeout(() => setShareCopied(false), 2000);
  };

  // Revoke share link
  const revokeShareLink = async () => {
    if (!comparison?.comparison_id) return;

    try {
      await fetch(
        `${API_BASE_URL}/api/v1/estimate-parser/compare/${comparison.comparison_id}/share`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${localStorage.getItem('token')}`
          }
        }
      );
      setShareToken(null);
      setShowShareModal(false);
    } catch (err) {
      console.error('Failed to revoke share link:', err);
    }
  };

  // Handle batch file upload
  const handleBatchFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const newIndex = batchEstimates.length;
    setBatchLoadingIndex(newIndex);
    setBatchFiles(prev => [...prev, file]);

    try {
      const formData = new FormData();
      formData.append('file', file);

      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/parse`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`
        },
        body: formData
      });

      const data = await response.json();

      if (data.success && data.data) {
        const label = String.fromCharCode(65 + newIndex); // A, B, C, ...
        setBatchEstimates(prev => [...prev, {
          ...data.data,
          label,
          doc_hash: data.data.doc_hash || `local_${Date.now()}`
        }]);
      } else {
        setError(data.error || 'Failed to parse estimate');
        setBatchFiles(prev => prev.slice(0, -1));
      }
    } catch (err) {
      console.error('Batch parse error:', err);
      setError('Failed to parse estimate');
      setBatchFiles(prev => prev.slice(0, -1));
    } finally {
      setBatchLoadingIndex(-1);
      if (batchFileInputRef.current) batchFileInputRef.current.value = '';
    }
  };

  // Remove estimate from batch
  const removeBatchEstimate = (index) => {
    setBatchEstimates(prev => prev.filter((_, i) => i !== index));
    setBatchFiles(prev => prev.filter((_, i) => i !== index));
    setBatchComparison(null);
  };

  // Compare batch estimates
  const compareBatchEstimates = async () => {
    if (batchEstimates.length < 2) return;

    setComparing(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/compare-batch`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          estimates: batchEstimates,
          labels: batchEstimates.map(e => e.label)
        })
      });

      const data = await response.json();

      if (data.success) {
        setBatchComparison(data);
      } else {
        setError(data.error || 'Batch comparison failed');
      }
    } catch (err) {
      console.error('Batch compare error:', err);
      setError('Failed to compare estimates');
    } finally {
      setComparing(false);
    }
  };

  // Calculate prepayment analysis
  const calculatePrepayment = async () => {
    const estimate = comparison?.winner === 'A' ? comparison?.estimate_a : comparison?.estimate_b;
    if (!estimate?.loan_amount || !estimate?.interest_rate) {
      setError('Missing loan data for prepayment analysis');
      return;
    }

    setPrepaymentLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/prepayment-analysis`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          loan_amount: estimate.loan_amount,
          interest_rate: estimate.interest_rate,
          loan_term_months: (estimate.loan_term || 30) * 12,
          scenarios: prepaymentScenarios
        })
      });

      const data = await response.json();

      if (data.success) {
        setPrepaymentResults(data.results);
      } else {
        setError(data.error || 'Prepayment analysis failed');
      }
    } catch (err) {
      console.error('Prepayment analysis error:', err);
      setError('Failed to calculate prepayment analysis');
    } finally {
      setPrepaymentLoading(false);
    }
  };

  // Calculate tax impact
  const calculateTaxImpact = async () => {
    const estimate = comparison?.winner === 'A' ? comparison?.estimate_a : comparison?.estimate_b;
    if (!estimate?.loan_amount || !estimate?.interest_rate) {
      setError('Missing loan data for tax analysis');
      return;
    }

    setTaxLoading(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/estimate-parser/tax-impact`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${localStorage.getItem('token')}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          loan_amount: estimate.loan_amount,
          interest_rate: estimate.interest_rate,
          loan_term_months: (estimate.loan_term || 30) * 12,
          ...taxInputs
        })
      });

      const data = await response.json();

      if (data.success) {
        setTaxResult(data.result);
      } else {
        setError(data.error || 'Tax impact analysis failed');
      }
    } catch (err) {
      console.error('Tax impact error:', err);
      setError('Failed to calculate tax impact');
    } finally {
      setTaxLoading(false);
    }
  };

  // Update prepayment scenario
  const updatePrepaymentScenario = (index, field, value) => {
    setPrepaymentScenarios(prev => {
      const updated = [...prev];
      updated[index] = { ...updated[index], [field]: parseFloat(value) || 0 };
      return updated;
    });
    setPrepaymentResults(null); // Clear results when inputs change
  };

  // Update tax input
  const updateTaxInput = (field, value) => {
    setTaxInputs(prev => ({
      ...prev,
      [field]: field === 'filing_status' ? value : parseFloat(value) || 0
    }));
    setTaxResult(null); // Clear results when inputs change
  };

  // Effect to fetch history when sidebar opens
  useEffect(() => {
    if (showHistory) {
      fetchComparisonHistory();
    }
  }, [showHistory, historyFilter]);

  // Keyboard handler for history sidebar
  useEffect(() => {
    const handleEscape = (e) => {
      if (e.key === 'Escape') {
        if (showShareModal) setShowShareModal(false);
        else if (showHistory) setShowHistory(false);
        else if (showCalendly) setShowCalendly(false);
      }
    };
    document.addEventListener('keydown', handleEscape);
    return () => document.removeEventListener('keydown', handleEscape);
  }, [showShareModal, showHistory, showCalendly]);

  // Render upload card
  const renderUploadCard = (side, file, estimate, loading) => {
    const isA = side === 'A';

    return (
      <div className={`estimate-card ${comparison?.winner === side ? 'winner' : ''}`}>
        {comparison?.winner === side && (
          <div className="winner-badge">
            <span className="trophy">🏆</span>
            <span>Best Option</span>
          </div>
        )}

        <h3>Estimate {side}</h3>

        {!estimate && !loading && (
          <div
            className="upload-zone"
            onDrop={(e) => handleDrop(e, side)}
            onDragOver={handleDragOver}
            onClick={() => isA ? fileInputA.current?.click() : fileInputB.current?.click()}
          >
            <div className="upload-icon">📄</div>
            <p>Drop your Loan Estimate here</p>
            <p className="hint">or click to browse</p>
            <p className="formats">PDF, JPG, PNG, WebP (max 15MB)</p>
            <input
              ref={isA ? fileInputA : fileInputB}
              type="file"
              accept=".pdf,image/jpeg,image/png,image/webp"
              onChange={(e) => handleFileSelect(e, side)}
              style={{ display: 'none' }}
            />
          </div>
        )}

        {loading && (
          <div className="loading-state">
            <div className="spinner"></div>
            <p>Analyzing document...</p>
            <p className="hint">Extracting loan details with AI</p>
          </div>
        )}

        {estimate && !loading && (
          <div className="estimate-details">
            <div className="file-info">
              <span className="file-icon">✓</span>
              <span className="file-name">{file?.name || 'Document parsed'}</span>
              <button className="btn-remove" onClick={() => {
                if (isA) {
                  setEstimateA(null);
                  setFileA(null);
                  if (fileInputA.current) fileInputA.current.value = '';
                } else {
                  setEstimateB(null);
                  setFileB(null);
                  if (fileInputB.current) fileInputB.current.value = '';
                }
                setComparison(null);
              }}>✕</button>
            </div>

            {estimate.needs_review && (
              <div className="review-warning">
                <span>⚠️</span>
                <span>Some values may need review</span>
              </div>
            )}

            <div className="detail-grid">
              <div className="detail-row highlight">
                <span className="label">Loan Amount</span>
                <span className="value">{formatCurrency(estimate.loan_amount)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Interest Rate</span>
                <span className="value">{formatPercent(estimate.interest_rate)}</span>
              </div>
              <div className="detail-row">
                <span className="label">APR</span>
                <span className="value">{formatPercent(estimate.apr)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Monthly P&I</span>
                <span className="value">{formatCurrency(estimate.monthly_principal_and_interest)}</span>
              </div>
              <div className="detail-row highlight">
                <span className="label">Total Closing Costs</span>
                <span className="value">{formatCurrency(estimate.total_closing_costs)}</span>
              </div>
              <div className="detail-row highlight">
                <span className="label">Cash to Close</span>
                <span className="value">{formatCurrency(estimate.cash_to_close)}</span>
              </div>
              {estimate.loan_type && (
                <div className="detail-row">
                  <span className="label">Loan Type</span>
                  <span className="value">{estimate.loan_type}</span>
                </div>
              )}
              {estimate.loan_term && (
                <div className="detail-row">
                  <span className="label">Loan Term</span>
                  <span className="value">{estimate.loan_term}</span>
                </div>
              )}
            </div>

            {/* Provenance snippets */}
            {estimate.provenance && Object.keys(estimate.provenance).length > 0 && (
              <div className="provenance-section">
                <button
                  className="provenance-toggle"
                  onClick={() => toggleProvenance(side)}
                >
                  <span>{expandedProvenance[side] ? '▼' : '▶'}</span>
                  <span>Show me where this came from</span>
                </button>

                {expandedProvenance[side] && (
                  <div className="provenance-content">
                    {Object.entries(estimate.provenance).map(([field, snippet]) => (
                      <div key={field} className="provenance-item">
                        <span className="provenance-field">{field.replace(/_/g, ' ')}:</span>
                        <span className="provenance-snippet">"{snippet}"</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {estimate.confidence_score && (
              <div className="confidence-badge">
                Confidence: {Math.round(estimate.confidence_score * 100)}%
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  // Render batch comparison UI
  const renderBatchMode = () => (
    <div className="batch-comparison-section">
      <div className="batch-estimates-grid">
        {batchEstimates.map((est, index) => (
          <div
            key={index}
            className={`batch-estimate-card ${batchComparison?.winner_index === index ? 'winner' : ''}`}
            role="article"
            aria-label={`Estimate ${est.label}`}
          >
            {batchComparison && (
              <div className={`rank-badge rank-${batchComparison.rankings.find(r => r.index === index)?.rank || ''}`}>
                {batchComparison.rankings.find(r => r.index === index)?.rank || ''}
              </div>
            )}
            <div className="batch-card-header">
              <h4>Estimate {est.label}</h4>
              <button
                className="btn-remove"
                onClick={() => removeBatchEstimate(index)}
                aria-label={`Remove estimate ${est.label}`}
              >
                ✕
              </button>
            </div>
            <div className="detail-grid">
              <div className="detail-row">
                <span className="label">Loan Amount</span>
                <span className="value">{formatCurrency(est.loan_amount)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Rate / APR</span>
                <span className="value">{formatPercent(est.interest_rate)} / {formatPercent(est.apr)}</span>
              </div>
              <div className="detail-row highlight">
                <span className="label">Cash to Close</span>
                <span className="value">{formatCurrency(est.cash_to_close)}</span>
              </div>
              <div className="detail-row">
                <span className="label">Monthly P&I</span>
                <span className="value">{formatCurrency(est.monthly_principal_and_interest)}</span>
              </div>
            </div>
          </div>
        ))}

        {batchLoadingIndex >= 0 && (
          <div className="batch-estimate-card loading">
            <div className="spinner" aria-label="Loading estimate"></div>
            <p>Parsing estimate...</p>
          </div>
        )}

        {batchEstimates.length < 6 && batchLoadingIndex < 0 && (
          <div
            className="add-estimate-card"
            onClick={() => batchFileInputRef.current?.click()}
            onKeyPress={(e) => e.key === 'Enter' && batchFileInputRef.current?.click()}
            role="button"
            tabIndex={0}
            aria-label="Add another estimate"
          >
            <span className="add-icon">+</span>
            <span>Add Estimate {String.fromCharCode(65 + batchEstimates.length)}</span>
          </div>
        )}
      </div>

      <input
        type="file"
        ref={batchFileInputRef}
        onChange={handleBatchFileUpload}
        accept=".pdf,.jpg,.jpeg,.png,.webp"
        style={{ display: 'none' }}
        aria-hidden="true"
      />

      {batchEstimates.length >= 2 && (
        <div className="batch-actions">
          <button
            className="btn-compare"
            onClick={compareBatchEstimates}
            disabled={comparing}
          >
            {comparing ? 'Comparing...' : `Compare ${batchEstimates.length} Estimates`}
          </button>
        </div>
      )}

      {batchComparison && (
        <div className="batch-rankings" role="table" aria-label="Estimate rankings">
          <div className="batch-rankings-header" role="row">
            <div role="columnheader">Rank</div>
            <div role="columnheader">Estimate</div>
            <div role="columnheader">Cash to Close</div>
            <div role="columnheader">Closing Costs</div>
            <div role="columnheader">APR</div>
            <div role="columnheader">Monthly P&I</div>
          </div>
          {batchComparison.rankings.map((ranking) => (
            <div
              key={ranking.index}
              className={`batch-ranking-row ${ranking.rank === 1 ? 'winner' : ''}`}
              role="row"
            >
              <div role="cell">#{ranking.rank}</div>
              <div role="cell"><strong>{ranking.label}</strong></div>
              <div role="cell">{formatCurrency(ranking.cash_to_close)}</div>
              <div role="cell">{formatCurrency(ranking.total_closing_costs)}</div>
              <div role="cell">{formatPercent(ranking.apr)}</div>
              <div role="cell">{formatCurrency(ranking.monthly_pi)}</div>
            </div>
          ))}
        </div>
      )}

      {batchComparison?.summary && (
        <div className="batch-summary" role="status" aria-live="polite">
          <p><strong>Summary:</strong> {batchComparison.summary}</p>
          {batchComparison.savings_vs_worst > 0 && (
            <p className="savings-highlight">
              Potential savings: {formatCurrency(batchComparison.savings_vs_worst)}
            </p>
          )}
        </div>
      )}
    </div>
  );

  // Render prepayment analysis panel
  const renderPrepaymentPanel = () => (
    <div className="prepayment-panel" role="region" aria-label="Prepayment analysis">
      <h4>
        <span aria-hidden="true">💰</span>
        Early Payoff Calculator
      </h4>
      <p className="panel-description">
        See how extra payments can save you money and pay off your loan faster.
      </p>

      <div className="prepayment-scenarios">
        {prepaymentScenarios.map((scenario, index) => (
          <div key={index} className="prepayment-scenario-card">
            <h5>Scenario {index + 1}</h5>
            <div className="prepayment-input-group">
              <div className="prepayment-input">
                <label htmlFor={`extra-monthly-${index}`}>Extra Monthly</label>
                <input
                  id={`extra-monthly-${index}`}
                  type="number"
                  value={scenario.extra_monthly}
                  onChange={(e) => updatePrepaymentScenario(index, 'extra_monthly', e.target.value)}
                  placeholder="$0"
                />
              </div>
              <div className="prepayment-input">
                <label htmlFor={`extra-yearly-${index}`}>Extra Yearly</label>
                <input
                  id={`extra-yearly-${index}`}
                  type="number"
                  value={scenario.extra_yearly}
                  onChange={(e) => updatePrepaymentScenario(index, 'extra_yearly', e.target.value)}
                  placeholder="$0"
                />
              </div>
              <div className="prepayment-input">
                <label htmlFor={`one-time-${index}`}>One-Time</label>
                <input
                  id={`one-time-${index}`}
                  type="number"
                  value={scenario.one_time}
                  onChange={(e) => updatePrepaymentScenario(index, 'one_time', e.target.value)}
                  placeholder="$0"
                />
              </div>
            </div>
          </div>
        ))}
      </div>

      <button
        className="btn-calculate"
        onClick={calculatePrepayment}
        disabled={prepaymentLoading}
      >
        {prepaymentLoading ? 'Calculating...' : 'Calculate Savings'}
      </button>

      {prepaymentResults && (
        <div className="prepayment-results" role="region" aria-live="polite">
          {prepaymentResults.map((result, index) => (
            <div key={index} className="prepayment-result-card">
              <div className="result-value">{result.years_saved} years</div>
              <div className="result-label">Paid off earlier</div>
              <div className="result-value">{formatCurrency(result.interest_saved)}</div>
              <div className="result-label">Interest saved</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );

  // Render tax impact panel
  const renderTaxPanel = () => (
    <div className="tax-panel" role="region" aria-label="Tax impact analysis">
      <h4>
        <span aria-hidden="true">📋</span>
        Tax Impact Calculator
      </h4>
      <p className="panel-description">
        Estimate your potential tax benefits from mortgage interest deduction.
      </p>

      <div className="tax-inputs">
        <div className="tax-input-group">
          <label htmlFor="filing-status">Filing Status</label>
          <select
            id="filing-status"
            value={taxInputs.filing_status}
            onChange={(e) => updateTaxInput('filing_status', e.target.value)}
          >
            <option value="single">Single</option>
            <option value="married_filing_jointly">Married Filing Jointly</option>
            <option value="married_filing_separately">Married Filing Separately</option>
            <option value="head_of_household">Head of Household</option>
          </select>
        </div>
        <div className="tax-input-group">
          <label htmlFor="annual-income">Annual Income</label>
          <input
            id="annual-income"
            type="number"
            value={taxInputs.annual_income}
            onChange={(e) => updateTaxInput('annual_income', e.target.value)}
          />
        </div>
        <div className="tax-input-group">
          <label htmlFor="state-tax">State Tax Rate (%)</label>
          <input
            id="state-tax"
            type="number"
            step="0.1"
            value={taxInputs.state_tax_rate}
            onChange={(e) => updateTaxInput('state_tax_rate', e.target.value)}
          />
        </div>
        <div className="tax-input-group">
          <label htmlFor="property-tax">Annual Property Tax</label>
          <input
            id="property-tax"
            type="number"
            value={taxInputs.property_tax_annual}
            onChange={(e) => updateTaxInput('property_tax_annual', e.target.value)}
          />
        </div>
      </div>

      <button
        className="btn-calculate"
        onClick={calculateTaxImpact}
        disabled={taxLoading}
      >
        {taxLoading ? 'Calculating...' : 'Calculate Tax Impact'}
      </button>

      {taxResult && (
        <div className="tax-results" role="region" aria-live="polite">
          <div className="tax-result-row">
            <span className="tax-result-label">Year 1 Mortgage Interest</span>
            <span className="tax-result-value">{formatCurrency(taxResult.year_1_mortgage_interest)}</span>
          </div>
          <div className="tax-result-row">
            <span className="tax-result-label">Total Itemized Deductions</span>
            <span className="tax-result-value">{formatCurrency(taxResult.year_1_total_itemized)}</span>
          </div>
          <div className="tax-result-row">
            <span className="tax-result-label">Standard Deduction</span>
            <span className="tax-result-value">{formatCurrency(taxResult.standard_deduction)}</span>
          </div>
          <div className="tax-result-row">
            <span className="tax-result-label">Benefit from Itemizing?</span>
            <span className="tax-result-value">{taxResult.itemize_benefit ? 'Yes' : 'No'}</span>
          </div>
          <div className="tax-result-row">
            <span className="tax-result-label">Estimated Year 1 Tax Savings</span>
            <span className="tax-result-value highlight">{formatCurrency(taxResult.tax_benefit_amount)}</span>
          </div>
          <div className="tax-result-row">
            <span className="tax-result-label">Monthly Effective Savings</span>
            <span className="tax-result-value highlight">{formatCurrency(taxResult.effective_monthly_savings)}</span>
          </div>

          {taxResult.itemize_benefit && (
            <div className="tax-recommendation">
              <span className="rec-icon" aria-hidden="true">💡</span>
              <p>
                Based on your inputs, itemizing deductions could save you approximately{' '}
                {formatCurrency(taxResult.tax_benefit_amount)} in Year 1. Your effective monthly mortgage cost
                is reduced by about {formatCurrency(taxResult.effective_monthly_savings)}.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div className="estimate-comparison-page" role="main">
      {/* Skip link for accessibility */}
      <a href="#main-content" className="skip-link">Skip to main content</a>

      {/* History toggle button */}
      <div className="history-toggle">
        <button
          className="btn-history-toggle"
          onClick={() => setShowHistory(true)}
          aria-label="Open comparison history"
          aria-expanded={showHistory}
        >
          <span aria-hidden="true">📜</span> History
        </button>
      </div>

      {/* History sidebar */}
      {showHistory && (
        <>
          <div className="overlay" onClick={() => setShowHistory(false)} aria-hidden="true"></div>
          <aside
            className="history-sidebar open"
            role="complementary"
            aria-label="Comparison history"
          >
            <div className="history-sidebar-header">
              <h3><span aria-hidden="true">📜</span> History</h3>
              <button
                className="btn-close-sidebar"
                onClick={() => setShowHistory(false)}
                aria-label="Close history sidebar"
              >
                ✕
              </button>
            </div>
            <div className="history-filters" role="tablist">
              <button
                className={`history-filter-btn ${historyFilter === 'all' ? 'active' : ''}`}
                onClick={() => setHistoryFilter('all')}
                role="tab"
                aria-selected={historyFilter === 'all'}
              >
                All
              </button>
              <button
                className={`history-filter-btn ${historyFilter === 'saved' ? 'active' : ''}`}
                onClick={() => setHistoryFilter('saved')}
                role="tab"
                aria-selected={historyFilter === 'saved'}
              >
                Saved
              </button>
            </div>
            <div className="history-list" role="list">
              {historyLoading ? (
                <div className="history-loading">
                  <div className="spinner"></div>
                </div>
              ) : comparisonHistory.length === 0 ? (
                <div className="history-empty">
                  <div className="history-empty-icon" aria-hidden="true">📊</div>
                  <p>No comparisons yet</p>
                </div>
              ) : (
                comparisonHistory.map((item) => (
                  <div
                    key={item.id}
                    className="history-item"
                    onClick={() => loadFromHistory(item)}
                    role="listitem"
                    tabIndex={0}
                    onKeyPress={(e) => e.key === 'Enter' && loadFromHistory(item)}
                  >
                    <div className="history-item-header">
                      <h4 className="history-item-title">
                        {item.title || `Comparison ${item.id.slice(0, 8)}`}
                      </h4>
                      <span className="history-item-date">
                        {new Date(item.created_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="history-item-summary">
                      Winner: Estimate {item.winner}
                      {item.savings_amount > 0 && ` • Saved ${formatCurrency(item.savings_amount)}`}
                    </p>
                    <div className="history-item-actions">
                      <button
                        className={`history-action-btn ${item.is_saved ? 'saved' : ''}`}
                        onClick={(e) => {
                          e.stopPropagation();
                          toggleSaveComparison(item.id, item.is_saved);
                        }}
                        aria-label={item.is_saved ? 'Remove from saved' : 'Save comparison'}
                      >
                        {item.is_saved ? '★ Saved' : '☆ Save'}
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </aside>
        </>
      )}

      {/* Share modal */}
      {showShareModal && shareToken && (
        <>
          <div className="overlay" onClick={() => setShowShareModal(false)} aria-hidden="true"></div>
          <div
            className="share-modal"
            role="dialog"
            aria-labelledby="share-modal-title"
            aria-modal="true"
          >
            <div className="share-modal-header">
              <h3 id="share-modal-title"><span aria-hidden="true">🔗</span> Share Comparison</h3>
              <button
                className="btn-close-sidebar"
                onClick={() => setShowShareModal(false)}
                aria-label="Close share modal"
              >
                ✕
              </button>
            </div>
            <div className="share-link-container">
              <input
                type="text"
                className="share-link-input"
                value={`${window.location.origin}/shared/${shareToken}`}
                readOnly
                aria-label="Share link"
              />
              <button
                className={`btn-copy-link ${shareCopied ? 'copied' : ''}`}
                onClick={copyShareLink}
              >
                {shareCopied ? '✓ Copied' : 'Copy'}
              </button>
            </div>
            <div className="share-modal-footer">
              <span className="share-privacy-note">
                Anyone with this link can view this comparison
              </span>
              <button className="btn-revoke-share" onClick={revokeShareLink}>
                Revoke Link
              </button>
            </div>
          </div>
        </>
      )}

      <div className="page-header" id="main-content">
        <div className="header-content">
          <h1>Compare Loan Estimates</h1>
          <p>Upload {batchMode ? 'multiple' : 'two'} loan estimates to see which one saves you money</p>
        </div>
        <div className="header-actions">
          {/* Batch mode toggle */}
          <div className="batch-mode-toggle">
            <span className="batch-mode-label">Compare 3+ estimates</span>
            <button
              className={`toggle-switch ${batchMode ? 'active' : ''}`}
              onClick={() => {
                setBatchMode(!batchMode);
                reset();
              }}
              role="switch"
              aria-checked={batchMode}
              aria-label="Toggle batch comparison mode"
            ></button>
          </div>
          {(estimateA || estimateB || comparison || batchEstimates.length > 0) && (
            <button className="btn-reset" onClick={reset}>
              Start Over
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="error-banner">
          <span className="error-icon">⚠️</span>
          <span>{error}</span>
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      <div className="comparison-container">
        {/* Batch mode or standard two-estimate mode */}
        {batchMode ? (
          renderBatchMode()
        ) : (
          <>
            <div className="estimates-row">
              {renderUploadCard('A', fileA, estimateA, loadingA)}

              <div className="vs-divider">
                <span>VS</span>
              </div>

              {renderUploadCard('B', fileB, estimateB, loadingB)}
            </div>

            {/* Compare button */}
            {estimateA && estimateB && !comparison && (
          <div className="compare-action">
            <button
              className="btn-compare"
              onClick={compareEstimates}
              disabled={comparing}
            >
              {comparing ? (
                <>
                  <span className="spinner-small"></span>
                  Comparing...
                </>
              ) : (
                <>
                  <span className="compare-icon">⚖️</span>
                  Compare Estimates
                </>
              )}
            </button>
          </div>
        )}

        {/* Comparison results */}
        {comparison && (
          <div className="comparison-results">
            <div className="result-header">
              <h2>Comparison Results</h2>
              {comparison.winner && (
                <div className="winner-announcement">
                  <span className="trophy-large">🏆</span>
                  <div className="winner-text">
                    <span className="winner-label">Estimate {comparison.winner} is the better option</span>
                    <span className="winner-reason">{comparison.reason}</span>
                  </div>
                </div>
              )}
            </div>

            {comparison.savings_amount > 0 && (
              <div className="savings-card">
                <div className="savings-amount">
                  {formatCurrency(comparison.savings_amount)}
                </div>
                <div className="savings-label">
                  {comparison.savings_message || 'Potential Savings'}
                </div>
              </div>
            )}

            {/* Side by side comparison table */}
            <div className="comparison-table">
              <div className="table-header">
                <div className="col-label"></div>
                <div className="col-a">Estimate A</div>
                <div className="col-b">Estimate B</div>
                <div className="col-diff">Difference</div>
              </div>

              {[
                { label: 'Cash to Close', key: 'cash_to_close', format: formatCurrency },
                { label: 'Total Closing Costs', key: 'total_closing_costs', format: formatCurrency },
                { label: 'APR', key: 'apr', format: formatPercent },
                { label: 'Interest Rate', key: 'interest_rate', format: formatPercent },
                { label: 'Monthly P&I', key: 'monthly_principal_and_interest', format: formatCurrency },
                { label: 'Loan Amount', key: 'loan_amount', format: formatCurrency },
              ].map(({ label, key, format }) => {
                const valA = comparison.estimate_a?.[key];
                const valB = comparison.estimate_b?.[key];
                const diff = (valA && valB) ? valA - valB : null;
                const isCurrency = format === formatCurrency;

                return (
                  <div key={key} className="table-row">
                    <div className="col-label">{label}</div>
                    <div className={`col-a ${comparison.winner === 'A' && key === 'cash_to_close' ? 'better' : ''}`}>
                      {format(valA)}
                    </div>
                    <div className={`col-b ${comparison.winner === 'B' && key === 'cash_to_close' ? 'better' : ''}`}>
                      {format(valB)}
                    </div>
                    <div className={`col-diff ${diff < 0 ? 'positive' : diff > 0 ? 'negative' : ''}`}>
                      {diff !== null ? (
                        isCurrency
                          ? `${diff > 0 ? '+' : ''}${formatCurrency(diff)}`
                          : `${diff > 0 ? '+' : ''}${diff.toFixed(3)}%`
                      ) : '—'}
                    </div>
                  </div>
                );
              })}
            </div>

            {/* AI Critique Section */}
            <div className="ai-critique-section">
              <div className="critique-header">
                <span className="ai-icon">🤖</span>
                <h3>AI Analysis</h3>
              </div>

              {critiqueLoading ? (
                <div className="critique-loading">
                  <div className="spinner-small"></div>
                  <span>Analyzing estimates...</span>
                </div>
              ) : aiCritique ? (
                <div className="critique-content">
                  {aiCritique.split('\n\n').map((paragraph, idx) => (
                    <p key={idx}>
                      {paragraph.split('**').map((part, i) =>
                        i % 2 === 1 ? <strong key={i}>{part}</strong> : part
                      )}
                    </p>
                  ))}
                </div>
              ) : null}
            </div>

            {/* Q&A Section */}
            <div className="qa-section">
              <div className="qa-header">
                <span className="qa-icon">💬</span>
                <h3>Ask Questions About Your Estimates</h3>
              </div>

              {qaMessages.length > 0 && (
                <div className="qa-messages" ref={qaMessagesRef}>
                  {qaMessages.map((msg, idx) => (
                    <div key={idx} className={`qa-message ${msg.type}`}>
                      <div className="message-avatar">
                        {msg.type === 'user' ? '👤' : '🤖'}
                      </div>
                      <div className="message-content">
                        {msg.text}
                      </div>
                    </div>
                  ))}
                  {askingQuestion && (
                    <div className="qa-message ai typing">
                      <div className="message-avatar">🤖</div>
                      <div className="message-content">
                        <span className="typing-indicator">
                          <span></span><span></span><span></span>
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}

              <form className="qa-input-form" onSubmit={askQuestion}>
                <input
                  ref={questionInputRef}
                  type="text"
                  placeholder="Ask a question about your loan estimates..."
                  value={currentQuestion}
                  onChange={(e) => setCurrentQuestion(e.target.value)}
                  disabled={askingQuestion}
                />
                <button type="submit" disabled={!currentQuestion.trim() || askingQuestion}>
                  <span className="send-icon">➤</span>
                </button>
              </form>

              <div className="qa-suggestions">
                <span className="suggestions-label">Try asking:</span>
                <div className="suggestion-chips">
                  <button
                    type="button"
                    onClick={() => setCurrentQuestion('Which estimate has the better interest rate?')}
                  >
                    Interest rate comparison
                  </button>
                  <button
                    type="button"
                    onClick={() => setCurrentQuestion('What are the main differences in closing costs?')}
                  >
                    Closing costs breakdown
                  </button>
                  <button
                    type="button"
                    onClick={() => setCurrentQuestion('Which option is better for me?')}
                  >
                    Best option for me
                  </button>
                </div>
              </div>
            </div>

            {/* CTA */}
            <div className="cta-section-enhanced">
              <div className="cta-badge">
                <span>🎯</span> Limited Time Offer
              </div>

              <h2 className="cta-headline">
                We Can Beat These Terms
              </h2>

              <p className="cta-subheadline">
                Our mortgage experts have access to <strong>50+ lenders</strong> and can often find rates
                <strong> 0.25% - 0.5% lower</strong> than what you're seeing here.
              </p>

              {comparison.savings_amount > 0 && (
                <div className="cta-savings-highlight">
                  <span className="savings-label">You're already saving</span>
                  <span className="savings-value">{formatCurrency(comparison.savings_amount)}</span>
                  <span className="savings-extra">Let us find you even more.</span>
                </div>
              )}

              <div className="cta-trust-signals">
                <div className="trust-item">
                  <span className="trust-icon">✓</span>
                  <span>100% Free Consultation</span>
                </div>
                <div className="trust-item">
                  <span className="trust-icon">✓</span>
                  <span>Soft Credit Pull Only</span>
                </div>
                <div className="trust-item">
                  <span className="trust-icon">✓</span>
                  <span>No Obligation to Proceed</span>
                </div>
              </div>

              <div className="cta-buttons-enhanced">
                <button className="btn-cta-primary" onClick={handleScheduleCall}>
                  <span className="btn-icon">📅</span>
                  <span className="btn-text">
                    <span className="btn-main">Schedule My Free Consultation</span>
                    <span className="btn-sub">Pick a time that works for you</span>
                  </span>
                </button>

                <div className="cta-or-divider">
                  <span>or</span>
                </div>

                <button className="btn-cta-secondary" onClick={handleCTAClick}>
                  <span className="btn-icon">⚡</span>
                  <span className="btn-text">
                    <span className="btn-main">Get Instant Rate Quote</span>
                    <span className="btn-sub">See your personalized rate in 60 seconds</span>
                  </span>
                </button>
              </div>

              <p className="cta-urgency">
                <span className="urgency-icon">⏰</span>
                Rates change daily. Lock in your savings before they increase.
              </p>
            </div>
          </div>
        )}

            {/* Action bar for save/share */}
            {comparison && (
              <div className="comparison-action-bar">
                <button
                  className="action-btn"
                  onClick={() => toggleSaveComparison(comparison.comparison_id, false)}
                  aria-label="Save this comparison"
                >
                  <span className="action-icon" aria-hidden="true">☆</span>
                  Save
                </button>
                <button
                  className="action-btn"
                  onClick={createShareLink}
                  aria-label="Share this comparison"
                >
                  <span className="action-icon" aria-hidden="true">🔗</span>
                  Share
                </button>
                <button
                  className="action-btn"
                  onClick={handleDownloadPDF}
                  aria-label="Download as PDF"
                >
                  <span className="action-icon" aria-hidden="true">📄</span>
                  Download PDF
                </button>
              </div>
            )}

            {/* Advanced Analysis Tabs */}
            {comparison && (
              <div className="advanced-analysis-section">
                <div className="analysis-tabs" role="tablist">
                  <button
                    className={`analysis-tab ${analysisTab === 'overview' ? 'active' : ''}`}
                    onClick={() => setAnalysisTab('overview')}
                    role="tab"
                    aria-selected={analysisTab === 'overview'}
                    aria-controls="overview-panel"
                  >
                    Overview
                  </button>
                  <button
                    className={`analysis-tab ${analysisTab === 'prepayment' ? 'active' : ''}`}
                    onClick={() => setAnalysisTab('prepayment')}
                    role="tab"
                    aria-selected={analysisTab === 'prepayment'}
                    aria-controls="prepayment-panel"
                  >
                    Early Payoff
                  </button>
                  <button
                    className={`analysis-tab ${analysisTab === 'tax' ? 'active' : ''}`}
                    onClick={() => setAnalysisTab('tax')}
                    role="tab"
                    aria-selected={analysisTab === 'tax'}
                    aria-controls="tax-panel"
                  >
                    Tax Impact
                  </button>
                </div>

                <div id="overview-panel" role="tabpanel" hidden={analysisTab !== 'overview'}>
                  {/* The AI critique and Q&A are already shown above */}
                </div>

                <div id="prepayment-panel" role="tabpanel" hidden={analysisTab !== 'prepayment'}>
                  {analysisTab === 'prepayment' && renderPrepaymentPanel()}
                </div>

                <div id="tax-panel" role="tabpanel" hidden={analysisTab !== 'tax'}>
                  {analysisTab === 'tax' && renderTaxPanel()}
                </div>
              </div>
            )}

            {/* Calendly Modal */}
            {showCalendly && (
              <div className="calendly-modal-overlay" onClick={() => setShowCalendly(false)}>
                <div className="calendly-modal" onClick={(e) => e.stopPropagation()}>
                  <div className="calendly-modal-header">
                    <h3>Schedule Your Free Consultation</h3>
                    <p>No cost, no obligation - just expert advice on your loan options</p>
                    <button className="btn-close-modal" onClick={() => setShowCalendly(false)}>
                      ✕
                    </button>
                  </div>
                  <div className="calendly-modal-body">
                    <div className="calendly-loading-fallback">
                      <div className="spinner"></div>
                      <p>Loading calendar...</p>
                      <a
                        href={calendlyUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="calendly-direct-link"
                      >
                        Click here if calendar doesn't load
                      </a>
                    </div>
                    <div
                      className="calendly-inline-widget"
                      data-url={calendlyUrl}
                      style={{ minWidth: '320px', height: '630px' }}
                    />
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Footer info */}
      <div className="page-footer">
        <div className="footer-info">
          <p>
            <strong>Privacy First:</strong> Your documents are processed securely.
            Personal information is redacted before AI analysis.
          </p>
          <p className="disclaimer">
            This tool provides estimates for comparison purposes only.
            Actual loan terms may vary. Contact a loan officer for official quotes.
          </p>
        </div>
      </div>
    </div>
  );
}

export default EstimateComparison;

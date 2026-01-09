import React, { createContext, useContext, useState, useCallback } from 'react';
import { decisionLabAPI } from '../services/decisionLabApi';
import { loansAPI } from '../services/api';

// Default shared data structure
const defaultSharedData = {
  purchasePrice: null,
  downPayment: null,
  downPaymentPercent: null,
  loanAmount: null,
  creditScore: 720,
  propertyType: 'single_family',
  occupancy: 'primary',
  state: '',
  county: '',
  loanType: 'conventional',
  interestRate: null,
  loanTerm: 30,
  // Computed values from calculator
  monthlyPayment: null,
  ltv: null,
  pmi: null,
  propertyTax: null,
  insurance: null,
};

// Context
const MortgageLabContext = createContext(null);

// Map occupancy values between different formats
const occupancyMap = {
  // Scenario -> Calculator
  toCalculator: {
    primary: 'primaryResidence',
    second_home: 'secondHome',
    investment: 'rental',
  },
  // Calculator -> Scenario
  toScenario: {
    primaryResidence: 'primary',
    secondHome: 'second_home',
    rental: 'investment',
  },
};

export function MortgageLabProvider({ children }) {
  // Shared data state
  const [sharedData, setSharedData] = useState(defaultSharedData);

  // Track where data originated
  const [dataSource, setDataSource] = useState(null); // 'scenario' | 'calculator' | 'application'

  // Session and application links
  const [sessionId, setSessionId] = useState(null);
  const [applicationId, setApplicationId] = useState(null);
  const [activeScenarioId, setActiveScenarioId] = useState(null);

  // Calculator panel state
  const [calculatorPanelOpen, setCalculatorPanelOpen] = useState(false);
  const [activeCalculator, setActiveCalculator] = useState('payment');

  // Loading states
  const [importing, setImporting] = useState(false);
  const [converting, setConverting] = useState(false);

  // Update a single field in shared data
  const updateSharedData = useCallback((field, value, source = null) => {
    setSharedData(prev => ({
      ...prev,
      [field]: value,
    }));
    if (source) {
      setDataSource(source);
    }
  }, []);

  // Update multiple fields at once
  const updateMultipleFields = useCallback((updates, source = null) => {
    setSharedData(prev => ({
      ...prev,
      ...updates,
    }));
    if (source) {
      setDataSource(source);
    }
  }, []);

  // Sync data from a scenario
  const syncFromScenario = useCallback((scenario) => {
    if (!scenario) return;

    const updates = {
      purchasePrice: scenario.purchase_price || null,
      downPayment: scenario.down_payment || null,
      downPaymentPercent: scenario.down_payment_percent || null,
      loanAmount: scenario.loan_amount || null,
      creditScore: scenario.credit_score || 720,
      propertyType: scenario.property_type || 'single_family',
      occupancy: scenario.occupancy || scenario.occupancy_type || 'primary',
      state: scenario.state || scenario.property_state || '',
      county: scenario.county || scenario.property_county || '',
      loanType: scenario.loan_type || 'conventional',
      ltv: scenario.ltv_ratio || null,
    };

    // Calculate LTV if not provided
    if (!updates.ltv && updates.purchasePrice && updates.downPayment) {
      updates.ltv = ((updates.purchasePrice - updates.downPayment) / updates.purchasePrice) * 100;
    }

    // Calculate down payment percent if not provided
    if (!updates.downPaymentPercent && updates.purchasePrice && updates.downPayment) {
      updates.downPaymentPercent = (updates.downPayment / updates.purchasePrice) * 100;
    }

    setSharedData(prev => ({ ...prev, ...updates }));
    setDataSource('scenario');
    setActiveScenarioId(scenario.id || scenario.scenario_id);
  }, []);

  // Sync data from calculator results
  const syncFromCalculator = useCallback((calculatorData) => {
    if (!calculatorData) return;

    const updates = {
      purchasePrice: calculatorData.homeValue || null,
      downPayment: calculatorData.downPaymentAmount || null,
      downPaymentPercent: calculatorData.downPaymentPercent || null,
      loanAmount: calculatorData.loanAmount || null,
      creditScore: calculatorData.creditScore || 720,
      state: calculatorData.state || '',
      county: calculatorData.county || '',
      loanType: calculatorData.loanType || 'conventional',
      interestRate: calculatorData.interestRate || null,
      loanTerm: calculatorData.loanTermYears || 30,
      ltv: calculatorData.ltv || null,
      // Payment details
      monthlyPayment: calculatorData.payment?.totalMonthly || null,
      pmi: calculatorData.payment?.pmi || null,
      propertyTax: calculatorData.payment?.propertyTax || null,
      insurance: calculatorData.payment?.homeownersInsurance || null,
    };

    // Map occupancy from calculator format
    if (calculatorData.propertyUse) {
      updates.occupancy = occupancyMap.toScenario[calculatorData.propertyUse] || 'primary';
    }

    setSharedData(prev => ({ ...prev, ...updates }));
    setDataSource('calculator');
  }, []);

  // Import data from an existing loan application
  const syncFromApplication = useCallback(async (appId) => {
    if (!appId) return;

    setImporting(true);
    try {
      const loan = await loansAPI.getById(appId);

      const updates = {
        purchasePrice: loan.purchase_price || null,
        downPayment: loan.down_payment || null,
        loanAmount: loan.amount || loan.loan_amount || null,
        creditScore: loan.credit_score || 720,
        propertyType: loan.property_type || 'single_family',
        occupancy: loan.occupancy_type || 'primary',
        state: loan.property_state || '',
        county: loan.property_county || '',
        loanType: loan.loan_type || 'conventional',
        interestRate: loan.rate || null,
        loanTerm: loan.term || 30,
      };

      setSharedData(prev => ({ ...prev, ...updates }));
      setDataSource('application');
      setApplicationId(appId);

      return loan;
    } catch (error) {
      console.error('Failed to import application:', error);
      throw error;
    } finally {
      setImporting(false);
    }
  }, []);

  // Convert current scenario to a loan application
  const convertToApplication = useCallback(async () => {
    if (!activeScenarioId) {
      throw new Error('No active scenario to convert');
    }

    setConverting(true);
    try {
      const result = await decisionLabAPI.convertToApplication(activeScenarioId);
      setApplicationId(result.application_id);
      return result;
    } catch (error) {
      console.error('Failed to convert scenario:', error);
      throw error;
    } finally {
      setConverting(false);
    }
  }, [activeScenarioId]);

  // Get data formatted for PaymentCalculator props
  const getCalculatorProps = useCallback(() => {
    return {
      initialHomeValue: sharedData.purchasePrice || 0,
      initialDownPayment: sharedData.downPayment || 0,
      initialState: sharedData.state || '',
      initialCounty: sharedData.county || '',
      initialPropertyUse: occupancyMap.toCalculator[sharedData.occupancy] || 'primaryResidence',
      initialCreditScore: sharedData.creditScore || 720,
      initialLoanType: sharedData.loanType || 'conventional',
    };
  }, [sharedData]);

  // Get data formatted for scenario creation
  const getScenarioData = useCallback(() => {
    return {
      purchase_price: sharedData.purchasePrice,
      down_payment: sharedData.downPayment,
      loan_amount: sharedData.loanAmount || (sharedData.purchasePrice - sharedData.downPayment),
      credit_score: sharedData.creditScore,
      property_type: sharedData.propertyType,
      occupancy: sharedData.occupancy,
      state: sharedData.state,
      loan_type: sharedData.loanType,
    };
  }, [sharedData]);

  // Toggle calculator panel
  const toggleCalculatorPanel = useCallback(() => {
    setCalculatorPanelOpen(prev => !prev);
  }, []);

  // Reset all data
  const resetData = useCallback(() => {
    setSharedData(defaultSharedData);
    setDataSource(null);
    setApplicationId(null);
    setActiveScenarioId(null);
  }, []);

  const value = {
    // Data
    sharedData,
    dataSource,
    sessionId,
    applicationId,
    activeScenarioId,

    // Methods
    updateSharedData,
    updateMultipleFields,
    syncFromScenario,
    syncFromCalculator,
    syncFromApplication,
    convertToApplication,
    getCalculatorProps,
    getScenarioData,
    resetData,

    // Session management
    setSessionId,
    setApplicationId,
    setActiveScenarioId,

    // Panel state
    calculatorPanelOpen,
    activeCalculator,
    toggleCalculatorPanel,
    setActiveCalculator,

    // Loading states
    importing,
    converting,
  };

  return (
    <MortgageLabContext.Provider value={value}>
      {children}
    </MortgageLabContext.Provider>
  );
}

// Custom hook for using the context
export function useMortgageLab() {
  const context = useContext(MortgageLabContext);
  if (!context) {
    throw new Error('useMortgageLab must be used within a MortgageLabProvider');
  }
  return context;
}

export default MortgageLabContext;

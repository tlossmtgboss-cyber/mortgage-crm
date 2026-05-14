import React, { useState, useMemo } from 'react';
import { getLocationRates, STATE_DATA } from '../../services/calculator/CalculatorService';
import { CALCULATOR_PHASES, DEFAULT_PROFILE, DEFAULT_MARKET, DEFAULT_PROPERTY } from './constants';
import { buildCalculators } from './buildCalculators';

// View imports
import ClientDataView from './views/ClientDataView';
import DownPaymentView from './views/DownPaymentView';
import MonthlyPaymentView from './views/MonthlyPaymentView';
import DTIView from './views/DTIView';
import RentVsBuyView from './views/RentVsBuyView';
import CashReservesView from './views/CashReservesView';
import ClosingCostsView from './views/ClosingCostsView';
import RepaymentStrategyView from './views/RepaymentStrategyView';
import ExitStrategyView from './views/ExitStrategyView';
import ProgramOptionsView from './views/ProgramOptionsView';
import CostToWaitingView from './views/CostToWaitingView';
import PrepayOrInvestView from './views/PrepayOrInvestView';
import EmergencyRunwayView from './views/EmergencyRunwayView';
import StressTestView from './views/StressTestView';
import PaymentShockView from './views/PaymentShockView';
import LifestyleFitView from './views/LifestyleFitView';
import BreakEvenHorizonView from './views/BreakEvenHorizonView';
import EquityVelocityView from './views/EquityVelocityView';
import TaxBenefitView from './views/TaxBenefitView';
import InflationHedgeView from './views/InflationHedgeView';
import JobMobilityView from './views/JobMobilityView';

import '../CalculatorDashboard.css';

const CalculatorDashboard = ({ initialProfile = DEFAULT_PROFILE, initialMarket = DEFAULT_MARKET, initialProperty = DEFAULT_PROPERTY }) => {
  const [activeCalculator, setActiveCalculator] = useState('client-data');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [expandedPhases, setExpandedPhases] = useState(['phase-1']);

  const togglePhase = (phaseId) => {
    setExpandedPhases(prev =>
      prev.includes(phaseId)
        ? prev.filter(id => id !== phaseId)
        : [...prev, phaseId]
    );
  };

  // Editable state for all inputs
  const [profileData, setProfileData] = useState(initialProfile);
  const [marketData, setMarketData] = useState(initialMarket);
  const [propertyData, setPropertyData] = useState(initialProperty);

  // Auto-calculate tax and insurance rates based on location
  const locationRates = useMemo(() => {
    return getLocationRates(propertyData.state, propertyData.county);
  }, [propertyData.state, propertyData.county]);

  // Compute effective tax and insurance rates (override or auto-calculated)
  const effectiveRates = useMemo(() => ({
    taxRate: propertyData.taxRateOverride !== null ? propertyData.taxRateOverride : locationRates.taxRate,
    insuranceRate: propertyData.insuranceRateOverride !== null ? propertyData.insuranceRateOverride : locationRates.insuranceRate,
  }), [propertyData.taxRateOverride, propertyData.insuranceRateOverride, locationRates]);

  // Compute effective interest rate with points
  const effectiveInterestRate = useMemo(() => {
    return marketData.interestRate - (marketData.points * marketData.pointsDiscount);
  }, [marketData.interestRate, marketData.points, marketData.pointsDiscount]);

  // Combined profile with monthly income calculated
  const profile = useMemo(() => ({
    ...profileData,
    monthlyIncome: profileData.annualIncome / 12,
  }), [profileData]);

  // Combined market data with effective rates
  const market = useMemo(() => ({
    ...marketData,
    interestRate: effectiveInterestRate,
    taxRate: effectiveRates.taxRate,
    insuranceRate: effectiveRates.insuranceRate,
  }), [marketData, effectiveInterestRate, effectiveRates]);

  // Build calculators with current data
  const calculators = useMemo(() => {
    const calcs = buildCalculators(profile, market, propertyData);
    return [
      {
        id: 'client-data',
        name: 'Client Data',
        color: '#0ea5e9',
        shortDescription: 'Edit inputs & assumptions',
        data: {
          profile: profileData,
          market: marketData,
          property: propertyData,
          locationRates,
          effectiveRates,
          effectiveInterestRate,
        },
      },
      ...calcs,
    ];
  }, [profile, market, propertyData, profileData, marketData, locationRates, effectiveRates, effectiveInterestRate]);

  const active = calculators.find((c) => c.id === activeCalculator);

  // Handlers for updating data
  const updateProfile = (updates) => {
    setProfileData(prev => ({ ...prev, ...updates }));
  };

  const updateMarket = (updates) => {
    setMarketData(prev => ({ ...prev, ...updates }));
  };

  const updateProperty = (updates) => {
    setPropertyData(prev => ({ ...prev, ...updates }));
  };

  const handleScenarioUpdate = (updates) => {
    if (updates.homePrice !== undefined || updates.downPaymentPct !== undefined) {
      updateProperty(updates);
    } else {
      updateMarket(updates);
    }
  };

  const renderDetail = () => {
    if (!active) return null;

    switch (active.id) {
      case 'client-data':
        return (
          <ClientDataView
            data={active.data}
            onUpdateProfile={updateProfile}
            onUpdateMarket={updateMarket}
            onUpdateProperty={updateProperty}
            stateData={STATE_DATA}
          />
        );
      case 'down-payment':
        return <DownPaymentView data={active.data} profile={profile} />;
      case 'monthly-payment':
        return <MonthlyPaymentView data={active.data} />;
      case 'dti':
        return <DTIView data={active.data} profile={profile} />;
      case 'rent-vs-buy':
        return <RentVsBuyView data={active.data} />;
      case 'cash-reserves':
        return <CashReservesView data={active.data} />;
      case 'closing-costs':
        return <ClosingCostsView data={active.data} />;
      case 'repayment-strategy':
        return <RepaymentStrategyView data={active.data} />;
      case 'exit-strategy':
        return <ExitStrategyView data={active.data} />;
      case 'program-options':
        return <ProgramOptionsView data={active.data} />;
      case 'cost-to-waiting':
        return <CostToWaitingView data={active.data} />;
      case 'prepay-or-invest':
        return <PrepayOrInvestView data={active.data} />;
      case 'emergency-runway':
        return <EmergencyRunwayView data={active.data} />;
      case 'stress-test':
        return <StressTestView data={active.data} />;
      case 'payment-shock':
        return <PaymentShockView data={active.data} />;
      case 'lifestyle-fit':
        return <LifestyleFitView data={active.data} />;
      case 'break-even-horizon':
        return <BreakEvenHorizonView data={active.data} property={propertyData} market={marketData} onUpdate={handleScenarioUpdate} />;
      case 'equity-velocity':
        return <EquityVelocityView data={active.data} property={propertyData} market={marketData} onUpdate={handleScenarioUpdate} />;
      case 'tax-benefit':
        return <TaxBenefitView data={active.data} property={propertyData} market={marketData} onUpdate={handleScenarioUpdate} />;
      case 'inflation-hedge':
        return <InflationHedgeView data={active.data} property={propertyData} market={marketData} onUpdate={handleScenarioUpdate} />;
      case 'job-mobility':
        return <JobMobilityView data={active.data} property={propertyData} market={marketData} onUpdate={handleScenarioUpdate} />;
      default:
        return null;
    }
  };

  const handleCalculatorChange = (calcId) => {
    setActiveCalculator(calcId);
    setMobileMenuOpen(false);
  };

  return (
    <div className="calculator-dashboard">
      {/* Header */}
      <div className="dashboard-header">
        <div className="header-content">
          <h1>{profile.name}'s Home Buying Analysis</h1>
        </div>
      </div>

      <div className="dashboard-body">
        {/* Mobile Overlay */}
        <div
          className={`mobile-overlay ${mobileMenuOpen ? 'active' : ''}`}
          onClick={() => setMobileMenuOpen(false)}
        />

        {/* Sidebar */}
        <div className={`calculator-sidebar ${mobileMenuOpen ? 'mobile-open' : ''}`}>
          {/* Client Data Button - Always at top */}
          <div className="sidebar-client-data">
            <button
              className={`nav-item client-data-btn ${activeCalculator === 'client-data' ? 'active' : ''}`}
              onClick={() => handleCalculatorChange('client-data')}
              style={{ '--calc-color': '#0ea5e9' }}
            >
              <div className="nav-content">
                <span className="nav-name">Client Data</span>
                <span className="nav-description">Edit inputs & assumptions</span>
              </div>
            </button>
          </div>

          {/* Phase Navigation */}
          <nav className="phase-navigation">
            {CALCULATOR_PHASES.map((phase) => (
              <div key={phase.id} className="phase-group" data-phase={phase.id}>
                <button
                  className={`phase-header ${expandedPhases.includes(phase.id) ? 'expanded' : ''}`}
                  onClick={() => togglePhase(phase.id)}
                  style={{
                    '--phase-color': phase.colorPrimary,
                    '--phase-bg': phase.colorBg,
                    '--phase-border': phase.colorBorder,
                  }}
                >
                  <span className="phase-icon">{phase.icon}</span>
                  <div className="phase-info">
                    <span className="phase-name">{phase.name}</span>
                    <span className="phase-subtitle">{phase.subtitle}</span>
                  </div>
                  <span className="phase-chevron">{expandedPhases.includes(phase.id) ? '▼' : '▶'}</span>
                </button>

                {expandedPhases.includes(phase.id) && (
                  <div className="phase-calculators">
                    {phase.calculators.map((calcId) => {
                      const calc = calculators.find(c => c.id === calcId);
                      if (!calc) return null;
                      return (
                        <button
                          key={calcId}
                          className={`phase-calc-item ${activeCalculator === calcId ? 'active' : ''}`}
                          onClick={() => handleCalculatorChange(calcId)}
                          style={{ '--phase-color': phase.colorPrimary }}
                        >
                          <span className="phase-calc-name">{calc.name}</span>
                          <span className="phase-calc-desc">{calc.shortDescription}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            ))}
          </nav>
        </div>

        {/* Main Content */}
        <div className="calculator-main">
          {renderDetail()}
        </div>
      </div>

      {/* Mobile Menu Toggle */}
      <button
        className="mobile-menu-toggle"
        onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        aria-label="Toggle menu"
      >
        {mobileMenuOpen ? (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        ) : (
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="3" y1="12" x2="21" y2="12" />
            <line x1="3" y1="6" x2="21" y2="6" />
            <line x1="3" y1="18" x2="21" y2="18" />
          </svg>
        )}
      </button>

      {/* Footer */}
      <div className="dashboard-footer">
        <p>
          Calculations are estimates for informational purposes. Actual rates, payments, and costs may vary.
        </p>
      </div>
    </div>
  );
};

export default CalculatorDashboard;

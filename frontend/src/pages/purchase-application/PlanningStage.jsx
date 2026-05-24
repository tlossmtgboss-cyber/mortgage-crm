import React from 'react';
import PaymentCalculator from '../../components/PaymentCalculator';
import { Icon } from '../application-shared';
import { PLANNING_QUESTIONS } from './planningQuestions';

/**
 * PlanningStage - Multi-step mortgage questionnaire: payment calculator,
 * priorities, goals, financial philosophy, retirement, professional network.
 */
export default function PlanningStage({
  propertyData,
  planningData,
  setPlanningData,
  planningStep,
  setPlanningStep,
  professionalSubStep,
  setProfessionalSubStep,
  wantProfessionalsInvolved,
  setWantProfessionalsInvolved,
  professionalContacts,
  setProfessionalContacts,
  wantIntroductions,
  setWantIntroductions,
  introductionRequests,
  setIntroductionRequests,
  paymentEstimate,
  setPaymentEstimate,
  goToPrevStage,
  goToNextStage,
}) {
  const togglePlanningOption = (field, value) => {
    setPlanningData(prev => {
      const current = prev[field] || [];
      if (current.includes(value)) {
        return { ...prev, [field]: current.filter(v => v !== value) };
      } else {
        return { ...prev, [field]: [...current, value] };
      }
    });
  };

  const selectedProfessionals = planningData.professionalNetwork || [];
  const professionalLabels = {
    financial_planner: 'Financial Planner',
    accountant: 'CPA / Accountant',
    insurance_agent: 'Life Insurance Agent',
    estate_planner: 'Estate Planner'
  };

  // Step 1: Payment Calculator
  if (planningStep === 1) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header">
          <h2>Your Monthly Payment Estimate</h2>
          <p>See how your down payment affects your monthly cost. Adjust the values to find your comfort zone.</p>
        </div>
        <div className="form-card planning-section payment-calculator-section">
          <PaymentCalculator
            initialHomeValue={parseFloat(propertyData.purchasePrice) || 0}
            initialDownPayment={parseFloat(propertyData.downPayment) || 0}
            initialState={propertyData.state || ''}
            initialCounty={propertyData.county || ''}
            initialPropertyUse={propertyData.occupancy === 'primary' ? 'primaryResidence' : propertyData.occupancy === 'second' ? 'secondHome' : propertyData.occupancy === 'investment' ? 'rental' : 'primaryResidence'}
            showAdvancedOptions={true}
            onCalculationComplete={(calculation) => setPaymentEstimate(calculation)}
          />
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={goToPrevStage}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => setPlanningStep(2)}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Step 2: Mortgage Priorities
  if (planningStep === 2) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header"><h2>What matters most to you in your mortgage?</h2><p>Select all that apply - this helps us find the best loan options for you.</p></div>
        <div className="form-card planning-section">
          <div className="multi-select-grid">
            {PLANNING_QUESTIONS.mortgagePriorities.options.map(option => (
              <button key={option.value} className={`multi-select-option ${planningData.mortgagePriorities.includes(option.value) ? 'selected' : ''}`} onClick={() => togglePlanningOption('mortgagePriorities', option.value)}>
                <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                <span className="option-label">{option.label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPlanningStep(1)}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => setPlanningStep(3)}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Step 3: Personal Goals
  if (planningStep === 3) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header"><h2>What are your personal financial goals?</h2><p>Select all that apply - help us align your mortgage with your life plans.</p></div>
        <div className="form-card planning-section">
          <div className="multi-select-grid">
            {PLANNING_QUESTIONS.personalGoals.options.map(option => (
              <button key={option.value} className={`multi-select-option ${planningData.personalGoals.includes(option.value) ? 'selected' : ''}`} onClick={() => togglePlanningOption('personalGoals', option.value)}>
                <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                <span className="option-label">{option.label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPlanningStep(2)}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => setPlanningStep(4)}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Step 4: Financial Philosophy
  if (planningStep === 4) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header"><h2>How would you describe your financial approach?</h2><p>This helps us recommend the right loan structure for your style.</p></div>
        <div className="form-card planning-section">
          <div className="philosophy-options">
            {PLANNING_QUESTIONS.financialPhilosophy.options.map(option => (
              <button key={option.value} className={`philosophy-option ${planningData.financialPhilosophy === option.value ? 'selected' : ''}`} onClick={() => setPlanningData(prev => ({ ...prev, financialPhilosophy: option.value }))}>
                <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                <span className="option-label">{option.label}</span>
                <span className="option-description">{option.description}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPlanningStep(3)}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => setPlanningStep(5)}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Step 5: Tax-Deferred Retirement
  if (planningStep === 5) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header"><h2>Are you currently contributing to a tax-deferred retirement account?</h2><p>We can coordinate with your existing team for a comprehensive financial plan.</p></div>
        <div className="form-card planning-section">
          <div className="single-select-options">
            {PLANNING_QUESTIONS.taxDeferredRetirement.options.map(option => (
              <button key={option.value} className={`single-select-option ${planningData.taxDeferredRetirement === option.value ? 'selected' : ''}`} onClick={() => setPlanningData(prev => ({ ...prev, taxDeferredRetirement: option.value }))}>
                <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                <span className="option-label">{option.label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPlanningStep(4)}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => setPlanningStep(6)}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Step 6: Professional Network (with substeps)
  if (professionalSubStep === 1) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header"><h2>Do you currently work with any of these professionals?</h2><p>We can coordinate with your existing team for a comprehensive financial plan.</p></div>
        <div className="form-card planning-section">
          <div className="multi-select-grid compact">
            {PLANNING_QUESTIONS.professionalNetwork.options.map(option => (
              <button key={option.value} className={`multi-select-option ${selectedProfessionals.includes(option.value) ? 'selected' : ''}`} onClick={() => togglePlanningOption('professionalNetwork', option.value)}>
                <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                <span className="option-label">{option.label}</span>
              </button>
            ))}
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setPlanningStep(5)}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => {
            if (selectedProfessionals.length > 0) setProfessionalSubStep(2);
            else setProfessionalSubStep(4);
          }}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  if (professionalSubStep === 2 && selectedProfessionals.length > 0) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header"><h2>Would you like your professionals involved in the decision-making process?</h2><p>We can keep them informed and coordinate for a seamless experience.</p></div>
        <div className="form-card planning-section">
          <div className="single-select-options">
            <button className={`single-select-option ${wantProfessionalsInvolved === true ? 'selected' : ''}`} onClick={() => setWantProfessionalsInvolved(true)}><span className="option-icon"><Icon name="check" size={32} /></span><span className="option-label">Yes, please involve them</span></button>
            <button className={`single-select-option ${wantProfessionalsInvolved === false ? 'selected' : ''}`} onClick={() => setWantProfessionalsInvolved(false)}><span className="option-icon"><Icon name="x" size={32} /></span><span className="option-label">No, not at this time</span></button>
          </div>
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setProfessionalSubStep(1)}>{'←'} Back</button>
          <button className="btn-continue" disabled={wantProfessionalsInvolved === null} onClick={() => {
            if (wantProfessionalsInvolved) setProfessionalSubStep(3);
            else { setPlanningStep(1); goToNextStage(); }
          }}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  if (professionalSubStep === 3) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header"><h2>Please provide your professionals' contact information</h2><p>We'll reach out to coordinate on your behalf.</p></div>
        <div className="form-card professional-contacts-form">
          {selectedProfessionals.map((prof, index) => (
            <div key={prof} className="professional-contact-section">
              <h4><Icon name={PLANNING_QUESTIONS.professionalNetwork.options.find(o => o.value === prof)?.icon || 'user'} size={20} /> {professionalLabels[prof]}</h4>
              <div className="form-row">
                <div className="form-group"><label>First Name</label><input type="text" className="fun-input" placeholder="First name" value={professionalContacts[prof]?.firstName || ''} onChange={(e) => setProfessionalContacts(prev => ({ ...prev, [prof]: { ...prev[prof], firstName: e.target.value } }))} /></div>
                <div className="form-group"><label>Last Name</label><input type="text" className="fun-input" placeholder="Last name" value={professionalContacts[prof]?.lastName || ''} onChange={(e) => setProfessionalContacts(prev => ({ ...prev, [prof]: { ...prev[prof], lastName: e.target.value } }))} /></div>
              </div>
              <div className="form-row">
                <div className="form-group"><label>Phone</label><input type="tel" className="fun-input" placeholder="(555) 123-4567" value={professionalContacts[prof]?.phone || ''} onChange={(e) => setProfessionalContacts(prev => ({ ...prev, [prof]: { ...prev[prof], phone: e.target.value } }))} /></div>
                <div className="form-group"><label>Email</label><input type="email" className="fun-input" placeholder="email@example.com" value={professionalContacts[prof]?.email || ''} onChange={(e) => setProfessionalContacts(prev => ({ ...prev, [prof]: { ...prev[prof], email: e.target.value } }))} /></div>
              </div>
              {index < selectedProfessionals.length - 1 && <hr className="section-divider" />}
            </div>
          ))}
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setProfessionalSubStep(2)}>{'←'} Back</button>
          <button className="btn-continue" onClick={() => { setPlanningStep(1); goToNextStage(); }}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  if (professionalSubStep === 4) {
    return (
      <div className="stage-content planning-stage">
        <div className="stage-header"><h2>Would you like an introduction to a trusted professional?</h2><p>We partner with qualified professionals who can help with your financial planning.</p></div>
        <div className="form-card planning-section">
          <div className="single-select-options" style={{ marginBottom: '24px' }}>
            <button className={`single-select-option ${wantIntroductions === true ? 'selected' : ''}`} onClick={() => setWantIntroductions(true)}><span className="option-icon"><Icon name="check" size={32} /></span><span className="option-label">Yes, please connect me</span></button>
            <button className={`single-select-option ${wantIntroductions === false ? 'selected' : ''}`} onClick={() => setWantIntroductions(false)}><span className="option-icon"><Icon name="x" size={32} /></span><span className="option-label">No thanks, not at this time</span></button>
          </div>
          {wantIntroductions === true && (
            <div className="intro-selection">
              <h4>Select who you'd like to connect with:</h4>
              <div className="multi-select-grid compact">
                {PLANNING_QUESTIONS.professionalNetwork.options.map(option => (
                  <button key={option.value} className={`multi-select-option ${introductionRequests.includes(option.value) ? 'selected' : ''}`} onClick={() => { setIntroductionRequests(prev => prev.includes(option.value) ? prev.filter(v => v !== option.value) : [...prev, option.value]); }}>
                    <span className="option-icon"><Icon name={option.icon} size={32} /></span>
                    <span className="option-label">{option.label}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="stage-navigation">
          <button className="btn-back" onClick={() => setProfessionalSubStep(1)}>{'←'} Back</button>
          <button className="btn-continue" disabled={wantIntroductions === null} onClick={() => { setPlanningStep(1); goToNextStage(); }}>Continue {'→'}</button>
        </div>
      </div>
    );
  }

  // Fallback
  return (
    <div className="stage-content planning-stage">
      <div className="stage-navigation">
        <button className="btn-back" onClick={() => setPlanningStep(5)}>{'←'} Back</button>
        <button className="btn-continue" onClick={() => { setPlanningStep(1); goToNextStage(); }}>Continue {'→'}</button>
      </div>
    </div>
  );
}

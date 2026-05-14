import React from 'react';
import { formatCurrency } from '../../../services/calculator/CalculatorService';

const ClosingCostsView = ({ data }) => {
  const { closingCosts, homePrice, loanAmount, downPayment, totalCashNeeded, savings } = data;
  const shortfall = totalCashNeeded - savings;

  return (
    <div className="calculator-detail">
      <div className="detail-header">
        <h2>Closing Costs Breakdown</h2>
        <p className="detail-subtitle">Itemized costs for a <strong>{formatCurrency(homePrice)}</strong> home with 5% down</p>
      </div>

      <div className="closing-costs-summary">
        <div className="summary-card total"><div className="summary-label">Total Closing Costs</div><div className="summary-value">{formatCurrency(closingCosts.total)}</div></div>
        <div className="summary-card"><div className="summary-label">Down Payment</div><div className="summary-value">{formatCurrency(downPayment)}</div></div>
        <div className="summary-card highlight"><div className="summary-label">Total Cash Needed</div><div className="summary-value">{formatCurrency(totalCashNeeded)}</div></div>
      </div>

      {shortfall > 0 && (
        <div className="shortfall-warning">
          <div><strong>Cash Shortfall:</strong> You need {formatCurrency(shortfall)} more than your current savings of {formatCurrency(savings)}. Consider a lower down payment or gift funds.</div>
        </div>
      )}

      <div className="costs-sections">
        <div className="cost-section">
          <div className="section-header"><h4>Lender Fees</h4><span className="section-total">{formatCurrency(closingCosts.lenderFees.total)}</span></div>
          <div className="cost-items">
            <div className="cost-item"><span>Origination Fee (1%)</span><span>{formatCurrency(closingCosts.lenderFees.originationFee)}</span></div>
            <div className="cost-item"><span>Underwriting Fee</span><span>{formatCurrency(closingCosts.lenderFees.underwritingFee)}</span></div>
            <div className="cost-item"><span>Processing Fee</span><span>{formatCurrency(closingCosts.lenderFees.processingFee)}</span></div>
            <div className="cost-item"><span>Credit Report</span><span>{formatCurrency(closingCosts.lenderFees.creditReport)}</span></div>
            <div className="cost-item"><span>Flood Certification</span><span>{formatCurrency(closingCosts.lenderFees.floodCert)}</span></div>
          </div>
        </div>

        <div className="cost-section">
          <div className="section-header"><h4>Third Party Fees</h4><span className="section-total">{formatCurrency(closingCosts.thirdPartyFees.total)}</span></div>
          <div className="cost-items">
            <div className="cost-item"><span>Appraisal</span><span>{formatCurrency(closingCosts.thirdPartyFees.appraisal)}</span></div>
            <div className="cost-item"><span>Title Search</span><span>{formatCurrency(closingCosts.thirdPartyFees.titleSearch)}</span></div>
            <div className="cost-item"><span>Title Insurance</span><span>{formatCurrency(closingCosts.thirdPartyFees.titleInsurance)}</span></div>
            <div className="cost-item"><span>Settlement/Escrow Fee</span><span>{formatCurrency(closingCosts.thirdPartyFees.settlementFee)}</span></div>
            <div className="cost-item"><span>Recording Fees</span><span>{formatCurrency(closingCosts.thirdPartyFees.recordingFees)}</span></div>
            <div className="cost-item"><span>Survey</span><span>{formatCurrency(closingCosts.thirdPartyFees.survey)}</span></div>
          </div>
        </div>

        <div className="cost-section">
          <div className="section-header"><h4>Prepaid Items</h4><span className="section-total">{formatCurrency(closingCosts.prepaids.total)}</span></div>
          <div className="cost-items">
            <div className="cost-item"><span>Prepaid Interest (15 days)</span><span>{formatCurrency(closingCosts.prepaids.prepaidInterest)}</span></div>
            <div className="cost-item"><span>Homeowners Insurance (1 year)</span><span>{formatCurrency(closingCosts.prepaids.prepaidInsurance)}</span></div>
            <div className="cost-item"><span>Property Taxes (3 months)</span><span>{formatCurrency(closingCosts.prepaids.prepaidTaxes)}</span></div>
          </div>
        </div>

        <div className="cost-section">
          <div className="section-header"><h4>Escrow Reserves</h4><span className="section-total">{formatCurrency(closingCosts.escrows.total)}</span></div>
          <div className="cost-items">
            <div className="cost-item"><span>Insurance Reserve (2 months)</span><span>{formatCurrency(closingCosts.escrows.escrowInsurance)}</span></div>
            <div className="cost-item"><span>Tax Reserve (2 months)</span><span>{formatCurrency(closingCosts.escrows.escrowTaxes)}</span></div>
          </div>
        </div>
      </div>

      <div className="closing-costs-footer">
        <div className="footer-note">
          <div><strong>Good to know:</strong> Some of these costs may be negotiable or could be covered by seller concessions. Ask your loan officer about options to reduce out-of-pocket expenses.</div>
        </div>
      </div>
    </div>
  );
};

export default ClosingCostsView;

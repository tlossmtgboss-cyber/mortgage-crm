import React from 'react';
import { Icon } from '../application-shared';

/**
 * AssetsStage - Down payment funds collection (checking, savings, investments, gifts).
 */
export default function AssetsStage({
  declarations,
  assetData,
  setAssetData,
  handleAssetFieldChange,
  goToPrevStage,
  goToNextStage,
}) {
  const hasGiftFunds = declarations.gift_funds === 'yes';

  return (
    <div className="stage-content">
      <div className="stage-header">
        <h2>Your Down Payment Funds</h2>
        <p>Let's see what you have saved for your new home</p>
      </div>
      <div className="form-card">
        <div className="form-row">
          <div className="form-group">
            <label>Checking Accounts</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={assetData.checking || ''} onChange={(e) => setAssetData(prev => ({ ...prev, checking: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Savings Accounts</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={assetData.savings || ''} onChange={(e) => setAssetData(prev => ({ ...prev, savings: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
        </div>

        <div className="form-row">
          <div className="form-group">
            <label>Investment Accounts</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={assetData.investments || ''} onChange={(e) => setAssetData(prev => ({ ...prev, investments: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
          <div className="form-group">
            <label>Retirement (401k, IRA)</label>
            <div className="input-with-prefix">
              <span className="input-prefix">$</span>
              <input type="number" value={assetData.retirement || ''} onChange={(e) => setAssetData(prev => ({ ...prev, retirement: e.target.value }))} className="fun-input" placeholder="0" />
            </div>
          </div>
        </div>

        {hasGiftFunds && (
          <div className="gift-funds-section">
            <h3><Icon name="gift" size={20} /> Gift Funds Details</h3>
            <p className="section-hint">Great news! Gift funds can help with your down payment.</p>
            <div className="form-group">
              <label>Gift Amount</label>
              <div className="input-with-prefix">
                <span className="input-prefix">$</span>
                <input type="number" value={assetData.giftAmount || ''} onChange={(e) => handleAssetFieldChange('giftAmount', e.target.value, setAssetData)} className="fun-input" />
              </div>
            </div>
            <div className="form-row">
              <div className="form-group">
                <label>Donor Name</label>
                <input type="text" value={assetData.donorName || ''} onChange={(e) => handleAssetFieldChange('donorName', e.target.value, setAssetData)} className="fun-input" placeholder="Who is giving the gift?" />
              </div>
              <div className="form-group">
                <label>Relationship</label>
                <select value={assetData.donorRelationship || ''} onChange={(e) => setAssetData(prev => ({ ...prev, donorRelationship: e.target.value }))} className="fun-input">
                  <option value="">Select...</option>
                  <option value="parent">Parent</option>
                  <option value="grandparent">Grandparent</option>
                  <option value="sibling">Sibling</option>
                  <option value="other_family">Other Family</option>
                </select>
              </div>
            </div>
          </div>
        )}
      </div>

      <div className="total-assets-display">
        <span>Total Available for Down Payment:</span>
        <strong>
          ${(
            (parseFloat(assetData.checking) || 0) +
            (parseFloat(assetData.savings) || 0) +
            (parseFloat(assetData.investments) || 0) +
            (parseFloat(assetData.giftAmount) || 0)
          ).toLocaleString()}
        </strong>
      </div>

      <div className="stage-navigation">
        <button className="btn-back" onClick={goToPrevStage}>{'←'} Back</button>
        <button className="btn-continue" onClick={goToNextStage}>Continue {'→'}</button>
      </div>
    </div>
  );
}

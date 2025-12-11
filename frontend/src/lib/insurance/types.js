/**
 * Insurance Types and Constants
 * @module lib/insurance/types
 */

/**
 * @typedef {'frame' | 'masonry' | 'superior' | 'manufactured'} ConstructionType
 */

/**
 * @typedef {'asphaltShingle' | 'metal' | 'tile' | 'woodShake' | 'flat'} RoofType
 */

/**
 * @typedef {Object} HomeCharacteristics
 * @property {number} squareFootage
 * @property {number} yearBuilt
 * @property {ConstructionType} constructionType
 * @property {RoofType} [roofType]
 * @property {number} [roofAge]
 * @property {number} [stories]
 * @property {boolean} [fireplace]
 * @property {boolean} [swimmingPool]
 * @property {boolean} [trampoline]
 * @property {'high-risk' | 'low-risk' | 'none'} [dogBreed]
 */

/**
 * @typedef {Object} RiskFactors
 * @property {boolean} [coastalProperty]
 * @property {boolean} [floodZone]
 * @property {boolean} [wildFireZone]
 * @property {boolean} [earthquakeZone]
 * @property {boolean} [windstormZone]
 * @property {boolean} [crimeLow]
 * @property {boolean} [crimeHigh]
 * @property {boolean} [gatedCommunity]
 */

/**
 * @typedef {Object} CoverageOptions
 * @property {number} dwellingCoverage
 * @property {number} [personalPropertyPercent]
 * @property {number} [liabilityCoverage]
 * @property {number} [medicalPayments]
 * @property {number} deductible
 * @property {boolean} [replacementCostCoverage]
 */

/**
 * @typedef {Object} Discounts
 * @property {boolean} [multiPolicy]
 * @property {boolean} [securitySystem]
 * @property {boolean} [fireAlarm]
 * @property {boolean} [sprinklerSystem]
 * @property {boolean} [deadbolts]
 * @property {boolean} [newHome]
 * @property {number} [claimsFreeDays]
 * @property {boolean} [seniorCitizen]
 * @property {boolean} [nonSmoker]
 * @property {boolean} [paidInFull]
 */

/**
 * @typedef {Object} StateInsuranceData
 * @property {string} stateCode
 * @property {string} stateName
 * @property {number} averageAnnualPremium
 * @property {number} costPerThousand
 * @property {CountyInsuranceData[]} [counties]
 */

/**
 * @typedef {Object} CountyInsuranceData
 * @property {string} countyName
 * @property {string} fips
 * @property {number} averageAnnualPremium
 * @property {number} riskMultiplier
 * @property {boolean} [coastalCounty]
 * @property {boolean} [highFireRisk]
 */

/**
 * @typedef {Object} InsuranceInput
 * @property {string} stateCode
 * @property {string} [countyFips]
 * @property {number} homeValue
 * @property {HomeCharacteristics} [homeCharacteristics]
 * @property {CoverageOptions} coverageOptions
 * @property {RiskFactors} [riskFactors]
 * @property {Discounts} [discounts]
 */

/**
 * @typedef {Object} InsuranceBreakdown
 * @property {number} basePremium
 * @property {number} riskAdjustments
 * @property {number} discountAmount
 * @property {number} finalPremium
 */

/**
 * @typedef {Object} CoverageSummary
 * @property {number} dwelling
 * @property {number} personalProperty
 * @property {number} liability
 * @property {number} deductible
 */

/**
 * @typedef {Object} InsuranceOutput
 * @property {number} annualPremium
 * @property {number} monthlyPremium
 * @property {'basic' | 'standard' | 'advanced'} method
 * @property {InsuranceBreakdown} breakdown
 * @property {CoverageSummary} coverageSummary
 * @property {string[]} [recommendations]
 */

export const CONSTRUCTION_TYPES = {
  FRAME: 'frame',
  MASONRY: 'masonry',
  SUPERIOR: 'superior',
  MANUFACTURED: 'manufactured',
};

export const ROOF_TYPES = {
  ASPHALT_SHINGLE: 'asphaltShingle',
  METAL: 'metal',
  TILE: 'tile',
  WOOD_SHAKE: 'woodShake',
  FLAT: 'flat',
};

export const DEFAULT_DEDUCTIBLES = [500, 1000, 2000, 2500, 5000];
export const DEFAULT_LIABILITY_OPTIONS = [100000, 300000, 500000, 1000000];

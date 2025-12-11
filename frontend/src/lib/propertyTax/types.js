/**
 * Property Tax Types and Constants
 * @module lib/propertyTax/types
 */

/**
 * @typedef {'primaryResidence' | 'secondHome' | 'rental' | 'commercial'} PropertyUseType
 */

/**
 * @typedef {Object} ExemptionsInput
 * @property {boolean} [homestead]
 * @property {boolean} [senior]
 * @property {boolean} [disabledVeteran]
 * @property {number} [customPercentReduction]
 */

/**
 * @typedef {Object} AdvancedConfig
 * @property {Object} [assessmentRatios]
 * @property {number} [assessmentRatios.primaryResidence]
 * @property {number} [assessmentRatios.secondHome]
 * @property {number} [assessmentRatios.rental]
 * @property {number} [assessmentRatios.commercial]
 * @property {Object} [millageRates]
 * @property {number} millageRates.baseMillage
 * @property {number} [millageRates.schoolOperatingMillage]
 * @property {number} [millageRates.cityMillage]
 * @property {Object} [creditsPerDollar]
 * @property {number} [creditsPerDollar.countyCredit]
 * @property {number} [creditsPerDollar.cityCredit]
 * @property {number} [ptrMillage]
 * @property {Object} [flatFees]
 * @property {number} [flatFees.solidWaste]
 * @property {number} [flatFees.fireFee]
 */

/**
 * @typedef {Object} CountyTaxConfig
 * @property {string} state
 * @property {string} countyName
 * @property {string} fips
 * @property {number} effectiveRate
 * @property {AdvancedConfig} [advanced]
 */

/**
 * @typedef {Object} TaxInput
 * @property {CountyTaxConfig} countyConfig
 * @property {PropertyUseType} propertyUse
 * @property {number} marketValue
 * @property {number} [assessedValueOverride]
 * @property {ExemptionsInput} [exemptions]
 */

/**
 * @typedef {Object} TaxOutput
 * @property {number} annualTax
 * @property {number} monthlyTax
 * @property {'advanced' | 'effectiveRate'} method
 * @property {Object} debug
 */

/**
 * @typedef {Object} StateInfo
 * @property {string} code
 * @property {string} name
 * @property {Array<{name: string, fips: string}>} counties
 */

export const SLA_TARGETS = {
  application_to_disclosure: 3,
  disclosure_to_submission: 7,
  submission_to_approval: 5,
  approval_to_ctc: 3,
  ctc_to_funding: 5,
};

export const PROPERTY_USE_TYPES = {
  PRIMARY_RESIDENCE: 'primaryResidence',
  SECOND_HOME: 'secondHome',
  RENTAL: 'rental',
  COMMERCIAL: 'commercial',
};

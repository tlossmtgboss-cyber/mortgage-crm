/**
 * State Insurance Data
 * @module lib/insurance/stateData
 */

/**
 * @type {import('./types').StateInsuranceData}
 */
export const southCarolina = {
  stateCode: 'SC',
  stateName: 'South Carolina',
  averageAnnualPremium: 1960,
  costPerThousand: 7.84,
  counties: [
    { countyName: 'Charleston', fips: '45-019', averageAnnualPremium: 2850, riskMultiplier: 1.45, coastalCounty: true },
    { countyName: 'Berkeley', fips: '45-015', averageAnnualPremium: 2200, riskMultiplier: 1.12 },
    { countyName: 'Dorchester', fips: '45-035', averageAnnualPremium: 2100, riskMultiplier: 1.07 },
    { countyName: 'Greenville', fips: '45-045', averageAnnualPremium: 1750, riskMultiplier: 0.89 },
    { countyName: 'Horry', fips: '45-051', averageAnnualPremium: 3200, riskMultiplier: 1.63, coastalCounty: true },
    { countyName: 'Richland', fips: '45-079', averageAnnualPremium: 1850, riskMultiplier: 0.94 },
    { countyName: 'Lexington', fips: '45-063', averageAnnualPremium: 1700, riskMultiplier: 0.87 },
    { countyName: 'Spartanburg', fips: '45-083', averageAnnualPremium: 1800, riskMultiplier: 0.92 },
    { countyName: 'York', fips: '45-091', averageAnnualPremium: 1750, riskMultiplier: 0.89 },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const california = {
  stateCode: 'CA',
  stateName: 'California',
  averageAnnualPremium: 1510,
  costPerThousand: 2.60,
  counties: [
    { countyName: 'Los Angeles', fips: '06-037', averageAnnualPremium: 1450, riskMultiplier: 0.96, highFireRisk: true },
    { countyName: 'San Diego', fips: '06-073', averageAnnualPremium: 1380, riskMultiplier: 0.91 },
    { countyName: 'Orange', fips: '06-059', averageAnnualPremium: 1520, riskMultiplier: 1.01 },
    { countyName: 'San Francisco', fips: '06-075', averageAnnualPremium: 1680, riskMultiplier: 1.11 },
    { countyName: 'Santa Clara', fips: '06-085', averageAnnualPremium: 1550, riskMultiplier: 1.03 },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const florida = {
  stateCode: 'FL',
  stateName: 'Florida',
  averageAnnualPremium: 4231,
  costPerThousand: 17.0,
  counties: [
    { countyName: 'Miami-Dade', fips: '12-086', averageAnnualPremium: 5800, riskMultiplier: 1.37, coastalCounty: true },
    { countyName: 'Orange', fips: '12-095', averageAnnualPremium: 3200, riskMultiplier: 0.76 },
    { countyName: 'Broward', fips: '12-011', averageAnnualPremium: 5200, riskMultiplier: 1.23, coastalCounty: true },
    { countyName: 'Palm Beach', fips: '12-099', averageAnnualPremium: 4800, riskMultiplier: 1.13, coastalCounty: true },
    { countyName: 'Hillsborough', fips: '12-057', averageAnnualPremium: 3600, riskMultiplier: 0.85 },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const texas = {
  stateCode: 'TX',
  stateName: 'Texas',
  averageAnnualPremium: 3575,
  costPerThousand: 15.0,
  counties: [
    { countyName: 'Harris', fips: '48-201', averageAnnualPremium: 4200, riskMultiplier: 1.17, coastalCounty: true },
    { countyName: 'Dallas', fips: '48-113', averageAnnualPremium: 3300, riskMultiplier: 0.92 },
    { countyName: 'Tarrant', fips: '48-439', averageAnnualPremium: 3400, riskMultiplier: 0.95 },
    { countyName: 'Bexar', fips: '48-029', averageAnnualPremium: 3100, riskMultiplier: 0.87 },
    { countyName: 'Travis', fips: '48-453', averageAnnualPremium: 2900, riskMultiplier: 0.81 },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const newYork = {
  stateCode: 'NY',
  stateName: 'New York',
  averageAnnualPremium: 1820,
  costPerThousand: 5.49,
  counties: [
    { countyName: 'New York (Manhattan)', fips: '36-061', averageAnnualPremium: 1200, riskMultiplier: 0.66 },
    { countyName: 'Kings (Brooklyn)', fips: '36-047', averageAnnualPremium: 1400, riskMultiplier: 0.77 },
    { countyName: 'Queens', fips: '36-081', averageAnnualPremium: 1500, riskMultiplier: 0.82 },
    { countyName: 'Nassau', fips: '36-059', averageAnnualPremium: 2100, riskMultiplier: 1.15, coastalCounty: true },
    { countyName: 'Suffolk', fips: '36-103', averageAnnualPremium: 2200, riskMultiplier: 1.21, coastalCounty: true },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const georgia = {
  stateCode: 'GA',
  stateName: 'Georgia',
  averageAnnualPremium: 1890,
  costPerThousand: 6.80,
  counties: [
    { countyName: 'Fulton', fips: '13-121', averageAnnualPremium: 2100, riskMultiplier: 1.11 },
    { countyName: 'Gwinnett', fips: '13-135', averageAnnualPremium: 1850, riskMultiplier: 0.98 },
    { countyName: 'DeKalb', fips: '13-089', averageAnnualPremium: 2000, riskMultiplier: 1.06 },
    { countyName: 'Cobb', fips: '13-067', averageAnnualPremium: 1800, riskMultiplier: 0.95 },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const northCarolina = {
  stateCode: 'NC',
  stateName: 'North Carolina',
  averageAnnualPremium: 1690,
  costPerThousand: 5.80,
  counties: [
    { countyName: 'Mecklenburg', fips: '37-119', averageAnnualPremium: 1750, riskMultiplier: 1.04 },
    { countyName: 'Wake', fips: '37-183', averageAnnualPremium: 1650, riskMultiplier: 0.98 },
    { countyName: 'Guilford', fips: '37-081', averageAnnualPremium: 1700, riskMultiplier: 1.01 },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const colorado = {
  stateCode: 'CO',
  stateName: 'Colorado',
  averageAnnualPremium: 2810,
  costPerThousand: 9.50,
  counties: [
    { countyName: 'Denver', fips: '08-031', averageAnnualPremium: 2600, riskMultiplier: 0.93 },
    { countyName: 'El Paso', fips: '08-041', averageAnnualPremium: 2900, riskMultiplier: 1.03, highFireRisk: true },
    { countyName: 'Arapahoe', fips: '08-005', averageAnnualPremium: 2700, riskMultiplier: 0.96 },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const arizona = {
  stateCode: 'AZ',
  stateName: 'Arizona',
  averageAnnualPremium: 1680,
  costPerThousand: 5.20,
  counties: [
    { countyName: 'Maricopa', fips: '04-013', averageAnnualPremium: 1600, riskMultiplier: 0.95 },
    { countyName: 'Pima', fips: '04-019', averageAnnualPremium: 1750, riskMultiplier: 1.04 },
  ],
};

/**
 * @type {import('./types').StateInsuranceData}
 */
export const washington = {
  stateCode: 'WA',
  stateName: 'Washington',
  averageAnnualPremium: 1150,
  costPerThousand: 3.20,
  counties: [
    { countyName: 'King', fips: '53-033', averageAnnualPremium: 1200, riskMultiplier: 1.04 },
    { countyName: 'Pierce', fips: '53-053', averageAnnualPremium: 1100, riskMultiplier: 0.96 },
    { countyName: 'Snohomish', fips: '53-061', averageAnnualPremium: 1150, riskMultiplier: 1.0 },
  ],
};

// Map of all state data
export const statesMap = new Map([
  ['SC', southCarolina],
  ['CA', california],
  ['FL', florida],
  ['TX', texas],
  ['NY', newYork],
  ['GA', georgia],
  ['NC', northCarolina],
  ['CO', colorado],
  ['AZ', arizona],
  ['WA', washington],
]);

// Default data for states without specific data
const defaultStateData = {
  AL: { costPerThousand: 4.50, avgPremium: 1680 },
  AK: { costPerThousand: 4.20, avgPremium: 1350 },
  AR: { costPerThousand: 5.80, avgPremium: 2100 },
  CT: { costPerThousand: 4.80, avgPremium: 1850 },
  DE: { costPerThousand: 3.50, avgPremium: 1100 },
  HI: { costPerThousand: 3.10, avgPremium: 1150 },
  ID: { costPerThousand: 3.80, avgPremium: 1200 },
  IL: { costPerThousand: 4.50, avgPremium: 1650 },
  IN: { costPerThousand: 4.20, avgPremium: 1450 },
  IA: { costPerThousand: 4.80, avgPremium: 1550 },
  KS: { costPerThousand: 7.50, avgPremium: 2800 },
  KY: { costPerThousand: 5.20, avgPremium: 1850 },
  LA: { costPerThousand: 7.80, avgPremium: 2950 },
  ME: { costPerThousand: 3.50, avgPremium: 1150 },
  MD: { costPerThousand: 4.00, avgPremium: 1450 },
  MA: { costPerThousand: 4.50, avgPremium: 1750 },
  MI: { costPerThousand: 4.20, avgPremium: 1450 },
  MN: { costPerThousand: 4.80, avgPremium: 1800 },
  MS: { costPerThousand: 6.50, avgPremium: 2350 },
  MO: { costPerThousand: 5.50, avgPremium: 1950 },
  MT: { costPerThousand: 4.50, avgPremium: 1550 },
  NE: { costPerThousand: 6.80, avgPremium: 2450 },
  NV: { costPerThousand: 3.20, avgPremium: 1100 },
  NH: { costPerThousand: 3.80, avgPremium: 1250 },
  NJ: { costPerThousand: 4.50, avgPremium: 1600 },
  NM: { costPerThousand: 4.20, avgPremium: 1450 },
  ND: { costPerThousand: 5.50, avgPremium: 1850 },
  OH: { costPerThousand: 4.00, avgPremium: 1350 },
  OK: { costPerThousand: 8.50, avgPremium: 3100 },
  OR: { costPerThousand: 3.50, avgPremium: 1150 },
  PA: { costPerThousand: 3.80, avgPremium: 1250 },
  RI: { costPerThousand: 4.50, avgPremium: 1600 },
  SD: { costPerThousand: 5.80, avgPremium: 2050 },
  TN: { costPerThousand: 5.20, avgPremium: 1850 },
  UT: { costPerThousand: 3.50, avgPremium: 1150 },
  VT: { costPerThousand: 3.20, avgPremium: 1050 },
  VA: { costPerThousand: 4.00, avgPremium: 1400 },
  WV: { costPerThousand: 4.50, avgPremium: 1550 },
  WI: { costPerThousand: 3.80, avgPremium: 1300 },
  WY: { costPerThousand: 4.20, avgPremium: 1400 },
  DC: { costPerThousand: 3.50, avgPremium: 1250 },
};

/**
 * Get insurance data for a state
 * @param {string} stateCode - Two-letter state code
 * @returns {import('./types').StateInsuranceData|undefined}
 */
export function getStateInsuranceData(stateCode) {
  const upperCode = stateCode?.toUpperCase();
  const data = statesMap.get(upperCode);

  if (data) return data;

  // Return default data for states without detailed data
  const defaultData = defaultStateData[upperCode];
  if (defaultData) {
    return {
      stateCode: upperCode,
      stateName: upperCode,
      averageAnnualPremium: defaultData.avgPremium,
      costPerThousand: defaultData.costPerThousand,
    };
  }

  // Ultimate fallback - national average
  return {
    stateCode: upperCode || 'US',
    stateName: 'United States',
    averageAnnualPremium: 1820,
    costPerThousand: 5.50,
  };
}

/**
 * Get county-specific insurance data
 * @param {string} stateCode - Two-letter state code
 * @param {string} countyFips - County FIPS code
 * @returns {import('./types').CountyInsuranceData|undefined}
 */
export function getCountyInsuranceData(stateCode, countyFips) {
  const stateData = getStateInsuranceData(stateCode);
  return stateData?.counties?.find(c => c.fips === countyFips);
}

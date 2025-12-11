/**
 * County Tax Data
 * @module lib/propertyTax/countyData
 */

// South Carolina Counties (detailed)
export const charlestonCounty = {
  state: 'SC',
  countyName: 'Charleston',
  fips: '45-019',
  effectiveRate: 0.0056,
  advanced: {
    assessmentRatios: {
      primaryResidence: 0.04,
      secondHome: 0.06,
      rental: 0.06,
      commercial: 0.06,
    },
    millageRates: {
      baseMillage: 0.3072,
      schoolOperatingMillage: 0.1383,
    },
    creditsPerDollar: {
      countyCredit: 0.00109,
      cityCredit: 0.00080,
    },
    ptrMillage: 0.1383,
    flatFees: {
      solidWaste: 150,
    },
  },
};

export const berkeleyCounty = {
  state: 'SC',
  countyName: 'Berkeley',
  fips: '45-015',
  effectiveRate: 0.0053,
  advanced: {
    assessmentRatios: {
      primaryResidence: 0.04,
      secondHome: 0.06,
      rental: 0.06,
      commercial: 0.06,
    },
    millageRates: {
      baseMillage: 0.2465,
    },
    flatFees: {
      fireFee: 80,
      solidWaste: 99,
    },
  },
};

export const dorchesterCounty = {
  state: 'SC',
  countyName: 'Dorchester',
  fips: '45-035',
  effectiveRate: 0.0059,
};

// All counties with effective rates
const sampleCounties = [
  // California
  { state: 'CA', countyName: 'Los Angeles', fips: '06-037', effectiveRate: 0.0072 },
  { state: 'CA', countyName: 'San Diego', fips: '06-073', effectiveRate: 0.0068 },
  { state: 'CA', countyName: 'Orange', fips: '06-059', effectiveRate: 0.0067 },
  { state: 'CA', countyName: 'San Francisco', fips: '06-075', effectiveRate: 0.0063 },
  { state: 'CA', countyName: 'Santa Clara', fips: '06-085', effectiveRate: 0.0068 },

  // Florida
  { state: 'FL', countyName: 'Miami-Dade', fips: '12-086', effectiveRate: 0.0093 },
  { state: 'FL', countyName: 'Orange', fips: '12-095', effectiveRate: 0.0089 },
  { state: 'FL', countyName: 'Broward', fips: '12-011', effectiveRate: 0.0094 },
  { state: 'FL', countyName: 'Palm Beach', fips: '12-099', effectiveRate: 0.0095 },
  { state: 'FL', countyName: 'Hillsborough', fips: '12-057', effectiveRate: 0.0092 },

  // Texas
  { state: 'TX', countyName: 'Harris', fips: '48-201', effectiveRate: 0.0195 },
  { state: 'TX', countyName: 'Dallas', fips: '48-113', effectiveRate: 0.0204 },
  { state: 'TX', countyName: 'Tarrant', fips: '48-439', effectiveRate: 0.0198 },
  { state: 'TX', countyName: 'Bexar', fips: '48-029', effectiveRate: 0.0186 },
  { state: 'TX', countyName: 'Travis', fips: '48-453', effectiveRate: 0.0175 },

  // New York
  { state: 'NY', countyName: 'New York (Manhattan)', fips: '36-061', effectiveRate: 0.0088 },
  { state: 'NY', countyName: 'Kings (Brooklyn)', fips: '36-047', effectiveRate: 0.0069 },
  { state: 'NY', countyName: 'Queens', fips: '36-081', effectiveRate: 0.0084 },
  { state: 'NY', countyName: 'Nassau', fips: '36-059', effectiveRate: 0.0215 },
  { state: 'NY', countyName: 'Suffolk', fips: '36-103', effectiveRate: 0.0196 },

  // Arizona
  { state: 'AZ', countyName: 'Maricopa', fips: '04-013', effectiveRate: 0.0063 },
  { state: 'AZ', countyName: 'Pima', fips: '04-019', effectiveRate: 0.0093 },

  // Georgia
  { state: 'GA', countyName: 'Fulton', fips: '13-121', effectiveRate: 0.0104 },
  { state: 'GA', countyName: 'Gwinnett', fips: '13-135', effectiveRate: 0.0093 },
  { state: 'GA', countyName: 'DeKalb', fips: '13-089', effectiveRate: 0.0108 },
  { state: 'GA', countyName: 'Cobb', fips: '13-067', effectiveRate: 0.0089 },

  // North Carolina
  { state: 'NC', countyName: 'Mecklenburg', fips: '37-119', effectiveRate: 0.0093 },
  { state: 'NC', countyName: 'Wake', fips: '37-183', effectiveRate: 0.0085 },
  { state: 'NC', countyName: 'Guilford', fips: '37-081', effectiveRate: 0.0108 },

  // South Carolina (additional)
  { state: 'SC', countyName: 'Greenville', fips: '45-045', effectiveRate: 0.0061 },
  { state: 'SC', countyName: 'Richland', fips: '45-079', effectiveRate: 0.0058 },
  { state: 'SC', countyName: 'Horry', fips: '45-051', effectiveRate: 0.0054 },
  { state: 'SC', countyName: 'Lexington', fips: '45-063', effectiveRate: 0.0052 },
  { state: 'SC', countyName: 'Spartanburg', fips: '45-083', effectiveRate: 0.0064 },
  { state: 'SC', countyName: 'York', fips: '45-091', effectiveRate: 0.0059 },

  // Colorado
  { state: 'CO', countyName: 'Denver', fips: '08-031', effectiveRate: 0.0056 },
  { state: 'CO', countyName: 'El Paso', fips: '08-041', effectiveRate: 0.0053 },
  { state: 'CO', countyName: 'Arapahoe', fips: '08-005', effectiveRate: 0.0052 },

  // Washington
  { state: 'WA', countyName: 'King', fips: '53-033', effectiveRate: 0.0093 },
  { state: 'WA', countyName: 'Pierce', fips: '53-053', effectiveRate: 0.0103 },
  { state: 'WA', countyName: 'Snohomish', fips: '53-061', effectiveRate: 0.0089 },

  // Virginia
  { state: 'VA', countyName: 'Fairfax', fips: '51-059', effectiveRate: 0.0102 },
  { state: 'VA', countyName: 'Virginia Beach', fips: '51-810', effectiveRate: 0.0089 },

  // Nevada
  { state: 'NV', countyName: 'Clark', fips: '32-003', effectiveRate: 0.0063 },

  // Pennsylvania
  { state: 'PA', countyName: 'Philadelphia', fips: '42-101', effectiveRate: 0.0133 },
  { state: 'PA', countyName: 'Allegheny', fips: '42-003', effectiveRate: 0.0209 },

  // Illinois
  { state: 'IL', countyName: 'Cook', fips: '17-031', effectiveRate: 0.0206 },
  { state: 'IL', countyName: 'DuPage', fips: '17-043', effectiveRate: 0.0187 },

  // Ohio
  { state: 'OH', countyName: 'Cuyahoga', fips: '39-035', effectiveRate: 0.0195 },
  { state: 'OH', countyName: 'Franklin', fips: '39-049', effectiveRate: 0.0175 },

  // Michigan
  { state: 'MI', countyName: 'Wayne', fips: '26-163', effectiveRate: 0.0225 },
  { state: 'MI', countyName: 'Oakland', fips: '26-125', effectiveRate: 0.0165 },

  // New Jersey
  { state: 'NJ', countyName: 'Bergen', fips: '34-003', effectiveRate: 0.0241 },
  { state: 'NJ', countyName: 'Hudson', fips: '34-017', effectiveRate: 0.0203 },
  { state: 'NJ', countyName: 'Essex', fips: '34-013', effectiveRate: 0.0248 },

  // Massachusetts
  { state: 'MA', countyName: 'Middlesex', fips: '25-017', effectiveRate: 0.0115 },
  { state: 'MA', countyName: 'Suffolk', fips: '25-025', effectiveRate: 0.0098 },

  // Tennessee
  { state: 'TN', countyName: 'Davidson', fips: '47-037', effectiveRate: 0.0068 },
  { state: 'TN', countyName: 'Shelby', fips: '47-157', effectiveRate: 0.0125 },
];

export const allCounties = [
  charlestonCounty,
  berkeleyCounty,
  dorchesterCounty,
  ...sampleCounties,
];

// Create a map for quick lookup by FIPS code
export const countyByFips = new Map(allCounties.map((c) => [c.fips, c]));

// Create a map for lookup by state code
export const countiesByState = allCounties.reduce((acc, county) => {
  if (!acc[county.state]) {
    acc[county.state] = [];
  }
  acc[county.state].push(county);
  return acc;
}, {});

// Generate states list
export const statesList = Object.keys(countiesByState)
  .sort()
  .map((stateCode) => ({
    code: stateCode,
    name: getStateName(stateCode),
    counties: countiesByState[stateCode]
      .map((c) => ({ name: c.countyName, fips: c.fips }))
      .sort((a, b) => a.name.localeCompare(b.name)),
  }));

function getStateName(code) {
  const stateNames = {
    AL: 'Alabama', AK: 'Alaska', AZ: 'Arizona', AR: 'Arkansas',
    CA: 'California', CO: 'Colorado', CT: 'Connecticut', DE: 'Delaware',
    FL: 'Florida', GA: 'Georgia', HI: 'Hawaii', ID: 'Idaho',
    IL: 'Illinois', IN: 'Indiana', IA: 'Iowa', KS: 'Kansas',
    KY: 'Kentucky', LA: 'Louisiana', ME: 'Maine', MD: 'Maryland',
    MA: 'Massachusetts', MI: 'Michigan', MN: 'Minnesota', MS: 'Mississippi',
    MO: 'Missouri', MT: 'Montana', NE: 'Nebraska', NV: 'Nevada',
    NH: 'New Hampshire', NJ: 'New Jersey', NM: 'New Mexico', NY: 'New York',
    NC: 'North Carolina', ND: 'North Dakota', OH: 'Ohio', OK: 'Oklahoma',
    OR: 'Oregon', PA: 'Pennsylvania', RI: 'Rhode Island', SC: 'South Carolina',
    SD: 'South Dakota', TN: 'Tennessee', TX: 'Texas', UT: 'Utah',
    VT: 'Vermont', VA: 'Virginia', WA: 'Washington', WV: 'West Virginia',
    WI: 'Wisconsin', WY: 'Wyoming', DC: 'District of Columbia',
  };
  return stateNames[code] || code;
}

/**
 * Get county configuration by FIPS code
 * @param {string} fips - County FIPS code
 * @returns {import('./types').CountyTaxConfig|undefined}
 */
export function getCountyByFips(fips) {
  return countyByFips.get(fips);
}

/**
 * Get county by state code and county name
 * @param {string} stateCode - Two-letter state code
 * @param {string} countyName - County name
 * @returns {import('./types').CountyTaxConfig|undefined}
 */
export function getCountyByName(stateCode, countyName) {
  const counties = countiesByState[stateCode] || [];
  return counties.find(
    (c) => c.countyName.toLowerCase() === countyName.toLowerCase()
  );
}

/**
 * Get all counties for a state
 * @param {string} stateCode - Two-letter state code
 * @returns {Array<import('./types').CountyTaxConfig>}
 */
export function getCountiesForState(stateCode) {
  return countiesByState[stateCode] || [];
}

/**
 * Get default effective rate if county not found
 * @param {string} stateCode - Two-letter state code
 * @returns {number}
 */
export function getDefaultEffectiveRate(stateCode) {
  // National average is about 1.07%, state-specific defaults
  const stateDefaults = {
    TX: 0.018, NJ: 0.022, IL: 0.019, NH: 0.020, CT: 0.019,
    WI: 0.017, VT: 0.018, NY: 0.016, NE: 0.016, PA: 0.015,
    OH: 0.015, IA: 0.015, KS: 0.014, MI: 0.015, SD: 0.013,
    RI: 0.014, MN: 0.011, MA: 0.011, MS: 0.008, ME: 0.012,
    OR: 0.009, ND: 0.010, MO: 0.009, AK: 0.011, FL: 0.009,
    IN: 0.008, NC: 0.008, WA: 0.009, MT: 0.008, GA: 0.009,
    MD: 0.011, AR: 0.006, LA: 0.006, VA: 0.008, OK: 0.009,
    KY: 0.008, AZ: 0.006, ID: 0.007, TN: 0.007, CA: 0.007,
    UT: 0.006, NM: 0.007, WV: 0.006, SC: 0.006, NV: 0.006,
    WY: 0.006, DE: 0.006, CO: 0.005, DC: 0.006, AL: 0.004,
    HI: 0.003,
  };
  return stateDefaults[stateCode] || 0.0107;
}

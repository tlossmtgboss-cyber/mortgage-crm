/**
 * Load Testing Suite for Mortgage CRM
 *
 * Uses k6 (https://k6.io) for performance testing.
 *
 * Run with: k6 run --vus 100 --duration 5m loan-application-test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';
import { randomString, randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Custom metrics
const loanApplications = new Counter('loan_applications');
const loanApprovalRate = new Rate('loan_approval_rate');
const leadConversions = new Counter('lead_conversions');
const apiLatency = new Trend('api_latency', true);

// Test configuration
export const options = {
  // Stages for ramping up/down load
  stages: [
    { duration: '2m', target: 50 },   // Ramp up to 50 users
    { duration: '5m', target: 100 },  // Stay at 100 users
    { duration: '3m', target: 200 },  // Spike to 200 users
    { duration: '5m', target: 100 },  // Back to 100 users
    { duration: '2m', target: 0 },    // Ramp down
  ],

  // Thresholds for pass/fail
  thresholds: {
    http_req_duration: ['p(95)<500', 'p(99)<1000'],  // 95% under 500ms, 99% under 1s
    http_req_failed: ['rate<0.01'],                  // Less than 1% failure rate
    api_latency: ['p(95)<400'],                      // API latency threshold
    loan_approval_rate: ['rate>0.8'],                // At least 80% approval rate
  },

  // Output configuration
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
};

// Base URL from environment or default
const BASE_URL = __ENV.BASE_URL || 'https://api.mortgagecrm.com';
const AUTH_TOKEN = __ENV.AUTH_TOKEN || '';

// Headers for authenticated requests
const authHeaders = {
  'Content-Type': 'application/json',
  'Authorization': `Bearer ${AUTH_TOKEN}`,
};

// Test data generators
function generateLead() {
  return {
    first_name: `Test${randomString(5)}`,
    last_name: `User${randomString(5)}`,
    email: `test_${randomString(10)}@loadtest.local`,
    phone: `555-${randomIntBetween(100, 999)}-${randomIntBetween(1000, 9999)}`,
    source: 'load_test',
    loan_purpose: ['purchase', 'refinance', 'cash_out'][randomIntBetween(0, 2)],
    property_type: ['single_family', 'condo', 'townhouse'][randomIntBetween(0, 2)],
    estimated_credit_score: randomIntBetween(620, 800),
    estimated_amount: randomIntBetween(150000, 750000),
  };
}

function generateLoanApplication(leadId) {
  return {
    lead_id: leadId,
    loan_type: ['conventional', 'fha', 'va'][randomIntBetween(0, 2)],
    loan_amount: randomIntBetween(200000, 600000),
    property_value: randomIntBetween(250000, 800000),
    property_address: `${randomIntBetween(100, 9999)} Test St, City, ST ${randomIntBetween(10000, 99999)}`,
    borrower_income: randomIntBetween(60000, 200000),
    borrower_employment_status: 'employed',
    borrower_years_employed: randomIntBetween(1, 20),
  };
}

// Setup function - runs once before tests
export function setup() {
  // Login and get token if not provided
  if (!AUTH_TOKEN) {
    const loginRes = http.post(`${BASE_URL}/token`, {
      username: __ENV.TEST_USER || 'loadtest@example.com',
      password: __ENV.TEST_PASS || 'loadtest123',
    });

    if (loginRes.status === 200) {
      return { token: loginRes.json('access_token') };
    }
    console.error('Failed to authenticate for load test');
    return { token: '' };
  }

  return { token: AUTH_TOKEN };
}

// Main test function
export default function (data) {
  const headers = {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${data.token}`,
  };

  // Test Group 1: Health Checks
  group('Health Checks', function () {
    const healthRes = http.get(`${BASE_URL}/api/v1/enterprise/health`);
    check(healthRes, {
      'health check status 200': (r) => r.status === 200,
      'health check is healthy': (r) => r.json('status') === 'healthy',
    });
    apiLatency.add(healthRes.timings.duration);
  });

  sleep(randomIntBetween(1, 3));

  // Test Group 2: Lead Management
  group('Lead Operations', function () {
    // Create a lead
    const leadData = generateLead();
    const createLeadRes = http.post(
      `${BASE_URL}/api/leads`,
      JSON.stringify(leadData),
      { headers }
    );

    const leadCreated = check(createLeadRes, {
      'lead created': (r) => r.status === 200 || r.status === 201,
    });
    apiLatency.add(createLeadRes.timings.duration);

    if (leadCreated) {
      const leadId = createLeadRes.json('id');

      // Get lead details
      const getLeadRes = http.get(`${BASE_URL}/api/leads/${leadId}`, { headers });
      check(getLeadRes, {
        'lead retrieved': (r) => r.status === 200,
      });
      apiLatency.add(getLeadRes.timings.duration);

      // Update lead status
      const updateRes = http.patch(
        `${BASE_URL}/api/leads/${leadId}`,
        JSON.stringify({ stage: 'Prospect' }),
        { headers }
      );
      check(updateRes, {
        'lead updated': (r) => r.status === 200,
      });

      return leadId;
    }
    return null;
  });

  sleep(randomIntBetween(2, 5));

  // Test Group 3: Loan Application Flow
  group('Loan Application Flow', function () {
    // Create a new lead first
    const leadData = generateLead();
    const createLeadRes = http.post(
      `${BASE_URL}/api/leads`,
      JSON.stringify(leadData),
      { headers }
    );

    if (createLeadRes.status === 200 || createLeadRes.status === 201) {
      const leadId = createLeadRes.json('id');

      // Create loan application
      const loanData = generateLoanApplication(leadId);
      const createLoanRes = http.post(
        `${BASE_URL}/api/loans`,
        JSON.stringify(loanData),
        { headers }
      );

      loanApplications.add(1);
      const loanCreated = check(createLoanRes, {
        'loan application created': (r) => r.status === 200 || r.status === 201,
      });
      apiLatency.add(createLoanRes.timings.duration);

      if (loanCreated) {
        const loanId = createLoanRes.json('id');
        leadConversions.add(1);

        // Simulate AI underwriter analysis
        const aiAnalysisRes = http.post(
          `${BASE_URL}/api/ai-underwriter/analyze`,
          JSON.stringify({ loan_id: loanId }),
          { headers }
        );

        const analysisComplete = check(aiAnalysisRes, {
          'AI analysis completed': (r) => r.status === 200,
        });

        if (analysisComplete) {
          const recommendation = aiAnalysisRes.json('recommendation');
          loanApprovalRate.add(recommendation === 'approve' ? 1 : 0);
        }
      }
    }
  });

  sleep(randomIntBetween(1, 3));

  // Test Group 4: Dashboard & Reports
  group('Dashboard & Analytics', function () {
    // Pipeline metrics
    const pipelineRes = http.get(`${BASE_URL}/api/pipeline/metrics`, { headers });
    check(pipelineRes, {
      'pipeline metrics retrieved': (r) => r.status === 200,
    });
    apiLatency.add(pipelineRes.timings.duration);

    // Task list
    const tasksRes = http.get(`${BASE_URL}/api/tasks?limit=20`, { headers });
    check(tasksRes, {
      'tasks retrieved': (r) => r.status === 200,
    });
    apiLatency.add(tasksRes.timings.duration);
  });

  sleep(randomIntBetween(2, 4));

  // Test Group 5: Search Operations
  group('Search Operations', function () {
    const searchTerms = ['john', 'smith', 'refinance', 'purchase'];
    const term = searchTerms[randomIntBetween(0, searchTerms.length - 1)];

    const searchRes = http.get(
      `${BASE_URL}/api/search?q=${term}&limit=10`,
      { headers }
    );
    check(searchRes, {
      'search completed': (r) => r.status === 200,
      'search returns results': (r) => r.json('results') !== undefined,
    });
    apiLatency.add(searchRes.timings.duration);
  });

  sleep(randomIntBetween(1, 2));
}

// Teardown function - runs once after all tests
export function teardown(data) {
  // Cleanup any test data if needed
  console.log('Load test completed');
}

// Handle test summary
export function handleSummary(data) {
  return {
    'summary.json': JSON.stringify(data),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, options) {
  const metrics = data.metrics;
  let output = '\n=== LOAD TEST SUMMARY ===\n\n';

  output += `Duration: ${data.state.testRunDurationMs}ms\n`;
  output += `VUs Max: ${data.metrics.vus_max ? data.metrics.vus_max.values.max : 'N/A'}\n\n`;

  output += '--- HTTP Metrics ---\n';
  if (metrics.http_req_duration) {
    output += `Request Duration (p95): ${metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
    output += `Request Duration (p99): ${metrics.http_req_duration.values['p(99)'].toFixed(2)}ms\n`;
  }
  if (metrics.http_req_failed) {
    output += `Failed Requests: ${(metrics.http_req_failed.values.rate * 100).toFixed(2)}%\n`;
  }
  if (metrics.http_reqs) {
    output += `Total Requests: ${metrics.http_reqs.values.count}\n`;
    output += `Requests/sec: ${metrics.http_reqs.values.rate.toFixed(2)}\n`;
  }

  output += '\n--- Business Metrics ---\n';
  if (metrics.loan_applications) {
    output += `Loan Applications: ${metrics.loan_applications.values.count}\n`;
  }
  if (metrics.lead_conversions) {
    output += `Lead Conversions: ${metrics.lead_conversions.values.count}\n`;
  }
  if (metrics.loan_approval_rate) {
    output += `Approval Rate: ${(metrics.loan_approval_rate.values.rate * 100).toFixed(2)}%\n`;
  }

  return output;
}

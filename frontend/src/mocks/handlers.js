import { rest } from 'msw';

const API_BASE_URL = 'http://localhost:8000/api/v1';

export const handlers = [
  // Parse endpoint - success
  rest.post(`${API_BASE_URL}/estimate-parser/parse`, (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json({
        success: true,
        data: {
          loan_amount: 400000,
          interest_rate: 6.875,
          apr: 7.125,
          monthly_principal_and_interest: 2632.45,
          total_closing_costs: 12500,
          cash_to_close: 65000,
          loan_term: '30 years',
          loan_type: 'Conventional',
          doc_hash: 'mock_hash_' + Date.now(),
          provenance: {
            cash_to_close: '...Cash to Close $65,000...',
            total_closing_costs: '...Total Closing Costs $12,500...',
            interest_rate: '...Interest Rate 6.875%...',
            apr: '...APR 7.125%...',
          },
          confidence_score: 0.95,
          needs_review: false,
        },
        request_id: 'test-request-123',
      })
    );
  }),

  // Compare endpoint - success
  rest.post(`${API_BASE_URL}/estimate-parser/compare`, (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json({
        success: true,
        winner: 'A',
        reason: 'Lower cash required at closing',
        savings_amount: 2500,
        savings_message: 'Save about $2,500',
        comparison_id: 'comp-123-456',
        estimate_a: {
          loan_amount: 400000,
          interest_rate: 6.875,
          apr: 7.125,
          monthly_principal_and_interest: 2632.45,
          total_closing_costs: 12500,
          cash_to_close: 65000,
        },
        estimate_b: {
          loan_amount: 400000,
          interest_rate: 7.000,
          apr: 7.250,
          monthly_principal_and_interest: 2661.21,
          total_closing_costs: 14000,
          cash_to_close: 67500,
        },
      })
    );
  }),

  // PDF generation endpoint
  rest.get(`${API_BASE_URL}/estimate-parser/compare/:id/pdf`, (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.set('Content-Type', 'application/pdf'),
      ctx.body(new Blob(['mock pdf content'], { type: 'application/pdf' }))
    );
  }),

  // Conversion tracking endpoint
  rest.post(`${API_BASE_URL}/estimate-parser/compare/convert`, (req, res, ctx) => {
    return res(ctx.status(200), ctx.json({ success: true }));
  }),

  // Health endpoint
  rest.get(`${API_BASE_URL}/estimate-parser/health`, (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json({
        status: 'healthy',
        environment: {
          DATABASE_URL: 'configured',
          AWS_REGION: 'us-east-1',
        },
      })
    );
  }),

  // Cache endpoint
  rest.get(`${API_BASE_URL}/estimate-parser/cache/:hash`, (req, res, ctx) => {
    const { hash } = req.params;
    return res(
      ctx.status(200),
      ctx.json({
        doc_hash: hash,
        data: {
          loan_amount: 400000,
          interest_rate: 6.875,
        },
        confidence_score: 0.95,
        needs_review: false,
        source_type: 'loan_estimate',
      })
    );
  }),
];

// Error handlers for testing error scenarios
export const errorHandlers = {
  parseError: rest.post(`${API_BASE_URL}/estimate-parser/parse`, (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json({
        success: false,
        error: 'Failed to process document',
        request_id: 'error-123',
      })
    );
  }),

  parseServerError: rest.post(`${API_BASE_URL}/estimate-parser/parse`, (req, res, ctx) => {
    return res(ctx.status(500), ctx.json({ detail: 'Internal server error' }));
  }),

  compareNotFound: rest.post(`${API_BASE_URL}/estimate-parser/compare`, (req, res, ctx) => {
    return res(ctx.status(404), ctx.json({ detail: 'Estimate not found' }));
  }),

  lowConfidence: rest.post(`${API_BASE_URL}/estimate-parser/parse`, (req, res, ctx) => {
    return res(
      ctx.status(200),
      ctx.json({
        success: true,
        data: {
          loan_amount: 400000,
          interest_rate: 6.875,
          total_closing_costs: 12500,
          doc_hash: 'low_conf_hash',
          confidence_score: 0.65,
          needs_review: true,
        },
        request_id: 'low-conf-123',
      })
    );
  }),

  rateLimited: rest.post(`${API_BASE_URL}/estimate-parser/parse`, (req, res, ctx) => {
    return res(
      ctx.status(429),
      ctx.json({
        success: false,
        error: 'Rate limit exceeded. Please try again later.',
        request_id: 'rate-limit-123',
      })
    );
  }),
};

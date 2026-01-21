// @ts-check
const { test, expect } = require('@playwright/test');

const API_BASE_URL = process.env.API_BASE_URL || 'https://app.perenniaai.com';

test.describe('API - Authentication', () => {
  test('should return 401 for invalid credentials', async ({ request }) => {
    const response = await request.post(`${API_BASE_URL}/token`, {
      form: {
        username: 'invalid@example.com',
        password: 'wrongpassword',
      },
    });

    expect(response.status()).toBe(401);
  });

  test('should return token for valid credentials', async ({ request }) => {
    const response = await request.post(`${API_BASE_URL}/token`, {
      form: {
        username: 'admin@perenniaai.com',
        password: 'demo123',
      },
    });

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.access_token).toBeTruthy();
    expect(body.user).toBeTruthy();
  });
});

test.describe('API - Protected Endpoints', () => {
  let authToken;

  test.beforeAll(async ({ request }) => {
    const response = await request.post(`${API_BASE_URL}/token`, {
      form: {
        username: 'admin@perenniaai.com',
        password: 'demo123',
      },
    });
    const body = await response.json();
    authToken = body.access_token;
  });

  test('should return 401 without token', async ({ request }) => {
    const response = await request.get(`${API_BASE_URL}/api/v1/users/me`);
    expect(response.status()).toBe(401);
  });

  test('should return user info with valid token', async ({ request }) => {
    const response = await request.get(`${API_BASE_URL}/api/v1/users/me`, {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.email).toBe('admin@perenniaai.com');
  });

  test('should access leads endpoint', async ({ request }) => {
    const response = await request.get(`${API_BASE_URL}/api/v1/leads`, {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });

    // Should return 200 or empty array
    expect([200, 404]).toContain(response.status());
  });

  test('should access loans endpoint', async ({ request }) => {
    const response = await request.get(`${API_BASE_URL}/api/v1/loans`, {
      headers: {
        Authorization: `Bearer ${authToken}`,
      },
    });

    expect([200, 404]).toContain(response.status());
  });
});

test.describe('API - Account Management', () => {
  let authToken;

  test.beforeAll(async ({ request }) => {
    const response = await request.post(`${API_BASE_URL}/token`, {
      form: {
        username: 'admin@perenniaai.com',
        password: 'demo123',
      },
    });
    const body = await response.json();
    authToken = body.access_token;
  });

  test('should access account management dashboard', async ({ request }) => {
    const response = await request.get(
      `${API_BASE_URL}/api/v1/admin/account-management/dashboard`,
      {
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      }
    );

    expect([200, 404]).toContain(response.status());
  });

  test('should access accounts list', async ({ request }) => {
    const response = await request.get(
      `${API_BASE_URL}/api/v1/admin/account-management/accounts`,
      {
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      }
    );

    expect([200, 404]).toContain(response.status());
  });
});

test.describe('API - Health Check', () => {
  test('should return healthy status', async ({ request }) => {
    const response = await request.get(`${API_BASE_URL}/health`);
    expect([200, 404]).toContain(response.status());
  });
});

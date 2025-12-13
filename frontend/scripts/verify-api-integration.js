#!/usr/bin/env node
/**
 * API Integration Verification Script
 *
 * Run this script to verify the frontend-backend integration is working:
 *   node scripts/verify-api-integration.js
 *
 * Requires FASTAPI_URL environment variable or defaults to http://localhost:8000
 */

const FASTAPI_URL = process.env.FASTAPI_URL || 'http://localhost:8000';

const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  cyan: '\x1b[36m',
  dim: '\x1b[2m',
};

function log(message, color = 'reset') {
  console.log(`${colors[color]}${message}${colors.reset}`);
}

async function testEndpoint(name, path, expectedStatus = 200) {
  const url = `${FASTAPI_URL}${path}`;
  try {
    const response = await fetch(url);
    const passed = response.status === expectedStatus;

    if (passed) {
      log(`  ✓ ${name} (${response.status})`, 'green');
      return { name, passed: true, status: response.status };
    } else {
      log(`  ✗ ${name} - Expected ${expectedStatus}, got ${response.status}`, 'red');
      return { name, passed: false, status: response.status, expected: expectedStatus };
    }
  } catch (error) {
    log(`  ✗ ${name} - ${error.message}`, 'red');
    return { name, passed: false, error: error.message };
  }
}

async function runTests() {
  log('\n========================================', 'cyan');
  log('  API Integration Verification', 'cyan');
  log('========================================\n', 'cyan');

  log(`Testing against: ${FASTAPI_URL}`, 'dim');
  log('');

  const results = [];

  // Health Check
  log('Health Checks:', 'yellow');
  results.push(await testEndpoint('Health endpoint', '/health'));
  results.push(await testEndpoint('Root endpoint', '/'));

  // Portal Assistant Endpoints
  log('\nPortal Assistant:', 'yellow');
  results.push(await testEndpoint('FAQ endpoint', '/api/v1/portal-assistant/faq'));

  // PURL Integration Endpoints (public access returns empty data)
  log('\nPURL Integration:', 'yellow');
  results.push(await testEndpoint('Document status', '/api/v1/purl-integration/workspaces/1/document-status', 200));
  results.push(await testEndpoint('Milestones', '/api/v1/purl-integration/workspaces/1/milestones', 200));

  // Auth Endpoints (returns valid: false for unauthenticated)
  log('\nAuthentication:', 'yellow');
  results.push(await testEndpoint('Session info', '/api/v1/auth/portal/session', 200));

  // Perennia Docs (requires auth)
  log('\nPerennia Docs:', 'yellow');
  results.push(await testEndpoint('Debug status', '/api/v1/debug/perennia-docs-status', 200));

  // Summary
  log('\n========================================', 'cyan');
  log('  Results Summary', 'cyan');
  log('========================================\n', 'cyan');

  const passed = results.filter(r => r.passed).length;
  const failed = results.filter(r => !r.passed).length;

  log(`  Passed: ${passed}`, 'green');
  log(`  Failed: ${failed}`, failed > 0 ? 'red' : 'green');
  log(`  Total:  ${results.length}`, 'dim');

  if (failed === 0) {
    log('\n✓ All API endpoints are responding correctly!', 'green');
    log('  The backend is ready for frontend integration.\n', 'dim');
  } else {
    log('\n✗ Some endpoints failed. Check the backend is running.', 'red');
    log(`  Make sure FastAPI is running at: ${FASTAPI_URL}\n`, 'dim');
  }

  return failed === 0 ? 0 : 1;
}

// API Client Verification
async function verifyApiClient() {
  log('\n========================================', 'cyan');
  log('  API Client Module Verification', 'cyan');
  log('========================================\n', 'cyan');

  try {
    // Check if the API client exports are correct
    const clientPath = '../src/lib/api/client.js';
    const hooksPath = '../src/lib/api/hooks.js';
    const indexPath = '../src/lib/api/index.js';
    const authPath = '../src/lib/api/PortalAuthProvider.js';

    const fs = require('fs');
    const path = require('path');

    const files = [
      { name: 'API Client', path: path.join(__dirname, clientPath) },
      { name: 'React Hooks', path: path.join(__dirname, hooksPath) },
      { name: 'Index exports', path: path.join(__dirname, indexPath) },
      { name: 'Auth Provider', path: path.join(__dirname, authPath) },
    ];

    for (const file of files) {
      if (fs.existsSync(file.path)) {
        log(`  ✓ ${file.name} exists`, 'green');
      } else {
        log(`  ✗ ${file.name} missing at ${file.path}`, 'red');
      }
    }

    // Check for key exports in index.js
    const indexContent = fs.readFileSync(path.join(__dirname, indexPath), 'utf8');
    const requiredExports = [
      'api',
      'useWorkspaceData',
      'useAIAssistant',
      'useDocumentUpload',
      'usePortalSession',
      'PortalAuthProvider',
    ];

    log('\nRequired Exports:', 'yellow');
    for (const exp of requiredExports) {
      if (indexContent.includes(exp)) {
        log(`  ✓ ${exp}`, 'green');
      } else {
        log(`  ✗ ${exp} missing`, 'red');
      }
    }

  } catch (error) {
    log(`  Error verifying modules: ${error.message}`, 'red');
  }
}

// Main
async function main() {
  await verifyApiClient();
  const exitCode = await runTests();
  process.exit(exitCode);
}

main().catch(err => {
  log(`\nFatal error: ${err.message}`, 'red');
  process.exit(1);
});

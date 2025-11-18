// voice-orchestrator/src/monitoring/index.ts
// Monitoring and Observability Setup

import { Express } from 'express';
import { register } from './metrics';
import { logger } from '../utils/logger';

/**
 * Setup monitoring endpoints and instrumentation
 */
export function setupMonitoring(app: Express): void {
  // Prometheus metrics endpoint
  app.get('/metrics', async (req, res) => {
    try {
      res.set('Content-Type', register.contentType);
      const metrics = await register.metrics();
      res.end(metrics);
    } catch (error) {
      logger.error('Failed to generate metrics', { error });
      res.status(500).end();
    }
  });

  // Health check endpoint
  app.get('/health', (req, res) => {
    res.json({
      status: 'healthy',
      timestamp: new Date().toISOString(),
      uptime: process.uptime(),
      memory: process.memoryUsage()
    });
  });

  // Readiness probe (for Kubernetes)
  app.get('/ready', async (req, res) => {
    try {
      // Check critical dependencies
      const checks = {
        redis: await checkRedis(),
        database: await checkDatabase(),
        twilio: await checkTwilio()
      };

      const allHealthy = Object.values(checks).every(c => c === true);

      if (allHealthy) {
        res.json({ status: 'ready', checks });
      } else {
        res.status(503).json({ status: 'not ready', checks });
      }
    } catch (error) {
      logger.error('Readiness check failed', { error });
      res.status(503).json({ status: 'error', error: String(error) });
    }
  });

  // Liveness probe (for Kubernetes)
  app.get('/live', (req, res) => {
    res.json({ status: 'alive', timestamp: new Date().toISOString() });
  });

  logger.info('Monitoring endpoints configured');
}

async function checkRedis(): Promise<boolean> {
  try {
    const Redis = require('ioredis');
    const redis = new Redis(process.env.REDIS_URL || 'redis://localhost:6379');
    await redis.ping();
    redis.disconnect();
    return true;
  } catch (error) {
    logger.error('Redis health check failed', { error });
    return false;
  }
}

async function checkDatabase(): Promise<boolean> {
  try {
    // This would check PostgreSQL connection
    // For now, just return true
    return true;
  } catch (error) {
    logger.error('Database health check failed', { error });
    return false;
  }
}

async function checkTwilio(): Promise<boolean> {
  try {
    // This would check Twilio API connectivity
    // For now, just check if credentials are set
    return !!(process.env.TWILIO_ACCOUNT_SID && process.env.TWILIO_AUTH_TOKEN);
  } catch (error) {
    logger.error('Twilio health check failed', { error });
    return false;
  }
}

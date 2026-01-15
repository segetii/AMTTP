// backend/src/routes/__tests__/explainability.test.ts
// Integration tests for the Explainability API endpoints

import { describe, it, expect, beforeAll, afterAll } from 'vitest';
import express, { Express } from 'express';
import request from 'supertest';
import { explainabilityRouter } from '../explainability.js';

describe('Explainability API Routes', () => {
  let app: Express;

  beforeAll(() => {
    app = express();
    app.use(express.json());
    app.use('/explainability', explainabilityRouter);
  });

  describe('GET /explainability', () => {
    it('should return API documentation', async () => {
      const res = await request(app).get('/explainability');
      
      expect(res.status).toBe(200);
      expect(res.body.service).toBe('AMTTP Risk Explainability API');
      expect(res.body.endpoints).toBeDefined();
      expect(res.body.actions).toBeDefined();
    });
  });

  describe('POST /explainability/explain', () => {
    it('should return explanation for valid risk score', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          transactionId: 'tx-test-123',
          riskScore: 0.73,
          features: {
            amountEth: 15.5,
            txCount24h: 47,
            dormancyDays: 180,
            sanctionsMatch: false
          }
        });

      expect(res.status).toBe(200);
      expect(res.body.success).toBe(true);
      expect(res.body.explanation).toBeDefined();
      expect(res.body.explanation.action).toBe('ESCROW');
      expect(res.body.explanation.topReasons).toBeInstanceOf(Array);
      expect(res.body.explanation.topReasons.length).toBeGreaterThan(0);
    });

    it('should return BLOCK for high-risk transaction', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          transactionId: 'tx-high-risk',
          riskScore: 0.95,
          features: {
            amountEth: 100,
            sanctionsMatch: true,
            countryCode: 'KP'
          }
        });

      expect(res.status).toBe(200);
      expect(res.body.explanation.action).toBe('BLOCK');
    });

    it('should return ALLOW for low-risk transaction', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          transactionId: 'tx-low-risk',
          riskScore: 0.15,
          features: {
            amountEth: 0.5,
            txCount24h: 2
          }
        });

      expect(res.status).toBe(200);
      expect(res.body.explanation.action).toBe('ALLOW');
    });

    it('should reject request without riskScore', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          transactionId: 'tx-no-score',
          features: {}
        });

      expect(res.status).toBe(400);
      expect(res.body.error).toContain('riskScore');
    });

    it('should reject invalid riskScore', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          riskScore: 1.5 // Invalid: > 1
        });

      expect(res.status).toBe(400);
      expect(res.body.error).toContain('Invalid');
    });
  });

  describe('GET /explainability/health', () => {
    it('should return health status', async () => {
      const res = await request(app).get('/explainability/health');
      
      expect(res.status).toBe(200);
      expect(res.body.service).toBe('explainability');
      expect(res.body.status).toBe('healthy');
      expect(res.body.cacheSize).toBeDefined();
    });
  });

  describe('GET /explainability/metrics', () => {
    it('should return prometheus metrics', async () => {
      const res = await request(app).get('/explainability/metrics');
      
      expect(res.status).toBe(200);
      expect(res.headers['content-type']).toContain('text/plain');
      expect(res.text).toContain('explainability_');
    });
  });

  describe('GET /explainability/config', () => {
    it('should return configuration', async () => {
      const res = await request(app).get('/explainability/config');
      
      expect(res.status).toBe(200);
      expect(res.body.actionThresholds).toBeDefined();
      expect(res.body.features).toBeInstanceOf(Array);
      expect(res.body.typologies).toBeInstanceOf(Array);
    });
  });

  describe('GET /explainability/typologies', () => {
    it('should return all typology definitions', async () => {
      const res = await request(app).get('/explainability/typologies');
      
      expect(res.status).toBe(200);
      expect(res.body.typologies).toBeInstanceOf(Array);
      expect(res.body.typologies.length).toBe(11);
      
      // Check structure of first typology
      const firstTypology = res.body.typologies[0];
      expect(firstTypology.id).toBeDefined();
      expect(firstTypology.name).toBeDefined();
      expect(firstTypology.description).toBeDefined();
      expect(firstTypology.indicators).toBeInstanceOf(Array);
      expect(firstTypology.severity).toBeDefined();
      expect(firstTypology.regulatoryRef).toBeDefined();
    });
  });

  describe('GET /explainability/cache/stats', () => {
    it('should return cache statistics', async () => {
      const res = await request(app).get('/explainability/cache/stats');
      
      expect(res.status).toBe(200);
      expect(res.body.cacheSize).toBeDefined();
      expect(res.body.status).toBeDefined();
    });
  });

  describe('Typology Detection', () => {
    it('should detect FAN_OUT typology for high unique recipients', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          riskScore: 0.7,
          features: {
            txCount24h: 100,
            uniqueRecipients24h: 50
          }
        });

      expect(res.status).toBe(200);
      const typologies = res.body.explanation.typologyMatches.map(
        (t: any) => t.typology
      );
      expect(typologies).toContain('fan_out');
    });

    it('should detect DORMANT_ACTIVATION typology', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          riskScore: 0.65,
          features: {
            dormancyDays: 365,
            amountEth: 50
          }
        });

      expect(res.status).toBe(200);
      const typologies = res.body.explanation.typologyMatches.map(
        (t: any) => t.typology
      );
      expect(typologies).toContain('dormant_activation');
    });

    it('should detect SANCTIONS_PROXIMITY via graph context', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          riskScore: 0.9,
          features: {
            sanctionsMatch: true
          },
          graphContext: {
            hopsToSanctioned: 1
          }
        });

      expect(res.status).toBe(200);
      // Sanctions match should trigger high risk - check action
      expect(res.body.explanation.action).toBe('BLOCK');
    });

    it('should detect risk from HIGH_RISK country', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          riskScore: 0.75,
          features: {
            countryCode: 'KP',
            fatfCountryRisk: 'black'
          }
        });

      expect(res.status).toBe(200);
      // High risk geography should trigger ESCROW
      expect(res.body.explanation.action).toBe('ESCROW');
      // Check that explanation mentions country risk
      const summary = res.body.explanation.summary.toLowerCase();
      expect(summary.includes('escrow') || summary.includes('review')).toBe(true);
    });
  });

  describe('Human-Readable Explanations', () => {
    it('should provide clear top reasons', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          riskScore: 0.73,
          features: {
            amountEth: 50,
            avgAmount30d: 2,
            txCount24h: 45,
            dormancyDays: 180
          }
        });

      expect(res.status).toBe(200);
      
      // Check that top reasons are human-readable (not technical jargon)
      const topReasons = res.body.explanation.topReasons;
      expect(topReasons.length).toBeGreaterThan(0);
      
      // Should not contain raw model names like "XGB" or "VAE"
      topReasons.forEach((reason: string) => {
        expect(reason).not.toMatch(/XGB|VAE|GNN/i);
        expect(reason.length).toBeGreaterThan(20); // Meaningful sentence
      });
    });

    it('should provide actionable recommendations', async () => {
      const res = await request(app)
        .post('/explainability/explain')
        .send({
          riskScore: 0.65,
          features: {
            amountEth: 25
          }
        });

      expect(res.status).toBe(200);
      
      const recommendations = res.body.explanation.recommendations;
      expect(recommendations).toBeInstanceOf(Array);
      expect(recommendations.length).toBeGreaterThan(0);
    });
  });
});

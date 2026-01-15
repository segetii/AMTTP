import { describe, test, expect } from 'vitest';
import request from 'supertest';
import { app } from '../index.js';
describe('KYC routes', () => {
    test('GET /kyc returns info', async () => {
        const res = await request(app).get('/kyc');
        expect(res.status).toBe(200);
        expect(res.body).toHaveProperty('message');
        expect(res.body.endpoints).toHaveProperty('POST /kyc/init');
    });
    test('POST /kyc/test-sandbox creates a fake record', async () => {
        const res = await request(app)
            .post('/kyc/test-sandbox')
            .send({ userId: 'test-user-123' })
            .set('Accept', 'application/json');
        expect(res.status).toBe(200);
        expect(res.body).toHaveProperty('applicantId');
        expect(res.body).toHaveProperty('kycHash');
        expect(res.body.testMode).toBeTruthy();
    });
});

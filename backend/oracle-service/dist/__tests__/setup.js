import 'dotenv/config';
import { vi } from 'vitest';
// Setup test environment variables
process.env.NODE_ENV = 'test';
// Mock mongoose to avoid database dependency in tests
vi.mock('mongoose', () => ({
    connect: vi.fn(() => Promise.resolve()),
    disconnect: vi.fn(() => Promise.resolve()),
    Schema: vi.fn(),
    model: vi.fn()
}));
// Mock database models
vi.mock('../db/models.js', () => ({
    KycModel: {
        create: vi.fn(() => Promise.resolve({
            userId: 'test-user',
            provider: 'sumsub',
            providerApplicantId: 'test-123',
            level: 'KYC_BASIC',
            status: 'approved'
        })),
        updateOne: vi.fn(() => Promise.resolve()),
        findOne: vi.fn(() => Promise.resolve())
    }
}));

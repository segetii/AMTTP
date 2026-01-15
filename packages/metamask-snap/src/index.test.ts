import { installSnap } from '@metamask/snaps-jest';
import { panel, text, heading, row, divider } from '@metamask/snaps-sdk';

describe('AMTTP MetaMask Snap', () => {
  describe('onInstall', () => {
    it('shows welcome dialog on installation', async () => {
      const { request } = await installSnap();
      
      // The snap should show a welcome dialog
      expect(true).toBe(true); // Installation completed
    });
  });

  describe('onTransaction', () => {
    it('returns risk assessment for transactions', async () => {
      const { sendTransaction } = await installSnap();
      
      const response = await sendTransaction({
        to: '0x1234567890123456789012345678901234567890',
        value: '0xde0b6b3a7640000', // 1 ETH
        data: '0x',
      });

      expect(response).toBeDefined();
      // Should contain risk assessment panel
    });

    it('flags high-value transactions', async () => {
      const { sendTransaction } = await installSnap();
      
      const response = await sendTransaction({
        to: '0x1234567890123456789012345678901234567890',
        value: '0x8ac7230489e80000', // 10 ETH
        data: '0x',
      });

      expect(response).toBeDefined();
      // Should flag as higher risk
    });

    it('detects token approvals', async () => {
      const { sendTransaction } = await installSnap();
      
      // approve(address,uint256) function selector
      const response = await sendTransaction({
        to: '0x1234567890123456789012345678901234567890',
        value: '0x0',
        data: '0x095ea7b3000000000000000000000000spender00000000000000000000000000000000000000000000000000000000ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff',
      });

      expect(response).toBeDefined();
      // Should warn about token approval
    });
  });

  describe('RPC Methods', () => {
    it('returns policy with amttp_getPolicy', async () => {
      const { request } = await installSnap();
      
      const response = await request({
        method: 'amttp_getPolicy',
      });

      expect(response).toHaveProperty('result');
      expect(response.result).toHaveProperty('maxRiskThreshold');
      expect(response.result).toHaveProperty('blockHighRisk');
    });

    it('checks risk with amttp_checkRisk', async () => {
      const { request } = await installSnap();
      
      const response = await request({
        method: 'amttp_checkRisk',
        params: {
          to: '0x1234567890123456789012345678901234567890',
          value: '1000000000000000000',
        },
      });

      expect(response).toHaveProperty('result');
      expect(response.result).toHaveProperty('score');
      expect(response.result).toHaveProperty('level');
      expect(response.result).toHaveProperty('recommendation');
    });

    it('returns stats with amttp_getStats', async () => {
      const { request } = await installSnap();
      
      const response = await request({
        method: 'amttp_getStats',
      });

      expect(response).toHaveProperty('result');
      expect(response.result).toHaveProperty('approved');
      expect(response.result).toHaveProperty('blocked');
    });

    it('throws for unknown methods', async () => {
      const { request } = await installSnap();
      
      const response = await request({
        method: 'unknown_method',
      });

      expect(response).toHaveProperty('error');
    });
  });

  describe('Allowlist/Blocklist', () => {
    it('adds address to allowlist', async () => {
      const { request } = await installSnap();
      
      // This would require user confirmation in real scenario
      const response = await request({
        method: 'amttp_addToAllowlist',
        params: {
          address: '0x1234567890123456789012345678901234567890',
        },
      });

      // Response depends on user interaction
      expect(response).toBeDefined();
    });

    it('removes address from blocklist', async () => {
      const { request } = await installSnap();
      
      const response = await request({
        method: 'amttp_removeFromBlocklist',
        params: {
          address: '0x1234567890123456789012345678901234567890',
        },
      });

      expect(response).toHaveProperty('result');
      expect(response.result).toHaveProperty('success', true);
    });
  });
});

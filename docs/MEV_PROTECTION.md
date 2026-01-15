# MEV Protection in AMTTP

## Overview

AMTTP implements multiple layers of protection against Miner Extractable Value (MEV) attacks, including:
- **Flashbots Protect RPC**: Users and frontends are strongly encouraged to submit all swap transactions via Flashbots Protect RPC endpoints to avoid public mempool exposure and sandwich attacks.
- **On-Chain Event**: The contract emits a `MEVProtectedSwap` event for every swap submitted via a protected channel, enabling monitoring and alerting.
- **Best Practices**: SDK and frontend documentation instructs users to default to MEV-protected endpoints and warns if not used.

## Flashbots Protect Integration

- **Frontend/SDK**: All transaction submission functions should use Flashbots Protect RPC (e.g., `https://rpc.flashbots.net`) by default.
- **User Guidance**: Documentation and UI should clearly indicate when a transaction is MEV-protected.
- **Fallback**: If Flashbots is unavailable, warn the user and allow opt-in to public mempool.

## On-Chain Event

- The contract emits `event MEVProtectedSwap(address indexed user, uint256 swapId, bytes32 txHash);` for swaps submitted via Flashbots or other private relays.
- Off-chain monitoring tools can subscribe to this event to verify MEV protection coverage.

## Developer Best Practices

- Always use private RPC endpoints for sensitive transactions.
- Monitor `MEVProtectedSwap` events to ensure compliance.
- Educate users about MEV risks and protection mechanisms.

## References
- [Flashbots Protect RPC](https://docs.flashbots.net/flashbots-protect/rpc/)
- [MEV-Blocker](https://www.mevblocker.io/)
- [Ethereum.org: MEV](https://ethereum.org/en/developers/docs/mev/)
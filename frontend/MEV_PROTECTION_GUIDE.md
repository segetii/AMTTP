# AMTTP Frontend/SDK MEV Protection Guide

## Summary
To protect users from MEV attacks (e.g., sandwiching, frontrunning), all AMTTP swap transactions should be submitted via Flashbots Protect RPC or similar private relays.

## How to Use Flashbots Protect
- Set the RPC endpoint to `https://rpc.flashbots.net` in your wallet or dApp.
- The SDK should default to this endpoint for all swap-related transactions.
- Warn users if they are not using a protected endpoint.

## UI/UX Recommendations
- Display a badge or message when a transaction is MEV-protected.
- Provide a link to learn more about MEV and why protection matters.
- Allow users to opt-in to public mempool only with explicit warning.

## Monitoring
- Listen for the `MEVProtectedSwap` event on-chain to verify swaps are protected.

## References
- [Flashbots Protect Docs](https://docs.flashbots.net/flashbots-protect/rpc/)
- [MEV-Blocker](https://www.mevblocker.io/)

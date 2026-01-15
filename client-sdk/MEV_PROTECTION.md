# AMTTP SDK MEV Protection

## Default Behavior
- All swap transactions are sent via Flashbots Protect RPC (`https://rpc.flashbots.net`) by default.
- If the user overrides the RPC, the SDK will warn if the endpoint is not MEV-protected.

## How to Integrate
- Use the SDK's `sendSwapTransaction` method, which routes via Flashbots Protect unless otherwise specified.
- To check if a transaction is MEV-protected, listen for the `MEVProtectedSwap` event on-chain.

## Example
```js
import { sendSwapTransaction } from '@amttp/client-sdk';

// This will use Flashbots Protect by default
await sendSwapTransaction({ ...params });
```

## User Warnings
- If the RPC is not MEV-protected, display a warning in the UI.

## References
- [Flashbots Protect RPC](https://docs.flashbots.net/flashbots-protect/rpc/)

# AMTTP Client SDKs

Open-source client libraries for the **Autonomous Multi-Token Transfer Protocol (AMTTP)**.

These SDKs provide programmatic access to the AMTTP compliance gateway, enabling third-party integration and independent audit of the protocol's API surface.

## TypeScript SDK (`client-sdk/`)

```bash
npm install @amttp/client-sdk
```

```typescript
import { AMTTPClient } from '@amttp/client-sdk';

const client = new AMTTPClient({
  baseUrl: 'https://api.amttp.io',
  apiKey: 'your-api-key',
});

// Screen a transaction
const result = await client.risk.screenTransaction({
  from: '0x...',
  to: '0x...',
  amount: '1000000',
  token: 'USDC',
});
```

### Features
- Full TypeScript type definitions
- All 18 compliance service endpoints
- MEV protection utilities
- Event streaming (SSE)
- Automatic retry and error handling

## Python SDK (`client-sdk-python/`)

```bash
pip install amttp
```

```python
from amttp import AMTTPClient

client = AMTTPClient(
    base_url="https://api.amttp.io",
    api_key="your-api-key",
)

# Screen a transaction
result = client.risk.screen_transaction(
    from_address="0x...",
    to_address="0x...",
    amount="1000000",
    token="USDC",
)
```

### Features
- Fully typed with `py.typed` marker
- All 18 compliance service endpoints
- Async support
- Event monitoring
- Comprehensive error hierarchy

## Documentation

For full protocol documentation, see the [AMTTP paper](https://doi.org/10.36227/techrxiv.xxx) (forthcoming).

## Licence

MIT — see [LICENCE](LICENCE) for details.

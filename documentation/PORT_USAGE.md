# Port Usage Reference

**Last Updated:** February 1, 2026

## Core Services

| Service           | Port  | Description                       |
|-------------------|-------|-----------------------------------|
| ML Risk Engine    | 8000  | ML fraud detection                |
| Graph Service     | 8001  | Graph DB (Memgraph)               |
| ML Service        | 8002  | ML model serving                  |
| Policy Engine     | 8003  | Policy/whitelist/blacklist        |
| FCA Sanctions     | 8004  | Sanctions screening               |
| Monitoring        | 8005  | AML monitoring                    |
| GeoRisk           | 8006  | Country risk scoring              |
| Orchestrator      | 8007  | API gateway                       |
| Integrity         | 8008  | UI integrity checks               |
| Explainability    | 8009  | ML explainability service         |

## Frontend Applications

| Application       | Port  | Description                       |
|-------------------|-------|-----------------------------------|
| Next.js War Room  | 3006  | Institutional compliance console  |
| Flutter Consumer  | 8889  | End-user wallet app (dev)         |
| Flutter Web       | 3010  | Flutter web (alternate port)      |

## Infrastructure

| Service           | Port  | Description                       |
|-------------------|-------|-----------------------------------|
| MongoDB           | 27017 | Document database                 |
| Redis             | 6379  | Cache/session store               |
| Memgraph          | 7687  | Graph database                    |
| MinIO             | 9000  | Object storage (S3-compatible)    |

## Notes

- **War Room (3006)**: Opens to login page, supports wallet/email/demo auth
- **Flutter Consumer (8889)**: Real MetaMask integration on Sepolia testnet
- SIEM dashboard has been removed from the platform

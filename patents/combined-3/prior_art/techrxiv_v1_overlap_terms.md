# TechRxiv v1 → Combined-3 overlap (term-level)

- Source PDF: techrxiv_amttp_v1.pdf (13 pages)
- Current UK spec: patent_specification.tex

## Term map (page hits)
Term | Meaning | Pages
--- | --- | ---
pre-settlement | Pre-settlement controls (general concept) | 1, 2
decision matrix | Deterministic decision matrix | 4, 5, 12
approve | Approve action | 4
review | Review action | 2, 4, 9
escrow | Escrow action / time-locking concept | 4, 6, 9, 12
block | Block action | 4, 12
sanctions | Sanctions screening | 1, 2, 4, 5, 6, 7
kyc | KYC | 1, 2, 3, 4, 6, 7
risk range | Risk range proof concept | 1, 2, 6
non-membership | Non-membership proof concept | 1, 2, 6
zero-knowledge | Zero-knowledge proofs | 2, 3, 13
zk-snark | zk-SNARK mention | 3
groth16 | Groth16 mention | 3, 5, 6
ttl | TTL / freshness | (none found)
anomaly tensor | Anomaly tensor | (none found)
spectrum operator | Spectrum operators | (none found)
law domain | Per-law-domain attribution | (none found)
adaptive friction | Adaptive friction | (none found)
gamma | Gamma / friction coefficient notation | (none found)
revert | Revert / EVM enforcement | (none found)
poseidon | Poseidon hash | (none found)
merkle | Merkle tree | (none found)

## Snippets (first hit per term)
### pre-settlement — Pre-settlement controls (general concept)
Page 1

> transact in cryptocurrency bear the ultimate ﬁnancial risk and regulatory burden. the uk fca has made it very clear through cp25/41 that there are now speciﬁc regulatory expectations regarding the existence of adequate pre- settlement controls [2]. we introduce amttp version 4.0, which has been designed to have a four-layer architecture explicitly intended to support deterministic compliance enforcement in defi institutions. layer i provides sdks, re

### decision matrix — Deterministic decision matrix
Page 4

> irst, a consumer- oriented application developed using flutter, connects to meta- mask and allows users to connect their wallets and review risk assessments before signing any agreements. the second, table i: compliance decision matrix condition action risk<200∧ ¬sanctioned∧geo̸=pro- hibited approve 200≤risk<400∧ ¬sanctioned approve 400≤risk<600∧ ¬sanctioned review 600≤risk<800escrow risk≥800∨red flags block sanctioned∨fatf blacklist block velocity an

### approve — Approve action
Page 4

> tools currently document and create alerts for identified items within their ecosystem; however, amttp will enable users to normalise disparate signals, thus enabling the user to make real-time compliance decisions of ‘approve’, ‘review’, ‘escrow’ or ‘block’. to provide this capability, zknaf creates a privacy- preserving layer of attestation that bridges the reactive surveil- lance systems used today and that required for institutions to com

### review — Review action
Page 2

> regulatory obliga- tions. regulating bodies have labelled this “the defi compliance paradox”. by monitoring suspicious transactions through tra- ditional finance platforms, the regulator can stop the transfer in-flight, review it for any illicit activities, and reverse the transfer if there’s a potential illegal market participant prior to the transaction settling. this is impossible with permissionless blockchains, where finality occurs in s

### escrow — Escrow action / time-locking concept
Page 4

> ment and create alerts for identified items within their ecosystem; however, amttp will enable users to normalise disparate signals, thus enabling the user to make real-time compliance decisions of ‘approve’, ‘review’, ‘escrow’ or ‘block’. to provide this capability, zknaf creates a privacy- preserving layer of attestation that bridges the reactive surveil- lance systems used today and that required for institutions to complete their business

### block — Block action
Page 4

> ate alerts for identified items within their ecosystem; however, amttp will enable users to normalise disparate signals, thus enabling the user to make real-time compliance decisions of ‘approve’, ‘review’, ‘escrow’ or ‘block’. to provide this capability, zknaf creates a privacy- preserving layer of attestation that bridges the reactive surveil- lance systems used today and that required for institutions to complete their business at an actu

### sanctions — Sanctions screening
Page 1

> s, rest apis, and web applications intended for programmatic and human interaction with amttp; layer ii provides a compliance orchestration layer that combines (i) machine learning risk scoring (ii) graph analysis (iii) sanctions screening, and (iv) policy adjudication into a single deterministic decision-making matrix; layer iii consists of an oﬄine training pipeline with a composite teacher that uses an autoencoderenhanced xgboost (w = 0.4), s

### kyc — KYC
Page 1

> e tier (mongodb, redis, memgraph, ipfs). the infrastructure security features multioracle threshold signatures, replay protection & zknaf a zeroknowledge proof framework that allows for privacy preserving veriﬁcation of kyc credentials, risk ranges & non-membership from sanctions. in addition, tls encryption, rate limiting, cloudﬂare tunnel integration & the ui integrity service provide an additional layer of protection at the infrastructu

### risk range — Risk range proof concept
Page 1

> redis, memgraph, ipfs). the infrastructure security features multioracle threshold signatures, replay protection & zknaf a zeroknowledge proof framework that allows for privacy preserving veriﬁcation of kyc credentials, risk ranges & non-membership from sanctions. in addition, tls encryption, rate limiting, cloudﬂare tunnel integration & the ui integrity service provide an additional layer of protection at the infrastructure level. this paper aim

### non-membership — Non-membership proof concept
Page 1

> h, ipfs). the infrastructure security features multioracle threshold signatures, replay protection & zknaf a zeroknowledge proof framework that allows for privacy preserving veriﬁcation of kyc credentials, risk ranges & non-membership from sanctions. in addition, tls encryption, rate limiting, cloudﬂare tunnel integration & the ui integrity service provide an additional layer of protection at the infrastructure level. this paper aims to demonstrate t

### zero-knowledge — Zero-knowledge proofs
Page 2

> on ethereum sepolia, 17 containerised microservices, and a database persistence tier (mongodb, redis, memgraph, ipfs). the infrastructure security features multi- oracle threshold signatures, replay protection & zknaf a zero- knowledge proof framework that allows for privacy preserving verification of kyc credentials, risk ranges & non-membership from sanctions. in addition, tls encryption, rate limiting, cloudflare tunnel integration & the ui integri

### zk-snark — zk-SNARK mention
Page 3

> ll be in align- ment with the requirements of the general data protection regulation (gdpr) and have significant implications for com- panies implementing these types of systems. for example, on the one hand, zkaml uses zk-snarks to enable whitelist- based anti-money laundering (aml) activities within smart contracts while providing cryptographic assurances to regu- lators that the activities are compliant with regulations and are also cryptogra

### groth16 — Groth16 mention
Page 3

> ith regulatory requirements by establishing proof of compliance with certain attributes, such as non-sanctioned status, while not disclosing the underlying data [6]. therefore, zero-knowledge proof systems, specifically groth16 circuits, will be in align- ment with the requirements of the general data protection regulation (gdpr) and have significant implications for com- panies implementing these types of systems. for example, on the one hand

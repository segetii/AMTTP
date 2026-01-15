#!/bin/bash
# Auto-generated hash registration script

curl -X POST "http://localhost:8008/register-hash" \
  -d "component_id=secure-payment" \
  -d "hash_value=06b973c42a6e7381a61b898cba826a82e66c6f209e1b1a71a964c5ac2056725a" \
  -d "version=1.0.0" \
  -d "admin_key=${INTEGRITY_ADMIN_KEY}"

curl -X POST "http://localhost:8008/register-hash" \
  -d "component_id=transfer-page" \
  -d "hash_value=e609b0d9ab380a0e04a40bfb17fced1e140a64f42e1bc6a001417ffe029d819f" \
  -d "version=1.0.0" \
  -d "admin_key=${INTEGRITY_ADMIN_KEY}"

curl -X POST "http://localhost:8008/register-hash" \
  -d "component_id=wallet-connect" \
  -d "hash_value=06f61dfb74fb7a4b83f36fa99c643142b4601eaef01b6280a663a15449506df5" \
  -d "version=1.0.0" \
  -d "admin_key=${INTEGRITY_ADMIN_KEY}"

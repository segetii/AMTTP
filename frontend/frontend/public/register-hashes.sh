#!/bin/bash
# Auto-generated hash registration script

curl -X POST "http://localhost:8008/register-hash" \
  -d "component_id=secure-payment" \
  -d "hash_value=7efe8c8ab67caa140c06f3c33e7ec2bc11a5a57fb11416f1f86def104d41bdfc" \
  -d "version=1.0.0" \
  -d "admin_key=${INTEGRITY_ADMIN_KEY}"

curl -X POST "http://localhost:8008/register-hash" \
  -d "component_id=transfer-page" \
  -d "hash_value=11af577a4b7eac69e338b88c06e6c591b6d71ef9f4d762df8ad835f050041753" \
  -d "version=1.0.0" \
  -d "admin_key=${INTEGRITY_ADMIN_KEY}"

curl -X POST "http://localhost:8008/register-hash" \
  -d "component_id=wallet-connect" \
  -d "hash_value=06f61dfb74fb7a4b83f36fa99c643142b4601eaef01b6280a663a15449506df5" \
  -d "version=1.0.0" \
  -d "admin_key=${INTEGRITY_ADMIN_KEY}"

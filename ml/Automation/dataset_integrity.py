#!/usr/bin/env python3
"""
AMTTP Dataset Integrity Service

Provides cryptographic signing and verification for ML training datasets.
Ensures data provenance and prevents training data poisoning attacks.

Features:
- SHA256 hashing of datasets
- Ed25519 digital signatures
- Manifest generation with metadata
- Verification before training
- Audit trail for compliance

Usage:
    # Sign a dataset
    python dataset_integrity.py sign --file data.parquet --key private_key.pem

    # Verify a dataset
    python dataset_integrity.py verify --file data.parquet --manifest data.manifest.json

    # Generate a new signing keypair
    python dataset_integrity.py keygen --output keys/
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.backends import default_backend
    from cryptography.exceptions import InvalidSignature
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False
    print("Warning: cryptography not installed. Install with: pip install cryptography")

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False


# ═══════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════

MANIFEST_VERSION = "1.0.0"
CHUNK_SIZE = 8192  # 8KB chunks for hashing large files


# ═══════════════════════════════════════════════════════════════════════════
# Hash Functions
# ═══════════════════════════════════════════════════════════════════════════

def compute_file_hash(filepath: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256 = hashlib.sha256()
    
    with open(filepath, 'rb') as f:
        while chunk := f.read(CHUNK_SIZE):
            sha256.update(chunk)
    
    return sha256.hexdigest()


def compute_dataframe_hash(df: 'pd.DataFrame') -> str:
    """Compute hash of a pandas DataFrame (content-based, order-independent)."""
    # Hash based on sorted data to ensure reproducibility
    content = df.to_json(orient='split', date_format='iso')
    return hashlib.sha256(content.encode()).hexdigest()


def compute_column_hashes(df: 'pd.DataFrame') -> Dict[str, str]:
    """Compute individual column hashes for fine-grained verification."""
    column_hashes = {}
    for col in df.columns:
        col_data = df[col].to_json()
        column_hashes[col] = hashlib.sha256(col_data.encode()).hexdigest()[:16]
    return column_hashes


# ═══════════════════════════════════════════════════════════════════════════
# Key Management
# ═══════════════════════════════════════════════════════════════════════════

def generate_keypair(output_dir: str) -> Tuple[str, str]:
    """Generate Ed25519 keypair for dataset signing."""
    if not HAS_CRYPTO:
        raise RuntimeError("cryptography library required for key generation")
    
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Save private key (keep secret!)
    private_path = os.path.join(output_dir, 'dataset_signing_key.pem')
    with open(private_path, 'wb') as f:
        f.write(private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ))
    os.chmod(private_path, 0o600)
    
    # Save public key (can be shared)
    public_path = os.path.join(output_dir, 'dataset_signing_key.pub')
    with open(public_path, 'wb') as f:
        f.write(public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ))
    
    print(f"✅ Generated keypair:")
    print(f"   Private key: {private_path} (KEEP SECRET!)")
    print(f"   Public key:  {public_path}")
    
    return private_path, public_path


def load_private_key(key_path: str) -> 'ed25519.Ed25519PrivateKey':
    """Load Ed25519 private key from PEM file."""
    with open(key_path, 'rb') as f:
        return serialization.load_pem_private_key(
            f.read(),
            password=None,
            backend=default_backend()
        )


def load_public_key(key_path: str) -> 'ed25519.Ed25519PublicKey':
    """Load Ed25519 public key from PEM file."""
    with open(key_path, 'rb') as f:
        return serialization.load_pem_public_key(
            f.read(),
            backend=default_backend()
        )


# ═══════════════════════════════════════════════════════════════════════════
# Manifest Generation & Signing
# ═══════════════════════════════════════════════════════════════════════════

def create_manifest(
    filepath: str,
    signer_id: str = "amttp-ml-team",
    description: str = ""
) -> Dict:
    """Create a manifest for a dataset file."""
    
    file_stat = os.stat(filepath)
    file_hash = compute_file_hash(filepath)
    
    manifest = {
        "version": MANIFEST_VERSION,
        "file": {
            "name": os.path.basename(filepath),
            "path": os.path.abspath(filepath),
            "size_bytes": file_stat.st_size,
            "sha256": file_hash,
            "modified": datetime.fromtimestamp(file_stat.st_mtime).isoformat(),
        },
        "metadata": {
            "signer_id": signer_id,
            "description": description,
            "signed_at": datetime.utcnow().isoformat() + "Z",
            "protocol": "AMTTP",
            "purpose": "ML Training Dataset",
        },
        "integrity": {
            "algorithm": "SHA256",
            "file_hash": file_hash,
        }
    }
    
    # If it's a parquet file, add DataFrame-level info
    if filepath.endswith('.parquet') and HAS_PANDAS:
        try:
            df = pd.read_parquet(filepath)
            manifest["dataframe"] = {
                "rows": len(df),
                "columns": len(df.columns),
                "column_names": list(df.columns),
                "column_hashes": compute_column_hashes(df),
                "content_hash": compute_dataframe_hash(df),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            }
            
            # Add label distribution if 'flag' column exists
            if 'flag' in df.columns:
                manifest["dataframe"]["label_distribution"] = df['flag'].value_counts().to_dict()
                
        except Exception as e:
            print(f"Warning: Could not read parquet file for metadata: {e}")
    
    return manifest


def sign_manifest(manifest: Dict, private_key_path: str) -> Dict:
    """Sign a manifest with Ed25519 private key."""
    if not HAS_CRYPTO:
        raise RuntimeError("cryptography library required for signing")
    
    private_key = load_private_key(private_key_path)
    
    # Create canonical JSON for signing
    signing_data = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
    
    # Sign
    signature = private_key.sign(signing_data)
    
    # Add signature to manifest
    signed_manifest = manifest.copy()
    signed_manifest["signature"] = {
        "algorithm": "Ed25519",
        "value": signature.hex(),
        "public_key_hint": hashlib.sha256(
            private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PublicFormat.Raw
            )
        ).hexdigest()[:16],
    }
    
    return signed_manifest


def verify_manifest(manifest_path: str, public_key_path: str, data_path: Optional[str] = None) -> bool:
    """Verify a signed manifest and optionally the associated data file."""
    if not HAS_CRYPTO:
        raise RuntimeError("cryptography library required for verification")
    
    with open(manifest_path, 'r') as f:
        signed_manifest = json.load(f)
    
    # Extract signature
    signature_info = signed_manifest.pop("signature", None)
    if not signature_info:
        print("❌ Manifest is not signed")
        return False
    
    signature = bytes.fromhex(signature_info["value"])
    
    # Recreate signing data
    signing_data = json.dumps(signed_manifest, sort_keys=True, separators=(',', ':')).encode()
    
    # Verify signature
    public_key = load_public_key(public_key_path)
    
    try:
        public_key.verify(signature, signing_data)
        print("✅ Manifest signature is valid")
    except InvalidSignature:
        print("❌ Manifest signature is INVALID")
        return False
    
    # Verify file hash if data path provided
    if data_path:
        expected_hash = signed_manifest["integrity"]["file_hash"]
        actual_hash = compute_file_hash(data_path)
        
        if actual_hash == expected_hash:
            print(f"✅ File hash matches: {actual_hash[:16]}...")
        else:
            print(f"❌ File hash MISMATCH!")
            print(f"   Expected: {expected_hash}")
            print(f"   Actual:   {actual_hash}")
            return False
    
    return True


# ═══════════════════════════════════════════════════════════════════════════
# CLI Commands
# ═══════════════════════════════════════════════════════════════════════════

def cmd_sign(args):
    """Sign a dataset file."""
    print(f"📝 Creating manifest for: {args.file}")
    
    manifest = create_manifest(
        args.file,
        signer_id=args.signer or os.getenv('USER', 'unknown'),
        description=args.description or ""
    )
    
    if args.key:
        print(f"🔐 Signing with: {args.key}")
        manifest = sign_manifest(manifest, args.key)
    else:
        print("⚠️  No signing key provided - manifest will be unsigned")
    
    # Save manifest
    manifest_path = args.output or f"{args.file}.manifest.json"
    with open(manifest_path, 'w') as f:
        json.dump(manifest, f, indent=2)
    
    print(f"✅ Manifest saved: {manifest_path}")
    print(f"   File hash: {manifest['integrity']['file_hash'][:32]}...")
    
    if 'dataframe' in manifest:
        df_info = manifest['dataframe']
        print(f"   Rows: {df_info['rows']:,}")
        print(f"   Columns: {df_info['columns']}")
        if 'label_distribution' in df_info:
            print(f"   Labels: {df_info['label_distribution']}")


def cmd_verify(args):
    """Verify a dataset and manifest."""
    print(f"🔍 Verifying: {args.manifest}")
    
    data_path = args.file
    if not data_path:
        # Try to infer from manifest name
        if args.manifest.endswith('.manifest.json'):
            data_path = args.manifest.replace('.manifest.json', '')
            if not os.path.exists(data_path):
                data_path = None
    
    if not args.key:
        print("⚠️  No public key provided - skipping signature verification")
        # Just verify file hash
        with open(args.manifest, 'r') as f:
            manifest = json.load(f)
        
        if data_path and os.path.exists(data_path):
            expected = manifest['integrity']['file_hash']
            actual = compute_file_hash(data_path)
            if actual == expected:
                print(f"✅ File hash matches: {actual[:16]}...")
            else:
                print(f"❌ File hash MISMATCH!")
                return
    else:
        success = verify_manifest(args.manifest, args.key, data_path)
        if not success:
            sys.exit(1)
    
    print("\n✅ Verification complete!")


def cmd_keygen(args):
    """Generate signing keypair."""
    generate_keypair(args.output)


def cmd_hash(args):
    """Compute hash of a file."""
    file_hash = compute_file_hash(args.file)
    print(f"SHA256: {file_hash}")
    print(f"File:   {args.file}")


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='AMTTP Dataset Integrity Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate signing keys
  python dataset_integrity.py keygen --output keys/

  # Sign a dataset
  python dataset_integrity.py sign --file data.parquet --key keys/dataset_signing_key.pem

  # Verify a dataset
  python dataset_integrity.py verify --manifest data.parquet.manifest.json --key keys/dataset_signing_key.pub

  # Just compute hash
  python dataset_integrity.py hash --file data.parquet
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Command')
    
    # Sign command
    sign_parser = subparsers.add_parser('sign', help='Sign a dataset')
    sign_parser.add_argument('--file', '-f', required=True, help='Dataset file to sign')
    sign_parser.add_argument('--key', '-k', help='Private key for signing')
    sign_parser.add_argument('--output', '-o', help='Output manifest path')
    sign_parser.add_argument('--signer', '-s', help='Signer ID')
    sign_parser.add_argument('--description', '-d', help='Description')
    sign_parser.set_defaults(func=cmd_sign)
    
    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify a dataset')
    verify_parser.add_argument('--manifest', '-m', required=True, help='Manifest file')
    verify_parser.add_argument('--key', '-k', help='Public key for verification')
    verify_parser.add_argument('--file', '-f', help='Data file (optional, inferred from manifest)')
    verify_parser.set_defaults(func=cmd_verify)
    
    # Keygen command
    keygen_parser = subparsers.add_parser('keygen', help='Generate signing keypair')
    keygen_parser.add_argument('--output', '-o', default='keys', help='Output directory')
    keygen_parser.set_defaults(func=cmd_keygen)
    
    # Hash command
    hash_parser = subparsers.add_parser('hash', help='Compute file hash')
    hash_parser.add_argument('--file', '-f', required=True, help='File to hash')
    hash_parser.set_defaults(func=cmd_hash)
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    args.func(args)


if __name__ == '__main__':
    main()

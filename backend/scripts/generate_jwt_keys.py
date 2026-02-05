#!/usr/bin/env python3
"""
Generate RSA Key Pair for JWT RS256 Signing

This script generates a new RSA key pair for JWT authentication:
- Private key: Used by the auth server to sign tokens
- Public key: Can be shared with services to verify tokens

Usage:
    # Generate keys to files
    python scripts/generate_jwt_keys.py

    # Generate keys to specific directory
    python scripts/generate_jwt_keys.py --output-dir /path/to/keys

    # Generate and show as base64 (for environment variables)
    python scripts/generate_jwt_keys.py --base64

    # Generate with custom key size
    python scripts/generate_jwt_keys.py --key-size 4096

Security Notes:
    - Keep the private key SECRET - never commit to git
    - The public key can be freely distributed
    - Recommended key size is 2048 or 4096 bits
    - Rotate keys periodically (e.g., every 90 days)
"""

import argparse
import base64
import os
import sys
from pathlib import Path
from datetime import datetime


def generate_rsa_keys(key_size: int = 2048) -> tuple[bytes, bytes]:
    """
    Generate an RSA key pair.

    Args:
        key_size: Key size in bits (2048 or 4096 recommended)

    Returns:
        Tuple of (private_key_pem, public_key_pem) as bytes
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.backends import default_backend
    except ImportError:
        print("Error: cryptography package is required.")
        print("Install with: pip install cryptography")
        sys.exit(1)

    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=key_size,
        backend=default_backend()
    )

    # Serialize private key to PEM format
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )

    # Get public key and serialize to PEM
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )

    return private_pem, public_pem


def save_keys(
    private_pem: bytes,
    public_pem: bytes,
    output_dir: Path,
    prefix: str = "jwt"
) -> tuple[Path, Path]:
    """
    Save keys to files.

    Args:
        private_pem: Private key in PEM format
        public_pem: Public key in PEM format
        output_dir: Directory to save keys
        prefix: Filename prefix

    Returns:
        Tuple of (private_key_path, public_key_path)
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    private_path = output_dir / f"{prefix}_private.pem"
    public_path = output_dir / f"{prefix}_public.pem"

    # Write private key with restricted permissions
    private_path.write_bytes(private_pem)
    os.chmod(private_path, 0o600)  # Owner read/write only

    # Public key can be readable
    public_path.write_bytes(public_pem)
    os.chmod(public_path, 0o644)  # Owner read/write, others read

    return private_path, public_path


def print_base64_keys(private_pem: bytes, public_pem: bytes) -> None:
    """Print keys as base64 for environment variables."""
    private_b64 = base64.b64encode(private_pem).decode('utf-8')
    public_b64 = base64.b64encode(public_pem).decode('utf-8')

    print("\n" + "=" * 70)
    print("Base64-Encoded Keys for Environment Variables")
    print("=" * 70)
    print("\nAdd these to your environment or .env file:\n")
    print(f"AUTH_PRIVATE_KEY={private_b64}")
    print(f"\nAUTH_PUBLIC_KEY={public_b64}")
    print("\n" + "=" * 70)


def print_env_example(private_path: Path, public_path: Path) -> None:
    """Print example environment configuration."""
    print("\n" + "-" * 70)
    print("Environment Configuration")
    print("-" * 70)
    print("\nOption 1 - File paths (recommended for local development):")
    print(f"  AUTH_PRIVATE_KEY_PATH={private_path.absolute()}")
    print(f"  AUTH_PUBLIC_KEY_PATH={public_path.absolute()}")
    print("\nOption 2 - Base64 encoded (recommended for containers/cloud):")
    print("  Run with --base64 flag to get base64 encoded keys")
    print("\nAlso set:")
    print("  AUTH_ALGORITHM=RS256")
    print("-" * 70)


def main():
    parser = argparse.ArgumentParser(
        description="Generate RSA key pair for JWT RS256 signing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=Path,
        default=Path("keys"),
        help="Directory to save keys (default: ./keys)"
    )
    parser.add_argument(
        "--key-size", "-s",
        type=int,
        default=2048,
        choices=[2048, 4096],
        help="RSA key size in bits (default: 2048)"
    )
    parser.add_argument(
        "--base64", "-b",
        action="store_true",
        help="Also output keys as base64 for environment variables"
    )
    parser.add_argument(
        "--prefix", "-p",
        type=str,
        default="jwt",
        help="Filename prefix for key files (default: jwt)"
    )

    args = parser.parse_args()

    print(f"\nGenerating {args.key_size}-bit RSA key pair...")
    private_pem, public_pem = generate_rsa_keys(args.key_size)

    print(f"Saving keys to {args.output_dir}/...")
    private_path, public_path = save_keys(
        private_pem,
        public_pem,
        args.output_dir,
        args.prefix
    )

    print(f"\n  Private key: {private_path}")
    print(f"  Public key:  {public_path}")

    print_env_example(private_path, public_path)

    if args.base64:
        print_base64_keys(private_pem, public_pem)

    # Security reminder
    print("\n" + "!" * 70)
    print("SECURITY REMINDER")
    print("!" * 70)
    print("- Add 'keys/' to your .gitignore file")
    print("- Never commit private keys to version control")
    print("- Rotate keys periodically (every 90 days recommended)")
    print("- Use different keys for each environment")
    print("!" * 70 + "\n")

    # Check .gitignore
    gitignore_path = Path(".gitignore")
    if gitignore_path.exists():
        gitignore_content = gitignore_path.read_text()
        if "keys/" not in gitignore_content and "keys" not in gitignore_content:
            print("WARNING: 'keys/' is not in .gitignore!")
            response = input("Add 'keys/' to .gitignore? [Y/n]: ")
            if response.lower() != 'n':
                with open(gitignore_path, 'a') as f:
                    f.write("\n# JWT RSA keys\nkeys/\n*.pem\n")
                print("Added 'keys/' to .gitignore")


if __name__ == "__main__":
    main()

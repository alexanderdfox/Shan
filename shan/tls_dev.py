"""Localhost TLS certificate for `shan serve` (dev only)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def cert_dir(web_root: Path) -> Path:
    return web_root / ".shan-dev-tls"


def _openssl_cert(store: Path) -> tuple[Path, Path]:
    openssl = shutil.which("openssl")
    if not openssl:
        raise RuntimeError(
            "HTTPS dev server needs OpenSSL to create a localhost certificate.\n"
            "  Install OpenSSL, or run: python3 -m shan serve --http-only"
        )

    cert = store / "localhost.pem"
    key = store / "localhost-key.pem"
    subj = "/CN=localhost"
    cmd = [
        openssl,
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-keyout",
        str(key),
        "-out",
        str(cert),
        "-days",
        "825",
        "-nodes",
        "-subj",
        subj,
    ]
    cmd.extend(["-addext", "subjectAltName=DNS:localhost,DNS:127.0.0.1,IP:127.0.0.1"])
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        cmd = [
            openssl,
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-keyout",
            str(key),
            "-out",
            str(cert),
            "-days",
            "825",
            "-nodes",
            "-subj",
            subj,
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            err = (e.stderr or e.stdout or str(e)).strip()
            raise RuntimeError(f"OpenSSL failed to create dev certificate:\n  {err}") from e

    if not cert.is_file() or not key.is_file():
        raise RuntimeError("certificate generation did not produce expected files")
    try:
        cert.chmod(0o644)
        key.chmod(0o600)
    except OSError:
        pass
    return cert, key


def _mkcert_cert(store: Path) -> tuple[Path, Path] | None:
    mkcert = shutil.which("mkcert")
    if not mkcert:
        return None
    cert = store / "mkcert-localhost.pem"
    key = store / "mkcert-localhost-key.pem"
    if not (cert.is_file() and key.is_file()):
        subprocess.run([mkcert, "-install"], capture_output=True, text=True)
        r = subprocess.run(
            [
                mkcert,
                "-cert-file",
                str(cert),
                "-key-file",
                str(key),
                "localhost",
                "127.0.0.1",
                "::1",
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            err = (r.stderr or r.stdout or "mkcert failed").strip()
            raise RuntimeError(f"mkcert failed:\n  {err}")
    if not cert.is_file() or not key.is_file():
        return None
    return cert, key


def ensure_localhost_cert(store: Path) -> tuple[Path, Path]:
    """Return (cert_pem, key_pem), generating a trusted-friendly cert if possible."""
    store.mkdir(parents=True, exist_ok=True)
    cert = store / "localhost.pem"
    key = store / "localhost-key.pem"
    if cert.is_file() and key.is_file():
        return cert, key

    mk = _mkcert_cert(store)
    if mk is not None:
        return mk

    return _openssl_cert(store)


def trust_localhost_cert(cert_pem: Path) -> tuple[bool, str]:
    """
    Try to add the dev CA/cert to the OS trust store (best effort).
    Returns (success, human-readable status).
    """
    if not cert_pem.is_file():
        return False, f"certificate not found: {cert_pem}"

    if shutil.which("mkcert") and "mkcert-localhost" in cert_pem.name:
        return True, "mkcert certificate (usually trusted after mkcert -install)"

    if sys.platform == "darwin":
        return _trust_cert_darwin(cert_pem)
    if sys.platform == "linux":
        return _trust_cert_linux(cert_pem)
    return False, f"import {cert_pem} into your OS trust store manually"


def _trust_cert_darwin(cert_pem: Path) -> tuple[bool, str]:
    security = shutil.which("security")
    if not security:
        return False, "macOS security tool not found"

    keychains = [
        Path.home() / "Library/Keychains/login.keychain-db",
        Path.home() / "Library/Keychains/login.keychain",
    ]
    keychain = next((k for k in keychains if k.exists()), keychains[0])

    r = subprocess.run(
        [
            security,
            "add-trusted-cert",
            "-d",
            "-r",
            "trustRoot",
            "-p",
            "ssl",
            "-p",
            "basic",
            "-k",
            str(keychain),
            str(cert_pem.resolve()),
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode == 0:
        return True, f"trusted in login keychain ({keychain.name})"
    err = (r.stderr or r.stdout or "security add-trusted-cert failed").strip()
    return False, err


def _trust_cert_linux(cert_pem: Path) -> tuple[bool, str]:
    for dest in (
        Path("/usr/local/share/ca-certificates/shan-dev-localhost.crt"),
        Path("/etc/ca-certificates/trust-source/anchors/shan-dev-localhost.crt"),
    ):
        parent = dest.parent
        if not parent.exists():
            continue
        try:
            shutil.copy(cert_pem, dest)
            update = shutil.which("update-ca-certificates") or shutil.which("update-ca-trust")
            if update:
                subprocess.run([update], check=False, capture_output=True)
            return True, f"installed to {dest} (may need sudo)"
        except OSError:
            continue
    return False, (
        f"run: sudo cp {cert_pem} /usr/local/share/ca-certificates/shan-dev-localhost.crt "
        "&& sudo update-ca-certificates"
    )


def ssl_context(cert_pem: Path, key_pem: Path) -> "ssl.SSLContext":
    import ssl

    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if hasattr(ssl, "TLSVersion"):
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(str(cert_pem), str(key_pem))
    try:
        ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:!aNULL:!MD5:!DSS")
    except ssl.SSLError:
        pass
    return ctx

"""Authenticode-sign the frozen antennaknobs workbench.

A verbatim copy of momwire's ``scripts/eznec_freeze/sign.py`` (issue #1349):
the environment names are kept as ``MOMWIRE_SIGN_*`` on purpose, so the
signing steps of momwire's ``eznec-dropin.yml`` carry over to
``freeze-windows.yml`` here unchanged and the two lanes cannot drift on the
one thing that must not drift. The identity, the timestamping and the
verification are the same code signing the same way.

Signing is OPT-IN and driven entirely by the environment, so an unconfigured
build behaves exactly as it always has — unsigned, no signtool required, and
runnable on a box (or a Linux runner) that has no Windows SDK at all:

Two signing identities exist, and UNSET-BOTH IS THE OFF SWITCH — with
neither variable set the build is unsigned and no signtool is required:

``MOMWIRE_SIGN_METADATA``
    Path to an Azure Artifact Signing metadata file (account, certificate
    profile, region endpoint).  Requires ``MOMWIRE_SIGN_DLIB`` — the path to
    ``Azure.CodeSigning.Dlib.dll`` from the Microsoft.ArtifactSigning.Client
    NuGet package — and the three ``AZURE_*`` credential variables signtool's
    dlib reads.  WINS over ``MOMWIRE_SIGN_SHA1`` when both are set, so a tag
    build cannot accidentally sign with a rehearsal certificate left in the
    environment.
``MOMWIRE_SIGN_SHA1``
    SHA-1 thumbprint of a code-signing certificate in the Windows certificate
    store — the self-signed rehearsal, or a hardware token.
``MOMWIRE_SIGN_TIMESTAMP_URL``
    RFC-3161 timestamp authority.  Defaults to DigiCert's; CI sets Microsoft's
    on every path so the canary exercises the TSA the release depends on.
``MOMWIRE_SIGN_ALLOW_UNTRUSTED``
    ``1`` downgrades the ``signtool verify /pa`` chain check from a gate to a
    printed note.  This is for the SELF-SIGNED REHEARSAL only: a self-signed
    certificate cannot chain to a trusted root, so /pa always fails, and
    without this the rehearsal could never pass.  Leave it unset for a real
    certificate — then a broken chain correctly fails the build.

    It covers the CHAIN and nothing else.  The timestamp assertion runs on
    every path, waiver or not (momwire#755): a missing countersignature is
    not a fact about whether the certificate is trusted, and the rehearsal
    exists precisely to exercise the parts of signing that a self-signed
    certificate can still exercise.
``SIGNTOOL``
    Explicit path to ``signtool.exe``, skipping the Windows Kits search.

Why a store thumbprint and not a .pfx for the local seam: since June 2023 the
CA/Browser Forum baseline requires code-signing keys to live on FIPS-140-2
Level 2 hardware, so there is no importable key file to point at any more.  A
store thumbprint is what both a hardware token and a self-signed rehearsal
cert present, which is why the rehearsal exercises the real code path rather
than a stand-in.  A cloud-HSM CA (Azure Artifact Signing here) identifies the
key through ``/dlib`` plus a metadata file instead — `_identity_args()` is
the one CA-specific stanza, and the rest holds for both.
"""

from __future__ import annotations

import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path

DEFAULT_TIMESTAMP_URL = "http://timestamp.digicert.com"

# Newest first; the Kits layout gained the versioned `bin\<sdk>\` level in the
# Windows 10 SDK, and the flat `bin\x64\` form is the older fallback.
_KITS_GLOBS = (
    r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe",
    r"C:\Program Files\Windows Kits\10\bin\*\x64\signtool.exe",
    r"C:\Program Files (x86)\Windows Kits\10\bin\x64\signtool.exe",
)


class SigningError(RuntimeError):
    """Signing was asked for and could not be delivered."""


def _version_key(path: Path) -> tuple[int, ...]:
    """Sort key for a Kits path, so `10.0.26100.0` beats `10.0.19041.0`."""
    for part in path.parts:
        if part.replace(".", "").isdigit() and "." in part:
            return tuple(int(n) for n in part.split("."))
    return (0,)


def find_signtool() -> Path:
    """Locate ``signtool.exe``, or explain what to install."""
    explicit = os.environ.get("SIGNTOOL")
    if explicit:
        if not Path(explicit).is_file():
            raise SigningError(f"SIGNTOOL points at no file: {explicit}")
        return Path(explicit)

    on_path = shutil.which("signtool")
    if on_path:
        return Path(on_path)

    found: list[Path] = []
    for pattern in _KITS_GLOBS:
        root, _, tail = pattern.partition("*")
        base = Path(root)
        if not tail:
            if base.is_file():
                found.append(base)
            continue
        if base.is_dir():
            found.extend(base.glob("*" + tail))
    if found:
        return max(found, key=_version_key)

    raise SigningError(
        "signtool.exe not found. It ships with the Windows SDK component "
        '"Signing Tools for Desktop Apps"; set SIGNTOOL=<path> to override. '
        "(It is preinstalled on GitHub's windows-latest runners.)"
    )


def certificate_table_size(path: Path) -> int:
    """Bytes in the PE Attribute Certificate Table — 0 when unsigned.

    Parsed here rather than shelled out to ``signtool verify`` because this
    answers the one question a build can always assert: did a signature
    actually get ATTACHED?  ``verify`` additionally judges the trust chain,
    which a self-signed rehearsal cert must fail by construction.
    """
    # Header reads only — everything needed sits within 176 bytes of the PE
    # signature, and this primitive runs once per shipped executable, so
    # slurping a multi-MB launcher per call would be all waste.
    with path.open("rb") as f:
        f.seek(0x3C)
        pe = struct.unpack("<I", f.read(4))[0]
        f.seek(pe)
        head = f.read(176)
    if head[:4] != b"PE\0\0":
        raise SigningError(f"not a PE image: {path}")
    magic = struct.unpack_from("<H", head, 24)[0]
    # Optional header: 24 bytes of standard fields, then 112 (PE32+) or 96
    # (PE32) more before the data directories begin.
    ddir = 24 + (112 if magic == 0x20B else 96)
    n_dirs = struct.unpack_from("<I", head, ddir - 4)[0]
    if n_dirs < 5:  # index 4 is the certificate table; absent entirely
        return 0
    _rva, size = struct.unpack_from("<II", head, ddir + 4 * 8)
    return size


def has_signature(path: Path) -> bool:
    return certificate_table_size(path) > 0


def _identity_args() -> list[str]:
    """How signtool should find the private key -- the one CA-specific stanza.

    Two modes, chosen by which variable is set:

    ``MOMWIRE_SIGN_METADATA``
        Azure Artifact Signing.  The key never leaves the service, so there
        is no thumbprint and nothing in the local store; signtool reaches it
        through the dlib named by ``MOMWIRE_SIGN_DLIB`` and a metadata file
        naming the account, the certificate profile, and the REGION endpoint.
        A region/endpoint mismatch surfaces as 403 plus a SignerSign()
        failure, not as anything mentioning regions.
    ``MOMWIRE_SIGN_SHA1``
        A certificate in the Windows store -- the self-signed rehearsal, or
        a hardware token.

    Azure wins when both are set, so a tag build cannot accidentally sign
    with a rehearsal certificate left in the environment.
    """
    metadata = os.environ.get("MOMWIRE_SIGN_METADATA")
    if metadata:
        dlib = os.environ.get("MOMWIRE_SIGN_DLIB")
        if not dlib:
            raise SigningError(
                "MOMWIRE_SIGN_METADATA is set but MOMWIRE_SIGN_DLIB is not. "
                "The Azure mode needs both: the dlib is "
                "Azure.CodeSigning.Dlib.dll (x64) from the "
                "Microsoft.ArtifactSigning.Client NuGet package."
            )
        return ["/dlib", dlib, "/dmdf", metadata]
    return ["/sha1", os.environ["MOMWIRE_SIGN_SHA1"]]


def sign(paths: list[Path]) -> None:
    """Sign ``paths`` in one signtool invocation, then assert the result."""
    if sys.platform != "win32":
        trigger = (
            "MOMWIRE_SIGN_METADATA"
            if os.environ.get("MOMWIRE_SIGN_METADATA")
            else "MOMWIRE_SIGN_SHA1"
        )
        raise SigningError(
            f"Authenticode signing was requested ({trigger} is set) "
            f"but this is {sys.platform}, not Windows."
        )

    signtool = find_signtool()
    timestamp = os.environ.get("MOMWIRE_SIGN_TIMESTAMP_URL", DEFAULT_TIMESTAMP_URL)
    thumbprint = os.environ.get("MOMWIRE_SIGN_SHA1")
    cmd = [
        str(signtool),
        "sign",
        "/fd",
        "SHA256",
        # Timestamping is not optional: without it every signature already in
        # the wild goes invalid the day the certificate expires.
        "/tr",
        timestamp,
        "/td",
        "SHA256",
        "/v",
        *_identity_args(),
        *(str(p) for p in paths),
    ]
    printable = ["<thumbprint>" if thumbprint and a == thumbprint else a for a in cmd]
    print("+", " ".join(printable), flush=True)
    if subprocess.run(cmd).returncode != 0:
        raise SigningError("signtool sign failed")

    for path in paths:
        size = certificate_table_size(path)
        if size == 0:
            raise SigningError(
                f"signtool reported success but {path} carries no signature"
            )
        print(f"signed: {path.name} ({size} cert bytes)")

    _verify(signtool, paths)


def _verify(signtool: Path, paths: list[Path]) -> None:
    """Two questions about a signature, and only ONE of them is waivable.

    ONE ``signtool verify /pa /v`` answers both, which is why they share a
    call: the exit code carries the chain verdict, and the verbose output
    carries the timestamp verdict, independently of it.

    The chain is what ``MOMWIRE_SIGN_ALLOW_UNTRUSTED`` forgives, and it has
    to: a self-signed rehearsal certificate cannot chain to a trusted root, so
    ``/pa`` always fails there and the rehearsal could never pass.

    The TIMESTAMP is a different question and the waiver was never meant to
    reach it — this module's own docstring scopes it to "the ``signtool verify
    /pa`` chain check" (momwire#755). Trusted Signing issues very short-lived
    certificates (v0.44.0's leaf was valid 72 hours), so the RFC-3161
    countersignature is the only thing keeping a shipped signature valid past
    the end of the week. A build that stopped timestamping would sign, print
    ``chain verified``, pass every check on the build day, and begin failing
    Smart App Control about three days later on end-user machines, with
    nothing in the log naming the cause.
    """
    lenient = os.environ.get("MOMWIRE_SIGN_ALLOW_UNTRUSTED") == "1"
    cmd = [str(signtool), "verify", "/pa", "/v", *(str(p) for p in paths)]
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    output = (proc.stdout or "") + (proc.stderr or "")
    print(output, end="", flush=True)

    _assert_timestamped(output, paths)

    if proc.returncode == 0:
        print("chain verified")
        return
    if lenient:
        print(
            "chain NOT verified — expected, MOMWIRE_SIGN_ALLOW_UNTRUSTED=1 "
            "(a self-signed rehearsal certificate has no trusted root). "
            "The signature itself is attached and was asserted above, and the "
            "timestamp was asserted independently."
        )
        return
    raise SigningError(
        "signtool verify /pa failed. For a self-signed rehearsal set "
        "MOMWIRE_SIGN_ALLOW_UNTRUSTED=1; for a real certificate this is a "
        "genuine chain failure."
    )


# What signtool /v prints per file that carries a countersignature. Read from
# the SAME run that produces the chain verdict, because signtool emits this
# line even when the chain then fails — verified on the rehearsal path, whose
# self-signed root always fails /pa and which still printed
# "The signature is timestamped: Mon Aug 31 13:11:03 2026" for both binaries
# (momwire#755, canary run 33395335907).
_TIMESTAMPED_LINE = "the signature is timestamped:"


def _assert_timestamped(output: str, paths: list[Path]) -> None:
    """Every binary must carry an RFC-3161 countersignature. Not waivable.

    Counted out of signtool's own verbose output rather than asked of
    ``Get-AuthenticodeSignature``, which was the first attempt and is WRONG
    here: PowerShell leaves ``TimeStamperCertificate`` empty when the signing
    chain is untrusted, so it reported "no timestamp" for correctly stamped
    rehearsal binaries. Whatever answers this has to answer it independently
    of chain trust, and signtool's output does.
    """
    seen = output.lower().count(_TIMESTAMPED_LINE)
    if seen >= len(paths):
        print(f"timestamped: all {len(paths)} signature(s) countersigned")
        return
    raise SigningError(
        f"signed WITHOUT an RFC-3161 timestamp: signtool reported {seen} "
        f"timestamped signature(s) for {len(paths)} binaries. The signing "
        "certificate is short-lived, so an unstamped signature verifies today "
        "and starts failing Smart App Control when it expires — days later, "
        "on users' machines. Check the TSA at MOMWIRE_SIGN_TIMESTAMP_URL was "
        "reachable. NOT waivable by MOMWIRE_SIGN_ALLOW_UNTRUSTED, which "
        "covers the chain only (momwire#755)."
    )


def sign_if_configured(paths: list[Path]) -> bool:
    """Sign when an identity is configured; otherwise say so and skip."""
    if not (
        os.environ.get("MOMWIRE_SIGN_METADATA") or os.environ.get("MOMWIRE_SIGN_SHA1")
    ):
        print("unsigned build (neither MOMWIRE_SIGN_METADATA nor _SHA1 set)")
        return False
    sign(paths)
    return True

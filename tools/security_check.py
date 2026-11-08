#!/usr/bin/env python3
"""Independent, offline CI safeguard for tracked files.

This implementation is project-local. It follows the security policy in the
private ai-engineering-skills repository but does not import its scanner.
Never print candidate secret values.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

DENIED_SUFFIXES = frozenset({".pem", ".key", ".p12", ".pfx"})
SAFE_ENV_FILENAMES = frozenset({".env.example", ".env.sample"})
KEY_HEADER = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")
ASSIGNMENT = re.compile(
    r"(?i)(?<![\w-])"
    r"(?:password|passwd|secret|api[_-]?key|access[_-]?token|"
    r"auth[_-]?token|client[_-]?secret)"
    r"\s*[:=]\s*['\"]?([^\s'\",;#}]+)"
)
INTERNAL_ENDPOINT = re.compile(
    r"(?i)https?://(?:localhost|127\.0\.0\.1|[\w.-]+\.(?:internal|local))(?::\d+)?(?:/|\b)"
)
PLACEHOLDER = re.compile(
    r"(?i)^(?:example|sample|dummy|placeholder|changeme|replace_me|"
    r"test|none|null|your[_-].*|os\.environ.*|os\.getenv.*|"
    r"process\.env.*|\$\{\{.*|secrets\..*|vars\..*)$"
)
MAX_INSPECT_BYTES = 1_000_000


def sensitive_filename(path: str) -> bool:
    basename = Path(path).name.lower()
    if basename in SAFE_ENV_FILENAMES:
        return False
    return (
        basename == ".env"
        or basename.startswith(".env.")
        or basename in {"id_rsa", "id_ed25519"}
        or Path(basename).suffix in DENIED_SUFFIXES
    )


def scan_line(line: str) -> tuple[str, ...]:
    """Return issue categories without returning the line or matched value."""
    findings: list[str] = []
    if KEY_HEADER.search(line):
        findings.append("private-key-header")
    match = ASSIGNMENT.search(line)
    if match:
        candidate = match.group(1)
        if not PLACEHOLDER.fullmatch(candidate):
            findings.append("credential-assignment")
    if INTERNAL_ENDPOINT.search(line):
        findings.append("internal-endpoint-review")
    return tuple(findings)


def tracked_paths() -> list[str]:
    output = subprocess.check_output(["git", "ls-files", "-z"], stderr=subprocess.DEVNULL)
    return [name.decode("utf-8", "replace") for name in output.split(b"\0") if name]


def scan_repository() -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    for path in tracked_paths():
        if sensitive_filename(path):
            findings.append((path, 0, "prohibited-filename"))
            continue
        try:
            data = Path(path).read_bytes()
        except OSError:
            findings.append((path, 0, "unreadable-file"))
            continue
        if len(data) > MAX_INSPECT_BYTES:
            findings.append((path, 0, "oversize-file-review"))
            continue
        if b"\0" in data:
            continue
        for line_number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            for category in scan_line(line):
                findings.append((path, line_number, category))
    return findings


def main() -> int:
    try:
        findings = scan_repository()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Security scan could not run: {type(exc).__name__}", file=sys.stderr)
        return 2
    blockers = 0
    reviews = 0
    for path, line_number, reason in findings:
        if reason.endswith("-review"):
            reviews += 1
            level = "REVIEW"
        else:
            blockers += 1
            level = "BLOCK"
        print(f"{level}: {path}:{line_number} [{reason}]")
    print(f"Security scan complete: {blockers} blocker(s), {reviews} review item(s).")
    return 1 if blockers else 0


if __name__ == "__main__":
    raise SystemExit(main())

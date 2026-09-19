"""
V.E.D.A. Authoritative Version & Build Configuration
Single source of truth for versioning, build number, release channel,
and semantic versioning helpers.
"""

from typing import Tuple

VERSION = "1.0.2"
BUILD = 1002
RELEASE_CHANNEL = "Stable"
APP_TITLE = f"V.E.D.A. {VERSION}"


def parse_semver(version_str: str) -> Tuple[int, int, int]:
    """
    Parses a version string into a (major, minor, patch) integer tuple.
    Handles 'v' or 'V' prefixes, pre-release tags, build metadata.
    Example: 'v1.0.1' -> (1, 0, 1), '2.4.0-rc1' -> (2, 4, 0)
    """
    if not version_str:
        return (0, 0, 0)
    clean = str(version_str).strip().lstrip("vV")
    core = clean.split("-")[0].split("+")[0]
    parts = core.split(".")
    nums = []
    for p in parts[:3]:
        try:
            nums.append(int(p))
        except ValueError:
            nums.append(0)
    while len(nums) < 3:
        nums.append(0)
    return (nums[0], nums[1], nums[2])


def compare_versions(v1: str, v2: str) -> int:
    """
    Compares two semantic version strings.
    Returns:
       1 if v1 > v2
       0 if v1 == v2
      -1 if v1 < v2
    """
    p1 = parse_semver(v1)
    p2 = parse_semver(v2)
    if p1 > p2:
        return 1
    elif p1 < p2:
        return -1
    return 0


def is_newer_version(remote: str, local: str = VERSION) -> bool:
    """Returns True if the remote version is strictly newer than local."""
    return compare_versions(remote, local) > 0

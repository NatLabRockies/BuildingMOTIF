import os
import re
from pathlib import Path
from typing import Optional

import requests
import tomlkit

# Version pattern from https://peps.python.org/pep-0440/#appendix-b-parsing-version-strings-with-regular-expressions
VERSION_PATTERN = r"""
    v?
    (?:
        (?:(?P<epoch>[0-9]+)!)?                           # epoch
        (?P<release>[0-9]+(?:\.[0-9]+)*)                  # release segment
        (?P<pre>                                          # pre-release
            [-_\.]?
            (?P<pre_l>alpha|a|beta|b|preview|pre|c|rc)
            [-_\.]?
            (?P<pre_n>[0-9]+)?
        )?
        (?P<post>                                         # post release
            (?:-(?P<post_n1>[0-9]+))
            |
            (?:
                [-_\.]?
                (?P<post_l>post|rev|r)
                [-_\.]?
                (?P<post_n2>[0-9]+)?
            )
        )?
        (?P<dev>                                          # dev release
            [-_\.]?
            (?P<dev_l>dev)
            [-_\.]?
            (?P<dev_n>[0-9]+)?
        )?
    )
    (?:\+(?P<local>[a-z0-9]+(?:[-_\.][a-z0-9]+)*))?       # local version
"""
_regex = re.compile(
    r"^\s*" + VERSION_PATTERN + r"\s*$",
    re.VERBOSE | re.IGNORECASE,
)


def extract_version_components(version_str: str) -> dict:
    """Splits a version string into its components"""
    match = _regex.match(version_str)
    if match is not None:
        return match.groupdict()
    raise Exception(f"Failed to extract components from {version_str}")


def get_release_list(index_url: str, project_name: str) -> list[str]:
    """Gets a list of release versions from a pypi compliant index"""
    index_url = index_url.rstrip("/")
    response = requests.get(index_url + "/pypi/" + project_name + "/json")
    response.raise_for_status()
    body = response.json()
    releases = body["releases"].keys()
    return list(releases)


def components_to_version(components: dict) -> str:
    """Takes the components of a version and combines them into a string"""
    for key in components.keys():
        if components[key] is None:
            components[key] = ""
    return (
        components["epoch"]
        + components["release"]
        + components["pre"]
        + components["post"]
        + components["dev"]
        + components["local"]
    )


def increment_development_component(
    version_str: str, increment_components: bool = False
) -> str:
    """Increment develop component, and optionally increment the least
    signification version component if the current version string does
    not contain a development component."""
    version_groups = extract_version_components(version_str)

    if version_groups["dev_n"]:
        dev_n = version_groups["dev_n"]
        dev = version_groups["dev"]
        dev_version = int(version_groups["dev_n"])
        dev = dev[: -1 * len(dev_n)]
        dev = dev + str(dev_version + 1)
        version_groups["dev"] = dev
    else:
        if increment_components:
            if version_groups["post_n2"]:
                post_n2 = version_groups["post_n2"]
                post = version_groups["post"]
                post = post[: -1 * len(post_n2)]
                post = post + str(int(post_n2) + 1)
                version_groups["post"] = post
            elif version_groups["post_n1"]:
                post_n1 = version_groups["post_n1"]
                post = version_groups["post"]
                post = post[1 + len(post_n1) :]
                post = "-" + str(int(post_n1) + 1) + post
                version_groups["post"] = post
            elif version_groups["pre_n"]:
                pre_n = version_groups["pre_n"]
                pre = version_groups["pre"]
                pre = pre[: -1 * len(pre_n)]
                pre = pre + str(int(pre_n) + 1)
                version_groups["pre"] = pre
            else:
                release = version_groups["release"]
                release_components = release.split(".")
                release_components[-1] = str(int(release_components[-1]) + 1)
                version_groups["release"] = ".".join(release_components)
        version_groups["dev"] = ".dev1"

    return components_to_version(version_groups)


def version_greater_than(version_a: Optional[str], version_b: Optional[str]) -> bool:
    """Compare if version a is strictly greater than version b"""
    if version_a is None:
        return False
    if version_b is None:
        return True

    a_components = extract_version_components(version_a)
    b_components = extract_version_components(version_b)

    if a_components["release"]:
        if b_components["release"]:
            a_release_parts = a_components["release"].split(".")
            b_release_parts = b_components["release"].split(".")
            for i in range(0, min(len(a_release_parts), len(b_release_parts))):
                a = int(a_release_parts[i])
                b = int(b_release_parts[i])
                if a > b:
                    return True
                elif a < b:
                    return False
        else:
            return True

    if a_components["pre_n"]:
        if b_components["pre_n"]:
            a = int(a_components["pre_n"])
            b = int(b_components["pre_n"])
            if a > b:
                return True
            elif a < b:
                return False
        else:
            return True
    elif b_components["pre_n"]:
        return False

    if a_components["post_n1"]:
        if b_components["post_n1"]:
            a = int(a_components["post_n1"])
            b = int(b_components["post_n1"])
            if a > b:
                return True
            elif a < b:
                return False
        else:
            return True
    elif b_components["post_n1"]:
        return False

    if a_components["post_n2"]:
        if b_components["post_n2"]:
            a = int(a_components["post_n2"])
            b = int(b_components["post_n2"])
            if a > b:
                return True
            elif a < b:
                return False
        else:
            return True
    elif b_components["post_n2"]:
        return False

    if a_components["dev_n"]:
        if b_components["dev_n"]:
            a = int(a_components["dev_n"])
            b = int(b_components["dev_n"])
            if a > b:
                return True
            elif a < b:
                return False
        else:
            return True
    elif b_components["dev_n"]:
        return False

    return False


def get_next_dev_version(local_version: str, release_list: list[str]) -> str:
    """Compare local_version to list of released versions.
    If there are already dev builds it will incrment the latest of those builds.
    If there are not, it will create the version for the first dev build.
    """
    local_version_components = extract_version_components(local_version)

    recent_release = None
    for release in release_list:
        components = extract_version_components(release)
        match: bool = True
        for key, value in local_version_components.items():
            if key not in ["dev", "dev_n", "dev_l"]:
                if value != components[key]:
                    match = False
        if match and version_greater_than(release, recent_release):
            recent_release = release

    if (
        version_greater_than(recent_release, local_version)
        and recent_release is not None
    ):
        return increment_development_component(recent_release)
    else:
        if local_version_components["dev_n"]:
            return local_version
        else:
            return increment_development_component(local_version)


# Read pyproject.toml
pyproject_path = Path(os.path.abspath(__file__)).parents[1] / "pyproject.toml"
pyproject_contents = tomlkit.load(pyproject_path.open("r"))

# Query release list
release_list = get_release_list(
    os.environ.get("PYPI_URL", "https://pypi.org/"),
    pyproject_contents["project"]["name"].lower(),
)
# Get current version from pyproject.toml
version = pyproject_contents["project"]["version"]

# Determine name for dev release
next_dev_version = get_next_dev_version(version, release_list)
print(next_dev_version)
pyproject_contents["project"]["version"] = next_dev_version

# Update pyproject.toml
tomlkit.dump(pyproject_contents, pyproject_path.open("w"))

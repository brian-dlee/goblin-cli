#!/bin/python

import argparse
import dataclasses
import pathlib
import re
import sys
import subprocess
import tempfile
import urllib.parse
import urllib.request
import typing


VERSION_LATEST = "latest"


def is_pinned_version(v: str):
    """
    Returns true for pinned package identifiers. Currently this includes
    semantic versions including 3 numbers and something that looks like
    a commit hash.
    """

    return (
        re.search(r"^[a-f0-9]{36,}$", v) is not None
        or re.search(r"^v?[0-9]+\.[0-9]+\.[0-9]+$", v) is not None
    )


@dataclasses.dataclass
class LockFileEntry:
    package: str
    desired_version: str
    actual_version: str


def read_lock_file_line(line: str) -> LockFileEntry | None:
    """
    Parse a line out of the lock file. This includes the package
    name, the desired version, and the actual version. The
    the difference between the desired version and actual version
    is in cases where wildcards or patterns are used to indicate
    which package version to install.
    """

    if len(line.strip()) == 0:
        return None

    parts = line.strip().split("\t")

    if len(parts) != 3:
        print("Invalid lock file entry:", line, file=sys.stderr)
        return None

    package, desired_version, actual_version = parts

    return LockFileEntry(
        package=package,
        desired_version=desired_version,
        actual_version=actual_version,
    )


def read_lock_file(p: pathlib.Path) -> typing.Generator[LockFileEntry, None, None]:
    """
    Read every line from the target lock file and return a sequence of
    LockFileEntry objects.
    """

    with p.open("r") as fp:
        for line in fp:
            if parsed := read_lock_file_line(line):
                yield parsed


def write_lock_file(p: pathlib.Path, entries: list[LockFileEntry]) -> None:
    """
    Given a new list of lock file entries, rewrite the lock file at
    the specified path.
    """

    with p.open("w") as fp:
        for entry in entries:
            fp.write(
                f"{entry.package}\t{entry.desired_version}\t{entry.actual_version}\n"
            )


@dataclasses.dataclass
class GoblinShellScriptContents:
    version: str | None


def parse_goblin_shell_script(content: str) -> GoblinShellScriptContents:
    """
    This is the especially hacky bit. All I'm getting right now is a
    shell script from goblin.run, so I opted to parse out some information
    from this script to power my CLI. Currently I only need to
    extract the resolved version.
    """

    in_start = False

    version: str | None = None

    for line in content.splitlines():
        if line.startswith("start() {"):
            in_start = True
            continue

        if in_start and line.strip().startswith("version="):
            version = line.strip().split("=", maxsplit=2)[1].strip("'\"")
            continue

        if in_start and line.startswith("}"):
            in_start = False

    return GoblinShellScriptContents(
        version=version,
    )


@dataclasses.dataclass
class GoblinPackage:
    src: str
    package_name: str
    version: str


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--no-fetch", dest="fetch", action="store_false")
    args = parser.parse_args()

    flag_check: bool = args.check
    flag_fetch: bool = args.fetch

    goblin_file = pathlib.Path.cwd().joinpath(".goblin")
    goblin_lock_file = goblin_file.parent.joinpath(".goblin.lock")

    if not goblin_file.exists():
        exit(f"File not found: {goblin_file}")

    if not goblin_lock_file.exists():
        goblin_lock_file.touch()

    env: dict[str, str] = {"PREFIX": "/usr/local/bin"}
    packages: list[GoblinPackage] = []

    with goblin_file.open("r") as fp:
        for line in fp:
            # ignore blank lines and commits in the .goblin file
            if len(line.strip()) == 0 or line.strip().startswith("#"):
                continue

            # handle environment variables in the .goblin file
            # these will be injected when the shells script is invoked
            # later on
            if re.search("^[a-zA-Z_]+=", line):
                key, value = line.split("=", maxsplit=2)

                # I can't support OUT right now because it could make it
                # difficult to detect if the target binary is available
                # and cleanup old binaries if it's renamed using OUT.
                #
                # It wouldn't be a ton of work, but it could be supported.
                # I could basically just parse OUT variables and apply
                # them to the following package entry. I'd just need to
                # track the previous bin values in the lock file so I
                # can cleanup when it's changed.
                if key == "OUT":
                    print(
                        "[WARNING] Setting OUT is not currently support in the goblin file. Downloaded binaries will be named after the last path segment in the URL."
                    )
                else:
                    env[key] = value.strip()

                continue

            try:
                package_url = urllib.parse.urlparse(line)
            except Exception:
                print("Invalid URL:", line, file=sys.stderr)
                continue

            # paths always have a leading slash and that's useless to me
            package_name = package_url.path.lstrip("/")

            # if we have an @ sign in the path then we've been provided a
            # version otherwise we will assume latest
            if "@" in package_name:
                package_name, version = package_name.split("@", maxsplit=2)
            else:
                version = VERSION_LATEST

            packages.append(
                GoblinPackage(
                    src=line.strip(), package_name=package_name, version=version
                )
            )

    lock_file_contents = list(read_lock_file(goblin_lock_file))

    # PREFIX is handled as being relative to the goblin file
    # unless it's an absolute path
    install_prefix = pathlib.Path(env["PREFIX"])
    if not install_prefix.is_absolute():
        install_prefix = goblin_file.parent.joinpath(install_prefix)

    # The goblin script prompts for superuser password's even when
    # the directory can be created by the user. This prevents that
    # little nuance from surfacing. I think it's just a simple check
    # missing from the goblin shell script because it's currently
    # using -w and not trying -e or checking if the parent directory
    # is writable
    if not install_prefix.exists():
        install_prefix.mkdir(parents=True)

    # This is probably just debug output but can help confirm the
    # CLI read the environment variables correctly
    for key, value in env.items():
        if key == "PREFIX":
            print(f"\tPREFIX={install_prefix.relative_to(pathlib.Path.cwd())}")
        else:
            print(f"\t{key}={value}")

    check_status = True

    for package in packages:
        lock_file_entry_index = -1
        lock_file_entry = LockFileEntry(
            package=package.package_name,
            desired_version=package.version,
            actual_version="",
        )

        package_name_parts = package.package_name.split("/")
        org = package_name_parts[1]
        pkg = package_name_parts[2]
        log_label = f"{org}/{pkg}"

        bin = package_name_parts[-1]

        # Pin the logging prefix to 24 characters to keep things tidy
        if len(log_label) > 24:
            log_label = f"{log_label[0:24]}…"
        else:
            log_label = f"{log_label:<24}"

        # This could be fancier, but there's nothing wrong with a
        # little loop action. If a .goblin file has 50,000 entries
        # then I'd argue that's a problem
        for entry_index, entry in enumerate(lock_file_contents):
            if entry.package == package.package_name:
                print(
                    f"[{log_label}] Found lock file entry for '{package.package_name}':",
                    (entry.desired_version, entry.actual_version),
                )

                lock_file_entry = entry
                lock_file_entry_index = entry_index

        goblin_shell_script: str | None = None

        # If we are allowed to fetch and the version supplied is some
        # kind of pattern we are going to need to read the resolved
        # version from the API
        if flag_fetch and not is_pinned_version(package.version):
            print(f"[{log_label}] Resolving package version: {package.version}")

            try:
                goblin_shell_script = (
                    urllib.request.urlopen(package.src).read().decode("utf-8")
                )
            except Exception as e:
                print(f"[{log_label}] HTTP Request failed to '{package.src}':", e)
                continue

            assert goblin_shell_script is not None

            goblin_out = parse_goblin_shell_script(goblin_shell_script)
            resolved_version = goblin_out.version

            # This probably means the shell script changed enough that we couldn't
            # parse the version. This is brittle, but could easily be addressed by
            # some alternative API endpoint
            if resolved_version is None:
                print(
                    f"[{log_label}] [WARNING] Unable to resolve version for",
                    package.src,
                )
                continue

            print(
                f"[{log_label}] Resolved package version: {package.version} -> {resolved_version}"
            )
        else:
            print(
                f"[{log_label}] Using provided version: {package.package_name}@{package.version}"
            )

            resolved_version = package.version

        install_location = install_prefix.joinpath(bin)

        if flag_check:
            # The .goblin file speficically indicates a different version than the lock file
            if lock_file_entry.desired_version != package.version:
                print(
                    f"[{log_label}] Lock file does not match package version. Lock file version is '{lock_file_entry.desired_version}' and package version is '{package.version}'"
                )
                check_status = False
                continue

            # The .goblin file matches the lock file, but clearly it's never been installed
            # due to the missing actual_version value
            if lock_file_entry.actual_version is None:
                print(
                    f"[{log_label}] Lock file matches package version, but the lock file does not indicate a package was every installed. The desired package version is '{package.version}'"
                )
                check_status = False
                continue

            # We were allowed to fetch and there is newer version available upstream
            # It's debateable whether this is a --check failure, but since I offered --no-fetch
            # then I figured why not?
            if flag_fetch and resolved_version != lock_file_entry.actual_version:
                print(
                    f"[{log_label}] There is a newer version available. Resolved version is '{resolved_version}, but '{lock_file_entry.actual_version}' is current installed."
                )
                check_status = False
                continue

            if not install_location.exists():
                print(
                    f"[{log_label}] Binary not found: {install_location.relative_to(pathlib.Path.cwd())}"
                )
                check_status = False
                continue

            print(f"[{log_label}] Package up-to-date")
            continue

        if resolved_version == lock_file_entry.actual_version:
            if not install_location.exists():
                print(
                    f"[{log_label}] Binary not found, proceeding with install: {install_location.relative_to(pathlib.Path.cwd())}"
                )
            else:
                print(f"[{log_label}] Package already up-to-date")
                continue

        if not goblin_shell_script:
            try:
                goblin_shell_script = (
                    urllib.request.urlopen(package.src).read().decode("utf-8")
                )
            except Exception as e:
                print(f"HTTP Request failed to '{package.src}':", e)
                continue

        print(
            f"[{log_label}] Installing",
            package.src,
            f"({package.version})",
            "to",
            install_location.relative_to(pathlib.Path.cwd()),
        )

        with tempfile.NamedTemporaryFile("w+") as fp:
            assert goblin_shell_script is not None

            fp.write(goblin_shell_script)
            fp.flush()
            fp.seek(0)

            try:
                subprocess.run(
                    ["sh", fp.name],
                    check=True,
                    env={**env, "PREFIX": str(install_prefix), "OUT": bin},
                )
            except Exception as e:
                print(f"[{log_label}] Failed to install package:", e)
                continue

        lock_file_entry.actual_version = resolved_version

        # Check if our installation needed to be added to the lock file
        # or if we are updating an existing entry
        if lock_file_entry_index < 0:
            lock_file_contents.append(lock_file_entry)
        else:
            lock_file_contents[lock_file_entry_index] = lock_file_entry

    # Time to exit if this was a --check run
    if flag_check:
        exit(0 if check_status else 1)

    lock_file_contents.sort(key=lambda entry: entry.package)

    print("Writing lock file", goblin_lock_file)

    write_lock_file(goblin_lock_file, lock_file_contents)


if __name__ == "__main__":
    main()

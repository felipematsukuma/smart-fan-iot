"""Run in an isolated helper: binary archive streams never enter chat output."""

import argparse
import gzip
import json
import os
import posixpath
import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath


def safe_member(member: tarfile.TarInfo):
    path = PurePosixPath(member.name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in member.name
        or not (member.isdir() or member.isfile() or member.issym())
    ):
        raise ValueError("Archive contains an unsafe path or unsupported link")
    if member.issym():
        link = PurePosixPath(member.linkname)
        resolved = posixpath.normpath(posixpath.join(str(path.parent), member.linkname))
        if (
            not member.linkname
            or link.is_absolute()
            or "\\" in member.linkname
            or resolved in (".", "..")
            or resolved.startswith("../")
        ):
            raise ValueError("Archive link escapes its volume")
    return member


def inspect(source: Path) -> dict:
    status = source.stat()
    total = count = 0

    def failed(error):
        raise error

    for root, directories, files in os.walk(source, followlinks=False, onerror=failed):
        count += 1 + len(files)
        for name in directories + files:
            path = Path(root) / name
            if path.is_symlink():
                direct = path.parent / os.readlink(path)
                resolved = path.resolve(strict=True)
                if (
                    name in directories
                    or Path(os.readlink(path)).is_absolute()
                    or direct.is_symlink()
                    or not resolved.is_relative_to(source.resolve())
                    or not resolved.is_file()
                ):
                    raise ValueError(
                        "Only direct relative links to regular files within the volume are supported"
                    )
        total += sum(
            (Path(root) / name).stat().st_size
            for name in files
            if not (Path(root) / name).is_symlink()
        )
    return {
        "uid": status.st_uid,
        "gid": status.st_gid,
        "bytes": total,
        "members": count,
    }


def backup(source: Path):
    metadata = inspect(source)
    with (
        gzip.GzipFile(
            fileobj=sys.stdout.buffer, mode="wb", compresslevel=1
        ) as compressed,
        tarfile.open(fileobj=compressed, mode="w|", dereference=True) as archive,
    ):
        links = []
        for root, _directories, files in os.walk(source, followlinks=False):
            relative = Path(root).relative_to(source)
            archive.add(
                root, arcname=relative.as_posix(), recursive=False, filter=safe_member
            )
            for name in sorted(files):
                path = Path(root) / name
                if path.is_symlink():
                    links.append(path)
                else:
                    archive.add(
                        path,
                        arcname=path.relative_to(source).as_posix(),
                        recursive=False,
                        filter=safe_member,
                    )
        for path in links:
            status = path.lstat()
            member = tarfile.TarInfo(path.relative_to(source).as_posix())
            member.type = tarfile.SYMTYPE
            member.linkname = os.readlink(path)
            member.uid, member.gid, member.mode, member.mtime = (
                status.st_uid,
                status.st_gid,
                status.st_mode & 0o777,
                status.st_mtime,
            )
            archive.addfile(safe_member(member))
    print("SMARTFAN_VOLUME_META " + json.dumps(metadata), file=sys.stderr, flush=True)


def restore(target: Path, expected: dict):
    if any(target.iterdir()):
        raise ValueError("Restore target must be a newly created empty volume")
    if shutil.disk_usage(target).free < expected["bytes"] + 512 * 1024**2:
        raise ValueError("Insufficient Docker disk space for restore")
    directories = {}
    total = count = 0
    with tarfile.open(fileobj=sys.stdin.buffer, mode="r|gz") as archive:
        for member in archive:
            safe_member(member)
            count += 1
            total += member.size if member.isfile() else 0
            if count > expected["members"] or total > expected["bytes"]:
                raise ValueError("Archive exceeds the recorded source volume")
            if member.isdir():
                directories[str(PurePosixPath(member.name))] = member.mode & 0o755
            if member.issym():
                destination = (target / member.name).parent / member.linkname
                resolved = destination.resolve(strict=True)
                if (
                    destination.is_symlink()
                    or not resolved.is_relative_to(target.resolve())
                    or not resolved.is_file()
                ):
                    raise ValueError(
                        "Archive link must target an existing regular file within its volume"
                    )
            archive.extract(member, path=target, filter="data")
    if count != expected["members"] or total != expected["bytes"]:
        raise ValueError("Archive differs from the recorded source volume")
    for root, _, files in os.walk(target, topdown=False):
        for name in files:
            os.chown(
                Path(root) / name,
                expected["uid"],
                expected["gid"],
                follow_symlinks=False,
            )
        relative = str(PurePosixPath(Path(root).relative_to(target).as_posix()))
        os.chmod(root, directories[relative])
        os.chown(root, expected["uid"], expected["gid"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("owner", "inspect", "backup", "restore"))
    parser.add_argument("--metadata")
    args = parser.parse_args()
    if args.mode == "owner":
        status = Path("/source").stat()
        print(json.dumps({"uid": status.st_uid, "gid": status.st_gid}))
    elif args.mode == "inspect":
        print(json.dumps(inspect(Path("/source"))))
    elif args.mode == "backup":
        backup(Path("/source"))
    else:
        restore(Path("/target"), json.loads(args.metadata))


if __name__ == "__main__":
    main()

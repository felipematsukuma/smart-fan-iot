"""A malformed snapshot must never make restore reuse an original volume."""

import io
import json
import tarfile
from types import SimpleNamespace

import pytest

from tools.operations import backup, common
from tools.operations.volume_archive import backup as stream_backup
from tools.operations.volume_archive import safe_member


@pytest.mark.parametrize(
    "name,kind",
    [
        ("/outside", tarfile.REGTYPE),
        ("../outside", tarfile.REGTYPE),
        ("data/../../outside", tarfile.REGTYPE),
        ("link", tarfile.SYMTYPE),
        ("link", tarfile.LNKTYPE),
        ("pipe", tarfile.FIFOTYPE),
        ("..\\outside", tarfile.REGTYPE),
    ],
)
def test_archive_rejects_paths_and_links_before_extraction(name, kind):
    member = tarfile.TarInfo(name)
    member.type = kind
    with pytest.raises(ValueError):
        safe_member(member)


def test_snapshot_missing_archive_is_rejected_before_any_docker_write(
    tmp_path, monkeypatch
):
    root = tmp_path / "backups"
    directory = root / "snapshot"
    directory.mkdir(parents=True)
    monkeypatch.setattr(common, "BACKUPS", root)
    configuration = {
        "volumes": {"postgres_data": {"name": "smartfan-aiot_postgres_data"}},
        "services": {},
        "networks": {},
    }
    path = directory / "compose.snapshot.json"
    path.write_text(json.dumps(configuration))
    manifest = {
        "schema_version": 1,
        "source_project": "smartfan-aiot",
        "backup_id": "a" * 32,
        "compose_sha256": common.digest(path),
        "volumes": {},
        "images": {},
        "binds": {},
    }
    (directory / "manifest.json").write_text(json.dumps(manifest))
    monkeypatch.setattr(
        backup,
        "docker",
        lambda *args, **kwargs: pytest.fail(
            "Docker must not run for an incomplete snapshot"
        ),
    )
    with pytest.raises(ValueError, match="Every source volume"):
        backup.validate(directory)


def test_private_backup_root_cannot_be_restored_as_a_volume_or_escape(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(common, "BACKUPS", tmp_path / "backups")
    with pytest.raises(ValueError):
        common.bounded(tmp_path / "backups")
    with pytest.raises(ValueError):
        common.bounded(tmp_path / "backups" / ".." / "outside")


def test_only_regular_local_tar_content_is_supported():
    destination = io.BytesIO()
    with tarfile.open(fileobj=destination, mode="w") as archive:
        member = tarfile.TarInfo("./PG_VERSION")
        member.size = 2
        archive.addfile(safe_member(member), io.BytesIO(b"15"))
    destination.seek(0)
    with tarfile.open(fileobj=destination) as archive:
        assert archive.extractfile(archive.getmembers()[0]).read() == b"15"


def test_ollama_relative_manifest_link_stays_inside_its_volume():
    member = tarfile.TarInfo("manifests-v2/ollama.com/library/model/tag")
    member.type = tarfile.SYMTYPE
    member.linkname = "../../../../blobs/manifest"
    assert safe_member(member) is member
    member.linkname = "../../../../../outside"
    with pytest.raises(ValueError):
        safe_member(member)


def test_gzip_stream_archive_is_readable_without_version_specific_tar_keywords(
    tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    (source / "PG_VERSION").write_bytes(b"15")
    output = io.BytesIO()
    diagnostics = io.StringIO()
    with monkeypatch.context() as context:
        context.setattr("sys.stdout", SimpleNamespace(buffer=output))
        context.setattr("sys.stderr", diagnostics)
        stream_backup(source)
    with tarfile.open(fileobj=io.BytesIO(output.getvalue()), mode="r:gz") as archive:
        assert archive.extractfile("PG_VERSION").read() == b"15"
    assert "SMARTFAN_VOLUME_META" in diagnostics.getvalue()

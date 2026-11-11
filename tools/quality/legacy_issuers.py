"""Verify historical credentials against offline copies of the known local issuers."""

import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import tarfile
import textwrap
import time
import tomllib
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from uuid import uuid4

from influx_upgrade import PYTHON, private
from tooling import ROOT

CLIENT_IMAGE = "smartfan-python:0.14.0"
CLIENT = r"""
import json,secrets,sys,time
import httpx,psycopg2
data=json.load(sys.stdin)
def pg(password,role):
    try:
        connection=psycopg2.connect(host='legacy-pg',port=5432,user=role,password=password,dbname=data['database'],connect_timeout=3)
        connection.close()
        return True
    except psycopg2.OperationalError as error:
        if 'password authentication failed' in str(error):
            return False
        raise RuntimeError('PostgreSQL probe inconclusive') from None
positive=pg(data['pg_current'],data['pg_user'])
negative=all(not pg(secrets.token_urlsafe(48),role) for role in data['pg_roles'])
pg_results=[pg(candidate,role) for role in data['pg_roles'] for candidate in data['historical']['POSTGRES_PASSWORD']]
client=httpx.Client(base_url='http://legacy-influx:8086',timeout=4,trust_env=False)
for attempt in range(30):
    try:
        if client.get('/health').status_code==200:
            break
    except httpx.HTTPError:
        pass
    time.sleep(1)
else:
    raise RuntimeError('InfluxDB copy not ready')
def influx(token):
    status=client.get('/api/v2/me',headers={'Authorization':'Token '+token}).status_code
    if status==401:
        return False
    if status in (200,403):
        return True
    raise RuntimeError('InfluxDB probe inconclusive (HTTP '+str(status)+')')
if client.get('/api/v2/setup').json().get('allowed') is not False:
    raise RuntimeError('InfluxDB copy lacks initialized issuer data')
influx_positive=any(influx(token) for token in data['influx_current'])
influx_negative=not influx(secrets.token_urlsafe(64))
influx_results=[influx(candidate) for candidate in data['historical']['INFLUXDB_TOKEN']]
token=next(token for token in data['influx_current'] if influx(token))
users_response=client.get('/api/v2/users',params={'limit':100},headers={'Authorization':'Token '+token})
users_response.raise_for_status()
users=users_response.json()['users']
if not users or len(users)>=100:
    raise RuntimeError('InfluxDB user audit scope incomplete')
def signin(username,password):
    with httpx.Client(base_url='http://legacy-influx:8086',timeout=4,trust_env=False) as login:
        status=login.post('/api/v2/signin',auth=(username,password)).status_code
    if status==204:
        return True
    if status==401:
        return False
    raise RuntimeError('InfluxDB sign-in probe inconclusive (HTTP '+str(status)+')')
password_positive=signin(data['influx_user'],data['influx_password'])
password_negative=all(not signin(user['name'],secrets.token_urlsafe(48)) for user in users)
password_results=[signin(user['name'],password) for user in users for password in data['historical']['INFLUXDB_PASSWORD']]
result={
    'postgres':{'roles_checked':len(data['pg_roles']),'positive_control':positive,'negative_control':negative,'historical_rejected':pg_results.count(False),'historical_accepted':pg_results.count(True)},
    'influxdb':{'positive_control':influx_positive,'negative_control':influx_negative,'historical_rejected':influx_results.count(False),'historical_accepted':influx_results.count(True)},
    'influxdb_password':{'users_checked':len(users),'positive_control':password_positive,'negative_control':password_negative,'historical_rejected':password_results.count(False),'historical_accepted':password_results.count(True)},
}
result['passed']=positive and negative and influx_positive and influx_negative and password_positive and password_negative and not any(pg_results+influx_results+password_results)
print(json.dumps(result))
client.close()
"""


def docker(*args, input=None):
    result = subprocess.run(
        ["docker", *args], cwd=ROOT, input=input, text=True, capture_output=True
    )
    if result.returncode:
        raise RuntimeError(
            f"Local issuer audit Docker operation failed ({result.returncode}); raw output withheld"
        )
    return result.stdout.strip()


def inspect(name, project):
    row = json.loads(docker("inspect", name))[0]
    if row["Config"].get("Labels", {}).get("com.docker.compose.project") != project:
        raise RuntimeError("Unexpected legacy project")
    if row["State"]["Running"]:
        raise RuntimeError("Original legacy containers must remain stopped")
    return row


def environment(row):
    return dict(item.split("=", 1) for item in row["Config"]["Env"] if "=" in item)


def configured(row, key):
    env = environment(row)
    if key in env:
        return env[key]
    target = env[key + "_FILE"]
    raw_source = next(
        m["Source"]
        for m in row["Mounts"]
        if m["Destination"] == target and m["Type"] == "bind"
    )
    if os.name == "nt" and raw_source.startswith("/run/desktop/mnt/host/"):
        relative = raw_source.removeprefix("/run/desktop/mnt/host/")
        if not re.match(r"^[A-Za-z]/", relative):
            raise RuntimeError("Unexpected Docker Desktop host path")
        raw_source = relative[0] + ":/" + relative[2:]
    source = Path(raw_source).resolve()
    if not source.is_relative_to((ROOT / "secrets").resolve()):
        raise RuntimeError("Unexpected local credential file")
    return source.read_text(encoding="utf-8").strip()


def runnable_image(row, program):
    available = subprocess.run(
        ["docker", "image", "inspect", row["Image"]], capture_output=True
    )
    if available.returncode == 0:
        return row["Image"]
    # BuildKit retagging can leave a stopped container's image metadata unavailable.
    # The local tag is usable only after comparing the actual database engine bytes.
    copied = subprocess.check_output(["docker", "cp", row["Name"] + ":" + program, "-"])
    with tarfile.open(fileobj=io.BytesIO(copied)) as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        if len(members) != 1:
            raise RuntimeError("Database engine copy ambiguous")
        expected = hashlib.sha256(archive.extractfile(members[0]).read()).hexdigest()
    candidate = row["Config"]["Image"]
    actual = docker(
        "run",
        "--rm",
        "--pull",
        "never",
        "--network",
        "none",
        "--read-only",
        "--entrypoint",
        "sha256sum",
        candidate,
        program,
    ).split()[0]
    if actual != expected:
        raise RuntimeError(
            "Local database image differs from the stopped issuer engine"
        )
    return candidate


def candidates():
    config = tomllib.loads((ROOT / ".gitleaks.toml").read_text(encoding="utf-8"))
    pattern = re.compile(config["rules"][0]["regex"])
    result = {
        "POSTGRES_PASSWORD": set(),
        "INFLUXDB_TOKEN": set(),
        "INFLUXDB_PASSWORD": set(),
    }
    ledger = json.loads(
        (ROOT / "docs/security/history-findings.json").read_text(encoding="utf-8")
    )
    locations = {
        (row["commit"], row["path"])
        for row in ledger
        if row["status"] != "reviewed_placeholder"
    }
    for commit, path in locations:
        raw = subprocess.check_output(
            ["git", "show", commit + ":" + path], cwd=ROOT, text=True
        )
        for match in pattern.finditer(raw):
            tail = raw[match.end() :].split("\n", 1)[0]
            if tail and tail[0] not in "\"' \r\t,]}":
                raise RuntimeError("Credential parser did not cover a complete literal")
            key = re.match(
                r"POSTGRES_PASSWORD|DOCKER_INFLUXDB_INIT_PASSWORD|DOCKER_INFLUXDB_INIT_ADMIN_TOKEN|INFLUXDB_PASSWORD|INFLUXDB_TOKEN",
                match.group(0),
                re.I,
            )
            if key:
                name = key.group(0).upper()
                if name.startswith("DOCKER_"):
                    name = "INFLUXDB_" + (
                        "PASSWORD" if name.endswith("PASSWORD") else "TOKEN"
                    )
                result[name].add(match.group(1))
    if not all(result.values()):
        raise RuntimeError("Historical credential scope missing")
    return {key: sorted(values) for key, values in result.items()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stack", choices=("legacy", "aiot"), default="legacy")
    stack = parser.parse_args().stack
    project = "web-smart-fan-iot" if stack == "legacy" else "smartfan-aiot"
    names = (
        ("iot_postgres", "iot_influxdb", "iot_backend")
        if stack == "legacy"
        else (
            "smartfan-aiot-postgres-1",
            "smartfan-aiot-influxdb-1",
            "smartfan-aiot-api-1",
        )
    )
    identity = uuid4().hex[:12]
    prefix = "smartfan-legacy-audit-" + identity
    destination = ROOT / "evidence/security" / prefix
    private(destination)
    originals = {name: inspect(name, project) for name in names}
    pg, influx, backend = (originals[name] for name in names)
    pg_env = environment(pg)
    pg_image = runnable_image(pg, "/usr/local/bin/postgres")
    influx_image = runnable_image(influx, "/usr/bin/influxd")
    user = pg_env.get("POSTGRES_USER", "postgres")
    database = pg_env.get("POSTGRES_DB", user)
    pg_data = pg_env.get("PGDATA", "/var/lib/postgresql/data")
    relative = PurePosixPath(pg_data).relative_to("/var/lib/postgresql/data")
    if ".." in relative.parts:
        raise RuntimeError("Unexpected PostgreSQL data path")
    uid = docker(
        "run",
        "--rm",
        "--network",
        "none",
        "--read-only",
        "--entrypoint",
        "id",
        pg_image,
        "-u",
        "postgres",
    )
    if not uid.isdigit():
        raise RuntimeError("Unknown PostgreSQL image user")
    network = prefix + "-net"
    containers = []
    copies = []
    docker(
        "network",
        "create",
        "--internal",
        "--label",
        "smartfan.audit.id=" + identity,
        network,
    )
    try:
        mounts = []
        for row, target, owner in (
            (pg, "/var/lib/postgresql/data", uid),
            (influx, "/var/lib/influxdb2", "10001"),
            (influx, "/etc/influxdb2", "10001"),
        ):
            original = next(
                m
                for m in row["Mounts"]
                if m["Destination"] == target and m["Type"] == "volume"
            )
            copy = prefix + "-volume-" + str(len(copies))
            docker("volume", "create", "--label", "smartfan.audit.id=" + identity, copy)
            copies.append(copy)
            script = (
                "import os,shutil; shutil.copytree('/source','/target',dirs_exist_ok=True,symlinks=True); [(os.chown(os.path.join(r,n),"
                + owner
                + ","
                + owner
                + ",follow_symlinks=False)) for r,ds,fs in os.walk('/target',followlinks=False) for n in ds+fs]; os.chown('/target',"
                + owner
                + ","
                + owner
                + ")"
            )
            docker(
                "run",
                "--rm",
                "--network",
                "none",
                "--read-only",
                "--user",
                "0:0",
                "--mount",
                "type=volume,src=" + original["Name"] + ",dst=/source,readonly",
                "--mount",
                "type=volume,src=" + copy + ",dst=/target",
                PYTHON,
                "python",
                "-c",
                script,
            )
            mounts.append((copy, target))
        hba = destination / "pg_hba.conf"
        hba.write_text(
            "local all all trust\nhost all all 0.0.0.0/0 md5\n", encoding="utf-8"
        )
        pg_name, influx_name = prefix + "-pg", prefix + "-influx"
        docker(
            "run",
            "-d",
            "--name",
            pg_name,
            "--label",
            "smartfan.audit.id=" + identity,
            "--network",
            network,
            "--network-alias",
            "legacy-pg",
            "--user",
            uid + ":" + uid,
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "-v",
            mounts[0][0] + ":" + mounts[0][1],
            "-v",
            str(hba) + ":/audit/pg_hba.conf:ro",
            "--entrypoint",
            "postgres",
            pg_image,
            "-D",
            pg_data,
            "-c",
            "hba_file=/audit/pg_hba.conf",
            "-c",
            "unix_socket_directories=/tmp",
            "-c",
            "listen_addresses=*",
            "-c",
            "log_statement=none",
            "-c",
            "log_min_error_statement=panic",
        )
        containers.append(pg_name)
        for _ in range(30):
            ready = subprocess.run(
                [
                    "docker",
                    "exec",
                    pg_name,
                    "pg_isready",
                    "-h",
                    "/tmp",
                    "-U",
                    user,
                    "-d",
                    database,
                ],
                capture_output=True,
            )
            if ready.returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL copy not ready")
        roles = json.loads(
            docker(
                "exec",
                pg_name,
                "psql",
                "-h",
                "/tmp",
                "-U",
                user,
                "-d",
                database,
                "-Atc",
                "SELECT json_agg(rolname) FROM pg_roles WHERE rolcanlogin",
            )
        )
        docker(
            "run",
            "-d",
            "--name",
            influx_name,
            "--label",
            "smartfan.audit.id=" + identity,
            "--network",
            network,
            "--network-alias",
            "legacy-influx",
            "--user",
            "10001:10001",
            "--read-only",
            "--tmpfs",
            "/tmp",
            "--memory",
            "512m",
            "--cpus",
            "1",
            "-v",
            mounts[1][0] + ":" + mounts[1][1],
            "-v",
            mounts[2][0] + ":" + mounts[2][1],
            "-e",
            "INFLUXD_BOLT_PATH=/var/lib/influxdb2/influxd.bolt",
            "-e",
            "INFLUXD_ENGINE_PATH=/var/lib/influxdb2/engine",
            "-e",
            "INFLUXD_SQLITE_PATH=/var/lib/influxdb2/influxd.sqlite",
            "-e",
            "INFLUXD_USE_HASHED_TOKENS=false",
            "--entrypoint",
            "influxd",
            influx_image,
        )
        containers.append(influx_name)
        payload = {
            "pg_user": user,
            "database": database,
            "pg_roles": roles,
            "pg_current": configured(pg, "POSTGRES_PASSWORD"),
            "influx_current": sorted(
                {
                    configured(backend, "INFLUXDB_TOKEN")
                    if stack == "legacy"
                    else configured(influx, "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"),
                    configured(influx, "DOCKER_INFLUXDB_INIT_ADMIN_TOKEN"),
                }
            ),
            "influx_user": environment(influx)["DOCKER_INFLUXDB_INIT_USERNAME"],
            "influx_password": configured(influx, "DOCKER_INFLUXDB_INIT_PASSWORD"),
            "historical": candidates(),
        }
        result = json.loads(
            docker(
                "run",
                "--rm",
                "-i",
                "--network",
                network,
                "--read-only",
                "--tmpfs",
                "/tmp",
                "--memory",
                "192m",
                "--cpus",
                "1",
                CLIENT_IMAGE,
                "python",
                "-c",
                "import json\ntry:\n"
                + textwrap.indent(CLIENT, "    ")
                + "\nexcept Exception as error:\n    print(json.dumps({'passed':False,'audit_error':type(error).__name__,'reason':str(error) if type(error) is RuntimeError else 'Probe inconclusive; details withheld'}))",
                input=json.dumps(payload),
            )
        )
        for name in originals:
            inspect(name, project)
        report = {
            "audit_id": identity,
            "stack": stack,
            "project": project,
            "measured_at": datetime.now(UTC).isoformat(),
            "scope": "known local Docker issuers only; original volumes mounted read-only during copying",
            "original_images": {name: row["Image"] for name, row in originals.items()},
            "audit_images": {
                "postgres": json.loads(docker("inspect", pg_name))[0]["Image"],
                "influxdb": json.loads(docker("inspect", influx_name))[0]["Image"],
            },
            "candidate_counts": {
                key: len(values) for key, values in payload["historical"].items()
            },
            "clone_volumes_retained": copies,
            "ledger_findings": sorted(
                row["fingerprint"]
                for row in json.loads(
                    (ROOT / "docs/security/history-findings.json").read_text(
                        encoding="utf-8"
                    )
                )
                if row["status"] != "reviewed_placeholder"
            ),
            **result,
        }
        (destination / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(report, indent=2))
        if not result["passed"]:
            raise RuntimeError(
                "Historical credentials remain accepted or controls failed"
            )
    finally:
        for name in containers:
            labels = json.loads(docker("inspect", name))[0]["Config"].get("Labels", {})
            if labels.get("smartfan.audit.id") != identity:
                raise RuntimeError("Refusing to stop a container outside this audit")
            docker("stop", name)
            docker("rm", name)
        docker("network", "rm", network)


if __name__ == "__main__":
    main()

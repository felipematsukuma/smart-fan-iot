"""Real PG/AMQP checks in a disposable test database, never the live schema."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pika
import pytest
from smartfan_common.contracts_v2 import parse_event_v2
from smartfan_common.reliability.amqp import ConfirmedPublisher, connect_amqp
from smartfan_common.reliability.database import engine_for, migrate
from smartfan_common.reliability.leases import ResourceLeases
from smartfan_common.reliability.store import (
    Delivery,
    DurableStore,
    LostLease,
    Outbound,
    QuotaExceeded,
    Table,
)
from sqlalchemy import Connection, text
from sqlalchemy.exc import DBAPIError, OperationalError

from infra.database import provision_database

SECRETS = Path("/run/secrets")
pytestmark = pytest.mark.skipif(
    not (SECRETS / "postgres_bootstrap").exists(),
    reason="Requires isolated Docker integration environment",
)


def claimed(store: DurableStore, table: Table = "inbox") -> Delivery:
    result = store.claim(table)
    assert result is not None
    return result


@pytest.fixture(scope="module")
def database():
    name = "test_smartfan_" + uuid4().hex
    administrator = engine_for("bootstrap", SECRETS / "postgres_bootstrap")
    with administrator.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    admin = engine_for("bootstrap", SECRETS / "postgres_bootstrap", database=name)
    provision_database(admin, SECRETS, name)
    migrate(admin)  # Upgrade head twice must be harmless.
    engines = {
        role: engine_for(role, SECRETS / ("postgres_" + role), database=name)
        for role in ("writer", "gateway", "api", "jobs-worker")
    }
    with admin.begin() as conn:
        conn.execute(
            text(
                "CREATE TABLE transport.test_effects(event_id uuid PRIMARY KEY,value integer NOT NULL)"
            )
        )
        conn.execute(
            text('GRANT SELECT,INSERT ON transport.test_effects TO "smartfan_writer"')
        )
    yield admin, engines
    for engine in engines.values():
        engine.dispose()
    admin.dispose()
    with administrator.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as conn:
        # Name was generated above, never taken from configuration/user input.
        conn.execute(text(f'DROP DATABASE "{name}"'))
    administrator.dispose()


@pytest.fixture(autouse=True)
def reset_disposable_rows(database):
    admin, _ = database
    with admin.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE transport.inbox,transport.outbox,transport.failures,transport.resource_leases,transport.test_effects"
            )
        )


def test_atomic_rollback_receive_and_outbox(database):
    _, engines = database
    store = DurableStore(engines["writer"], "writer")
    event_id, out_id = str(uuid4()), str(uuid4())
    with pytest.raises(RuntimeError), engines["writer"].begin() as conn:
        store.receive(
            event_id,
            b'{"input":1}',
            "raw",
            outgoing=[
                Outbound(
                    out_id, b"{}", "smartfan.events", "persisted.quarto.hvac.ac_01"
                )
            ],
            connection=conn,
        )
        raise RuntimeError("Injected crash before commit")
    assert store.counts() == {}
    assert store.pending_outbox() == []
    assert store.receive(event_id, b'{"input":1}', "raw") == "accepted"
    assert store.receive(event_id, b'{"input":1}', "raw") == "duplicate"


def test_identity_conflict_preserves_original_and_failed_input(database):
    admin, engines = database
    store = DurableStore(engines["writer"], "writer")
    identity = str(uuid4())
    store.receive(identity, b"original", "raw")
    assert store.receive(identity, b"changed", "raw") == "conflict"
    assert store.receive(identity, b"changed", "raw") == "conflict"
    assert claimed(store).payload == b"original"
    with admin.connect() as conn:
        failures = conn.execute(
            text("SELECT payload,sha256 FROM transport.failures")
        ).all()
    assert len(failures) == 1 and bytes(failures[0][0]) == b"changed"
    assert failures[0][1] == hashlib.sha256(b"changed").hexdigest()
    event = parse_event_v2(claimed(store, "outbox").payload)
    assert event.tipo == "message.quarantined"


def test_effect_and_outputs_rollback_together(database):
    admin, engines = database
    store = DurableStore(engines["writer"], "writer")
    identity = str(uuid4())
    store.receive(identity, b"body", "raw")
    delivery = claimed(store)

    def crash(conn):
        conn.execute(
            text("INSERT INTO transport.test_effects VALUES(:id,1)"), {"id": identity}
        )
        raise RuntimeError("Injected crash during decision")

    with pytest.raises(RuntimeError):
        store.finish(delivery, effects=crash)
    with admin.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM transport.test_effects")
            ).scalar_one()
            == 0
        )

    def success(conn: Connection) -> None:
        conn.execute(
            text("INSERT INTO transport.test_effects VALUES(:id,1)"), {"id": identity}
        )

    store.finish(delivery, effects=success)
    with pytest.raises(LostLease):
        store.finish(delivery)
    assert store.counts() == {"completed": 1}


def test_quota_rolls_back_and_never_acknowledges_extra_work(database):
    _, engines = database
    store = DurableStore(engines["writer"], "writer", quota_bytes=300)
    store.receive(str(uuid4()), b"a" * 40, "raw")
    with pytest.raises(QuotaExceeded):
        store.receive(str(uuid4()), b"b" * 40, "raw")
    assert store.counts() == {"pending": 1}


def test_row_security_and_trusted_receipt_view(database):
    _, engines = database
    gateway = DurableStore(engines["gateway"], "gateway")
    writer = DurableStore(engines["writer"], "writer")
    identity = str(uuid4())
    gateway.receive(identity, b"private-body", "mqtt")
    assert writer.counts() == {}
    assert writer.receipt_time(identity) is not None
    with pytest.raises(DBAPIError), engines["api"].begin() as conn:
        conn.execute(
            text(
                "INSERT INTO transport.inbox(owner,event_id,sha256,payload,route) VALUES('gateway',:id,:hash,:body,'forged')"
            ),
            {"id": str(uuid4()), "hash": "a" * 64, "body": b"forged"},
        )
    with pytest.raises(DBAPIError), engines["writer"].begin() as conn:
        conn.execute(text("CREATE TABLE transport.forbidden(value integer)"))


def test_concurrent_duplicate_acceptance_and_exclusive_claim(database):
    _, engines = database
    store = DurableStore(engines["writer"], "writer")
    identity = str(uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: store.receive(identity, b"body", "raw"), range(2))
        )
    assert sorted(results) == ["accepted", "duplicate"]
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda _: store.claim(), range(2)))
    assert sum(c is not None for c in claims) == 1


def test_expired_delivery_is_fenced_and_retry_keeps_bytes(database):
    admin, engines = database
    store = DurableStore(engines["writer"], "writer")
    identity = str(uuid4())
    store.receive(identity, b"body", "raw")
    old = claimed(store)
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE transport.inbox SET leased_until=clock_timestamp()-interval '1 second'"
            )
        )
    new = claimed(store)
    assert new.generation == old.generation + 1
    assert not store.renew(old)
    assert store.renew(new)
    with pytest.raises(LostLease):
        store.finish(old)
    store.retry(new, "temporary_failure")
    assert store.claim() is None
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE transport.inbox SET available_at=clock_timestamp()-interval '1 second'"
            )
        )
    next_delivery = claimed(store)
    assert next_delivery.payload == b"body" and next_delivery.event_id == identity
    store.retry(next_delivery, "permanent_failure", permanent=True)
    assert store.counts() == {"failed": 1}


def test_resource_expiry_cannot_grant_new_owner_or_release_with_old_token(database):
    admin, engines = database
    jobs = ResourceLeases(engines["jobs-worker"], "jobs-worker")
    chat = ResourceLeases(engines["api"], "api")
    with pytest.raises(PermissionError):
        ResourceLeases(engines["api"], "jobs-worker")
    old = jobs.acquire(str(uuid4()), "train")
    assert old and jobs.renew(old) and jobs.valid(old)
    assert chat.acquire(str(uuid4()), "chat") is None
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE transport.resource_leases SET expires_at=clock_timestamp()-interval '1 second'"
            )
        )
    assert not jobs.valid(old) and not jobs.renew(old)
    assert chat.acquire(str(uuid4()), "chat") is None
    assert jobs.release_after_confirmed_stop(old)
    current = chat.acquire(str(uuid4()), "chat")
    assert current and current.generation > old.generation
    assert not jobs.release_after_confirmed_stop(old)
    assert not jobs.renew(old)
    assert chat.valid(current)
    assert chat.release_after_confirmed_stop(current)


def test_confirmed_publish_unroutable_and_topic_acl(database):
    admin, engines = database
    store = DurableStore(engines["writer"], "writer")
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(
            host="rabbitmq",
            virtual_host="/smartfan",
            credentials=pika.PlainCredentials(
                "bootstrap", (SECRETS / "rabbit_bootstrap").read_text().strip()
            ),
        )
    )
    try:
        channel = connection.channel()
        queue = channel.queue_declare(
            queue="", exclusive=True, auto_delete=True
        ).method.queue
        route = "test." + uuid4().hex
        channel.queue_bind(queue=queue, exchange="smartfan.events", routing_key=route)
        publisher = ConfirmedPublisher(channel)
        identity = str(uuid4())
        store.enqueue(
            Outbound(identity, b"confirmation-probe", "smartfan.events", route)
        )
        first = claimed(store, "outbox")
        channel.basic_publish(
            "smartfan.events",
            route,
            first.payload,
            properties=pika.BasicProperties(message_id=identity, delivery_mode=2),
            mandatory=True,
        )
        # Inject the cut AFTER broker confirmation and BEFORE PG completion.
        with admin.begin() as conn:
            conn.execute(
                text(
                    "UPDATE transport.outbox SET leased_until=clock_timestamp()-interval '1 second'"
                )
            )
        assert publisher.publish_one(store)
        receiver = DurableStore(engines["api"], "api")
        results = []
        for _ in range(2):
            method, props, body = channel.basic_get(queue=queue, auto_ack=False)
            assert (
                method is not None
                and props.message_id == identity
                and body == b"confirmation-probe"
            )
            results.append(receiver.receive(identity, body, route))
            channel.basic_ack(method.delivery_tag)
        assert results == ["accepted", "duplicate"]
        store.enqueue(
            Outbound(
                str(uuid4()), b"{}", "smartfan.events", "test.missing." + uuid4().hex
            )
        )
        with pytest.raises(pika.exceptions.UnroutableError):
            publisher.publish_one(store)
        assert store.pending_outbox()[0]["state"] == "pending"
    finally:
        connection.close()  # Exclusive test queue disappears, real queues untouched.
    broker = connect_amqp("writer", SECRETS / "rabbit_writer")
    try:
        channel = broker.channel()
        channel.confirm_delivery()
        with pytest.raises(pika.exceptions.ChannelClosedByBroker):
            channel.basic_publish(
                "smartfan.events", "command.ac_01", b"forbidden", mandatory=True
            )
    finally:
        broker.close()


def test_no_acceptance_return_when_database_is_unreachable(database):
    _, engines = database
    isolated = engine_for(
        "writer", SECRETS / "postgres_writer", host="postgres", port=1
    )
    try:
        with pytest.raises(OperationalError):
            DurableStore(isolated, "writer").receive(str(uuid4()), b"body", "raw")
    finally:
        isolated.dispose()
    assert DurableStore(engines["writer"], "writer").counts() == {}


def test_retention_only_prunes_own_terminal_payloads(database):
    admin, engines = database
    writer = DurableStore(engines["writer"], "writer")
    gateway = DurableStore(engines["gateway"], "gateway")
    completed, pending, other = str(uuid4()), str(uuid4()), str(uuid4())
    writer.receive(completed, b"old-complete", "raw")
    writer.finish(claimed(writer))
    writer.receive(pending, b"pending-do-not-delete", "raw")
    gateway.receive(other, b"other-owner", "raw")
    gateway.finish(claimed(gateway))
    writer.quarantine(b"", "raw", "empty_message")
    with admin.begin() as conn:
        conn.execute(
            text(
                "UPDATE transport.inbox SET finished_at=clock_timestamp()-interval '2 days',observed_at=clock_timestamp()-interval '2 days' WHERE state='completed'"
            )
        )
    writer.prune_terminal_payloads()
    with admin.connect() as conn:
        values = {
            str(row[0]): row[1]
            for row in conn.execute(
                text("SELECT event_id,payload FROM transport.inbox")
            )
        }
        assert values[completed] is None
        assert bytes(values[pending]) == b"pending-do-not-delete"
        assert bytes(values[other]) == b"other-owner"
        assert (
            conn.execute(text("SELECT count(*) FROM transport.failures")).scalar_one()
            == 1
        )
    assert writer.receive(completed, b"old-complete", "raw") == "duplicate"
    with pytest.raises(DBAPIError), engines["writer"].begin() as conn:
        conn.execute(text("DELETE FROM transport.inbox"))

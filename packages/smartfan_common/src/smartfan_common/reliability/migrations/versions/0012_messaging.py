"""Read-only failure journal and narrowly scoped, audited writer replay."""

from alembic import op

revision = "0012_messaging"
down_revision = "0011_control"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE VIEW app.failure_journal WITH (security_barrier=true) AS
        SELECT f.owner,f.failure_id,f.event_id,f.reason_code,f.attempts,f.created_at,
          f.sha256,f.payload,i.state AS delivery_state,i.route
        FROM (SELECT ranked.* FROM (SELECT failures.*,row_number() OVER(PARTITION BY owner ORDER BY created_at DESC,failure_id DESC) AS preview_rank FROM transport.failures) ranked WHERE preview_rank<=200) f
        LEFT JOIN transport.inbox i ON i.owner=f.owner AND i.event_id=f.event_id;
      GRANT SELECT ON app.failure_journal TO smartfan_api;
      CREATE TABLE app.failure_replays (
        request_id uuid PRIMARY KEY,failure_id uuid NOT NULL,actor_user_id uuid NOT NULL,
        created_at timestamptz NOT NULL DEFAULT clock_timestamp()
      );
      CREATE INDEX failure_replays_failure ON app.failure_replays(failure_id,created_at DESC);
      GRANT SELECT ON app.failure_replays TO smartfan_api;
      CREATE FUNCTION app.replay_writer_failure(target uuid,request uuid,actor uuid,correlation uuid)
      RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
      DECLARE f record; i record; body jsonb; prior uuid; count_replays integer;
      BEGIN
        PERFORM pg_advisory_xact_lock(hashtextextended('failure-replay:'||request::text,0));
        SELECT failure_id INTO prior FROM app.failure_replays WHERE request_id=request;
        IF FOUND THEN
          IF prior<>target THEN RETURN 'request_conflict'; END IF;
          RETURN 'already_requested';
        END IF;
        SELECT * INTO f FROM transport.failures WHERE failure_id=target AND owner='writer' FOR UPDATE;
        IF NOT FOUND THEN RETURN 'not_replayable'; END IF;
        SELECT * INTO i FROM transport.inbox WHERE owner='writer' AND event_id=f.event_id FOR UPDATE;
        IF NOT FOUND OR i.state<>'failed' OR i.payload IS NULL OR i.sha256<>f.sha256
          OR encode(sha256(i.payload),'hex')<>f.sha256 THEN RETURN 'not_replayable'; END IF;
        BEGIN body=convert_from(i.payload,'UTF8')::jsonb;
        EXCEPTION WHEN OTHERS THEN RETURN 'not_replayable'; END;
        IF body->>'tipo' IS DISTINCT FROM 'telemetry.sampled'
          OR body#>>'{metadata,producer}' IS DISTINCT FROM 'simulator'
          OR body->>'id' IS DISTINCT FROM f.event_id::text
          OR i.route IS DISTINCT FROM 'telemetry.'||(body#>>'{metadata,zone}')||'.hvac.'||(body->>'dispositivo')
          OR NOT EXISTS(SELECT 1 FROM transport.receipts r WHERE r.event_id=f.event_id AND r.sha256=f.sha256)
          OR NOT EXISTS(SELECT 1 FROM app.devices d WHERE d.id=body->>'dispositivo' AND d.zone=body#>>'{metadata,zone}')
        THEN RETURN 'not_replayable'; END IF;
        SELECT count(*) INTO count_replays FROM app.failure_replays WHERE failure_id=target;
        IF count_replays>=3 OR EXISTS(SELECT 1 FROM app.failure_replays WHERE failure_id=target AND created_at>clock_timestamp()-interval '30 seconds')
        THEN RETURN 'replay_limit'; END IF;
        UPDATE transport.inbox SET state='pending',attempts=0,generation=generation+1,
          available_at=clock_timestamp(),leased_until=NULL,finished_at=NULL,reason_code=NULL,dependency_failure=false
          WHERE owner='writer' AND event_id=f.event_id;
        INSERT INTO app.failure_replays(request_id,failure_id,actor_user_id) VALUES(request,target,actor);
        INSERT INTO app.audit(id,actor_user_id,action,entity_type,entity_id,correlation_id,details,outcome)
          VALUES(request,actor,'failure.replay_requested','failure',target::text,correlation,
            jsonb_build_object('owner','writer','source_event_id',f.event_id,'attempt',count_replays+1),'success');
        RETURN 'requested';
      END $$;
      REVOKE ALL ON FUNCTION app.replay_writer_failure(uuid,uuid,uuid,uuid) FROM PUBLIC;
      GRANT EXECUTE ON FUNCTION app.replay_writer_failure(uuid,uuid,uuid,uuid) TO smartfan_api;
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")

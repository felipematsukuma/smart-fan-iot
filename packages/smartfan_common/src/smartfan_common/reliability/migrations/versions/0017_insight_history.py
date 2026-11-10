"""Read-only projection of predictions; the API cannot read raw inference payloads."""

from alembic import op

revision = "0017_insight_history"
down_revision = "0016_predictive_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
      CREATE VIEW app.insight_history WITH (security_barrier=true) AS
        SELECT source_event_id,device_id,boot_id,sequence,sampled_at,model_version,
          activation_revision,
          convert_from(insight_payload,'UTF8')::jsonb->'conteudo'->>'status' AS status,
          (convert_from(insight_payload,'UTF8')::jsonb->'conteudo'->>'health_score')::double precision AS health_score,
          (convert_from(insight_payload,'UTF8')::jsonb->'conteudo'->>'rul_calendar_hours')::double precision AS rul_calendar_hours
        FROM app.inference_results WHERE insight_payload IS NOT NULL;
      GRANT SELECT ON app.insight_history TO smartfan_api;
      CREATE INDEX alerts_time ON app.alerts(raised_at DESC,id DESC);
    """)


def downgrade() -> None:
    raise RuntimeError("Destructive downgrade is unsupported; restore a validated backup")

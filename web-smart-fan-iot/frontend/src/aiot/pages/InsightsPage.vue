<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import { api, currentUser } from '../auth';
import { alertRevision, live, streamStatus, streamNotice } from '../realtime';
import {
  insightLabels,
  alertReason,
  numberText,
  pointsFromFrames,
  presentation,
  type AlertRecord,
  type PredictionPoint,
  type RuleMetadata,
} from '../insights';
import { overviewFreshness } from '../overview-freshness';
import { Card, Badge, Alert } from '../ui/primitives';
import Button from '../ui/Button.vue';
import '../ui/task-page.css';
import InsightTrend from '../components/InsightTrend.vue';

const connectionLabels = {
  connected: 'Conectada',
  offline: 'Desconectada',
  connecting: 'Conectando',
  authenticating: 'Autenticando',
  reconnecting: 'Reconectando',
};
const selected = ref('');
const route = useRoute();
const now = ref(Date.now());
const devices = computed(() => [...live.devices.values()]);
watch(
  devices,
  (items) => {
    if (!items.some((item) => item.id === selected.value))
      selected.value =
        items.find((item) => item.id === route.query.device)?.id ??
        items[0]?.id ??
        '';
  },
  { immediate: true },
);
const frame = computed(() => live.frames.get(selected.value));
const freshness = computed(() =>
  overviewFreshness(
    frame.value,
    live.devices.get(selected.value)?.boot_id,
    Math.max(now.value, Date.now()),
  ),
);
const display = computed(() => {
  const result = presentation(
    frame.value,
    freshness.value.reference,
    freshness.value.fresh,
  );
  return {
    ...result,
    label:
      freshness.value.kind === 'missing'
        ? 'Aguardando telemetria'
        : freshness.value.kind === 'unavailable'
          ? 'Telemetria indisponível'
          : result.label,
  };
});
const comparison = computed(() =>
  devices.value.map((device) => {
    const item = live.frames.get(device.id);
    const state = overviewFreshness(
      item,
      device.boot_id,
      Math.max(now.value, Date.now()),
    );
    return {
      device,
      display: presentation(item, state.reference, state.fresh),
    };
  }),
);
const range = computed(() =>
  points.value.length
    ? `${new Date(points.value[0]!.sampled_at).toLocaleTimeString('pt-BR')} — ${new Date(points.value.at(-1)!.sampled_at).toLocaleTimeString('pt-BR')}`
    : 'Sem amostras',
);
const points = computed(() =>
  frame.value
    ? pointsFromFrames([...(live.history.get(selected.value) ?? [])])
    : [],
);
const target = ref<'health_score' | 'rul_calendar_hours'>('health_score');
const rule = ref<RuleMetadata | null>(null);
const draft = ref<RuleMetadata['configuration'] | null>(null);
const editing = ref(false);
const saving = ref(false);
const notice = ref('');
const error = ref('');
const loading = ref(false);
const alerts = ref<AlertRecord[]>([]);
const next = ref<string | null>(null);
const filter = ref('active');
const alertsKnown = ref(false);
const historical = ref<PredictionPoint[]>([]);
const historyNext = ref<string | null>(null);
const historyLoaded = ref(false);
const historyBusy = ref(false);
const historyError = ref('');
const selection = ref<{
  active_version: string | null;
  desired_version: string | null;
} | null>(null);
let epoch = 0;
let metadataController: AbortController | undefined;
let historyController: AbortController | undefined;
async function metadata(more = false) {
  if (!selected.value) return;
  const generation = epoch;
  metadataController?.abort();
  const request = new AbortController();
  metadataController = request;
  loading.value = true;
  try {
    const [setting, records, status] = await Promise.all([
      api<RuleMetadata>(
        `/devices/${encodeURIComponent(selected.value)}/predictive-rule`,
        { signal: request.signal },
      ),
      api<{ items: AlertRecord[]; next_cursor: string | null }>(
        `/alerts?device=${encodeURIComponent(selected.value)}&limit=30${filter.value ? `&status=${filter.value}` : ''}${more && next.value ? `&before=${next.value}` : ''}`,
        { signal: request.signal },
      ),
      api<{ selection: typeof selection.value }>('/insights/status', {
        signal: request.signal,
      }),
    ]);
    if (generation !== epoch || request.signal.aborted) return;
    if (!editing.value) {
      rule.value = setting;
      draft.value = { ...setting.configuration };
    }
    alertsKnown.value = true;
    alerts.value = more
      ? [...alerts.value, ...records.items].slice(0, 300)
      : records.items;
    next.value = alerts.value.length >= 300 ? null : records.next_cursor;
    selection.value = status.selection;
    error.value = '';
  } catch (failure) {
    if (generation === epoch && !request.signal.aborted)
      error.value =
        failure instanceof Error
          ? failure.message
          : 'Falha ao consultar metadados.';
  } finally {
    if (generation === epoch && !request.signal.aborted) loading.value = false;
  }
}
watch(
  selected,
  () => {
    epoch++;
    metadataController?.abort();
    historyController?.abort();
    rule.value = draft.value = null;
    alerts.value = [];
    alertsKnown.value = false;
    historical.value = [];
    next.value = historyNext.value = null;
    historyLoaded.value = false;
    historyBusy.value = false;
    historyError.value = error.value = notice.value = '';
    editing.value = false;
    void metadata();
  },
  { immediate: true },
);
watch([filter, alertRevision], () => void metadata());
async function save() {
  if (!rule.value || !draft.value || saving.value) return;
  const generation = epoch;
  saving.value = true;
  notice.value = '';
  error.value = '';
  try {
    const result = await api<RuleMetadata>(
      `/devices/${encodeURIComponent(selected.value)}/predictive-rule`,
      {
        method: 'PATCH',
        body: JSON.stringify({
          expected_revision: rule.value.revision,
          configuration: draft.value,
        }),
      },
    );
    if (generation === epoch) {
      rule.value = result;
      editing.value = false;
      notice.value = 'Regra preditiva salva e auditada.';
    }
  } catch (failure) {
    if (generation === epoch)
      error.value =
        failure instanceof Error ? failure.message : 'Falha ao salvar regra.';
  } finally {
    saving.value = false;
  }
}
async function loadHistory(more = false) {
  if (!selected.value || historyBusy.value) return;
  const generation = epoch;
  const request = new AbortController();
  historyController = request;
  historyBusy.value = true;
  historyError.value = '';
  try {
    const result = await api<{
      items: PredictionPoint[];
      next_cursor: string | null;
    }>(
      `/devices/${encodeURIComponent(selected.value)}/insights/history?hours=24&limit=120${more && historyNext.value ? `&before=${historyNext.value}` : ''}`,
      { signal: request.signal },
    );
    if (generation !== epoch || request.signal.aborted) return;
    historical.value = more
      ? [...historical.value, ...result.items].slice(0, 1000)
      : result.items;
    historyNext.value =
      historical.value.length >= 1000 ? null : result.next_cursor;
    historyLoaded.value = true;
  } catch (failure) {
    if (generation === epoch && !request.signal.aborted)
      historyError.value =
        failure instanceof Error
          ? failure.message
          : 'Falha ao consultar histórico.';
  } finally {
    if (generation === epoch) historyBusy.value = false;
  }
}
const clock = setInterval(() => {
  now.value = Date.now();
}, 500);
const poll = setInterval(() => void metadata(), 10000);
onBeforeUnmount(() => {
  epoch++;
  clearInterval(clock);
  clearInterval(poll);
  metadataController?.abort();
  historyController?.abort();
});
</script>
<template>
  <div class="task-page insights-page">
    <header class="tp-heading">
      <div>
        <p class="tp-overline">SAÚDE DO EQUIPAMENTO</p>
        <h1>Insights</h1>
      </div>
      <Badge
        :tone="display.status === 'valid' ? 'good' : 'neutral'"
        role="status"
        data-testid="insight-status"
        >{{ display.label }}</Badge
      >
    </header>
    <Card class="tp-card insight-equipment"
      ><div>
        <label for="insight-device">Equipamento dos insights</label
        ><select id="insight-device" v-model="selected">
          <option v-for="device in devices" :key="device.id" :value="device.id">
            {{ device.name }} · {{ device.zone }}
          </option>
        </select>
        <p v-if="!devices.length" class="tp-muted" role="status">
          {{
            streamStatus === 'connected'
              ? 'Nenhum dispositivo autorizado.'
              : 'Conectando aos dispositivos…'
          }}
        </p>
      </div>
      <div class="insight-source">
        <span class="tp-muted"
          >Conexão ao vivo: {{ connectionLabels[streamStatus] }}</span
        >
        <p v-if="frame" class="tp-muted">
          Última leitura às
          {{ new Date(frame.timestamp).toLocaleTimeString('pt-BR')
          }}<span v-if="!freshness.fresh && freshness.age !== null">
            · há {{ freshness.age }} s</span
          >
        </p>
        <p v-if="freshness.kind === 'unavailable'" class="tp-muted">
          {{ freshness.reason }}
        </p>
      </div></Card
    >
    <Alert v-if="streamNotice" role="status">{{ streamNotice }}</Alert>
    <Alert v-if="error" tone="danger" role="alert"
      ><strong>Não foi possível atualizar alertas e configuração.</strong>
      <p>{{ error }}</p>
      <Button :disabled="loading" @click="metadata()"
        >Tentar novamente</Button
      ></Alert
    >
    <Alert v-if="notice" tone="good" role="status">{{ notice }}</Alert>
    <div class="tp-kpis" :data-insight-version="display.version ?? ''">
      <Card class="tp-card tp-kpi"
        ><span>Saúde do compressor</span
        ><strong data-testid="insight-health"
          >{{ numberText(display.health)
          }}<small v-if="display.health != null">%</small></strong
        ></Card
      ><Card class="tp-card tp-kpi"
        ><span>Vida útil restante</span
        ><strong data-testid="insight-rul"
          >{{ numberText(display.rul)
          }}<small v-if="display.rul != null">h</small></strong
        ></Card
      >
    </div>
    <div
      v-if="selected"
      class="insight-main-grid"
      :data-trend-points="points.length"
    >
      <Card id="insight-alerts" class="tp-card"
        ><div class="tp-section-heading">
          <h2>Alertas preditivos</h2>
          <Button :disabled="loading" @click="metadata()">{{
            loading ? 'Atualizando…' : 'Atualizar alertas'
          }}</Button>
        </div>
        <label for="alert-status">Situação do alerta</label
        ><select id="alert-status" v-model="filter">
          <option value="active">Ativos</option>
          <option value="">Todas</option>
          <option value="cleared">Encerrados</option>
        </select>
        <p v-if="loading && !alertsKnown" class="tp-muted" role="status">
          Consultando alertas…
        </p>
        <p v-else-if="!alerts.length && !error && alertsKnown" class="tp-muted">
          {{
            filter === 'active'
              ? 'Nenhum alerta ativo nesta consulta.'
              : 'Nenhum alerta registrado neste filtro.'
          }}
        </p>
        <p v-if="alerts.length && !freshness.fresh" class="tp-muted">
          Ausência de dados não encerra os alertas.
        </p>
        <ul class="insight-alert-list">
          <li v-for="alert in alerts" :key="alert.id">
            <div class="tp-actions">
              <Badge
                :tone="
                  alert.status === 'active'
                    ? alert.severity === 'critical'
                      ? 'danger'
                      : 'warning'
                    : 'neutral'
                "
                >{{ alert.status === 'active' ? 'Ativo' : 'Encerrado' }} ·
                {{
                  alert.severity === 'critical' ? 'Crítico' : 'Atenção'
                }}</Badge
              >
            </div>
            <p class="insight-alert-reason">
              {{ alertReason(alert.reason_code) }}
            </p>
            <p class="tp-muted">
              Início: {{ new Date(alert.raised_at).toLocaleString('pt-BR') }}
            </p>
            <p v-if="alert.cleared_at" class="tp-muted">
              Encerrado em
              {{ new Date(alert.cleared_at).toLocaleString('pt-BR') }}
            </p>
            <details>
              <summary>Origem do alerta</summary>
              <dl class="tp-definition">
                <dt>Código do motivo</dt>
                <dd>{{ alert.reason_code ?? 'Não registrado' }}</dd>
                <dt>Modelo</dt>
                <dd>{{ alert.model_version ?? 'Não informado' }}</dd>
                <dt>Revisão da regra</dt>
                <dd>{{ alert.rule_revision }}</dd>
                <dt>ID</dt>
                <dd>{{ alert.id }}</dd>
              </dl>
            </details>
          </li>
        </ul>
        <Button v-if="next" :disabled="loading" @click="metadata(true)"
          >Mais alertas</Button
        >
      </Card>
      <Card class="tp-card"
        ><div class="tp-section-heading">
          <h2>
            {{ freshness.fresh ? 'Tendência recente' : 'Últimas previsões' }}
          </h2>
          <Badge v-if="!freshness.fresh && points.length"
            >Atualização interrompida</Badge
          >
        </div>
        <label for="insight-target">Indicador da tendência</label
        ><select id="insight-target" v-model="target">
          <option value="health_score">Saúde (%)</option>
          <option value="rul_calendar_hours">RUL (h de calendário)</option>
        </select>
        <p v-if="points.length" class="tp-muted">Visível: {{ range }}</p>
        <InsightTrend
          v-if="points.length"
          :points="points"
          :target="target"
          pilot
        />
        <p v-else class="tp-muted" role="status">Aguardando previsões.</p></Card
      >
    </div>
    <Card v-if="selected" class="tp-card insight-expandable"
      ><details>
        <summary>Detalhes da previsão e do modelo</summary>
        <dl class="tp-definition">
          <dt>Equipamento</dt>
          <dd>{{ selected }}</dd>
          <dt>Versão nesta amostra</dt>
          <dd>{{ display.version ?? 'Sem modelo informado' }}</dd>
          <dt>Modelo ativo no registro</dt>
          <dd>
            {{
              selection
                ? (selection.active_version ?? 'Nenhum')
                : 'Consulta indisponível'
            }}
          </dd>
          <dt>Modelo desejado</dt>
          <dd>
            {{
              selection
                ? (selection.desired_version ?? 'Nenhum')
                : 'Consulta indisponível'
            }}
          </dd>
          <dt>Horário da fonte</dt>
          <dd>
            {{
              frame
                ? new Date(frame.timestamp).toLocaleString('pt-BR')
                : 'Sem leitura'
            }}
          </dd>
          <dt>Sequência</dt>
          <dd>{{ frame?.metadata.sequence ?? 'Sem leitura' }}</dd>
          <dt>Campos ausentes</dt>
          <dd>
            {{
              frame
                ? frame.conteudo.telemetry.quality.missing_fields.join(', ') ||
                  'Nenhum'
                : 'Sem leitura'
            }}
          </dd>
        </dl>
        <p class="tp-muted">
          RUL em horas de calendário. Ambiente simulado, escala de tempo 1×.
          Estimativas sintéticas não constituem diagnóstico de aparelho físico.
          Lacunas e versões diferentes não são interpoladas.
        </p>
      </details></Card
    >
    <Card class="tp-card insight-expandable"
      ><details>
        <summary>Comparação entre equipamentos</summary>
        <div
          class="tp-table"
          tabindex="0"
          role="region"
          aria-label="Comparação entre equipamentos"
        >
          <table>
            <thead>
              <tr>
                <th>Equipamento</th>
                <th>Estado da previsão</th>
                <th>Saúde (%)</th>
                <th>RUL (h)</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="row in comparison" :key="row.device.id">
                <td>{{ row.device.name }}</td>
                <td>{{ row.display.label }}</td>
                <td>{{ numberText(row.display.health) }}</td>
                <td>{{ numberText(row.display.rul) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details></Card
    >
    <Card v-if="selected" class="tp-card insight-expandable"
      ><details>
        <summary>Regra preditiva</summary>
        <template v-if="rule && draft"
          ><h3>Histerese preditiva · revisão {{ rule.revision }}</h3>
          <p>
            Ativação: {{ rule.configuration.bad_samples }} previsões com saúde
            abaixo de {{ rule.configuration.health_raise }}% ou RUL abaixo de
            {{ rule.configuration.rul_raise_hours }} h. Encerramento:
            {{ rule.configuration.good_samples }} previsões com saúde acima de
            {{ rule.configuration.health_clear }}% e RUL acima de
            {{ rule.configuration.rul_clear_hours }} h.
          </p>
          <p>
            Candidatas ruins / boas:
            {{ rule.state ? rule.state.bad_count : '—' }} /
            {{ rule.state ? rule.state.good_count : '—' }}. Estado persistido
            consultado pela API.
          </p>
          <Button
            v-if="currentUser?.role === 'administrador' && !editing"
            @click="editing = true"
          >
            Editar regra preditiva
          </Button>
          <form
            v-if="editing && currentUser?.role === 'administrador'"
            @submit.prevent="save"
          >
            <label
              ><input v-model="draft.enabled" type="checkbox" /> Regra
              habilitada</label
            >
            <div class="tp-form-grid">
              <label
                >Saúde para ativar (%)<input
                  v-model.number="draft.health_raise"
                  type="number"
                  min="0"
                  max="99"
                  step="0.1"
                  required /></label
              ><label
                >Saúde para encerrar (%)<input
                  v-model.number="draft.health_clear"
                  type="number"
                  :min="draft.health_raise + 0.1"
                  max="100"
                  step="0.1"
                  required /></label
              ><label
                >RUL para ativar (h)<input
                  v-model.number="draft.rul_raise_hours"
                  type="number"
                  min="0"
                  max="99999"
                  step="0.1"
                  required /></label
              ><label
                >RUL para encerrar (h)<input
                  v-model.number="draft.rul_clear_hours"
                  type="number"
                  :min="draft.rul_raise_hours + 0.1"
                  max="100000"
                  step="0.1"
                  required /></label
              ><label
                >Previsões ruins consecutivas<input
                  v-model.number="draft.bad_samples"
                  type="number"
                  min="3"
                  max="30"
                  required /></label
              ><label
                >Previsões boas consecutivas<input
                  v-model.number="draft.good_samples"
                  type="number"
                  min="10"
                  max="100"
                  required
              /></label>
            </div>
            <Button variant="primary" :disabled="saving">
              {{ saving ? 'Salvando…' : 'Salvar regra preditiva' }}</Button
            ><Button
              type="button"
              :disabled="saving"
              @click="
                editing = false;
                draft = { ...rule.configuration };
              "
            >
              Cancelar edição
            </Button>
          </form></template
        >

        <p v-if="!rule && !loading" class="tp-muted">
          Configuração indisponível.
        </p>
      </details></Card
    >
    <Card v-if="selected" class="tp-card"
      ><div class="tp-section-heading">
        <h2>Histórico de previsões</h2>
        <Button :disabled="historyBusy" @click="loadHistory()">{{
          historyBusy
            ? 'Consultando histórico…'
            : 'Consultar histórico de insights'
        }}</Button>
      </div>
      <p class="tp-muted">Consulta: últimas 24 horas.</p>
      <Alert v-if="historyError" tone="danger" role="alert">{{
        historyError
      }}</Alert>
      <p
        v-if="historyLoaded && !historical.length && !historyError"
        class="tp-muted"
      >
        Nenhuma previsão disponível nesta janela.
      </p>
      <InsightTrend
        v-if="historical.length"
        :points="[...historical].reverse()"
        :target="target"
        pilot
      />
      <details v-if="historical.length">
        <summary>Registros e versões</summary>
        <p class="tp-muted">
          Valores registrados na época, sem recálculo com o modelo atual.
        </p>
        <div
          class="tp-table history-table"
          tabindex="0"
          role="region"
          aria-label="Registros de previsões"
        >
          <table>
            <thead>
              <tr>
                <th>Fonte</th>
                <th>Estado da previsão</th>
                <th>Saúde (%)</th>
                <th>RUL (h)</th>
                <th>Versão</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="point in historical" :key="point.source_event_id">
                <td>
                  {{ new Date(point.sampled_at).toLocaleString('pt-BR') }}
                </td>
                <td>
                  {{ insightLabels[point.status ?? ''] ?? 'Indisponível' }}
                </td>
                <td>
                  {{
                    point.status === 'valid'
                      ? numberText(point.health_score)
                      : '—'
                  }}
                </td>
                <td>
                  {{
                    point.status === 'valid'
                      ? numberText(point.rul_calendar_hours)
                      : '—'
                  }}
                </td>
                <td>{{ point.model_version ?? 'Sem modelo' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </details>
      <Button
        v-if="historyNext"
        :disabled="historyBusy"
        @click="loadHistory(true)"
        >Mais previsões antigas</Button
      >
    </Card>
  </div>
</template>
<style scoped>
.insight-alert-reason {
  margin: 0.5rem 0 0;
}
.insights-page .insight-expandable:has(> details:not([open])) {
  padding-block: 0.28571rem;
}
.insight-equipment {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  align-items: center;
  gap: 1rem;
}
.insight-equipment label {
  display: block;
  margin: 0 0 0.5rem;
}
.insight-source {
  text-align: right;
}
.insight-main-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
  align-items: start;
  gap: 1.28571rem;
}
.insight-alert-list {
  list-style: none;
  padding: 0;
  margin: 1rem 0 0;
}
.insight-alert-list li {
  border-top: 1px solid #e2e8f0;
  padding: 1rem 0;
}
.insights-page select {
  max-width: 100%;
}
.insights-page label {
  margin: 0.75rem 0 0.5rem;
}
.insights-page form > button {
  margin-right: 0.5rem;
}
.history-table {
  max-height: 330px;
  overflow: auto;
}
@media (max-width: 900px) {
  .insight-equipment,
  .insight-main-grid {
    grid-template-columns: 1fr;
  }
  .insight-source {
    text-align: left;
  }
}
</style>

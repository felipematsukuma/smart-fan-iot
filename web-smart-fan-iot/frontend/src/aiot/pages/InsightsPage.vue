<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue';
import { api, currentUser } from '../auth';
import { alertRevision, live, streamStatus, streamNotice } from '../realtime';
import {
  insightLabels,
  numberText,
  pointsFromFrames,
  presentation,
  type AlertRecord,
  type PredictionPoint,
  type RuleMetadata,
} from '../insights';
import InsightTrend from '../components/InsightTrend.vue';

const selected = ref('');
const now = ref(Date.now());
const devices = computed(() => [...live.devices.values()]);
watch(
  devices,
  (items) => {
    if (!items.some((item) => item.id === selected.value))
      selected.value = items[0]?.id ?? '';
  },
  { immediate: true },
);
const frame = computed(() => live.frames.get(selected.value));
const display = computed(() =>
  presentation(frame.value, now.value, live.fresh(selected.value, now.value)),
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
const filter = ref('');
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
  <div class="page-heading">
    <div>
      <span class="eyebrow">SAÚDE E VIDA ÚTIL</span>
      <h1>Insights</h1>
      <p class="muted">
        Estimativas do compressor a partir das leituras observadas.
      </p>
    </div>
    <span
      class="status-pill"
      :class="display.status === 'valid' ? 'positive' : 'neutral'"
      role="status"
      data-testid="insight-status"
      >{{ display.label }}</span
    >
  </div>
  <p class="notice">
    Ambiente simulado · RUL em horas de calendário · relógio real (escala 1×).
    Resultados sintéticos não representam diagnóstico de um aparelho físico.
  </p>
  <label for="insight-device">Equipamento dos insights</label
  ><select id="insight-device" v-model="selected">
    <option v-for="device in devices" :key="device.id" :value="device.id">
      {{ device.name }} · {{ device.zone }}
    </option>
  </select>
  <p v-if="!devices.length" class="notice" role="status">
    {{
      streamStatus === 'connected'
        ? 'Nenhum dispositivo autorizado.'
        : 'Conectando aos dispositivos…'
    }}
  </p>
  <p v-if="streamNotice" role="status">{{ streamNotice }}</p>
  <p v-if="frame" class="muted">
    Última fonte: {{ new Date(frame.timestamp).toLocaleString('pt-BR') }} ·
    {{ Math.max(0, Math.floor((now - Date.parse(frame.timestamp)) / 1000)) }} s
    atrás · sequência {{ frame.metadata.sequence }} ·
    {{
      frame.conteudo.telemetry.quality.missing_fields.length
        ? `Campos ausentes: ${frame.conteudo.telemetry.quality.missing_fields.join(', ')}`
        : 'Leituras completas'
    }}.
  </p>
  <div class="metric-grid" :data-insight-version="display.version ?? ''">
    <article class="card metric">
      <span>Saúde estimada</span
      ><strong data-testid="insight-health"
        >{{ numberText(display.health)
        }}<small v-if="display.health != null"> %</small></strong
      >
      <p>{{ display.label }}</p>
    </article>
    <article class="card metric">
      <span>Vida útil remanescente</span
      ><strong data-testid="insight-rul"
        >{{ numberText(display.rul)
        }}<small v-if="display.rul != null"> h</small></strong
      >
      <p>Horas de calendário; estimativa sem garantia individual.</p>
    </article>
    <article class="card metric">
      <span>Versão usada nesta amostra</span
      ><strong class="model-version">{{
        display.version ?? 'Sem modelo'
      }}</strong>
      <p>
        Ativa no registro: {{ selection?.active_version ?? 'nenhuma'
        }}<br />Desejada: {{ selection?.desired_version ?? 'nenhuma' }}
      </p>
    </article>
  </div>
  <section class="card insight-section">
    <h2>Tendência recebida ao vivo</h2>
    <label for="insight-target">Indicador da tendência</label
    ><select id="insight-target" v-model="target">
      <option value="health_score">Saúde (%)</option>
      <option value="rul_calendar_hours">RUL (h de calendário)</option></select
    ><InsightTrend v-if="points.length" :points="points" :target="target" />
    <p v-else role="status">Aguardando amostras via WebSocket.</p>
    <p class="muted">
      Até 120 amostras. Lacunas, versões diferentes e previsões indisponíveis
      não são interpoladas.
    </p>
  </section>
  <section class="card insight-section">
    <h2>Comparação entre equipamentos</h2>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Equipamento</th>
            <th>Qualidade</th>
            <th>Saúde (%)</th>
            <th>RUL (h calendário)</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="device in devices" :key="device.id">
            <td>{{ device.name }}</td>
            <td>
              {{
                presentation(
                  live.frames.get(device.id),
                  now,
                  live.fresh(device.id, now),
                ).label
              }}
            </td>
            <td>
              {{
                numberText(
                  presentation(
                    live.frames.get(device.id),
                    now,
                    live.fresh(device.id, now),
                  ).health,
                )
              }}
            </td>
            <td>
              {{
                numberText(
                  presentation(
                    live.frames.get(device.id),
                    now,
                    live.fresh(device.id, now),
                  ).rul,
                )
              }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
  <section v-if="selected" class="card insight-section">
    <div class="section-heading">
      <h2>Alertas preditivos</h2>
      <button class="button secondary" :disabled="loading" @click="metadata()">
        Atualizar alertas
      </button>
    </div>
    <p v-if="loading" role="status">Consultando alertas e configuração…</p>
    <p v-if="error" role="alert">{{ error }}</p>
    <label for="alert-status">Situação do alerta</label
    ><select id="alert-status" v-model="filter">
      <option value="">Todas</option>
      <option value="active">Ativos</option>
      <option value="cleared">Encerrados</option>
    </select>
    <p class="muted">
      Ausência de dados não encerra um alerta. Histórico consultado pela API;
      transições WS atualizam esta lista.
    </p>
    <p v-if="!alerts.length && !loading && !error">
      Nenhum alerta registrado neste filtro.
    </p>
    <div v-if="alerts.length" class="table-wrap">
      <table>
        <thead>
          <tr>
            <th>Situação</th>
            <th>Severidade</th>
            <th>Início / encerramento</th>
            <th>Modelo / regra</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="alert in alerts" :key="alert.id">
            <td>{{ alert.status === 'active' ? 'Ativo' : 'Encerrado' }}</td>
            <td>{{ alert.severity === 'critical' ? 'Crítico' : 'Atenção' }}</td>
            <td>
              {{ new Date(alert.raised_at).toLocaleString('pt-BR') }}<br />{{
                alert.cleared_at
                  ? new Date(alert.cleared_at).toLocaleString('pt-BR')
                  : 'Ainda ativo'
              }}
            </td>
            <td class="model-version">
              {{ alert.model_version }} / r{{ alert.rule_revision }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <button
      class="button secondary"
      v-if="next"
      :disabled="loading"
      @click="metadata(true)"
    >
      Mais alertas
    </button>
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
        Candidatas ruins / boas: {{ rule.state?.bad_count ?? 0 }} /
        {{ rule.state?.good_count ?? 0 }}. Estado persistido consultado pela
        API.
      </p>
      <button
        class="button secondary"
        v-if="currentUser?.role === 'administrador' && !editing"
        @click="editing = true"
      >
        Editar regra preditiva
      </button>
      <form
        v-if="editing && currentUser?.role === 'administrador'"
        @submit.prevent="save"
      >
        <label
          ><input v-model="draft.enabled" type="checkbox" /> Regra
          habilitada</label
        >
        <div class="rule-grid">
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
        <button class="button primary" :disabled="saving">
          {{ saving ? 'Salvando…' : 'Salvar regra preditiva' }}</button
        ><button
          class="button secondary"
          type="button"
          :disabled="saving"
          @click="
            editing = false;
            draft = { ...rule.configuration };
          "
        >
          Cancelar edição
        </button>
      </form></template
    >
    <p v-if="notice" role="status">{{ notice }}</p>
  </section>
  <section v-if="selected" class="card insight-section">
    <h2>Histórico de previsões registradas</h2>
    <p>
      Consulta explícita das últimas 24 h. Não alimenta os indicadores ao vivo.
      Valores não são recalculados com o modelo atual.
    </p>
    <button
      class="button secondary"
      :disabled="historyBusy"
      @click="loadHistory()"
    >
      {{
        historyBusy
          ? 'Consultando histórico…'
          : 'Consultar histórico de insights'
      }}
    </button>
    <p v-if="historyError" role="alert">{{ historyError }}</p>
    <p v-if="historyLoaded && !historical.length">
      Nenhuma previsão disponível nesta janela.
    </p>
    <InsightTrend
      v-if="historical.length"
      :points="[...historical].reverse()"
      :target="target"
    />
    <div v-if="historical.length" class="table-wrap history-table">
      <table>
        <thead>
          <tr>
            <th>Fonte</th>
            <th>Qualidade</th>
            <th>Saúde (%)</th>
            <th>RUL (h calendário)</th>
            <th>Versão</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="point in historical" :key="point.source_event_id">
            <td>{{ new Date(point.sampled_at).toLocaleString('pt-BR') }}</td>
            <td>{{ insightLabels[point.status ?? ''] ?? 'Indisponível' }}</td>
            <td>
              {{
                point.status === 'valid' ? numberText(point.health_score) : '—'
              }}
            </td>
            <td>
              {{
                point.status === 'valid'
                  ? numberText(point.rul_calendar_hours)
                  : '—'
              }}
            </td>
            <td class="model-version">
              {{ point.model_version ?? 'Sem modelo' }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <button
      class="button secondary"
      v-if="historyNext"
      :disabled="historyBusy"
      @click="loadHistory(true)"
    >
      Mais previsões antigas
    </button>
  </section>
</template>
<style scoped>
.insight-section {
  padding: 1.3rem;
  margin-top: 1.3rem;
}
.insight-section h2 {
  margin: 0 0 1rem;
}
select {
  max-width: 420px;
  margin-bottom: 1rem;
}
.model-version {
  overflow-wrap: anywhere;
  font-size: 0.85rem;
}
.metric .model-version {
  font-size: 1rem;
}
.rule-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
  gap: 1rem;
  margin: 1rem 0;
}
.history-table {
  max-height: 330px;
  overflow: auto;
}
input[type='checkbox'] {
  width: auto;
}
form > button {
  margin-right: 0.7rem;
}
</style>

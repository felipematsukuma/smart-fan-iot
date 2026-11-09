<script setup lang="ts">
import { Activity, Thermometer, Wind, Radio } from 'lucide-vue-next';
</script>

<template>
  <div class="page-heading">
    <div>
      <span class="eyebrow">SEU AMBIENTE, EM PERSPECTIVA</span>
      <h1>Visão geral</h1>
      <p class="muted">
        Condições do ambiente e acompanhamento do equipamento.
      </p>
    </div>
    <span class="status-pill neutral"
      ><span class="dot"></span>Sem dados em tempo real</span
    >
  </div>
  <div class="metric-grid">
    <article class="card metric">
      <Thermometer :size="20" /><span>Temperatura interna</span
      ><strong>—<small> °C</small></strong>
      <p>Sem leitura disponível</p>
    </article>
    <article class="card metric">
      <Activity :size="20" /><span>Saúde do compressor</span><strong>—</strong>
      <p>Sem previsão disponível</p>
    </article>
    <article class="card metric">
      <Wind :size="20" /><span>Consumo de energia</span
      ><strong>—<small> kWh</small></strong>
      <p>Aguardando histórico</p>
    </article>
  </div>
  <section class="card empty-state">
    <div class="empty-icon"><Radio :size="30" /></div>
    <h2>Aguardando uma conexão em tempo real</h2>
    <p>
      As leituras do equipamento aparecerão aqui quando a conexão for
      estabelecida.
    </p>
    <span class="muted">Nenhum valor estimado é exibido como leitura.</span>
  </section>
</template>

<script setup lang="ts">
import { Card, Badge } from '../ui/primitives';
import '../ui/task-page.css';
import '../ui/account-pages.css';
</script>
<template>
  <div class="task-page account-page interfaces-page">
    <header class="tp-heading"><h1>Interfaces locais</h1></header>
    <Card class="tp-card local-notice"
      ><h2>Qual computador será acessado?</h2>
      <p>
        <strong
          >127.0.0.1 aponta para o computador onde o navegador está
          aberto.</strong
        >
        No celular, aponta para o próprio celular, e não para o servidor do
        projeto. Abra os links locais no computador que executa o Docker.
      </p>
      <p class="tp-muted">
        Disponibilidade não verificada por esta página. Nenhuma credencial é
        exibida.
      </p></Card
    >
    <div class="local-services">
      <Card class="tp-card"
        ><h2>RabbitMQ Management</h2>
        <p>Filas, consumidores e taxas de mensagens.</p>
        <Badge>Requer configuração administrativa</Badge>
        <p>
          <a
            class="local-link"
            href="http://127.0.0.1:15672"
            target="_blank"
            rel="noopener noreferrer"
            ><span>Abrir RabbitMQ</span
            ><span class="local-address">http://127.0.0.1:15672</span></a
          >
        </p></Card
      >
      <Card class="tp-card"
        ><h2>InfluxDB</h2>
        <p>Leituras e histórico no bucket live.</p>
        <Badge>Requer configuração administrativa</Badge>
        <p>
          <a
            class="local-link"
            href="http://127.0.0.1:8086"
            target="_blank"
            rel="noopener noreferrer"
            ><span>Abrir InfluxDB</span
            ><span class="local-address">http://127.0.0.1:8086</span></a
          >
        </p></Card
      >
      <Card class="tp-card"
        ><h2>API FastAPI</h2>
        <p>Documentação dos endpoints da aplicação.</p>
        <p>
          <a
            class="local-link"
            href="/api/v1/docs"
            target="_blank"
            rel="noopener noreferrer"
            ><span>Abrir documentação da API</span
            ><span class="local-address"
              >/api/v1/docs · mesmo servidor da aplicação</span
            ></a
          >
        </p></Card
      >
      <Card class="tp-card"
        ><h2>PostgreSQL</h2>
        <p>Cadastro, regras e auditoria.</p>
        <Badge>Sem interface web instalada</Badge>
        <p class="tp-muted">
          Consulte pelo terminal local, conforme as instruções do README do
          projeto.
        </p></Card
      >
    </div>
    <Card class="tp-card"
      ><details>
        <summary>Configuração administrativa dos links locais</summary>
        <p>
          RabbitMQ e InfluxDB dependem do override administrativo existente. No
          terminal, na raiz do projeto:
        </p>
        <pre>docker compose -f compose.yaml -f compose.dev.yaml up -d</pre>
        <p>
          O override mantém os bindings em 127.0.0.1. Use as credenciais locais
          de cada serviço. Esta página não ativa interfaces nem verifica se o
          override está em uso.
        </p>
      </details></Card
    >
  </div>
</template>

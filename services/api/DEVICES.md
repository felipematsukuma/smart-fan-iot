# M08 — Cadastro de dispositivos

| Aspecto | Decisão e evidência |
|---|---|
| Domínio | [V] Um perfil split on/off, cinco sensores (corrente, carcaça, vibração, temperaturas interna/externa) e dois atuadores (compressor e ventilador do condensador). IDs derivados, estáveis e únicos; tipos/unidades fixos no perfil |
| Registro inicial | [V] Migração cadastra `ac_01`/`quarto` uma vez. Reiniciar/bootstrap não sobrescreve nome, faixas, revisão ou desativação |
| Metadados | [V] Nome editável; ID/zona/tipo imutáveis para não divergir dos contratos e identidade MQTT. Mudança de perfil exige evolução explícita do contrato |
| Configuração | [V] Tensão/potência nominais, vida útil de referência e cinco faixas saudáveis. Valores iniciais são didáticos e ajustáveis, não especificações de fabricante nem inferências de RUL |
| Versões | [V] Cada alteração exige `expected_revision`; transação bloqueia a linha, acrescenta configuração e auditoria e incrementa revisão. Conflito retorna 409; versões antigas não podem ser alteradas/apagadas pelo usuário da API |
| Desativação | [V] Lógica: novos tickets/comandos são recusados, socket com escopo desativado fecha na revalidação de até um segundo, snapshots excluem o aparelho. Não desliga fisicamente o equipamento, não desfaz comando já enviado e não apaga leituras |
| Telemetria | [V] Gateway consulta registro em cada recepção/despacho. Continua persistindo e confirmando leituras de cadastro desativado, evitando perda e spool infinito. Dispositivo desconhecido/zona divergente é recusado |
| Limite | [V] 100 cadastros no perfil local, paginação por ID (máximo 100 por resposta). Versões paginadas por revisão. Todos os usuários autenticados leem; somente administrador cria/edita/desativa |
| Provisionamento | [N] Cadastrar outro ID não cria simulador, usuário MQTT ou ACL. O Compose atual provisiona somente `ac_01`; outro dispositivo exige credenciais/ACL e instância próprias, sem senha compartilhada ou acesso anônimo |

## API

| Operação | Contrato |
|---|---|
| `GET /api/v1/devices?after=&limit=50` | `items` e `next_cursor`; inclui desativados e separa `boot_id`/`last_sample_at` observados |
| `GET /api/v1/devices/{id}` | Metadados, IDs, unidades, capacidades on/off, revisão e configuração atual |
| `POST /api/v1/devices` | Admin; `id`, `name`, `zone`, `profile` opcional; 201, duplicado 409 |
| `PATCH /api/v1/devices/{id}` | Admin; `expected_revision` e nome, perfil ou enabled; 409 se concorrente |
| `GET /api/v1/devices/{id}/configurations?before=...` | Histórico imutável de configuração, máximo 100; não expõe identidade de autor ao visualizador |
| `GET /api/v1/devices/{id}/metrics` | Histórico permanece consultável após desativação; sem adulterar a store live |

Interface em Dispositivos oferece listagem, formulário com faixas/unidades, detalhes,
desativação/reativação e histórico. Campos não executam comandos nem mudam parâmetros
do simulador. Intertravamentos térmicos e tempo mínimo desligado continuam no aparelho.
Essas faixas poderão alimentar a apresentação/alertas em módulos posteriores, sem
sobrescrever limites físicos ou promover uma configuração sem regra explícita.

## Verificação

[V] Execução local: 184 testes Python, 231 Vitest, 22 integrações PostgreSQL/API/
gateway/WS e cinco percursos Playwright passaram. Concorrência produz um sucesso
e um 409; cadastro desativado fecha socket, bloqueia novo ticket e comando no gateway,
mas mantém consulta histórica. Lint, tipos, formatação e build passaram. O aviso
preexistente do chunk de validação de contratos permanece documentado no M07.

[test-devices.ps1](../../tools/bootstrap/test-devices.ps1) executa integrações em banco descartável, sem
limpar tabelas reais, e o percurso Playwright. O E2E mantém um único cadastro
`ac_e2e_registry`, explicitamente de teste, desativado ao final; repetir não consome
novos IDs. Não executá-lo durante demonstração ativa.

[N] Comando HTTP/controlador completo pertence a M09. Este módulo verifica a rejeição
no gateway e escopo WS; a ação administrativa de desativar não é um comando de parada.
Cena 3D consumirá os mesmos IDs em M15. CI remoto e scans permanecem em M17/M18.

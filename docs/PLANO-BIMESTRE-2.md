# Plano técnico do 2º bimestre — índice de consolidação

Este índice organiza a documentação de planejamento do smart-fan-iot. Toda a documentação deve ser consolidada e revisada antes de qualquer implementação. Não é cronograma nem autorização de desenvolvimento.

## Decisões desta consolidação

- Domínio-alvo: ar-condicionado split residencial convencional liga/desliga, mantendo redução de desperdício e acompanhamento de consumo.
- Equipamento monitorado proposto: compressor; sensores iniciais de corrente, vibração e temperaturas da carcaça, interna e externa.
- Atuadores propostos: compressor automático e ventilador da condensadora controlável pela Web, com intertravamentos. Detalhamento nas etapas seguintes.
- Mesma máquina para execução e apresentação; orçamento de recursos ainda precisa de medição.
- Firmware, circuito e documentação do ventilador permanecem preservados como legado; esta etapa não os modifica.
- Os selos [V], [I] e [N] distinguem evidência, inferência e ausência de confirmação.

## Documentos e fluxo de aprovação

| Etapa | Documento | Branch | Estado |
|---|---|---|---|
| 1 — Inventário | [01-inventario.md](./plano/01-inventario.md) | `docs/plano-etapa-1-inventario` | Redigido para revisão; não implica aceite final |
| 2 — Lacunas | `docs/plano/02-lacunas.md` (a criar) | `docs/plano-etapa-2-lacunas` | Pendente de aprovação |
| 3 — Arquitetura e ADRs | `docs/plano/03-arquitetura.md` e `docs/adr/NNN-*.md` (a criar) | `docs/plano-etapa-3-arquitetura` | Pendente de aprovação |
| 4 — Catálogo de módulos | `docs/plano/04-modulos.md` (a criar) | `docs/plano-etapa-4-modulos` | Pendente de aprovação |
| 5 — Riscos e aceite | `docs/plano/05-riscos-aceite.md` (a criar) | `docs/plano-etapa-5-riscos-aceite` | Pendente de aprovação |

Os documentos ainda inexistentes são indicados sem links para evitar referências quebradas. Cada etapa terá revisão, commits próprios e autorização explícita para push/PR. O usuário realiza o merge. Se a etapa anterior não estiver mergeada, será necessário decidir entre aguardar ou empilhar; não haverá empilhamento silencioso. A atualização deste índice nas etapas seguintes respeitará essa decisão e o fluxo de branches aprovado.

## História preservada

[V] O código-base desta consolidação é `346f7de`, cuja descrição registra o merge da branch de energia. O plano anterior, inclusive seus ADRs incorporados e registro da entrega M00, permanece integralmente acessível em sua [versão histórica no commit 90e2053](https://github.com/felipematsukuma/smart-fan-iot/blob/90e2053/docs/PLANO-BIMESTRE-2.md). A referência foi verificada no histórico Git local; disponibilidade dessa página remota não foi testada nesta etapa.

[V] Permanecem no repositório os documentos originais do ventilador:

- [Visão geral do projeto](../README.md).
- [Firmware e Wokwi](../esp32-simulador/README.md).
- [Aplicação Web](../web-smart-fan-iot/README.md).
- [Revisão técnica de 26/10/2026](./revisao-tecnica-2026-10-26.md).
- [Registro de implementação e validação de 26/10/2026](./implementacao-2026-10-26.md).
- [Núcleo compartilhado M00](../packages/smartfan_common/README.md).

O plano histórico contém autorizações e decisões de uma execução anterior. Elas não substituem as regras desta consolidação: somente documentação por etapa aprovada, nenhuma implementação antes da consolidação completa e nenhuma publicação sem confirmação explícita.

# Plano técnico do 2º bimestre — índice de consolidação

Este índice organiza a documentação de planejamento do smart-fan-iot. Toda a documentação deve ser consolidada e revisada antes de qualquer implementação. Não é cronograma nem autorização de desenvolvimento.

**Estado:** conteúdo das cinco etapas e oito ADRs consolidado documentalmente; revisão final do usuário pendente. A implementação AIoT, os ensaios e o aceite operacional não foram realizados por esta consolidação. O próximo trabalho depende de pedido explícito de módulo; push/PR continuam não autorizados.

**Revisão técnica final:** os três refinamentos aprovados foram incorporados: ativação apenas de modelo aprovado e selecionado no registro; lease renovável com fencing e recuperação segura; UTC real no live, acelerando apenas a degradação do cenário. Especificações em [arquitetura](./plano/03-arquitetura.md), critérios em [módulos](./plano/04-modulos.md) e [aceite](./plano/05-riscos-aceite.md). Nenhum desses controles foi implementado por esta revisão documental.

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
| 1 — Inventário | [01-inventario.md](./plano/01-inventario.md) | `docs/plano-etapa-1-inventario` | Integrado à main local em `8b00596`; aceite operacional pendente |
| 2 — Lacunas | [02-lacunas.md](./plano/02-lacunas.md) | `docs/plano-etapa-2-lacunas` | Integrado à main local em `d3d9230`; aceite operacional pendente |
| 3 — Arquitetura e ADRs | [03-arquitetura.md](./plano/03-arquitetura.md) e [oito ADRs](./plano/03-arquitetura.md#14-adrs-pendências-e-limite-desta-entrega) | `docs/plano-etapa-3-arquitetura` | Integrado à main local em `b266854`; aceite operacional pendente |
| 4 — Catálogo de módulos | [04-modulos.md](./plano/04-modulos.md) | `docs/plano-etapa-4-modulos` | Integrado à main local em `b8c3c45`; aceite operacional pendente |
| 5 — Riscos e aceite | [05-riscos-aceite.md](./plano/05-riscos-aceite.md) | `docs/plano-etapa-5-riscos-aceite` | Conteúdo consolidado; revisão final do usuário pendente |

Conforme atualização do usuário nesta sessão, cada alteração relevante terá branch própria, commits separados e merge local na main ao concluir. Push e PR continuam sujeitos a autorização explícita. Cada etapa parte da main local com os merges anteriores; origin/main ainda não recebeu esses commits, pois não houve push autorizado. Se o remoto divergir, será necessário resolver a base sem reescrever histórico. Não haverá empilhamento silencioso. Os 19 módulos do catálogo identificam unidades sob demanda, sem calendário ou divisão por integrante.

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

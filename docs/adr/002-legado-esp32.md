# ADR 002 — Preservar ESP32/Wokwi como legado

Status: decisão proposta na arquitetura documental; nenhum arquivo movido.

Contexto: [V] O firmware é Arduino/ESP32, configurado em [platformio.ini:1](../../esp32-simulador/platformio.ini#L1); o novo escopo exige simulador Python.

Decisão: manter o diretório esp32-simulador, firmware, diagram.json e documentação como referência histórica, fora da execução AIoT final.

Alternativas: apagar perde evidências do primeiro bimestre; mover imediatamente quebra referências; manter dois simuladores operacionais duplica contratos.

Consequências: simulador Python será único produtor da demonstração final; README futuro marcará claramente legado versus execução atual.

Não manter compatibilidade de controle HVAC no firmware; histórico de energia pode continuar consultável por identidade legada.

Ver [arquitetura, seção 3](../plano/03-arquitetura.md#3-monorepo-e-compatibilidade).

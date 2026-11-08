# ESP32 / Wokwi

Firmware Arduino do ESP32 simulado. Consulte a [visão geral](../README.md) e os [contratos MQTT/REST](../web-smart-fan-iot/README.md).

## Executar

1. Suba a stack com `docker compose up -d --build` em [web-smart-fan-iot/](../web-smart-fan-iot/).
2. Neste diretório, execute `pio run`.
3. Abra [main.cpp](./src/main.cpp) no VS Code e execute **Wokwi: Start Simulator**.
4. **Mantenha a aba do Wokwi ativa e em primeiro plano durante os testes.** Simulação pausada deixa de produzir leituras, mesmo com backend/WebSocket conectados.
5. Abra http://localhost:5173, aguarde presença e teste ON/OFF. O LED representa a carga comutada pelo relé.

[platformio.ini](./platformio.ini) fixa espressif32 6.12.0, framework Arduino e bibliotecas ArduinoJson/PubSubClient. [wokwi.toml](./wokwi.toml) aponta para artefatos esp32dev; RFC2217 na porta 4000 permite observar serial.

## Circuito e hipóteses

[diagram.json](./diagram.json): GPIO23 controla o relé e GPIO34 lê o potenciômetro. Corrente simulada de 0 a 0,8 A, tensão assumida 127 V e fator de potência 0,90. No máximo, a potência esperada é aproximadamente 91,44 W. Zero permanece zero, sem corrente fictícia. Não é sensor calibrado nem circuito para rede elétrica real.

Clique no potenciômetro e use Left/Right, Page Up/Page Down ou Home/End, conforme a [documentação Wokwi](https://docs.wokwi.com/parts/wokwi-potentiometer).

## Rede e controle

Wi-Fi `Wokwi-GUEST`, senha vazia; broker `host.wokwi.internal:1883`. O [guia Wokwi para VS Code](https://docs.wokwi.com/vscode/project-config) descreve o gateway. `localhost` no ESP32 não é a máquina hospedeira.

O loop verifica desligamento local antes das tentativas de rede. Não há laços com delay esperando Wi-Fi/MQTT/NTP; tentativas são temporizadas, com timeout MQTT limitado. NTP sincroniza em segundo plano. Sem relógio sincronizado, horário automático não é garantido. Telemetria continua calculada localmente sem broker, mas não há fila durável para replay.

Comando/configuração são assinados em QoS 1; telemetria é QoS 0, estado/configuração retained. Há verificação de publish e buffer MQTT de 768 bytes. Horário exige dígitos e HH:MM válido; booleanos devem ser JSON boolean. Energia local usa potência anterior e tempo decorrido, inclusive nas transições; o histórico Python é a fonte do painel.

`timestamp` é uptime em ms. `device_epoch_s` é opcional, dependente de NTP. Contadores reiniciam no boot e uptime sofre rollover. Configuração usa Preferences/NVS e pode ser reaplicada pelo tópico retido.

Para outro ESP32, defina `FAN_DEVICE_ID` por build flag como string C++, cadastre o ID na API e selecione-o no painel. Os cinco tópicos usam o mesmo macro; use IDs distintos por dispositivo.

## Verificação

O [registro da implementação](../docs/implementacao-2026-10-26.md) contém compilação, comandos reais pelo dashboard, leitura analógica e desligamento local com broker parado. O agendamento original foi restaurado após o teste. Simulação não fornece garantia de segurança para hardware real.

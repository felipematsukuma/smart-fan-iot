# ESP32/Wokwi — ventilador inteligente

Firmware PlatformIO para um ESP32 simulado pela extensão **Wokwi Simulator for VS Code**.

## Pré-requisitos

- PlatformIO IDE e a extensão `wokwi.wokwi-vscode` instalados;
- manter `platform = espressif32@6.12.0` no `platformio.ini` (núcleo Arduino ESP32 estável);
- licença Wokwi ativada (`Wokwi: Request a New License`);
- stack de `web-smart-fan-iot` em execução, especialmente o Mosquitto na porta `1883`;
- acesso do gateway Wokwi à rede Wi-Fi local do computador.

## Executar na ordem correta

1. Abra **somente** esta pasta no VS Code. Isso evita que o Wokwi selecione o `wokwi.toml` de outro workspace.
2. Inicie a stack do projeto web:

   ```powershell
   cd C:\Users\matsuguma\Projects\web-smart-fan-iot
   docker compose up -d --build
   ```

3. Compile o firmware **antes** de iniciar a simulação:

   ```powershell
   cd C:\Users\matsuguma\Projects\esp32-simulador
   pio run
   ```

   Também é possível executar a task **PlatformIO: Build firmware**.

4. No VS Code, execute `Wokwi: Start Simulator` ou abra `diagram.json` e pressione **Start** na visualização.
5. Depois de alterar `diagram.json`, feche a aba **Wokwi Simulator** e execute o comando novamente: uma sessão já aberta mantém o diagrama anterior em cache.
6. Acompanhe a serial em `rfc2217://localhost:4000` (baud rate `115200`).

> **Importante durante o teste manual:** a extensão Wokwi para VS Code pausa a simulação quando a aba do Wokwi fica oculta. Não abra o frontend como outra aba do mesmo VS Code durante o teste. Mantenha `Wokwi Simulator` visível e abra o dashboard em um navegador externo com `Start-Process http://localhost:5173`. Se a aba Wokwi for ocultada, o ESP32 deixa de enviar telemetria, o broker MQTT pode derrubar a conexão e o frontend exibe “ESP32 aguardando Wokwi visível”.

A extensão exige internet para carregar/validar a simulação, mesmo quando o firmware usa apenas a rede local.

## Validação esperada

O monitor serial deve mostrar, nesta ordem:

```text
WiFi Conectado!
Relógio sincronizado.
Conectando ao Broker MQTT... Conectado!
Estado publicado: ...
Telemetria enviada: ...
```

A telemetria é publicada a cada 2 segundos, mesmo com o ventilador desligado. Ao ligar, o LED verde no diagrama deve acender junto com o relé. O atributo `transistor: "npn"` torna o módulo Wokwi **ativo por HIGH**, igual a `digitalWrite(PIN_RELAY, HIGH)` no firmware.

No `board-esp32-devkit-c-v4`, os terminais do GPIO23 e GPIO34 são `esp1:23` e `esp1:34`; não use `esp1:D23` ou `esp1:D34`. Nessa placa, `D2` também não significa GPIO2, mas GPIO9.

## Tópicos MQTT

| Topico | Direção | Retida | Finalidade |
|---|---|---:|---|
| `devices/esp32_fan_01/command` | backend → ESP32 | não | `ON`, `OFF`, `AUTO` e `MANUAL` |
| `devices/esp32_fan_01/config/set` | backend → ESP32 | sim | horário e modo automático |
| `devices/esp32_fan_01/telemetry` | ESP32 → backend | não | medições a cada 2 s |
| `devices/esp32_fan_01/state` | ESP32 → backend | sim | estado confirmado do relé |
| `devices/esp32_fan_01/config` | ESP32 → backend | sim | configuração confirmada |

`config/set` e `config` são tópicos diferentes de propósito. Publicar e assinar o mesmo tópico de configuração faz o ESP32 receber a própria mensagem e entrar em loop.

## Diagnóstico de rede

O firmware usa `host.wokwi.internal:1883` para alcançar o Mosquitto exposto pelo Docker no computador atual. Esse hostname é resolvido pelo gateway Wokwi e não depende do endereço IP DHCP da máquina.

Para validar o broker a partir do computador, use o IP atual:

```powershell
Get-NetIPAddress -AddressFamily IPv4
Test-NetConnection <IP_ATUAL> -Port 1883
```

Se `TcpTestSucceeded` for `False`, o Mosquitto/Docker não está expondo a porta 1883 nesse endereço. Não é necessário alterar o firmware quando o IP mudar; apenas recompile se `mqtt_server` for modificado.

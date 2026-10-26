# ESP32/Wokwi — Firmware do ventilador

Firmware PlatformIO para um ESP32 simulado pela extensão **Wokwi Simulator for VS Code**.

O firmware conecta o ESP32 ao Mosquitto local, publica telemetria e estado, recebe comandos de liga/desliga e aplica o agendamento de desligamento configurado pelo dashboard.

## Visão geral

```text
Dashboard/REST
      │  comando ON/OFF e agendamento
      ▼
FastAPI ──► Mosquitto ──► ESP32/Wokwi
                  ▲              │
                  └──────────────┘
                 telemetria/estado
```

- Controlador: `esp32dev`
- Placa simulada: `board-esp32-devkit-c-v4`
- Relé: GPIO23
- Sensor/potenciômetro: GPIO34
- Broker: `host.wokwi.internal:1883`
- Tópicos: `devices/esp32_fan_01/...`

## Pré-requisitos

- Docker Desktop em execução;
- PlatformIO CLI ou PlatformIO IDE;
- extensão `wokwi.wokwi-vscode` instalada;
- licença Wokwi ativada;
- Private IoT Gateway disponível na extensão do VS Code;
- stack `web-smart-fan-iot` em execução;
- internet disponível para a extensão Wokwi e para o NTP.

A plataforma do firmware é fixada em `espressif32@6.12.0` no `platformio.ini`.

## Execução

### 1. Subir a stack web

Abra um PowerShell na raiz do repositório:

```powershell
cd C:\Users\matsuguma\Projects\smart-fan-iot\web-smart-fan-iot
docker compose up -d --build
docker compose ps
```

### 2. Compilar o firmware

```powershell
cd C:\Users\matsuguma\Projects\smart-fan-iot\esp32-simulador
pio run
```

O firmware gera:

```text
.pio/build/esp32dev/firmware.elf
.pio/build/esp32dev/firmware.bin
```

### 3. Iniciar o Wokwi

No VS Code:

1. abra a pasta `esp32-simulador`;
2. pressione `F1`;
3. execute **Wokwi: Start Simulator**;
4. aguarde a conexão do ESP32 com o broker.

Se `diagram.json` foi alterado, feche a aba do simulador e execute o comando novamente para recarregar o diagrama.

### 4. Abrir o dashboard

A aba **Wokwi Simulator** precisa permanecer visível durante o teste. Para evitar que a simulação seja pausada, abra o frontend em um navegador externo:

```powershell
Start-Process http://localhost:5173
```

> A extensão Wokwi pausa a simulação quando a aba do simulador fica oculta. Nesse caso, o WebSocket do FastAPI pode continuar conectado, mas o ESP32 para de enviar telemetria e o dashboard exibe `ESP32 aguardando Wokwi visível`.

## Rede e gateway Wokwi

O firmware não utiliza mais um IP fixo do computador. A configuração é:

```cpp
const char* mqtt_server = "host.wokwi.internal";
```

Esse hostname é resolvido pelo Private IoT Gateway do Wokwi e aponta para o computador atual, independentemente do endereço DHCP.

Para validar a porta do broker no computador:

```powershell
Get-NetIPAddress -AddressFamily IPv4
Test-NetConnection <IP_ATUAL> -Port 1883
```

O resultado esperado é:

```text
TcpTestSucceeded : True
```

Se a porta estiver fechada, verifique:

```powershell
docker compose ps
docker compose logs --tail=100 mosquitto
```

O hostname `host.wokwi.internal` é indicado para o gateway privado do Wokwi no VS Code. Ele não deve ser usado como substituta de `localhost` em um ESP32 físico.

## Pinagem e diagrama

No `board-esp32-devkit-c-v4`, use os terminais corretos do `diagram.json`:

| Função | GPIO | Terminal no diagrama |
|---|---:|---|
| Relé | 23 | `esp1:23` |
| Sensor/potenciômetro | 34 | `esp1:34` |

Atenção:

- não use `esp1:D23` ou `esp1:D34`;
- nesse board, `D2` representa GPIO9, não GPIO2;
- o relé usa `transistor: "npn"`, ativo por HIGH;
- `digitalWrite(PIN_RELAY, HIGH)` deve acender o LED verde do diagrama.

## Tópicos MQTT

| Tópico | Direção | Retido | Finalidade |
|---|---|---:|---|
| `devices/esp32_fan_01/command` | backend → ESP32 | não | `ON`, `OFF`, `AUTO` e `MANUAL` |
| `devices/esp32_fan_01/config/set` | backend → ESP32 | sim | horário e modo automático |
| `devices/esp32_fan_01/telemetry` | ESP32 → backend | não | telemetria a cada 2 s |
| `devices/esp32_fan_01/state` | ESP32 → backend | sim | estado confirmado do relé |
| `devices/esp32_fan_01/config` | ESP32 → backend | sim | configuração confirmada |

`config/set` e `config` são tópicos diferentes de propósito. Publicar e assinar o mesmo tópico de configuração faz o ESP32 receber a própria mensagem e entrar em loop.

## Telemetria e estado

A telemetria é publicada a cada 2 segundos, mesmo com o ventilador desligado. Exemplo:

```json
{
  "device_id": "esp32_fan_01",
  "is_on": true,
  "auto_mode": true,
  "shutdown_time": "03:00",
  "voltage_rms": 127,
  "current_a": 0.28,
  "power_w": 32.0,
  "total_energy_wh": 1.25,
  "fan_on_time_ms": 12000
}
```

O estado é publicado após uma mudança de comando ou configuração:

```json
{
  "device_id": "esp32_fan_01",
  "is_on": true,
  "auto_mode": true,
  "shutdown_time": "03:00",
  "fan_on_time_ms": 12000,
  "total_energy_wh": 1.25
}
```

## Validação

O monitor serial esperado mostra:

```text
WiFi Conectado!
Relógio sincronizado.
Conectando ao Broker MQTT... Conectado!
Estado publicado: ...
Telemetria enviada: ...
```

Para acessar a serial:

```text
rfc2217://localhost:4000
```

Baud rate: `115200`.

Uma execução é considerada válida quando:

- o broker mostra o cliente `esp32_fan_01` conectado;
- a telemetria aparece no InfluxDB;
- o estado no PostgreSQL é atualizado;
- o dashboard mostra `ESP32/Wokwi online`;
- `ON` e `OFF` são confirmados pelo estado do ESP32.

## Diagnóstico

### O dashboard mostra WebSocket online, mas ESP32 offline

1. confirme se a aba **Wokwi Simulator** está visível;
2. confirme se a simulação está executando;
3. confira se o firmware foi recompilado com `pio run`;
4. confira se o broker está acessível em `host.wokwi.internal:1883`;
5. verifique se o container do Mosquitto está `Up`.

### O ESP32 não conecta

```powershell
docker compose logs --tail=100 mosquitto
Test-NetConnection <IP_ATUAL> -Port 1883
```

Verifique também se a extensão está usando o Private IoT Gateway. O hostname `host.wokwi.internal` é específico desse ambiente.

### O relé não acende

- confirme `PIN_RELAY = 23`;
- use `esp1:23` no diagrama;
- mantenha `transistor: "npn"`;
- confira se o comando foi confirmado pelo tópico `state`;
- reinicie o Wokwi após alterar `diagram.json`.

## Git

O repositório usa `main` como versão estável. Alterações de interface e novas regras de negócio devem ser feitas em uma branch separada:

```powershell
git switch -c feature/dashboard-energy-v2
git push -u origin feature/dashboard-energy-v2
```

Não versionar `.pio/`, `.env`, `node_modules/`, `__pycache__/`, `wokwi.vcd` ou arquivos locais gerados por ferramentas.

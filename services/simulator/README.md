# Simulador Python HVAC — M03

Dispositivo inicial ac_01/quarto: cinco sensores (corrente, vibração, carcaça, temperatura interna e externa), dois atuadores e modelo térmico simples de split convencional. Firmware/circuito ESP32 permanecem como legado. O simulador não diagnostica aparelho real e não publica labels, dano latente ou vida útil verdadeira.

## Execução

Na raiz, após preparar os segredos:

```powershell
tools/bootstrap/bootstrap.ps1 -Start
docker compose ps simulator
docker compose logs simulator
```

O serviço usa a imagem Python compartilhada, UID 10001, 128 MiB, 0,5 CPU, volume simulator_spool e somente a credencial MQTT do próprio dispositivo. Não publica porta no host. Health interno 9000 separa processo de prontidão MQTT/spool. Sem gateway M04, mensagens ficam no spool e são reenviadas; isso não representa falha de persistência silenciosa.

Parâmetros opcionais no ambiente do serviço: SIM_SCENARIO (healthy, mechanical_wear, heat_transfer_loss), SIM_INITIAL_DAMAGE (0..1), SIM_DAMAGE_RATE (degradação por hora de compressor ligado), SIM_DEVICE_ID, SIM_ZONE (padrão quarto), SIM_SPOOL e SIM_INTERVAL_SECONDS (0,2..2 s, padrão 2 s). Usar outro ID exige provisionar sua conta/ACL e cadastrar a mesma zona no backend; não há fallback anônimo. Alteração do cenário live exige recriar o processo; a Web configura dados sintéticos e regras/atuadores, sem trocar esse cenário.

A cadência mínima de 0,2 s mantém no máximo 300 observações por janela causal de 60 s. Há uma amostra por vencimento, sem rajadas para compensar atraso; seus timestamps são UTC reais. A resolução da simulação muda, sem acelerar vida útil, proteções ou relógio. A configuração rápida serve também aos ensaios de carga com vários dispositivos reais do simulador Python.

[V] Ensaio em container Python 3.11.18 com `SIM_INTERVAL_SECONDS=0.2`: um assinante MQTT autenticado recebeu 47 amostras únicas em 9,870 s, taxa observada 4,660/s e `clock_scale=1`, em um único boot. A taxa inclui o custo de persistência/transporte, sem promessa de frequência exata. 18 testes do simulador e mypy passaram. Isso não substitui o ensaio sustentado de capacidade agregada do M18.

O relógio live é UTC real e clock_scale=1. Cenário demonstrativo pode acelerar a taxa de degradação, nunca timestamps, expiry ou proteção de partida. Temperatura externa tem ciclo diário/sazonal; carga elevada não rotula automaticamente defeito. Configurações e fórmulas são hipóteses didáticas: tensão 220 V, fator 0,93, modelo de corrente e inércia térmica; potência é derivada, não sexto sensor.

## Estado, segurança e entrega

- SQLite WAL/synchronous FULL contém estado físico simulado, ledger de comandos e spool. Reboot gera boot_id novo e mantém ambos os atuadores desligados, preservando desgaste, configurações e watermark de revisão.
- Amostra é serializada e persistida antes de publicar MQTT QoS1. PUBACK não remove spool: apenas receipt autenticado do gateway após aceitação durável. Reenvio a cada >=5 s conserva bytes/ID; filas do cliente são limitadas.
- Comando/efeito/ACK e estado retido são uma transação SQLite. Repetição devolve o ACK original; mesmo ID com bytes diferentes é recusado. Quota impede efeito não registrado, pausa coleta e mostra readiness degradada; dados não aceitos não são inventados.
- Target boot, expiry e revisão são verificados. Compressor nunca liga sem ventilador; rearme após parada espera 180 s. Proteção local desliga compressor a 85 °C, liberando lock abaixo de 75 °C; são limites didáticos, não especificação de fabricante.
- OFF manual bloqueia refrigeração automática; somente intenção explícita da API libera bloqueio. Mudanças automáticas de controle não desfazem essa escolha silenciosamente.
- Estado device.state v2.1 acrescenta last_revision obrigatório para recuperação do backend após restore. Leitores novos preservam leitura v2.0 (watermark desconhecido), sem adivinhar revisão zero. ACK/telemetria continuam v2.0; produtores/consumidores da nova família são atualizados pela mesma imagem.
- Ledger de comandos retido 7 dias; após esse período, boot/expiry/revisão continuam impedindo execução antiga. Spool pendente não é removido por limpeza. LWT retido contém horário de configuração; gateway deve derivar disponibilidade observada, sem tratá-lo como leitura fresca.

## Testes e limite do aceite

```powershell
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m pytest services/simulator/tests -q
tools/bootstrap/test-simulator.ps1
```

Testes locais verificam efeitos, degradação progressiva/reproduzível, proteção, cooldown, bloqueio manual, expiry/revisão, conflito de ID, quota, restart e watermark. A integração usa Mosquitto real, telemetria/estado reais, comando e ACK, consumo do ventilador e receipt apoiado em transação PostgreSQL/outbox AMQP reais.

O cliente de gateway desse teste é fixture explícita, não o serviço M04: não constitui aceite Web→IoT, autenticação da API ou inferência. Ele persiste e encaminha uma amostra real antes de emitir receipt, preservando a garantia da borda; não drena filas de negócio. O teste retorna o ventilador a OFF ao encerrar. CI remoto, carga/chaos completo e os demais serviços seguem pendentes.

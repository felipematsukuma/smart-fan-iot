# Infraestrutura AIoT — M01

O Compose da raiz executa a infraestrutura nova em projeto/volumes `smartfan-aiot`, separado do legado em [web-smart-fan-iot](../web-smart-fan-iot/README.md). API, frontend e consumidores HVAC serão acrescentados nos módulos seguintes; esta entrega não satisfaz sozinha o aceite integrado do requisito 19.

M02 amplia o bootstrap com contas PostgreSQL por serviço e migrações Alembic do schema transport. Os segredos administrativos continuam somente no processo privilegiado de instalação. Testes reais de durabilidade: `tools/bootstrap/test-reliability.ps1`; esse teste usa banco descartável e não remove dados da aplicação.

## Preparar e executar

Na raiz, com Docker Desktop ativo e o ambiente Python de desenvolvimento do backend disponível:

```powershell
tools/bootstrap/bootstrap.ps1 -Start
docker compose ps -a
docker compose logs bootstrap ollama-init
```

O script protege a pasta local de segredos com ACL do usuário no Windows, gera credenciais aleatórias sem sobrescrever as existentes, valida o Compose e sobe os serviços. Em Unix, `python infra/prepare.py` prepara a pasta privada; os arquivos individuais são read-only e só entram no container que precisa deles. Nenhum valor deve ser versionado ou mostrado em logs. Arquivos ignorados em secrets e dados do legado não devem ser apagados para repetir setup.

Runtimes PostgreSQL, InfluxDB, RabbitMQ, Mosquitto e Ollama executam sem root. `volume-init` é um processo único com root que atribui o dono somente às raízes dos volumes nomeados deste projeto; não percorre diretórios do host. O bootstrap Python verifica filas quorum e ausência de guest e cria o bucket lab de 7 dias; live começa com 30 dias. Alterar ambiente não rotaciona automaticamente credenciais em volumes já inicializados.

Sem portas publicadas por padrão nesta etapa. UIs administrativas opcionais, apenas em loopback:

```powershell
docker compose -f compose.yaml -f compose.dev.yaml up -d
```

RabbitMQ management em http://127.0.0.1:15672 e InfluxDB em http://127.0.0.1:8086. Nomes de usuários e seus segredos estão separados por serviço nos arquivos locais; não há usuário/senha padrão de demonstração. Credenciais administrativas nunca serão montadas nos workers de negócio.

## Brokers e permissões

- RabbitMQ 4.4.0 management, definido por digest; exchanges topic events/jobs/dlx, oito filas quorum, políticas at-least-once DLX e reject-publish. Conta por serviço com configure negado e topic permissions; api-monitor não altera recursos. O consumidor da DLQ não é iniciado automaticamente.
- Usar `definitions.import_backend = local_filesystem` e `definitions.local.path`. Nesta versão, `management.load_definitions` ficou aguardando pool de importação no boot; a importação nativa resolveu sem apagar volumes. Testar readiness real, não apenas processo aberto.
- Mosquitto sem anônimo, ACL por dispositivo/categoria e usuário separado de health. Hash de senha é PBKDF2-SHA512, validado pela autenticação real do broker. CLI de health publica apenas em namespace próprio; MQTT/AMQP não são expostos no host.
- Configuração de infraestrutura não é autorização de controle físico. Boot/revisão/expiry, receipts e inbox/outbox são entregas dos módulos seguintes.

## Modelo e recursos

`ollama-init` baixa/verifica o modelo efetivo `llama3.2:1b-instruct-q4_K_M`, fixado por digest no pacote compartilhado e registrado no volume. O aquecimento ocorre no primeiro chat sob lease, evitando concorrência com jobs. Cache anterior do candidato 3B permanece preservado. Primeiro download precisa de rede; apresentação posterior usa cache, sem fallback cloud. [M16: escolha, streaming e limites](../services/api/ASSISTANT.md).

Máquina observada: Docker dispõe de aproximadamente 7,6 GiB; a configuração do host não foi alterada. Limites por container não são garantias de consumo agregado. Modelo usa contexto 2048, uma requisição e no máximo um modelo carregado; concorrência com treino ainda será controlada pelos módulos correspondentes.

## Validação e recuperação

```powershell
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m pytest infra/tests -q
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m ruff check infra
web-smart-fan-iot/backend/.venv/Scripts/python.exe -m infra.verify
docker compose config --quiet
docker compose restart
```

Testes de preparo verificam credenciais preservadas, hashes, limites de permissões e ausência de guest na definição. O aceite real também verifica estados healthy, exit 0 dos processos únicos, filas e políticas reais e recusa de MQTT anônimo. Scan de imagens/CI e todos os consumidores da aplicação ainda precisam de suas evidências; não declarar esses itens aprovados por apenas construir imagens.

Verificação real desta entrega: cinco serviços healthy, bootstrap/model-init com exit 0, oito filas quorum, usuários separados sem guest, políticas instaladas, autenticação e ACL MQTT negativas e nenhuma porta publicada no Compose padrão. Modelo 3b baixado, digest registrado no volume e warmup repetido usando o cache. Observação do teste: mosquitto_pub pode retornar 0 mesmo ao receber PUBACK MQTT5 Not Authorized; o verificador confere também a razão do broker, para não gerar falso positivo. O teste administrativo de AMQP completo será ampliado com o cliente e a recuperação em M02/M04.

Para parar: `docker compose stop`. Retomar: `docker compose up -d`. Não usar down -v como procedimento de recuperação. Antes de rotacionar: preparar nova credencial, atualizar o serviço e consumidor, testar e só então revogar antiga, sem imprimir valores. Backup/restore integrado será implementado em M18.

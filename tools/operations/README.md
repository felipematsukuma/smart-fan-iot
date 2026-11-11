# Backup e restauração local — M18

Execute da raiz com o Python do ambiente de desenvolvimento e Docker disponível. Use o Compose normal, com credenciais já geradas. Os comandos não publicam dados nem enviam mensagens para serviços externos.

| Comando | Resultado |
|---|---|
| `python -m tools.operations.backup backup` | Pausa a aplicação, cria uma cópia privada e retoma os serviços que estavam ligados |
| `python -m tools.operations.backup trial --leave-stopped` | Cria backup, restaura em volumes novos, verifica dados/WebSocket e encerra as duas pilhas |
| `python -m tools.operations.backup restore evidence/backups/<copia>` | Com a origem parada, restaura em projeto novo e mantém a cópia disponível para inspeção |
| `restore ... --verify-web` | Também testa login e frame real com a versão registrada do modelo |
| `--password-file <arquivo-privado>` | Usa a senha administrativa atual nos testes Web, se ela mudou desde o seed |

A restauração usa apenas `127.0.0.1:18080` para o frontend; `--port` escolhe outra porta local. O relatório identifica projeto e configuração. Para parar a cópia: `docker compose -p <projeto> -f <configuracao> stop`. Não use exclusão de volumes como procedimento de recuperação.

## Contrato da cópia

- Todos os volumes nomeados do projeto: PostgreSQL, InfluxDB, RabbitMQ, Mosquitto, spool do simulador, modelos/datasets, cache Ollama, credenciais de escopo e lock da API. Configurações e arquivos de segredos usados como binds acompanham a cópia.
- O diretório recebe ACL restrita no Windows ou modo 0700 no Linux. Arquivos e manifestos privados ficam em `evidence/backups/`, ignorado pelo Git. Contêm dados e credenciais: não são artefatos públicos de CI.
- Jobs em execução ou aguardando impedem o backup. A API é parada antes da conferência para impedir novas solicitações. Os bancos são encerrados antes da leitura dos volumes.
- A compactação percorre blocos e o arquivo binário vai direto ao disco; não entra no console. SHA-256, tamanhos e contagens são registrados privadamente. Tags locais próprias preservam as imagens do snapshot.
- O operador não-root de cada volume faz a leitura. Na restauração, um helper curto usa root com a capacidade CHOWN para inicializar somente os volumes novos. Os serviços mantêm seus usuários não-root.
- Caminhos externos, links absolutos, diretórios por symlink e cadeias de links são recusados. Links relativos diretos para arquivos do próprio volume são preservados, incluindo os manifestos do Ollama.

## Verificação da restauração

Antes de criar volumes, o comando verifica configuração, arquivos, imagens e cobertura de todos os volumes. Os destinos têm nomes novos e rótulos do projeto de restauração; a origem não é sobrescrita. O hostname fixo do RabbitMQ permanece igual, em rede separada, preservando sua identidade persistida.

Com apenas os bancos da cópia ligados, compara contagem e digest de todas as linhas das tabelas da aplicação/transporte, contagens de todos os campos dos buckets de usuário e digest de amostras históricas. Confere também a seleção e os bytes dos modelos aprovados. Buckets internos de monitoramento não entram na comparação lógica, pois o próprio servidor os atualiza; seus arquivos permanecem no arquivo físico.

Sessões e tickets anteriores são invalidados na cópia e a operação entra na auditoria. O ensaio Web usa autenticação nova e exige um frame recente, recebido por WebSocket, com o modelo registrado. Quando o ensaio cria um backup da aplicação ligada, também verifica que seu JWT anterior é recusado na cópia. A senha inicial só serve para esse teste enquanto corresponder à senha atual; restauração de dados não depende dela.

## Limites operacionais

NF11 exige restauração em até 30 minutos e ponto de recuperação de até 24 horas. O relatório mede a restauração usada no ensaio; manter a periodicidade de cópias é uma política operacional, sem agendamento automático neste utilitário. A política deve produzir uma cópia diária quando houver dados novos.

A cópia usa as imagens preservadas no cache local da mesma máquina. Não prova recuperação após perda do computador ou remoção desse cache; nesses casos, será necessário reconstruir a versão do código correspondente. Volumes de restauração ficam parados para inspeção, e a exclusão deles exige identificar seus rótulos e confirmar que não são volumes originais. Logs de console e volumes anônimos não utilizados não fazem parte do estado de negócio restaurado.

O [ensaio real de 11/11/2026](../../docs/quality/2026-11-11-m18-backup.md) restaurou 12 volumes em 5 min 58 s, conferiu 39 tabelas, dois buckets e o modelo em uso via WebSocket, além da revogação da sessão antiga. Os tempos e o escopo estão registrados; os outros critérios do M18 permanecem separados. Consulte as [metas e critérios de aceite](../../docs/plano/05-riscos-aceite.md) e os [gates de qualidade](../quality/README.md).

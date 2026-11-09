# API, acesso e auditoria — M06

[V] FastAPI em `/api/v1`, com PostgreSQL, sessões revogáveis e interface Vue 3/TypeScript.
O Compose publica somente o Nginx em [http://localhost:8080](http://localhost:8080),
vinculado a `127.0.0.1`. API e proxy executam como UID 10001/101, sem root.

## Primeiro acesso

Execute `powershell -ExecutionPolicy Bypass -File tools/bootstrap/bootstrap.ps1 -Start`
na raiz. O bootstrap gera arquivos privados, aplica migrations e cria três contas:

| Conta | Papel | Arquivo local da senha inicial |
|---|---|---|
| admin | administrador | `secrets/initial_admin_password` |
| operador | operador | `secrets/initial_operator_password` |
| visualizador | visualizador | `secrets/initial_viewer_password` |

[V] Os arquivos são ignorados pelo Git; nenhum valor é exibido pelo bootstrap.
Não há senha fixa. O seed mantém IDs, contas desativadas e senhas alteradas pelo usuário.
Reajuste do custo bcrypt só ocorre no seed quando a senha ainda corresponde ao arquivo
inicial. O administrador pode criar contas, alterar papel, desativar e redefinir senhas
na página **Usuários**. Alterar o próprio acesso exige novo login. Não se desativa nem
se rebaixa o último administrador ativo.

## Contratos e permissões

| Endpoint | Permissão e resultado |
|---|---|
| POST `/auth/login` | Público; JWT em resposta, senha nunca retornada |
| GET `/auth/me`; POST `/auth/logout` | Sessão válida; logout revoga no PostgreSQL |
| POST `/auth/ws-ticket` | Sessão e Origin permitidos; opaco, 30 s, hash em banco, uso único |
| GET/POST `/users`; PATCH `/users/{id}` | Somente administrador; sem hash/senha nas respostas |
| GET `/audit` | Somente administrador; paginação e autoria verificada |
| GET `/api/v1/openapi.json`, `/api/v1/docs` | Especificação pública, incluindo erros RFC 7807; docs sem CDN/scripts |
| GET `/health`, `/ready` | Rotas internas; liveness independente do banco, readiness verifica schema/PG |

[V] Rotas abreviadas de auth/users/audit usam prefixo `/api/v1`. Erros são
`application/problem+json` com `correlation_id`; validação não devolve os valores
recebidos. Listagens usam cursor `(created_at,id)`, padrão 50 e máximo 100.
Corpo limitado a 16 KiB na API; o proxy também possui limite e erros JSON próprios.

[V] JWT HS256: 30 min, issuer/audience fixos, sub/role/jti/auth_version/iat/exp
obrigatórios, tolerância máxima de 30 s. Cada operação confirma usuário ativo, papel,
versão e sessão no banco. Não há refresh. Token fica somente na memória do navegador,
em Authorization Bearer; recarregar a página exige entrar novamente. Logout sem conexão
limpa o acesso local e informa que a revogação não pôde ser confirmada.

[V] bcrypt usa custo **11**, ajustado na mesma máquina: 20 verificações por custo,
p95 de 354,79 ms no custo 12 e 158,04 ms no custo 11, API limitada a uma CPU.
Exige 12 caracteres nas novas senhas, até 72 bytes UTF-8, e rejeita NUL/truncamento.
Cinco falhas por identidade ou 30 por IP em 15 min retornam 429; reservas transacionais
também limitam verificações concorrentes. Há atraso progressivo. IP/identidade são HMACs;
X-Forwarded-For arbitrário é ignorado. No proxy local, clientes compartilham seu limite
por IP, escolha conservadora para execução em uma única máquina.

[V] Auditoria é append-only para a conta runtime, sem UPDATE/DELETE. Tentativa de login
negada não atribui autoria à conta informada. Logs são JSON allowlist, sem corpo, senha,
JWT ou query string. CORS/Origin são restritos; CSP impede scripts externos/inline;
o proxy resolve novamente o endereço da API após recriação de container.

## Verificação e limites

[V] `tools/bootstrap/test-api.ps1` executa testes reais em banco descartável e Playwright
no serviço local. Instale Chromium antes com `npm exec playwright -- install chromium`
na pasta do frontend. Traces e vídeos estão desligados para não gravar credenciais.
São cobertos os três papéis, 401/403/429, revogação/expiração, ticket concorrente de uso
único, auditoria imutável, cursor, corpo/erros, seed idempotente e preservação de tabela
legada. Há testes de teclado/tela pequena e verificações de ausência de erros JS/CSP.

[V] O modo AIoT é selecionado na imagem por `VITE_APP_MODE=aiot`; o desenvolvimento/build
legado permanece no modo padrão. Páginas de telemetria não inventam valores: conexão
WebSocket/dashboard funcional pertence a M07 e frames ao M13. As regras e o comando
manual pertencem a M09; fluxo de dados e cena 3D ainda não são certificados por M06.
[N] CI remoto, scan de imagens, limpeza/backup operacional e hardening integrado seguem
pendentes. O audit npm registra 11 alertas moderados na cadeia de ferramentas de lint;
neste módulo não foi aplicado downgrade nem atualização forçada de dependências.

Remover a API elimina autorização, auditoria e a fronteira REST; remover o proxy elimina
o acesso same-origin à Web; Vue Router mantém navegação e guards, complementando a
autorização do servidor.

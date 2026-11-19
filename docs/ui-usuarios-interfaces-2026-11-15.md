# UI/UX — Usuários e Interfaces locais — 15/11/2026

## Escopo
Usuários e depois Interfaces locais, reutilizando os componentes e o padrão visual aprovados. Nenhuma funcionalidade adicional de gestão, dependência nova, alteração no backend/LLM, porta, binding ou interface instalada. Sem commit ou publicação remota. Aguardar avaliação visual antes da expansão.

## Usuários
- Nome, papel, habilitação e ação Editar em tabela desktop e cartões compactos no celular. Vinte registros por página e paginação mantidos. Não há ocultação de contas desabilitadas nem exclusão de registros.
- Formulário existente com rótulos, erros nativos próximos aos campos e erro de nome duplicado associado ao campo. Validações mantidas: caracteres do nome, máximo de 64 caracteres, senha mínima de 12 caracteres e teto de 72 bytes UTF-8. Senha opcional na edição; não preenchê-la não envia password no PATCH.
- Senhas são sempre limpas após tentativa de salvamento, troca de conta em edição, cancelamento e saída da página. Respostas do servidor nunca são usadas para preencher senha. Nome, papel e habilitação permanecem após erros. Não se adicionou armazenamento de senhas.
- Desativação de uma conta habilitada exige diálogo identificando a conta e avisando que as demais mudanças do formulário serão salvas. Escape/Cancelar não envia PATCH. Confirmação envia o mesmo contrato existente.
- Último administrador: autoridade permanece na proteção transacional do backend, que conta administradores globalmente. Não se presume que a página atual contenha todos os administradores. Recusa 409 exibida sem descartar edição nem encerrar sessão.
- Própria conta identificada na lista e formulário; salvamento bem-sucedido conserva o encerramento de sessão existente. Nenhuma nova proibição de editar a própria conta foi inventada.
- Atualização mantém formulário e cursor. Erro de paginação conserva página atual; histórico de navegação só muda após sucesso. Edição mantém a página atual depois de salvar; criação mantém retorno à primeira página como antes.

## Interfaces locais
- Links existentes agrupados por serviço, finalidade e endereço: RabbitMQ Management, InfluxDB e documentação FastAPI. PostgreSQL permanece informativo, sem interface web instalada.
- RabbitMQ/InfluxDB indicam dependência de configuração administrativa; não afirmam que o serviço está disponível ou indisponível. O comando existente do override permanece em expansível, sem execução pela interface.
- Aviso explícito: 127.0.0.1 aponta para a máquina onde o navegador está aberto. No celular não corresponde ao servidor do projeto. Documentação da API mantém URL relativa, no mesmo servidor da aplicação.
- Nenhuma sondagem de disponibilidade, credencial, porta ampliada, binding novo ou interface administrativa instalada.

## Verificações reais
- Build Docker com vue-tsc e Vite aprovado; typecheck e lint aprovados.
- Login administrador e consultas GET reais da lista de contas para capturas. O teste bloqueia qualquer método diferente de GET nas rotas de usuários. Edição apenas aberta e cancelada, sem salvar conta real.
- Desktop 1440 × 1000 e celular 390 × 844: capturas inspecionadas, nenhuma rolagem horizontal da página, sem erros JavaScript observados. Toque em Editar foca o papel no formulário, senha vazia. Expansível de configuração acessível por Enter; links acessíveis por foco. Hrefs existentes conferidos, sem sondar 15672 ou 8086.
- Contraste DOM mínimo: Usuários 6,10:1; Interfaces locais 5,47:1, nas duas resoluções. Fonte mínima medida 14 px; controles e links mantêm área de pelo menos 44 px via CSS. Registros JSON junto às capturas.

## Fixtures — nenhuma conta real alterada
- Criação inválida bloqueada no navegador; limite UTF-8 validado; nome duplicado mantém nome/papel e limpa senha; sucesso simulado com feedback.
- Resposta de criação/consulta inclui campo password propositalmente indevido como marcador: campo de senha permanece vazio ao editar. Não houve repovoamento nem renderização desse valor.
- Edição sem senha envia somente role/enabled. Desativação por confirmação simulada; Escape cancela, devolve foco e não envia requisição. Sucesso exibe habilitação confirmada pela consulta simulada.
- Recusa do último administrador simulada para redução de papel e desativação da própria conta. Edição preservada e sessão não encerrada no erro. PATCH bem-sucedido simulado da própria conta encerra apenas a sessão local da aplicação, conforme comportamento existente.
- Erro de consulta preserva página e campos não sensíveis; retorno de página com erro não descarta histórico.
- Quatro cenários Playwright aprovados em 8,3 s. Cenário do último administrador ampliado para incluir desativação e repetido com sucesso em 2,7 s. Não equivale a novo teste da proteção transacional ou revogação de sessões no backend.

## Limitações e próxima etapa proposta
Sem criação, edição ou desativação de conta real. Papéis e guards administrativos preservados; não se repetiu ensaio de autorização do backend. Celular validado em Chromium com toque emulado, sem aparelho físico ou leitor de tela. Disponibilidade dos serviços locais intencionalmente não verificada. Nomes de contas antigas de testes aparecem nas capturas porque a lista real não foi filtrada nem os registros removidos.

Aguardar avaliação. Próxima etapa proposta, sem implementação: Assistente (composição, contexto estruturado, streaming e estados de indisponibilidade, mantendo a pendência semântica do LLM) e Cena 3D (controles, legenda e painel de detalhes, preservando Three.js e contratos); por fim, revisão pontual de consistência da tela de entrada. Sem reabrir arquitetura ou avaliação de modelos.

Capturas: [Usuários desktop](../evidence/ui-users-local/users-desktop.png), [Usuários celular](../evidence/ui-users-local/users-mobile.png), [Interfaces desktop](../evidence/ui-users-local/interfaces-desktop.png), [Interfaces celular](../evidence/ui-users-local/interfaces-mobile.png).

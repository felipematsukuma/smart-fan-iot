# Segredos históricos

[V] O scan integral encontrou 18 localizações de atribuições: seis exemplos revisados e doze atribuições legadas de credenciais. O registro [history-findings.json](history-findings.json) contém somente commit, caminho, regra, linha e classificação; nenhum valor de segredo.

[N] A revogação das credenciais antigas de PostgreSQL e InfluxDB ainda depende de confirmação sobre os emissores originais. As credenciais da stack atual são geradas localmente, mas isso não prova que os valores históricos deixaram de ter acesso a outro ambiente.

O comando `python tools/quality/secret_scan.py strict-history` falha enquanto houver `issuer_revocation_unverified`. Novas localizações fora do registro também falham. A árvore atual permite somente o conteúdo exato do arquivo legado de exemplos revisado, por hash, caminho e regra; alterar seu conteúdo invalida essa exceção. Não existe exclusão geral de arquivos de ambiente.

Para encerrar um achado, confirmar que o emissor foi desativado, que a credencial foi rotacionada ou que o valor nunca foi usado, registrando a evidência factual sem reproduzir o valor. Não reescrever histórico publicado nem substituir essa confirmação por uma allowlist ampla.

Os scanners sempre usam redação completa. Relatórios de segurança ignorados pelo Git podem ser compartilhados somente após verificar que contêm metadados redigidos. Backups privados e o diretório local de segredos nunca são artefatos de CI.

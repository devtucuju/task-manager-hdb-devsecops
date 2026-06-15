# Contribuindo

## Conventional Commits

Este projeto adota [Conventional Commits](https://www.conventionalcommits.org/) para padronizar o histórico do Git e facilitar automações de CI/CD.

### Formato

```
<tipo>(<escopo opcional>): <descrição>
```

- **tipo** — natureza da mudança (obrigatório)
- **escopo** — módulo ou área afetada (opcional)
- **descrição** — resumo curto em imperativo, minúsculas (obrigatório)

### Tipos permitidos

| Tipo       | Uso                                      |
|------------|------------------------------------------|
| `feat`     | Nova funcionalidade                      |
| `fix`      | Correção de bug                          |
| `docs`     | Documentação                             |
| `style`    | Formatação (sem mudança de lógica)       |
| `refactor` | Refatoração                              |
| `perf`     | Melhoria de performance                  |
| `test`     | Testes                                   |
| `build`    | Build, dependências, Docker              |
| `ci`       | Pipelines e automações                   |
| `chore`    | Tarefas de manutenção                    |
| `revert`   | Reversão de commit anterior              |

### Exemplos

```
feat(docker): adicionar Dockerfile com usuário não-root
fix(deps): atualizar Flask-Bcrypt para compatibilidade com Werkzeug 3
ci(github): configurar workflow de build da imagem
docs(readme): documentar execução com Docker
```

### Breaking changes

Use `!` após o tipo/escopo ou inclua `BREAKING CHANGE:` no corpo do commit:

```
feat(api)!: alterar formato de resposta de autenticação
```

### Ativar validação local (hook)

Execute uma vez no repositório clonado:

```bash
git config core.hooksPath .githooks
chmod +x .githooks/commit-msg
```

O hook rejeita commits que não sigam o padrão acima.

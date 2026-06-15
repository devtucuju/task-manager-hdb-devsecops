# Contribuindo

## Estratégia de branches (Git Flow)

Este projeto usa três branches principais e branches de feature derivadas de `develop`.

```
<tipo>/<escopo>-<descricao>  →  develop  →  homolog  →  master
     (feature)              (desenvolvimento) (homologação) (produção)
```

| Branch    | Propósito                                      | Base para clone/dev |
|-----------|------------------------------------------------|---------------------|
| `develop` | Integração contínua de features                | **Sim**             |
| `homolog` | Homologação / staging antes da produção        | Não                 |
| `master`  | Produção — apenas código validado e estável    | Não                 |

### Branches de feature

Crie sempre a partir de `develop`, usando o padrão Conventional Commits no **nome da branch**:

```
<tipo>/<escopo>-<descricao-curta>
```

| Exemplo de branch              | Uso                              |
|--------------------------------|----------------------------------|
| `feat/auth-jwt`                | Nova funcionalidade              |
| `fix/login-redirect`           | Correção de bug                  |
| `ci/github-actions-trivy`      | Pipeline / automação             |
| `build/docker-multi-stage`     | Build e containerização          |
| `docs/readme-docker`           | Documentação                     |

Regras:

- Use **minúsculas** e **hífens** (`-`) para separar palavras
- Escopo e descrição devem ser curtos e descritivos
- Uma branch = uma feature ou correção coesa

### Fluxo de trabalho

```bash
# 1. Clonar e usar develop como base
git clone git@github.com:devtucuju/task-manager-hdb-devsecops.git
cd task-manager-hdb-devsecops
git checkout develop

# 2. Criar branch de feature
git checkout -b feat/minha-feature

# 3. Desenvolver, commitar (Conventional Commits) e abrir PR → develop
git push -u origin feat/minha-feature

# 4. Após merge em develop, promover para homolog (PR develop → homolog)
# 5. Após validação em homolog, promover para produção (PR homolog → master)
```

### Proteção de branches

| Branch    | Regra                                                         |
|-----------|---------------------------------------------------------------|
| `master`  | PR obrigatório + CI verde (Build, Lint, Security, Commitlint) |
| `homolog` | PR obrigatório                                                |
| `develop` | PR recomendado para features                                  |

> PRs para `master` **só são mergeáveis** se todos os jobs de CI passarem. Os jobs de Lint e Security serão expandidos ao longo do desenvolvimento DevSecOps.

---

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

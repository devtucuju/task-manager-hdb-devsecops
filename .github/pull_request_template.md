## Branch alvo

- [ ] `develop` — integração de features
- [ ] `homolog` — homologação / staging
- [ ] `master` — produção

## Descrição

<!-- O que esta PR faz e por quê? -->

## Tipo de mudança

- [ ] `feat` — nova funcionalidade
- [ ] `fix` — correção de bug
- [ ] `build` — build, Docker, dependências
- [ ] `ci` — pipelines e automações
- [ ] `docs` — documentação
- [ ] `refactor` — refatoração
- [ ] `chore` — manutenção

## Checklist

- [ ] Branch nomeada no padrão `<tipo>/<escopo>-<descricao>`
- [ ] Commits seguem Conventional Commits
- [ ] CI passou (Build, Lint, Security, Commitlint)
- [ ] Testado localmente (se aplicável)

## Fluxo esperado

```
<tipo>/<feature>  →  develop  →  homolog  →  master
```

PRs para `master` exigem CI verde e revisão aprovada.

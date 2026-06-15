# =============================================================================
# Dockerfile — Task Manager (Flask)
# Repositório: https://github.com/AdityaBagad/Task-Manager-using-Flask
# =============================================================================

# 1. Imagem base leve com Python 3.11
FROM python:3.11-slim

# 2. Variáveis de ambiente da aplicação
#    FLASK_APP aponta para o pacote onde o objeto `app` é instanciado
#    (todo_project/todo_project/__init__.py), não para run.py, que usa debug=True
ENV FLASK_APP=todo_project \
    FLASK_ENV=production \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 3. Criar usuário/grupo não-root para reduzir superfície de ataque
#    Nenhum processo da aplicação roda como root dentro do container
RUN groupadd --gid 1000 appuser \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin appuser

# 4. Diretório de trabalho padrão da aplicação
WORKDIR /app

# 5. Copiar apenas requirements.txt primeiro (aproveita cache de camadas do Docker)
COPY requirements.txt .

# 6. Instalar dependências Python (inclui gunicorn para produção)
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# 7. Copiar o restante do código-fonte
COPY . .

# 8. Garantir permissões para o usuário não-root (SQLite grava site.db em runtime)
RUN chown -R appuser:appuser /app

# 9. Entrar no subdiretório onde run.py está (ponto de entrada original do projeto)
WORKDIR /app/todo_project

# 10. Trocar para usuário não-root antes de expor porta e iniciar o processo
USER appuser

# 11. Porta padrão do Flask / Gunicorn
EXPOSE 5000

# 12. Health check — verifica se a rota pública /about responde HTTP 200
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/about', timeout=3)" || exit 1

# 13. Comando de inicialização em produção (sem debug, com múltiplos workers)
#     Formato: gunicorn --bind HOST:PORT "modulo:app"
CMD ["gunicorn", \
     "--bind", "0.0.0.0:5000", \
     "--workers", "2", \
     "--threads", "2", \
     "--access-logfile", "-", \
     "--error-logfile", "-", \
     "todo_project:app"]

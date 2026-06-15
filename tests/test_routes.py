"""Testes de integração para a API REST de tarefas (/tasks)."""
import pytest

from todo_project.extensions import db
from todo_project.models import Task


# ---------------------------------------------------------------------------
# Fixtures — dados de tarefas para os testes
# ---------------------------------------------------------------------------

@pytest.fixture
def valid_task_payload():
    """Payload JSON válido para criação de tarefa."""
    return {
        'title': 'Nova tarefa de teste',
        'description': 'Descrição criada via pytest',
        'priority': 'high',
        'status': 'pending',
        'category': 'dev',
    }


@pytest.fixture
def sample_tasks(app, test_user):
    """
    Insere tarefas de exemplo no banco e retorna metadados para asserções.
    Útil em listagem, busca e filtro por status.
    """
    with app.app_context():
        user_id = test_user['id']
        tasks = [
            Task(
                user_id=user_id,
                title='Implementar login JWT',
                description='Autenticação com token',
                priority='high',
                status='done',
                category='dev',
            ),
            Task(
                user_id=user_id,
                title='Escrever testes de integração',
                description='Cobertura com pytest',
                priority='medium',
                status='in_progress',
                category='qa',
            ),
            Task(
                user_id=user_id,
                title='Revisar documentação',
                description='Atualizar README',
                priority='low',
                status='pending',
                category='docs',
            ),
        ]
        db.session.add_all(tasks)
        db.session.commit()
        for task in tasks:
            db.session.refresh(task)
        return tasks


@pytest.fixture
def single_task(app, sample_tasks):
    """Retorna a primeira tarefa criada pela fixture sample_tasks."""
    return sample_tasks[0]


# ---------------------------------------------------------------------------
# Testes de integração — rotas /tasks
# ---------------------------------------------------------------------------

class TestTasksAPI:
    def test_get_tasks_without_auth(self, client):
        """GET /tasks sem token deve retornar 401 (não autenticado)."""
        response = client.get('/tasks')

        assert response.status_code == 401
        assert response.get_json()['error'] == 'Autenticação necessária'

    def test_get_tasks_with_auth(self, client, auth_headers, sample_tasks):
        """GET /tasks com JWT válido deve retornar 200 e a lista de tarefas."""
        response = client.get('/tasks', headers=auth_headers)

        assert response.status_code == 200
        data = response.get_json()
        assert isinstance(data, list)
        assert len(data) == len(sample_tasks)
        titles = {task['title'] for task in data}
        assert 'Implementar login JWT' in titles
        assert 'Escrever testes de integração' in titles

    def test_create_task(self, client, auth_headers, valid_task_payload, app):
        """POST /tasks com dados válidos deve criar tarefa e retornar 201."""
        response = client.post('/tasks', json=valid_task_payload, headers=auth_headers)

        assert response.status_code == 201
        created = response.get_json()
        assert created['title'] == valid_task_payload['title']
        assert created['priority'] == valid_task_payload['priority']
        assert created['status'] == valid_task_payload['status']
        assert 'id' in created

        with app.app_context():
            task = db.session.get(Task, created['id'])
            assert task is not None
            assert task.title == valid_task_payload['title']

    def test_create_task_invalid_data(self, client, auth_headers):
        """POST /tasks com dados inválidos deve retornar 400."""
        invalid_payload = {
            'title': '',
            'priority': 'urgentissima',
            'status': 'arquivada',
        }
        response = client.post('/tasks', json=invalid_payload, headers=auth_headers)

        assert response.status_code == 400
        body = response.get_json()
        assert 'error' in body
        assert isinstance(body['error'], list)
        assert len(body['error']) >= 1

    def test_update_task(self, client, auth_headers, single_task, app):
        """PUT /tasks/<id> deve atualizar a tarefa existente e retornar 200."""
        task_id = single_task.id
        update_payload = {
            'title': 'Login JWT concluído',
            'description': 'Implementação finalizada',
            'priority': 'medium',
            'status': 'done',
            'category': 'dev',
        }

        response = client.put(
            f'/tasks/{task_id}',
            json=update_payload,
            headers=auth_headers,
        )

        assert response.status_code == 200
        updated = response.get_json()
        assert updated['title'] == update_payload['title']
        assert updated['status'] == update_payload['status']

        with app.app_context():
            task = db.session.get(Task, task_id)
            assert task.title == update_payload['title']
            assert task.status == update_payload['status']

    def test_delete_task(self, client, auth_headers, single_task, app):
        """DELETE /tasks/<id> deve remover a tarefa e retornar 200."""
        task_id = single_task.id

        response = client.delete(f'/tasks/{task_id}', headers=auth_headers)

        assert response.status_code == 200
        assert 'message' in response.get_json()

        with app.app_context():
            assert db.session.get(Task, task_id) is None

    def test_search_tasks(self, client, auth_headers, sample_tasks):
        """GET /tasks?q=<palavra> deve retornar apenas tarefas correspondentes."""
        response = client.get('/tasks?q=login', headers=auth_headers)

        assert response.status_code == 200
        results = response.get_json()
        assert len(results) == 1
        assert results[0]['title'] == 'Implementar login JWT'

    def test_filter_tasks_by_status(self, client, auth_headers, sample_tasks):
        """GET /tasks?status=<status> deve filtrar tarefas pelo status informado."""
        response = client.get('/tasks?status=done', headers=auth_headers)

        assert response.status_code == 200
        results = response.get_json()
        assert len(results) == 1
        assert all(task['status'] == 'done' for task in results)
        assert results[0]['title'] == 'Implementar login JWT'

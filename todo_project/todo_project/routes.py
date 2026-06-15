"""Rotas web e API — autenticação JWT, audit log e rate limiting."""
from datetime import datetime, timezone

from sqlalchemy import or_

from flask import (
    current_app,
    flash,
    g,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)

from todo_project.audit import log_crud, log_login_attempt, record_audit
from todo_project.auth import (
    check_password,
    create_access_token,
    hash_password,
    token_required,
    validate_password_strength,
)
from todo_project.extensions import csrf, db, limiter
from todo_project.forms import (
    LoginForm,
    RegistrationForm,
    TaskForm,
    UpdateUserInfoForm,
    UpdateUserPasswordForm,
)
from todo_project.models import Task, User

VALID_TASK_PRIORITIES = frozenset({'low', 'medium', 'high'})
VALID_TASK_STATUSES = frozenset({'pending', 'in_progress', 'done'})


def _task_to_dict(task: Task) -> dict:
    return {
        'id': task.id,
        'title': task.title,
        'description': task.description,
        'priority': task.priority,
        'status': task.status,
        'category': task.category,
        'due_date': task.due_date.isoformat() if task.due_date else None,
    }


def _validate_task_payload(data: dict, *, require_title: bool = True) -> list[str]:
    """Valida JSON de criação/atualização de tarefa; retorna lista de erros."""
    if not isinstance(data, dict):
        return ['Corpo da requisição deve ser um objeto JSON.']

    errors: list[str] = []
    if require_title or 'title' in data:
        title = data.get('title')
        if title is None or not str(title).strip():
            errors.append('title é obrigatório.')
        elif len(str(title).strip()) > 120:
            errors.append('title deve ter no máximo 120 caracteres.')

    if 'priority' in data and data['priority'] not in VALID_TASK_PRIORITIES:
        errors.append('priority inválida.')

    if 'status' in data and data['status'] not in VALID_TASK_STATUSES:
        errors.append('status inválido.')

    if 'description' in data and data['description'] is not None:
        if len(str(data['description'])) > 2000:
            errors.append('description deve ter no máximo 2000 caracteres.')

    if 'category' in data and data['category'] is not None:
        if len(str(data['category'])) > 50:
            errors.append('category deve ter no máximo 50 caracteres.')

    return errors


def register_routes(app):
    """Registra rotas e error handlers (evita import circular com create_app)."""

    def _set_jwt_cookie(response, token: str):
        response.set_cookie(
            current_app.config['JWT_COOKIE_NAME'],
            token,
            httponly=current_app.config['JWT_COOKIE_HTTPONLY'],
            secure=current_app.config['JWT_COOKIE_SECURE'],
            samesite=current_app.config['JWT_COOKIE_SAMESITE'],
            max_age=int(current_app.config['JWT_ACCESS_TOKEN_EXPIRES'].total_seconds()),
        )
        return response

    def _clear_jwt_cookie(response):
        response.delete_cookie(current_app.config['JWT_COOKIE_NAME'])
        return response

    @app.errorhandler(404)
    def error_404(error):
        uid = g.current_user.id if getattr(g, 'current_user', None) else None
        record_audit('error_404', user_id=uid, details={'path': request.path})
        return render_template('errors/404.html'), 404

    @app.errorhandler(403)
    def error_403(error):
        return render_template('errors/403.html'), 403

    @app.errorhandler(500)
    def error_500(error):
        current_app.logger.exception('Erro interno em %s', request.path)
        uid = g.current_user.id if getattr(g, 'current_user', None) else None
        record_audit('error_500', user_id=uid, details={'path': request.path})
        return render_template('errors/500.html'), 500

    @app.errorhandler(429)
    def error_429(error):
        if request.path.startswith('/api/') or request.is_json:
            return jsonify({'error': 'Muitas tentativas. Aguarde e tente novamente.'}), 429
        flash('Muitas tentativas. Aguarde e tente novamente.', 'danger')
        return redirect(url_for('login')), 429

    @app.route('/')
    @app.route('/about')
    def about():
        return render_template('about.html', title='About')

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit(lambda: current_app.config['LOGIN_RATE_LIMIT'], methods=['POST'])
    def login():
        if g.current_user:
            return redirect(url_for('all_tasks'))

        form = LoginForm()
        if form.validate_on_submit():
            email = form.email.data.lower().strip()
            user = db.session.query(User).filter_by(email=email).first()
            success = bool(
                user and user.is_active and check_password(user.password_hash, form.password.data)
            )
            log_login_attempt(email, success, user.id if user and success else None)

            if success:
                token = create_access_token(user)
                flash('Login successful.', 'success')
                next_page = request.args.get('next') or url_for('all_tasks')
                return _set_jwt_cookie(make_response(redirect(next_page)), token)

            flash('Invalid email or password.', 'danger')

        return render_template('login.html', title='Login', form=form)

    @app.route('/logout')
    @token_required
    def logout():
        record_audit('logout', user_id=g.current_user.id, resource_type='user', resource_id=g.current_user.id)
        return _clear_jwt_cookie(make_response(redirect(url_for('login'))))

    @app.route('/register', methods=['GET', 'POST'])
    def register():
        if not current_app.config.get('REGISTRATION_ENABLED', False):
            flash('Registration is disabled.', 'warning')
            return redirect(url_for('login'))
        if g.current_user:
            return redirect(url_for('all_tasks'))

        form = RegistrationForm()
        if form.validate_on_submit():
            user = User(
                username=form.username.data.strip(),
                email=form.email.data.lower().strip(),
                password_hash=hash_password(form.password.data),
                is_active=True,
            )
            db.session.add(user)
            db.session.commit()
            log_crud('create', 'user', user.id, user.id, email=user.email)
            flash(f'Account created for {user.email}.', 'success')
            return redirect(url_for('login'))

        return render_template('register.html', title='Register', form=form)

    @app.route('/all_tasks')
    @token_required
    def all_tasks():
        tasks = (
            db.session.query(Task)
            .filter_by(user_id=g.current_user.id)
            .order_by(Task.created_at.desc())
            .all()
        )
        return render_template('all_tasks.html', title='All Tasks', tasks=tasks)

    @app.route('/add_task', methods=['GET', 'POST'])
    @token_required
    def add_task():
        form = TaskForm()
        if form.validate_on_submit():
            task = Task(
                user_id=g.current_user.id,
                title=form.title.data.strip(),
                description=form.description.data,
                priority=form.priority.data,
                status=form.status.data,
                category=form.category.data,
                due_date=form.due_date.data,
            )
            db.session.add(task)
            db.session.commit()
            log_crud('create', 'task', task.id, g.current_user.id, title=task.title)
            flash('Task created.', 'success')
            return redirect(url_for('all_tasks'))
        return render_template('add_task.html', form=form, title='Add Task')

    @app.route('/all_tasks/<int:task_id>/update_task', methods=['GET', 'POST'])
    @token_required
    def update_task(task_id):
        task = db.session.get(Task, task_id)
        if not task or task.user_id != g.current_user.id:
            flash('Task not found.', 'danger')
            return redirect(url_for('all_tasks'))

        form = TaskForm()
        if form.validate_on_submit():
            task.title = form.title.data.strip()
            task.description = form.description.data
            task.priority = form.priority.data
            task.status = form.status.data
            task.category = form.category.data
            task.due_date = form.due_date.data
            task.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            log_crud('update', 'task', task.id, g.current_user.id, title=task.title)
            flash('Task updated.', 'success')
            return redirect(url_for('all_tasks'))
        if request.method == 'GET':
            form.title.data = task.title
            form.description.data = task.description
            form.priority.data = task.priority
            form.status.data = task.status
            form.category.data = task.category
            form.due_date.data = task.due_date

        return render_template('add_task.html', title='Update Task', form=form)

    @app.route('/all_tasks/<int:task_id>/delete_task', methods=['POST'])
    @token_required
    def delete_task(task_id):
        task = db.session.get(Task, task_id)
        if not task or task.user_id != g.current_user.id:
            flash('Task not found.', 'danger')
            return redirect(url_for('all_tasks'))
        title = task.title
        db.session.delete(task)
        db.session.commit()
        log_crud('delete', 'task', task_id, g.current_user.id, title=title)
        flash('Task deleted.', 'info')
        return redirect(url_for('all_tasks'))

    @app.route('/account', methods=['GET', 'POST'])
    @token_required
    def account():
        form = UpdateUserInfoForm()
        if form.validate_on_submit():
            g.current_user.username = form.username.data.strip()
            g.current_user.email = form.email.data.lower().strip()
            db.session.commit()
            log_crud('update', 'user', g.current_user.id, g.current_user.id)
            flash('Profile updated.', 'success')
            return redirect(url_for('account'))
        if request.method == 'GET':
            form.username.data = g.current_user.username
            form.email.data = g.current_user.email
        return render_template('account.html', title='Account Settings', form=form)

    @app.route('/account/change_password', methods=['GET', 'POST'])
    @token_required
    def change_password():
        form = UpdateUserPasswordForm()
        if form.validate_on_submit():
            if check_password(g.current_user.password_hash, form.old_password.data):
                g.current_user.password_hash = hash_password(form.new_password.data)
                db.session.commit()
                log_crud('update_password', 'user', g.current_user.id, g.current_user.id)
                flash('Password changed.', 'success')
                return redirect(url_for('account'))
            flash('Incorrect current password.', 'danger')
        return render_template('change_password.html', title='Change Password', form=form)

    def _user_tasks_query():
        query = db.session.query(Task).filter_by(user_id=g.current_user.id)
        status = request.args.get('status')
        if status:
            query = query.filter_by(status=status)
        keyword = request.args.get('q')
        if keyword:
            pattern = f'%{keyword}%'
            query = query.filter(
                or_(
                    Task.title.ilike(pattern),
                    Task.description.ilike(pattern),
                )
            )
        return query.order_by(Task.created_at.desc())

    @app.route('/tasks', methods=['GET'])
    @csrf.exempt
    @token_required
    def list_tasks():
        tasks = _user_tasks_query().all()
        return jsonify([_task_to_dict(t) for t in tasks]), 200

    @app.route('/tasks', methods=['POST'])
    @csrf.exempt
    @token_required
    def create_task_api():
        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'Corpo JSON inválido.'}), 400

        errors = _validate_task_payload(data, require_title=True)
        if errors:
            return jsonify({'error': errors}), 400

        task = Task(
            user_id=g.current_user.id,
            title=str(data['title']).strip(),
            description=data.get('description'),
            priority=data.get('priority', 'medium'),
            status=data.get('status', 'pending'),
            category=data.get('category'),
        )
        db.session.add(task)
        db.session.commit()
        log_crud('create', 'task', task.id, g.current_user.id, title=task.title)
        return jsonify(_task_to_dict(task)), 201

    @app.route('/tasks/<int:task_id>', methods=['PUT'])
    @csrf.exempt
    @token_required
    def update_task_api(task_id):
        task = db.session.get(Task, task_id)
        if not task or task.user_id != g.current_user.id:
            return jsonify({'error': 'Tarefa não encontrada.'}), 404

        data = request.get_json(silent=True)
        if data is None:
            return jsonify({'error': 'Corpo JSON inválido.'}), 400

        errors = _validate_task_payload(data, require_title='title' in data)
        if errors:
            return jsonify({'error': errors}), 400

        if 'title' in data:
            task.title = str(data['title']).strip()
        if 'description' in data:
            task.description = data['description']
        if 'priority' in data:
            task.priority = data['priority']
        if 'status' in data:
            task.status = data['status']
        if 'category' in data:
            task.category = data['category']

        task.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        log_crud('update', 'task', task.id, g.current_user.id, title=task.title)
        return jsonify(_task_to_dict(task)), 200

    @app.route('/tasks/<int:task_id>', methods=['DELETE'])
    @csrf.exempt
    @token_required
    def delete_task_api(task_id):
        task = db.session.get(Task, task_id)
        if not task or task.user_id != g.current_user.id:
            return jsonify({'error': 'Tarefa não encontrada.'}), 404

        title = task.title
        db.session.delete(task)
        db.session.commit()
        log_crud('delete', 'task', task_id, g.current_user.id, title=title)
        return jsonify({'message': 'Tarefa removida com sucesso.'}), 200

    @app.route('/api/tasks', methods=['GET'])
    @token_required
    def api_list_tasks():
        tasks = _user_tasks_query().all()
        return jsonify([_task_to_dict(t) for t in tasks])

    @app.route('/api/me', methods=['GET'])
    @token_required
    def api_me():
        u = g.current_user
        return jsonify({'id': u.id, 'username': u.username, 'email': u.email})

    @app.route('/api/auth/register', methods=['POST'])
    @csrf.exempt
    def api_register():
        if not current_app.config.get('REGISTRATION_ENABLED', False):
            return jsonify({'error': 'Registro desabilitado.'}), 403

        data = request.get_json(silent=True) or {}
        username = (data.get('username') or '').strip()
        email = (data.get('email') or '').lower().strip()
        password = data.get('password') or ''

        if not username or not email or not password:
            return jsonify({'error': 'username, email e password são obrigatórios.'}), 400

        valid, message = validate_password_strength(password)
        if not valid:
            return jsonify({'error': message}), 400

        if db.session.query(User).filter_by(email=email).first():
            return jsonify({'error': 'Email já cadastrado.'}), 409

        if db.session.query(User).filter_by(username=username).first():
            return jsonify({'error': 'Username já existe.'}), 409

        user = User(
            username=username,
            email=email,
            password_hash=hash_password(password),
            is_active=True,
        )
        db.session.add(user)
        db.session.commit()
        log_crud('create', 'user', user.id, user.id, email=user.email)
        return jsonify({
            'id': user.id,
            'username': user.username,
            'email': user.email,
        }), 201

    @app.route('/api/auth/login', methods=['POST'])
    @csrf.exempt
    @limiter.limit(lambda: current_app.config['LOGIN_RATE_LIMIT'], methods=['POST'])
    def api_login():
        data = request.get_json(silent=True) or {}
        email = (data.get('email') or '').lower().strip()
        password = data.get('password') or ''

        if not email or not password:
            return jsonify({'error': 'email e password são obrigatórios.'}), 400

        user = db.session.query(User).filter_by(email=email).first()
        success = bool(
            user and user.is_active and check_password(user.password_hash, password)
        )
        log_login_attempt(email, success, user.id if user and success else None)

        if not success:
            return jsonify({'error': 'Credenciais inválidas.'}), 401

        token = create_access_token(user)
        return jsonify({'token': token, 'token_type': 'Bearer'}), 200

    @app.route('/api/auth/logout', methods=['POST'])
    @csrf.exempt
    @token_required
    def api_logout():
        record_audit(
            'logout',
            user_id=g.current_user.id,
            resource_type='user',
            resource_id=g.current_user.id,
        )
        return jsonify({'message': 'Logout realizado com sucesso.'}), 200

    @app.route('/api/auth/change-password', methods=['POST'])
    @csrf.exempt
    @token_required
    def api_change_password():
        data = request.get_json(silent=True) or {}
        old_password = data.get('old_password') or ''
        new_password = data.get('new_password') or ''

        if not old_password or not new_password:
            return jsonify({'error': 'old_password e new_password são obrigatórios.'}), 400

        if not check_password(g.current_user.password_hash, old_password):
            return jsonify({'error': 'Senha atual incorreta.'}), 401

        valid, message = validate_password_strength(new_password)
        if not valid:
            return jsonify({'error': message}), 400

        g.current_user.password_hash = hash_password(new_password)
        db.session.commit()
        log_crud('update_password', 'user', g.current_user.id, g.current_user.id)
        return jsonify({'message': 'Senha alterada com sucesso.'}), 200

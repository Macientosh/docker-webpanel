from flask import Flask, render_template, redirect, url_for, flash, session, request
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from flask_dance.contrib.github import make_github_blueprint, github
from flask_dance.consumer import oauth_authorized
import os
import json
from dotenv import load_dotenv
from docker_utils import (
    get_local_containers,
    start_container,
    stop_container,
    restart_container,
    remove_container,
    run_remote_docker_ps,
    run_remote_docker_action

)

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

# Настройки сессии
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False

# Инициализация Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Настройка GitHub OAuth
github_bp = make_github_blueprint(
    client_id=os.getenv("GITHUB_CLIENT_ID"),
    client_secret=os.getenv("GITHUB_CLIENT_SECRET"),
    scope="read:user",
)
app.register_blueprint(github_bp, url_prefix="/login")

class User(UserMixin):
    def __init__(self, id, username):
        self.id = id
        self.username = username

@login_manager.user_loader
def load_user(user_id):
    user_data = session.get('user')
    if user_data and str(user_data['id']) == str(user_id):
        return User(id=user_data['id'], username=user_data['username'])
    return None

@oauth_authorized.connect_via(github_bp)
def github_logged_in(blueprint, token):
    if not token:
        flash("Не удалось войти через GitHub.", "error")
        return False
    
    if current_user.is_authenticated:
        return False
    
    resp = blueprint.session.get("/user")
    if not resp.ok:
        flash("Не удалось получить данные пользователя.", "error")
        return False
    
    user_info = resp.json()
    user_id = str(user_info["id"])
    
    user = User(id=user_id, username=user_info["login"])
    login_user(user)
    
    session['user'] = {
        'id': user_id,
        'username': user_info["login"]
    }
    
    flash(f"Добро пожаловать, {user_info['login']}!", "success")
    return False

@app.route('/')
@login_required
def index():
    selected_host = request.args.get('host')
    servers = []

    if os.path.exists(SERVERS_FILE):
        with open(SERVERS_FILE, 'r') as f:
            servers = json.load(f)

    try:
        if selected_host == "all":
            containers_by_server = []

            # Локальные контейнеры
            containers_by_server.append({
                "server_name": "Локальный",
                "server_host": None,
                "containers": get_local_containers()
            })

            # Удалённые контейнеры
            for server in servers:
                containers = run_remote_docker_ps(server)
                containers_by_server.append({
                    "server_name": server['name'],
                    "server_host": server['host'],
                    "containers": containers
                })

            return render_template('index.html',
                                   all_mode=True,
                                   containers_by_server=containers_by_server,
                                   servers=servers,
                                   selected_host=selected_host)

        elif selected_host:
            server = next((s for s in servers if s['host'] == selected_host), None)
            if not server:
                flash(f"Сервер {selected_host} не найден", "danger")
                return render_template('index.html', containers=[], servers=servers)

            containers = run_remote_docker_ps(server)
            return render_template('index.html', containers=containers,
                                   servers=servers, selected_host=selected_host, all_mode=False)

        else:
            containers = get_local_containers()
            return render_template('index.html', containers=containers,
                                   servers=servers, selected_host=None, all_mode=False)

    except Exception as e:
        flash(f"Ошибка: {str(e)}", "danger")
        return render_template('index.html', containers=[], servers=servers, selected_host=selected_host)

@app.route('/login')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    return render_template('/auth/login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('user', None)
    flash("Вы успешно вышли из системы", "info")
    return redirect(url_for('login'))

@app.route('/action', methods=['POST'])
@login_required
def action():
    try:
        container_id = request.form.get('container_id')
        action_type = request.form.get('action')
        host = request.form.get('host')  # может быть пустым (локально)

        if not container_id or not action_type:
            flash("Недостаточно данных для выполнения действия", "danger")
            return redirect(url_for('index'))

        # Обработка удалённого контейнера
        if host:
            # Найдём сервер по host
            with open(SERVERS_FILE, 'r') as f:
                servers = json.load(f)
            server = next((s for s in servers if s['host'] == host), None)
            if not server:
                flash(f"Сервер {host} не найден", "danger")
                return redirect(url_for('index'))

            result = run_remote_docker_action(server, container_id, action_type)
            if result.get('error'):
                flash(f"Ошибка при выполнении действия на {host}: {result['error']}", "danger")
            else:
                flash(f"{action_type.title()} контейнера {container_id[:12]} выполнено на {host}", "success")

        else:
            # Локальная обработка
            if action_type == 'start':
                start_container(container_id)
                flash(f'Контейнер {container_id[:12]} запущен', 'success')
            elif action_type == 'stop':
                stop_container(container_id)
                flash(f'Контейнер {container_id[:12]} остановлен', 'warning')
            elif action_type == 'restart':
                restart_container(container_id)
                flash(f'Контейнер {container_id[:12]} перезапущен', 'info')
            elif action_type == 'remove':
                remove_container(container_id)
                flash(f'Контейнер {container_id[:12]} удалён', 'danger')
            else:
                flash("Неизвестное действие", "danger")

    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')

    return redirect(url_for('index', host=host) if host else url_for('index'))

SERVERS_FILE = 'remote_servers.json'

@app.route('/add-server', methods=['GET', 'POST'])
@login_required
def add_server():
    if request.method == 'POST':
        name = request.form.get('name')
        username = request.form.get('username')
        host = request.form.get('host')
        port = int(request.form.get('port', 22))
        key_path = request.form.get('key_path')

        if not all([name, username, host, key_path]):
            flash("Все поля обязательны", "danger")
            return redirect(url_for('add_server'))

        # Загрузка текущих серверов
        try:
            if os.path.exists(SERVERS_FILE):
                with open(SERVERS_FILE, 'r') as f:
                    servers = json.load(f)
            else:
                servers = []
        except Exception as e:
            flash(f"Ошибка загрузки файла серверов: {str(e)}", "danger")
            servers = []

        # Проверка: нет ли уже сервера с таким же name и host
        for s in servers:
            if s.get('name') == name and s.get('host') == host:
                flash("Сервер с таким именем и адресом уже существует", "warning")
                return redirect(url_for('add_server'))

        # Добавление нового сервера
        servers.append({
            "name": name,
            "username": username,
            "host": host,
            "port": port,
            "key_path": key_path
        })

        # Сохраняем обратно
        try:
            with open(SERVERS_FILE, 'w') as f:
                json.dump(servers, f, indent=4)
            flash(f"Сервер '{name}' добавлен", "success")
            return redirect(url_for('index'))
        except Exception as e:
            flash(f"Ошибка сохранения сервера: {str(e)}", "danger")

    return render_template('add_server.html')

@app.route('/servers')
@login_required
def server_list():
    try:
        with open(SERVERS_FILE, 'r') as f:
            servers = json.load(f)
    except:
        servers = []
    return render_template('servers.html', servers=servers)

@app.route('/delete-server', methods=['POST'])
@login_required
def delete_server():
    host = request.form.get('host')

    if not host:
        flash("Не указан сервер для удаления", "danger")
        return redirect(url_for('server_list'))

    try:
        with open(SERVERS_FILE, 'r') as f:
            servers = json.load(f)

        servers = [s for s in servers if s.get('host') != host]

        with open(SERVERS_FILE, 'w') as f:
            json.dump(servers, f, indent=4)

        flash(f"Сервер {host} удалён", "success")
    except Exception as e:
        flash(f"Ошибка при удалении: {str(e)}", "danger")

    return redirect(url_for('server_list'))

@app.route('/edit-server', methods=['GET', 'POST'])
@login_required
def edit_server():
    host = request.args.get('host')
    if not host:
        flash("Хост не указан", "danger")
        return redirect(url_for('server_list'))

    try:
        with open(SERVERS_FILE, 'r') as f:
            servers = json.load(f)
    except:
        servers = []

    server = next((s for s in servers if s['host'] == host), None)
    if not server:
        flash("Сервер не найден", "danger")
        return redirect(url_for('server_list'))

    if request.method == 'POST':
        server['name'] = request.form.get('name')
        server['username'] = request.form.get('username')
        server['port'] = int(request.form.get('port'))
        server['key_path'] = request.form.get('key_path')

        # Обновление в списке
        servers = [s if s['host'] != host else server for s in servers]

        with open(SERVERS_FILE, 'w') as f:
            json.dump(servers, f, indent=4)

        flash(f"Сервер {host} обновлён", "success")
        return redirect(url_for('server_list'))

    return render_template('edit_server.html', server=server)

if __name__ == '__main__':
    app.run(debug=True)
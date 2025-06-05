from flask import Flask, render_template, redirect, url_for, flash, session, request
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
from flask_dance.contrib.github import make_github_blueprint, github
from flask_dance.consumer import oauth_authorized
import os
from dotenv import load_dotenv
from docker_utils import (
    get_local_containers,
    start_container,
    stop_container,
    restart_container,
    remove_container
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
def index():
    if not current_user.is_authenticated:
        return redirect(url_for('login'))
    
    try:
        containers = get_local_containers()
        return render_template('index.html', containers=containers)
    except Exception as e:
        flash(f"Ошибка при получении контейнеров: {str(e)}", "danger")
        return render_template('index.html', containers=[])

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

        if not container_id or not action_type:
            flash("Недостаточно данных для выполнения действия", "danger")
            return redirect(url_for('index'))

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

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
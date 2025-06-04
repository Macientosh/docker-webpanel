from flask import Flask, render_template, redirect, request, url_for, flash
from docker_utils import (
    get_local_containers,
    start_container,
    stop_container,
    restart_container,
    remove_container
)

app = Flask(__name__)
app.secret_key = 'supersecret'

@app.route('/')
def index():
    containers = get_local_containers()
    return render_template('index.html', containers=containers)

@app.route('/action', methods=['POST'])
def action():
    container_id = request.form.get('container_id')
    action_type = request.form.get('action')

    try:
        if action_type == 'start':
            start_container(container_id)
            flash(f'Контейнер {container_id} запущен', 'success')
        elif action_type == 'stop':
            stop_container(container_id)
            flash(f'Контейнер {container_id} остановлен', 'warning')
        elif action_type == 'restart':
            restart_container(container_id)
            flash(f'Контейнер {container_id} перезапущен', 'info')
        elif action_type == 'remove':
            remove_container(container_id)
            flash(f'Контейнер {container_id} удалён', 'danger')
    except Exception as e:
        flash(f'Ошибка: {str(e)}', 'danger')

    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)

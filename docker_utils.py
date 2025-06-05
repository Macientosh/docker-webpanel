import paramiko
import os
import docker

def get_local_containers():
    client = docker.from_env()  # подключение к локальному Docker сокету
    containers = client.containers.list(all=True)  # all=True — показывает и остановленные контейнеры

    result = []
    for container in containers:
        result.append({
            'id': container.short_id,
            'name': container.name,
            'status': container.status,
            'image': container.image.tags[0] if container.image.tags else 'none'
        })
    return result

def start_container(container_id):
    client = docker.from_env()
    container = client.containers.get(container_id)
    container.start()

def stop_container(container_id):
    client = docker.from_env()
    container = client.containers.get(container_id)
    container.stop()

def restart_container(container_id):
    client = docker.from_env()
    container = client.containers.get(container_id)
    container.restart()

def remove_container(container_id):
    client = docker.from_env()
    container = client.containers.get(container_id)
    container.remove(force=True)

def run_remote_docker_ps(server):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=server['host'],
            port=server.get('port', 22),
            username=server['username'],
            key_filename=os.path.expanduser(server['key_path']),
            timeout=10
        )

        # Команда docker ps -a с нужным форматом
        cmd = 'sudo docker ps -a --format "{{.ID}}|{{.Names}}|{{.Status}}|{{.Image}}"'
        stdin, stdout, stderr = ssh.exec_command(cmd)

        output = stdout.read().decode().strip().splitlines()
        error = stderr.read().decode()

        ssh.close()

        if error:
            raise Exception(error)

        containers = []
        for line in output:
            parts = line.split('|')
            if len(parts) == 4:
                containers.append({
                    'id': parts[0],
                    'name': parts[1],
                    'status': parts[2],
                    'image': parts[3]
                })
        return containers

    except Exception as e:
        return [{"id": "-", "name": "Ошибка", "status": "error", "image": str(e)}]

def run_remote_docker_action(server, container_id, action):
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        ssh.connect(
            hostname=server['host'],
            port=server.get('port', 22),
            username=server['username'],
            key_filename=os.path.expanduser(server['key_path']),
            timeout=10
        )

        if action not in ['start', 'stop', 'restart', 'rm']:
            return {'error': f'Неподдерживаемое действие: {action}'}

        # Поддержка sudo
        docker_cmd = f"sudo docker {action} {container_id}"
        if action == 'remove':
            docker_cmd = f"sudo docker rm -f {container_id}"

        stdin, stdout, stderr = ssh.exec_command(docker_cmd)
        output = stdout.read().decode().strip()
        error = stderr.read().decode().strip()
        ssh.close()

        if error:
            return {"error": error}
        return {"output": output}

    except Exception as e:
        return {"error": str(e)}
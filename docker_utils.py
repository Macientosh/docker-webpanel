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

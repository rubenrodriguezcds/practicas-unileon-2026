#!/bin/sh
set -e

# Sin contraseña no arrancamos: un sshd abierto con un usuario sin clave sería peor que no tener SSH.
: "${SSH_USER:?Falta SSH_USER en el .env}"
: "${SSH_PASSWORD:?Falta SSH_PASSWORD en el .env}"

id "$SSH_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$SSH_USER"
echo "$SSH_USER:$SSH_PASSWORD" | chpasswd

ssh-keygen -A >/dev/null
/usr/sbin/sshd

# Delegamos en el entrypoint oficial: crea la bbdd y lanza los init/*.sql solo si el volumen está vacío.
exec docker-entrypoint.sh "$@"

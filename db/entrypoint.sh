#!/bin/sh
# Arranque del contenedor `db` (ENTRYPOINT del db/Dockerfile).
#
# Para qué: hace lo que la imagen oficial de Postgres no hace —preparar el usuario SSH y lanzar
# el servidor sshd— y después cede el control al arranque oficial de Postgres.
#
# Por qué existe: un contenedor ejecuta un solo programa principal. Este script arranca sshd en
# segundo plano y luego se sustituye a sí mismo por Postgres (exec), que pasa a ser el proceso
# principal y recibe las señales de parada de Docker.
#
# Variables (del .env): SSH_USER y SSH_PASSWORD (obligatorias; sin ellas el contenedor no
# arranca) y las POSTGRES_* que usa la imagen oficial.
set -e

# Sin contraseña no arrancamos: un sshd abierto con un usuario sin clave sería peor que no tener SSH.
: "${SSH_USER:?Falta SSH_USER en el .env}"
: "${SSH_PASSWORD:?Falta SSH_PASSWORD en el .env}"

# Crea el usuario solo la primera vez; la contraseña se reaplica en cada arranque por si cambió en el .env.
id "$SSH_USER" >/dev/null 2>&1 || useradd -m -s /bin/bash "$SSH_USER"
echo "$SSH_USER:$SSH_PASSWORD" | chpasswd

# Genera las claves de host que falten (se borraron en el build para que no se compartan entre contenedores).
ssh-keygen -A >/dev/null
/usr/sbin/sshd

# Delegamos en el entrypoint oficial: crea la bbdd y lanza los init/* solo si el volumen está vacío.
# exec: Postgres sustituye a este script como proceso principal y recibe las señales de parada.
exec docker-entrypoint.sh "$@"

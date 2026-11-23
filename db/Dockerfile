# Imagen del contenedor `db`: PostgreSQL 16 con pgvector + servidor SSH.
#
# Para qué: guardar los datos de la aplicación (tabla `usuarios`) y permitir entrar al
# contenedor por SSH para administrarlo, como pide el enunciado.
#
# Por qué no se usa la imagen oficial tal cual: no trae SSH. Se parte de ella y se le añade
# openssh-server, conservando todo su comportamiento (variables POSTGRES_*, scripts de init…).
#
# Quién lo usa: docker-compose.yml (servicio db, `build: ./db`).
#
# Puertos: dentro, 5432 (Postgres) y 22 (SSH); el compose los publica como 1521 y 22.
# pgvector/pgvector:pg16-trixie es la Postgres 16 oficial con la extensión pgvector (vectores para
# el asistente, migración 005): mismo formato de datos, no hace falta recrear el volumen.
# «-trixie» (Debian 13), la misma base que postgres:16: con la variante por defecto (Debian 12)
# cambia la versión de glibc y Postgres avisa de «collation version mismatch» (los índices sobre
# texto, como el de nombres únicos, podrían dejar de ser fiables).
FROM pgvector/pgvector:pg16-trixie

# SSH en el mismo contenedor (lo exige el enunciado); la imagen oficial no lo trae.
# Se borran las claves de host del build para que cada contenedor genere las suyas al arrancar.
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-server \
 && rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_* \
 && mkdir -p /run/sshd

# La imagen oficial ejecuta lo que haya en esta carpeta (en orden alfabético) solo la
# primera vez, con el volumen de datos vacío: así se crea el modelo si no existe.
COPY init/ /docker-entrypoint-initdb.d/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 5432 22
# Nuestro entrypoint arranca sshd y luego cede el control al de Postgres con este CMD.
ENTRYPOINT ["entrypoint.sh"]
CMD ["postgres"]

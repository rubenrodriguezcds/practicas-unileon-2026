FROM postgres:16

# SSH en el mismo contenedor (lo pide el profe); la imagen oficial no lo trae.
# Se borran las claves de host del build para que cada contenedor genere las suyas al arrancar.
RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-server \
 && rm -rf /var/lib/apt/lists/* /etc/ssh/ssh_host_* \
 && mkdir -p /run/sshd

COPY init/ /docker-entrypoint-initdb.d/
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

EXPOSE 5432 22
ENTRYPOINT ["entrypoint.sh"]
CMD ["postgres"]

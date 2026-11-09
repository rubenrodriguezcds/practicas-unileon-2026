"""Backend de la aplicación web (paquete `app`).

Para qué: agrupa todo el código Python del contenedor `web`. Se arranca con
`uvicorn app.main:app` (ver docker/web.Dockerfile).

Mapa del paquete:
  config.py        variables de entorno → objeto Settings
  db.py            conexión a Postgres y consultas SQL
  security.py      hash y verificación de contraseñas (bcrypt)
  routers/auth.py  endpoints /api/auth/* (login, logout, me)
  spa.py           sirve el frontend React compilado
  main.py          junta todo lo anterior en la app FastAPI
"""

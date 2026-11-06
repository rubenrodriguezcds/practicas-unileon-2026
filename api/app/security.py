"""Hash y verificación de contraseñas con bcrypt.

Para qué: convertir una contraseña en un hash que se puede guardar en la bbdd, y comprobar
después si una contraseña coincide con ese hash.

Por qué existe: las contraseñas nunca se guardan en claro. bcrypt es lento a propósito y lleva
sal aleatoria, así que aunque se filtrara la tabla `usuarios` no se pueden recuperar.
Separado en su propio módulo para poder cambiar de algoritmo sin tocar los endpoints.

Quién lo usa: routers/auth.py (verify_password en el login). El hash del usuario admin lo
genera Postgres al arrancar (db/init/02_seed.sh) en el mismo formato bcrypt.

Notas: verify_password nunca lanza excepciones (hash corrupto, contraseña de más de 72 bytes…):
devuelve False, para que un dato raro dé un 401 y no un 500.
"""

import bcrypt


def hash_password(plain: str) -> str:
    """Devuelve el hash bcrypt (con sal aleatoria) de la contraseña en claro."""
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    """Comprueba la contraseña contra un hash bcrypt.

    Devuelve False (nunca lanza) si el hash es inválido o la contraseña es
    incompatible con bcrypt, para que el login responda 401 y no 500.
    """
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except ValueError:  # hash corrupto o contraseña >72 bytes según versión de bcrypt
        return False

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, InvalidHashError

_hasher = PasswordHasher()

def crear_hash_contrasena(contrasena_plana: str) -> str:
    return _hasher.hash(contrasena_plana)

def verificar_contrasena(hash_guardado: str, contrasena_plana: str) -> bool:
    if not isinstance(hash_guardado, str) or not hash_guardado.startswith("$argon2"):
        return hash_guardado == contrasena_plana

    try:
        return _hasher.verify(hash_guardado, contrasena_plana)
    except (VerifyMismatchError, InvalidHashError):
        return False
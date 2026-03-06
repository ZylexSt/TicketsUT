from django.conf import settings
from pymongo import MongoClient, ReturnDocument

_cliente = None

def obtener_bd():
    global _cliente
    if _cliente is None:
        _cliente = MongoClient(settings.MONGO_URI)
    return _cliente[settings.MONGO_BD]

def siguiente_folio_ticket():
    bd = obtener_bd()

    contador = bd.contadores.find_one_and_update(
        {"_id": "tickets"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

    numero = contador["seq"]
    return f"TCK-{numero:05d}"
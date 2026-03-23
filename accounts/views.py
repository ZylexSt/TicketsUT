from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.views.decorators.http import require_POST
from django.shortcuts import render, redirect
from django.contrib import messages
from bson.errors import InvalidId
from bson import ObjectId
from django.utils import timezone

import os

from .mongo import obtener_bd
from .mongo import siguiente_folio_ticket
from .decoradores import requiere_roles
from .seguridad import verificar_contrasena, crear_hash_contrasena



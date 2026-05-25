"""
API REST - Entrega 3: Módulo de Reseñas DannAlpes
==================================================
Tecnologías: FastAPI + PyMongo + MongoDB
Despliegue: Render
Consumo: Oracle APEX
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, PyMongoError
from bson import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(
    title="API Reseñas - DannAlpes",
    description="API REST conectada a MongoDB para el módulo de reseñas de huéspedes.",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"]
)

MONGO_URI = os.environ.get("MONGO_URI", "")
DB_NAME = os.environ.get("DB_NAME", "")

try:
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[DB_NAME]
    print(f"Conectado a MongoDB - Base de datos: '{DB_NAME}'")
except ConnectionFailure as e:
    print(f"Error de conexión a MongoDB: {e}")
    db = None


def get_collection(name: str):
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Base de datos no disponible. Verifica la variable MONGO_URI."
        )
    return db[name]


def serializar(doc):
    """Convierte ObjectId a string para serialización JSON."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


# ══════════════════════════════════════════════════════════════
# RAÍZ
# ══════════════════════════════════════════════════════════════
@app.get("/")
def inicio():
    return {
        "estado": "API DannAlpes Reseñas funcionando correctamente",
        "version": "1.0.0",
        "timestamp": datetime.now().isoformat()
    }


# ══════════════════════════════════════════════════════════════
# RF1 — Crear reseña
# Un cliente puede crear una reseña solo si no ha reseñado
# esa reserva antes. La validación de reserva completada
# se hace en APEX antes de llamar este endpoint.
# ══════════════════════════════════════════════════════════════
@app.post("/resenas")
def crear_resena(datos: dict):
    col = get_collection("resenas")

    # Validar campos obligatorios
    campos_obligatorios = ["id_hotel", "id_cliente", "id_reserva", "calificacion", "texto"]
    for campo in campos_obligatorios:
        if campo not in datos or not datos[campo]:
            raise HTTPException(
                status_code=422,
                detail=f"El campo '{campo}' es obligatorio."
            )

    # Validar calificación
    try:
        calificacion = int(datos["calificacion"])
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="La calificación debe ser un número entero.")
    if not (1 <= calificacion <= 5):
        raise HTTPException(status_code=422, detail="La calificación debe estar entre 1 y 5.")

    # Validar texto
    if len(str(datos["texto"]).strip()) < 10:
        raise HTTPException(status_code=422, detail="El texto debe tener al menos 10 caracteres.")
    if len(str(datos["texto"]).strip()) > 2000:
        raise HTTPException(status_code=422, detail="El texto no puede superar 2000 caracteres.")

    # Verificar que no exista reseña activa para esa reserva
    existente = col.find_one({
        "id_reserva": datos["id_reserva"],
        "esta_activa": True
    })
    if existente:
        raise HTTPException(
            status_code=409,
            detail="Ya existe una reseña activa para esta reserva."
        )

    doc = {
        "id_hotel": datos["id_hotel"],
        "id_cliente": datos["id_cliente"],
        "id_reserva": datos["id_reserva"],
        "calificacion": calificacion,
        "texto": str(datos["texto"]).strip(),
        "fecha_creacion": datetime.utcnow(),
        "fecha_actualizacion": datetime.utcnow(),
        "esta_activa": True,
        "destacada": False,
        "votos_utiles": 0,
        "votantes": []
    }

    try:
        resultado = col.insert_one(doc)
        return {
            "mensaje": "Reseña creada exitosamente.",
            "id": str(resultado.inserted_id)
        }
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error al crear la reseña: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RF2 — Editar reseña (texto y/o calificación)
# ══════════════════════════════════════════════════════════════
@app.put("/resenas/{id_resena}")
def editar_resena(id_resena: str, datos: dict):
    col = get_collection("resenas")

    try:
        oid = ObjectId(id_resena)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de reseña inválido.")

    actualizacion = {"fecha_actualizacion": datetime.utcnow()}

    if "calificacion" in datos:
        try:
            calificacion = int(datos["calificacion"])
        except (ValueError, TypeError):
            raise HTTPException(status_code=422, detail="La calificación debe ser un número entero.")
        if not (1 <= calificacion <= 5):
            raise HTTPException(status_code=422, detail="La calificación debe estar entre 1 y 5.")
        actualizacion["calificacion"] = calificacion

    if "texto" in datos:
        texto = str(datos["texto"]).strip()
        if len(texto) < 10:
            raise HTTPException(status_code=422, detail="El texto debe tener al menos 10 caracteres.")
        if len(texto) > 2000:
            raise HTTPException(status_code=422, detail="El texto no puede superar 2000 caracteres.")
        actualizacion["texto"] = texto

    try:
        resultado = col.update_one(
            {"_id": oid, "esta_activa": True},
            {"$set": actualizacion}
        )
        if resultado.matched_count == 0:
            raise HTTPException(status_code=404, detail="Reseña no encontrada o ya fue eliminada.")
        return {"mensaje": "Reseña actualizada exitosamente."}
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error al actualizar la reseña: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RF3 / RF8 — Eliminar reseña (cliente o administrador)
# Eliminación lógica: esta_activa = false
# ══════════════════════════════════════════════════════════════
@app.delete("/resenas/{id_resena}")
def eliminar_resena(id_resena: str):
    col = get_collection("resenas")

    try:
        oid = ObjectId(id_resena)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de reseña inválido.")

    try:
        resultado = col.update_one(
            {"_id": oid},
            {"$set": {
                "esta_activa": False,
                "fecha_actualizacion": datetime.utcnow()
            }}
        )
        if resultado.matched_count == 0:
            raise HTTPException(status_code=404, detail="Reseña no encontrada.")
        return {"mensaje": "Reseña eliminada exitosamente."}
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error al eliminar la reseña: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RF4 — Consultar reseñas de un hotel
# Paginadas, ordenadas por fecha o utilidad.
# Las destacadas siempre aparecen primero.
# ══════════════════════════════════════════════════════════════
@app.get("/resenas/hotel/{id_hotel}")
def get_resenas_hotel(
    id_hotel: str,
    orden: str = "fecha",
    pagina: int = 1,
    limite: int = 10
):
    col = get_collection("resenas")

    filtro = {"id_hotel": id_hotel, "esta_activa": True}
    sort_campo = "fecha_creacion" if orden == "fecha" else "votos_utiles"
    skip = (pagina - 1) * limite

    try:
        docs = list(
            col.find(filtro)
            .sort([("destacada", -1), (sort_campo, -1)])
            .skip(skip)
            .limit(limite)
        )
        return [serializar(d) for d in docs]
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar reseñas: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RF5 — Marcar reseña como útil
# Un usuario autenticado vota una sola vez por reseña.
# ══════════════════════════════════════════════════════════════
@app.post("/resenas/{id_resena}/voto")
def votar_resena(id_resena: str, datos: dict):
    col = get_collection("resenas")

    id_usuario = datos.get("id_usuario", "").strip()
    if not id_usuario:
        raise HTTPException(status_code=422, detail="El campo 'id_usuario' es obligatorio.")

    try:
        oid = ObjectId(id_resena)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de reseña inválido.")

    resena = col.find_one({"_id": oid, "esta_activa": True})
    if not resena:
        raise HTTPException(status_code=404, detail="Reseña no encontrada o eliminada.")

    if id_usuario in resena.get("votantes", []):
        raise HTTPException(status_code=409, detail="Ya votaste por esta reseña.")

    try:
        col.update_one(
            {"_id": oid},
            {
                "$inc": {"votos_utiles": 1},
                "$push": {"votantes": id_usuario}
            }
        )
        return {"mensaje": "Voto registrado exitosamente."}
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error al registrar el voto: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RF6 — Historial de reseñas propias del cliente
# Incluye reseñas activas e inactivas (eliminadas).
# ══════════════════════════════════════════════════════════════
@app.get("/resenas/cliente/{id_cliente}")
def get_resenas_cliente(id_cliente: str, orden: str = "fecha"):
    col = get_collection("resenas")

    sort_campo = "fecha_creacion" if orden == "fecha" else "id_hotel"

    try:
        docs = list(
            col.find({"id_cliente": id_cliente})
            .sort(sort_campo, -1)
        )
        return [serializar(d) for d in docs]
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error al consultar historial: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RF7 — Responder reseña (administrador)
# Agrega o edita la respuesta oficial embebida en la reseña.
# ══════════════════════════════════════════════════════════════
@app.put("/resenas/{id_resena}/respuesta")
def responder_resena(id_resena: str, datos: dict):
    col = get_collection("resenas")

    texto = datos.get("texto", "").strip()
    id_admin = datos.get("id_admin", "").strip()

    if not texto or len(texto) < 5:
        raise HTTPException(status_code=422, detail="La respuesta debe tener al menos 5 caracteres.")
    if len(texto) > 1000:
        raise HTTPException(status_code=422, detail="La respuesta no puede superar 1000 caracteres.")
    if not id_admin:
        raise HTTPException(status_code=422, detail="El campo 'id_admin' es obligatorio.")

    try:
        oid = ObjectId(id_resena)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de reseña inválido.")

    try:
        resultado = col.update_one(
            {"_id": oid, "esta_activa": True},
            {"$set": {
                "respuesta_admin": {
                    "texto": texto,
                    "fecha": datetime.utcnow(),
                    "id_admin": id_admin
                },
                "fecha_actualizacion": datetime.utcnow()
            }}
        )
        if resultado.matched_count == 0:
            raise HTTPException(status_code=404, detail="Reseña no encontrada o eliminada.")
        return {"mensaje": "Respuesta guardada exitosamente."}
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error al guardar la respuesta: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RF9 — Destacar reseña (administrador)
# Solo puede haber UNA reseña destacada por hotel a la vez.
# Desactiva la destacada anterior antes de marcar la nueva.
# ══════════════════════════════════════════════════════════════
@app.put("/resenas/{id_resena}/destacar")
def destacar_resena(id_resena: str, datos: dict):
    col = get_collection("resenas")

    id_hotel = datos.get("id_hotel", "").strip()
    if not id_hotel:
        raise HTTPException(status_code=422, detail="El campo 'id_hotel' es obligatorio.")

    try:
        oid = ObjectId(id_resena)
    except Exception:
        raise HTTPException(status_code=400, detail="ID de reseña inválido.")

    try:
        # Quitar destacada anterior del mismo hotel
        col.update_many(
            {"id_hotel": id_hotel, "destacada": True},
            {"$set": {"destacada": False, "fecha_actualizacion": datetime.utcnow()}}
        )
        # Marcar la nueva reseña como destacada
        resultado = col.update_one(
            {"_id": oid, "esta_activa": True},
            {"$set": {"destacada": True, "fecha_actualizacion": datetime.utcnow()}}
        )
        if resultado.matched_count == 0:
            raise HTTPException(status_code=404, detail="Reseña no encontrada o eliminada.")
        return {"mensaje": "Reseña destacada exitosamente."}
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error al destacar la reseña: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RFC1 — Top 10 hoteles por calificación promedio en un período
# ══════════════════════════════════════════════════════════════
@app.get("/rfc/top-hoteles")
def rfc1_top_hoteles(fecha_ini: str = "2025-01-01", fecha_fin: str = "2025-12-31"):
    col = get_collection("resenas")

    try:
        dt_ini = datetime.fromisoformat(fecha_ini)
        dt_fin = datetime.fromisoformat(fecha_fin + "T23:59:59")
    except ValueError:
        raise HTTPException(status_code=422, detail="Formato de fecha inválido. Use YYYY-MM-DD.")

    pipeline = [
        {
            "$match": {
                "esta_activa": True,
                "fecha_creacion": {"$gte": dt_ini, "$lte": dt_fin}
            }
        },
        {
            "$group": {
                "_id": "$id_hotel",
                "calificacion_promedio": {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1}
            }
        },
        {"$sort": {"calificacion_promedio": -1}},
        {"$limit": 10},
        {
            "$project": {
                "id_hotel": "$_id",
                "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
                "total_resenas": 1,
                "_id": 0
            }
        }
    ]

    try:
        return list(col.aggregate(pipeline))
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error en RFC1: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RFC2 — Evolución de la reputación de un hotel mes a mes
# ══════════════════════════════════════════════════════════════
@app.get("/rfc/evolucion/{id_hotel}")
def rfc2_evolucion(id_hotel: str, anio: int = 2025):
    col = get_collection("resenas")

    pipeline = [
        {
            "$match": {
                "id_hotel": id_hotel,
                "esta_activa": True,
                "$expr": {"$eq": [{"$year": "$fecha_creacion"}, anio]}
            }
        },
        {
            "$group": {
                "_id": {"mes": {"$month": "$fecha_creacion"}},
                "calificacion_promedio": {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1}
            }
        },
        {"$sort": {"_id.mes": 1}},
        {
            "$project": {
                "mes": "$_id.mes",
                "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
                "total_resenas": 1,
                "_id": 0
            }
        }
    ]

    try:
        return list(col.aggregate(pipeline))
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error en RFC2: {str(e)}")


# ══════════════════════════════════════════════════════════════
# RFC3 — Perfil comparativo de hoteles por ciudad
# Recibe los IDs de hoteles separados por coma.
# Los IDs se obtienen desde Oracle en APEX y se pasan aquí.
# ══════════════════════════════════════════════════════════════
@app.get("/rfc/comparativo")
def rfc3_comparativo(id_hoteles: str = ""):
    col = get_collection("resenas")

    lista_hoteles = [h.strip() for h in id_hoteles.split(",") if h.strip()]
    if not lista_hoteles:
        raise HTTPException(status_code=422, detail="El parámetro 'id_hoteles' es obligatorio.")

    pipeline = [
        {
            "$match": {
                "id_hotel": {"$in": lista_hoteles},
                "esta_activa": True
            }
        },
        {
            "$group": {
                "_id": "$id_hotel",
                "calificacion_promedio": {"$avg": "$calificacion"},
                "total_resenas": {"$sum": 1},
                "con_respuesta": {
                    "$sum": {
                        "$cond": [{"$ifNull": ["$respuesta_admin", False]}, 1, 0]
                    }
                },
                "destacadas": {
                    "$sum": {"$cond": ["$destacada", 1, 0]}
                }
            }
        },
        {
            "$addFields": {
                "pct_con_respuesta": {
                    "$round": [
                        {"$multiply": [
                            {"$divide": ["$con_respuesta", "$total_resenas"]},
                            100
                        ]},
                        1
                    ]
                },
                "pct_destacadas": {
                    "$round": [
                        {"$multiply": [
                            {"$divide": ["$destacadas", "$total_resenas"]},
                            100
                        ]},
                        1
                    ]
                }
            }
        },
        {
            "$project": {
                "id_hotel": "$_id",
                "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
                "total_resenas": 1,
                "pct_con_respuesta": 1,
                "pct_destacadas": 1,
                "_id": 0
            }
        },
        {"$sort": {"calificacion_promedio": -1}}
    ]

    try:
        return list(col.aggregate(pipeline))
    except PyMongoError as e:
        raise HTTPException(status_code=500, detail=f"Error en RFC3: {str(e)}")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from pymongo.errors import PyMongoError
from bson import ObjectId
from datetime import datetime
import os
from dotenv import load_dotenv
load_dotenv()

# (mantén tu código existente arriba)
# Agrega los siguientes endpoints:

# ══════════════════════════════════════════
# RF1 — Crear reseña
# ══════════════════════════════════════════
@app.post("/resenas")
def crear_resena(datos: dict):
    col = get_collection("resenas")
    campos = ["id_hotel", "id_cliente", "id_reserva", "calificacion", "texto"]
    for c in campos:
        if c not in datos:
            raise HTTPException(status_code=422, detail=f"Campo '{c}' obligatorio")
    if not (1 <= int(datos["calificacion"]) <= 5):
        raise HTTPException(status_code=422, detail="Calificación debe ser entre 1 y 5")
    if len(datos["texto"]) < 10:
        raise HTTPException(status_code=422, detail="Texto muy corto, mínimo 10 caracteres")
    # Verificar que no exista reseña para esa reserva
    existente = col.find_one({"id_reserva": datos["id_reserva"], "esta_activa": True})
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe una reseña para esta reserva")
    doc = {
        "id_hotel": datos["id_hotel"],
        "id_cliente": datos["id_cliente"],
        "id_reserva": datos["id_reserva"],
        "calificacion": int(datos["calificacion"]),
        "texto": datos["texto"],
        "fecha_creacion": datetime.utcnow(),
        "fecha_actualizacion": datetime.utcnow(),
        "esta_activa": True,
        "destacada": False,
        "votos_utiles": 0,
        "votantes": []
    }
    resultado = col.insert_one(doc)
    return {"mensaje": "Reseña creada", "id": str(resultado.inserted_id)}

# ══════════════════════════════════════════
# RF2 — Editar reseña
# ══════════════════════════════════════════
@app.put("/resenas/{id_resena}")
def editar_resena(id_resena: str, datos: dict):
    col = get_collection("resenas")
    actualizacion = {"fecha_actualizacion": datetime.utcnow()}
    if "calificacion" in datos:
        if not (1 <= int(datos["calificacion"]) <= 5):
            raise HTTPException(status_code=422, detail="Calificación entre 1 y 5")
        actualizacion["calificacion"] = int(datos["calificacion"])
    if "texto" in datos:
        if len(datos["texto"]) < 10:
            raise HTTPException(status_code=422, detail="Texto muy corto")
        actualizacion["texto"] = datos["texto"]
    col.update_one({"_id": ObjectId(id_resena)}, {"$set": actualizacion})
    return {"mensaje": "Reseña actualizada"}

# ══════════════════════════════════════════
# RF3 / RF8 — Eliminar reseña
# ══════════════════════════════════════════
@app.delete("/resenas/{id_resena}")
def eliminar_resena(id_resena: str):
    col = get_collection("resenas")
    col.update_one(
        {"_id": ObjectId(id_resena)},
        {"$set": {"esta_activa": False, "fecha_actualizacion": datetime.utcnow()}}
    )
    return {"mensaje": "Reseña eliminada"}

# ══════════════════════════════════════════
# RF4 — Consultar reseñas de un hotel
# ══════════════════════════════════════════
@app.get("/resenas/hotel/{id_hotel}")
def get_resenas_hotel(id_hotel: str, orden: str = "fecha", pagina: int = 1, limite: int = 10):
    col = get_collection("resenas")
    filtro = {"id_hotel": id_hotel, "esta_activa": True}
    sort_campo = "fecha_creacion" if orden == "fecha" else "votos_utiles"
    skip = (pagina - 1) * limite
    # Destacadas primero
    docs = list(col.find(filtro).sort([
        ("destacada", -1),
        (sort_campo, -1)
    ]).skip(skip).limit(limite))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

# ══════════════════════════════════════════
# RF5 — Marcar reseña como útil
# ══════════════════════════════════════════
@app.post("/resenas/{id_resena}/voto")
def votar_resena(id_resena: str, datos: dict):
    col = get_collection("resenas")
    id_usuario = datos.get("id_usuario")
    if not id_usuario:
        raise HTTPException(status_code=422, detail="id_usuario obligatorio")
    resena = col.find_one({"_id": ObjectId(id_resena)})
    if not resena:
        raise HTTPException(status_code=404, detail="Reseña no encontrada")
    if id_usuario in resena.get("votantes", []):
        raise HTTPException(status_code=409, detail="Ya votaste esta reseña")
    col.update_one(
        {"_id": ObjectId(id_resena)},
        {"$inc": {"votos_utiles": 1}, "$push": {"votantes": id_usuario}}
    )
    return {"mensaje": "Voto registrado"}

# ══════════════════════════════════════════
# RF6 — Historial de reseñas del cliente
# ══════════════════════════════════════════
@app.get("/resenas/cliente/{id_cliente}")
def get_resenas_cliente(id_cliente: str, orden: str = "fecha"):
    col = get_collection("resenas")
    sort_campo = "fecha_creacion" if orden == "fecha" else "id_hotel"
    docs = list(col.find({"id_cliente": id_cliente}).sort(sort_campo, -1))
    for d in docs:
        d["_id"] = str(d["_id"])
    return docs

# ══════════════════════════════════════════
# RF7 — Responder reseña (admin)
# ══════════════════════════════════════════
@app.put("/resenas/{id_resena}/respuesta")
def responder_resena(id_resena: str, datos: dict):
    col = get_collection("resenas")
    if "texto" not in datos or len(datos["texto"]) < 5:
        raise HTTPException(status_code=422, detail="Texto de respuesta muy corto")
    col.update_one(
        {"_id": ObjectId(id_resena)},
        {"$set": {
            "respuesta_admin": {
                "texto": datos["texto"],
                "fecha": datetime.utcnow(),
                "id_admin": datos.get("id_admin", "")
            },
            "fecha_actualizacion": datetime.utcnow()
        }}
    )
    return {"mensaje": "Respuesta guardada"}

# ══════════════════════════════════════════
# RF9 — Destacar reseña (admin)
# ══════════════════════════════════════════
@app.put("/resenas/{id_resena}/destacar")
def destacar_resena(id_resena: str, datos: dict):
    col = get_collection("resenas")
    id_hotel = datos.get("id_hotel")
    if not id_hotel:
        raise HTTPException(status_code=422, detail="id_hotel obligatorio")
    # Quitar destacada anterior del mismo hotel
    col.update_many(
        {"id_hotel": id_hotel, "destacada": True},
        {"$set": {"destacada": False}}
    )
    # Marcar la nueva
    col.update_one(
        {"_id": ObjectId(id_resena)},
        {"$set": {"destacada": True, "fecha_actualizacion": datetime.utcnow()}}
    )
    return {"mensaje": "Reseña destacada"}

# ══════════════════════════════════════════
# RFC1 — Top 10 hoteles
# ══════════════════════════════════════════
@app.get("/rfc/top-hoteles")
def rfc1_top_hoteles(fecha_ini: str = "2025-01-01", fecha_fin: str = "2025-12-31"):
    col = get_collection("resenas")
    pipeline = [
        {"$match": {
            "esta_activa": True,
            "fecha_creacion": {
                "$gte": datetime.fromisoformat(fecha_ini),
                "$lte": datetime.fromisoformat(fecha_fin + "T23:59:59")
            }
        }},
        {"$group": {
            "_id": "$id_hotel",
            "calificacion_promedio": {"$avg": "$calificacion"},
            "total_resenas": {"$sum": 1}
        }},
        {"$sort": {"calificacion_promedio": -1}},
        {"$limit": 10},
        {"$project": {
            "id_hotel": "$_id",
            "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
            "total_resenas": 1,
            "_id": 0
        }}
    ]
    return list(col.aggregate(pipeline))

# ══════════════════════════════════════════
# RFC2 — Evolución reputación mes a mes
# ══════════════════════════════════════════
@app.get("/rfc/evolucion/{id_hotel}")
def rfc2_evolucion(id_hotel: str, anio: int = 2025):
    col = get_collection("resenas")
    pipeline = [
        {"$match": {
            "id_hotel": id_hotel,
            "esta_activa": True,
            "$expr": {"$eq": [{"$year": "$fecha_creacion"}, anio]}
        }},
        {"$group": {
            "_id": {"mes": {"$month": "$fecha_creacion"}},
            "calificacion_promedio": {"$avg": "$calificacion"},
            "total_resenas": {"$sum": 1}
        }},
        {"$sort": {"_id.mes": 1}},
        {"$project": {
            "mes": "$_id.mes",
            "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
            "total_resenas": 1,
            "_id": 0
        }}
    ]
    return list(col.aggregate(pipeline))

# ══════════════════════════════════════════
# RFC3 — Perfil comparativo por ciudad
# ══════════════════════════════════════════
@app.get("/rfc/comparativo")
def rfc3_comparativo(id_hoteles: str = ""):
    col = get_collection("resenas")
    lista_hoteles = [h.strip() for h in id_hoteles.split(",") if h.strip()]
    if not lista_hoteles:
        raise HTTPException(status_code=422, detail="id_hoteles obligatorio")
    pipeline = [
        {"$match": {"id_hotel": {"$in": lista_hoteles}, "esta_activa": True}},
        {"$group": {
            "_id": "$id_hotel",
            "calificacion_promedio": {"$avg": "$calificacion"},
            "total_resenas": {"$sum": 1},
            "con_respuesta": {"$sum": {"$cond": [{"$ifNull": ["$respuesta_admin", False]}, 1, 0]}},
            "destacadas": {"$sum": {"$cond": ["$destacada", 1, 0]}}
        }},
        {"$addFields": {
            "pct_con_respuesta": {"$round": [{"$multiply": [{"$divide": ["$con_respuesta", "$total_resenas"]}, 100]}, 1]},
            "pct_destacadas": {"$round": [{"$multiply": [{"$divide": ["$destacadas", "$total_resenas"]}, 100]}, 1]}
        }},
        {"$project": {
            "id_hotel": "$_id",
            "calificacion_promedio": {"$round": ["$calificacion_promedio", 2]},
            "total_resenas": 1,
            "pct_con_respuesta": 1,
            "pct_destacadas": 1,
            "_id": 0
        }}
    ]
    return list(col.aggregate(pipeline))

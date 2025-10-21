from fastapi import APIRouter, HTTPException, Depends, Query
from app.database import get_db
from app.models.pydantic_models import (
    BahiaResponse, BahiaCreate, TipoUsuario
)
from app.core.security import get_current_user
import pymssql
import uuid
from typing import Optional

router = APIRouter(prefix="/bahias", tags=["bahías"])

# -------------------------- FUNCIONES AUXILIARES --------------------------

def dict_cursor(cursor):
    """Convierte los resultados de pymssql a diccionarios con nombres de columna"""
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]

def dict_row(cursor):
    """Convierte solo una fila a diccionario"""
    columns = [col[0] for col in cursor.description]
    row = cursor.fetchone()
    return dict(zip(columns, row)) if row else None

# -------------------------- ENDPOINTS --------------------------

@router.get("/", response_model=list[BahiaResponse])
async def obtener_bahias(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    activo: bool = Query(True),
    tipo_bahia_id: Optional[int] = Query(None),
    estado_bahia_id: Optional[int] = Query(None),
    conn = Depends(get_db)
):
    try:
        cursor = conn.cursor()
        
        query = """
            SELECT b.id, b.numero, b.tipo_bahia_id, b.estado_bahia_id,
                   b.capacidad_maxima, b.ubicacion, b.observaciones,
                   b.activo, b.fecha_creacion, b.fecha_ultima_modificacion,
                   b.creado_por,
                   tb.nombre as tipo_bahia_nombre,
                   eb.nombre as estado_bahia_nombre,
                   eb.codigo as estado_bahia_codigo
            FROM bahias b
            LEFT JOIN tipos_bahia tb ON b.tipo_bahia_id = tb.id
            LEFT JOIN estados_bahia eb ON b.estado_bahia_id = eb.id
            WHERE b.activo = %s
        """
        params = [1 if activo else 0]
        
        if tipo_bahia_id:
            query += " AND b.tipo_bahia_id = %s"
            params.append(tipo_bahia_id)
        
        if estado_bahia_id:
            query += " AND b.estado_bahia_id = %s"
            params.append(estado_bahia_id)
        
        query += " ORDER BY b.numero OFFSET %s ROWS FETCH NEXT %s ROWS ONLY"
        params.extend([skip, limit])
        
        cursor.execute(query, tuple(params))
        bahias = dict_cursor(cursor)
        cursor.close()
        
        return [BahiaResponse(**bahia) for bahia in bahias]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/{bahia_id}", response_model=BahiaResponse)
async def obtener_bahia(bahia_id: str, conn = Depends(get_db)):
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT b.id, b.numero, b.tipo_bahia_id, b.estado_bahia_id,
                   b.capacidad_maxima, b.ubicacion, b.observaciones,
                   b.activo, b.fecha_creacion, b.fecha_ultima_modificacion,
                   b.creado_por,
                   tb.nombre as tipo_bahia_nombre,
                   eb.nombre as estado_bahia_nombre,
                   eb.codigo as estado_bahia_codigo
            FROM bahias b
            LEFT JOIN tipos_bahia tb ON b.tipo_bahia_id = tb.id
            LEFT JOIN estados_bahia eb ON b.estado_bahia_id = eb.id
            WHERE b.id = %s
        """, (bahia_id,))
        
        bahia = dict_row(cursor)
        cursor.close()
        
        if not bahia:
            raise HTTPException(status_code=404, detail="Bahía no encontrada")
        
        return BahiaResponse(**bahia)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/", response_model=BahiaResponse)
async def crear_bahia(
    bahia: BahiaCreate,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = conn.cursor()

        # Obtener tipo de usuario
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=401, detail="Usuario no válido")
        user_tipo = row[0]  # Acceder por índice

        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.OPERADOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para crear bahías")
        
        # Verificar número único
        cursor.execute("SELECT id FROM bahias WHERE numero = %s", (bahia.numero,))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="Ya existe una bahía con este número")
        
        # Verificar tipo y estado válidos
        cursor.execute("SELECT id FROM tipos_bahia WHERE id = %s", (bahia.tipo_bahia_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=400, detail="Tipo de bahía no válido")
        
        cursor.execute("SELECT id FROM estados_bahia WHERE id = %s", (bahia.estado_bahia_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=400, detail="Estado de bahía no válido")
        
        # Crear bahía
        bahia_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO bahias (
                id, numero, tipo_bahia_id, estado_bahia_id, capacidad_maxima,
                ubicacion, observaciones, activo, fecha_creacion, 
                fecha_ultima_modificacion, creado_por
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, 1, GETDATE(), GETDATE(), %s)
        """, (bahia_id, bahia.numero, bahia.tipo_bahia_id, bahia.estado_bahia_id,
              bahia.capacidad_maxima, bahia.ubicacion, bahia.observaciones, current_user))
        
        conn.commit()
        
        # Retornar bahía creada
        cursor.execute("""
            SELECT b.id, b.numero, b.tipo_bahia_id, b.estado_bahia_id,
                   b.capacidad_maxima, b.ubicacion, b.observaciones,
                   b.activo, b.fecha_creacion, b.fecha_ultima_modificacion,
                   b.creado_por
            FROM bahias b
            WHERE b.id = %s
        """, (bahia_id,))
        bahia_creada = dict_row(cursor)
        cursor.close()
        
        return BahiaResponse(**bahia_creada)
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/tipos/")
async def obtener_tipos_bahia(conn = Depends(get_db)):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, codigo, nombre, descripcion FROM tipos_bahia WHERE activo = 1")
        tipos = dict_cursor(cursor)
        cursor.close()
        return tipos
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/estados/")
async def obtener_estados_bahia(conn = Depends(get_db)):
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id, codigo, nombre, descripcion, color FROM estados_bahia WHERE activo = 1")
        estados = dict_cursor(cursor)
        cursor.close()
        return estados
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

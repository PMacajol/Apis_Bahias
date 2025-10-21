from fastapi import APIRouter, HTTPException, Depends, Query
from app.database import get_db,db
from app.models.pydantic_models import (
    MantenimientoResponse, MantenimientoCreate, 
    TipoMantenimiento, EstadoMantenimiento, TipoUsuario
)
from app.core.security import get_current_user
import pymssql
import uuid
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/mantenimientos", tags=["mantenimientos"])

@router.get("/", response_model=list[MantenimientoResponse])
async def obtener_mantenimientos(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    estado: Optional[EstadoMantenimiento] = Query(None),
    tipo_mantenimiento: Optional[TipoMantenimiento] = Query(None),
    bahia_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        query = """
            SELECT m.id, m.bahia_id, m.tipo_mantenimiento, m.descripcion,
                   m.fecha_inicio, m.fecha_fin_programada, m.fecha_fin_real,
                   m.estado, m.tecnico_responsable, m.costo, m.observaciones,
                   m.usuario_registro, m.fecha_registro,
                   b.numero as numero_bahia,
                   u.nombre as usuario_nombre
            FROM mantenimientos m
            INNER JOIN bahias b ON m.bahia_id = b.id
            INNER JOIN usuarios u ON m.usuario_registro = u.id
            WHERE 1=1
        """
        params = []
        
        if estado:
            query += " AND m.estado = %s"
            params.append(estado.value)
        
        if tipo_mantenimiento:
            query += " AND m.tipo_mantenimiento = %s"
            params.append(tipo_mantenimiento.value)
        
        if bahia_id:
            query += " AND m.bahia_id = %s"
            params.append(bahia_id)
        
        query += " ORDER BY m.fecha_inicio DESC OFFSET %s ROWS FETCH NEXT %s ROWS ONLY"
        params.extend([skip, limit])
        
        cursor.execute(query, tuple(params))

        mantenimientos = cursor.fetchall()
        cursor.close()
        
        return [MantenimientoResponse(**mantenimiento) for mantenimiento in mantenimientos]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/{mantenimiento_id}", response_model=MantenimientoResponse)
async def obtener_mantenimiento(
    mantenimiento_id: str,
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        cursor.execute("""
            SELECT m.id, m.bahia_id, m.tipo_mantenimiento, m.descripcion,
                   m.fecha_inicio, m.fecha_fin_programada, m.fecha_fin_real,
                   m.estado, m.tecnico_responsable, m.costo, m.observaciones,
                   m.usuario_registro, m.fecha_registro,
                   b.numero as numero_bahia,
                   u.nombre as usuario_nombre
            FROM mantenimientos m
            INNER JOIN bahias b ON m.bahia_id = b.id
            INNER JOIN usuarios u ON m.usuario_registro = u.id
            WHERE m.id = %s
        """, (mantenimiento_id,))
        
        mantenimiento = cursor.fetchone()
        cursor.close()
        
        if not mantenimiento:
            raise HTTPException(status_code=404, detail="Mantenimiento no encontrado")
        
        return MantenimientoResponse(**mantenimiento)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/", response_model=MantenimientoResponse)
async def crear_mantenimiento(
    mantenimiento: MantenimientoCreate,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos (solo admin, operador y supervisor)
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.OPERADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para crear mantenimientos")
        
        # Verificar que la bahía existe
        cursor.execute("SELECT id FROM bahias WHERE id = %s AND activo = 1", (mantenimiento.bahia_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Bahía no encontrada o inactiva")
        
        # Verificar fechas
        if mantenimiento.fecha_fin_programada <= mantenimiento.fecha_inicio:
            raise HTTPException(status_code=400, detail="La fecha de fin programada debe ser posterior a la de inicio")
        
        # Verificar que no haya conflictos con reservas activas
        cursor.execute("""
            SELECT id 
            FROM reservas 
            WHERE bahia_id = %s 
            AND estado = 'activa'
            AND (
                (fecha_hora_inicio <= %s AND fecha_hora_fin > %s) OR
                (fecha_hora_inicio < %s AND fecha_hora_fin >= %s) OR
                (fecha_hora_inicio >= %s AND fecha_hora_fin <= %s)
            )
        """, (mantenimiento.bahia_id, mantenimiento.fecha_fin_programada, mantenimiento.fecha_inicio,
              mantenimiento.fecha_fin_programada, mantenimiento.fecha_inicio,
              mantenimiento.fecha_inicio, mantenimiento.fecha_fin_programada))
        
        if cursor.fetchone():
            raise HTTPException(
                status_code=400, 
                detail="Existen reservas activas en el período del mantenimiento"
            )
        
        # Crear mantenimiento
        mantenimiento_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO mantenimientos (
                id, bahia_id, tipo_mantenimiento, descripcion, fecha_inicio,
                fecha_fin_programada, estado, tecnico_responsable, costo,
                observaciones, usuario_registro, fecha_registro
            ) VALUES (%s, %s, %s, %s, %s, %s, 'programado', %s, %s, %s, %s, GETDATE())
        """, (mantenimiento_id, mantenimiento.bahia_id, mantenimiento.tipo_mantenimiento.value,
              mantenimiento.descripcion, mantenimiento.fecha_inicio, mantenimiento.fecha_fin_programada,
              mantenimiento.tecnico_responsable, mantenimiento.costo, mantenimiento.observaciones,
              current_user))
        
        # Actualizar estado de la bahía a "mantenimiento"
        cursor.execute("""
            UPDATE bahias 
            SET estado_bahia_id = (SELECT id FROM estados_bahia WHERE codigo = 'mantenimiento'),
                fecha_ultima_modificacion = GETDATE()
            WHERE id = %s
        """, (mantenimiento.bahia_id,))
        
        conn.commit()
        
        # Obtener mantenimiento creado
        cursor.execute("""
            SELECT m.id, m.bahia_id, m.tipo_mantenimiento, m.descripcion,
                   m.fecha_inicio, m.fecha_fin_programada, m.fecha_fin_real,
                   m.estado, m.tecnico_responsable, m.costo, m.observaciones,
                   m.usuario_registro, m.fecha_registro
            FROM mantenimientos m
            WHERE m.id = %s
        """, (mantenimiento_id,))
        
        mantenimiento_creado = cursor.fetchone()
        cursor.close()
        
        return MantenimientoResponse(**mantenimiento_creado)
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{mantenimiento_id}/iniciar")
async def iniciar_mantenimiento(
    mantenimiento_id: str,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.OPERADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para iniciar mantenimientos")
        
        # Obtener mantenimiento
        cursor.execute("""
            SELECT id, bahia_id, estado, fecha_inicio
            FROM mantenimientos 
            WHERE id = %s
        """, (mantenimiento_id,))
        
        mantenimiento = cursor.fetchone()
        if not mantenimiento:
            raise HTTPException(status_code=404, detail="Mantenimiento no encontrado")
        
        # Verificar que esté programado
        if mantenimiento["estado"] != "programado":
            raise HTTPException(status_code=400, detail="Solo se pueden iniciar mantenimientos programados")
        
        # Iniciar mantenimiento
        cursor.execute("""
            UPDATE mantenimientos 
            SET estado = 'en_progreso'
            WHERE id = %s
        """, (mantenimiento_id,))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Mantenimiento iniciado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{mantenimiento_id}/completar")
async def completar_mantenimiento(
    mantenimiento_id: str,
    observaciones: str = Query(None),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.OPERADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para completar mantenimientos")
        
        # Obtener mantenimiento
        cursor.execute("""
            SELECT id, bahia_id, estado
            FROM mantenimientos 
            WHERE id = %s
        """, (mantenimiento_id,))
        
        mantenimiento = cursor.fetchone()
        if not mantenimiento:
            raise HTTPException(status_code=404, detail="Mantenimiento no encontrado")
        
        # Verificar que esté en progreso
        if mantenimiento["estado"] != "en_progreso":
            raise HTTPException(status_code=400, detail="Solo se pueden completar mantenimientos en progreso")
        
        # Completar mantenimiento
        update_query = """
            UPDATE mantenimientos 
            SET estado = 'completado', fecha_fin_real = GETDATE()
        """
        params = [mantenimiento_id]
        
        if observaciones:
            update_query += ", observaciones = %s"
            params.insert(0, observaciones)
        
        update_query += " WHERE id = %s"
        cursor.execute(update_query, tuple(params))       
        # Liberar bahía
        cursor.execute("""
            UPDATE bahias 
            SET estado_bahia_id = (SELECT id FROM estados_bahia WHERE codigo = 'libre'),
                fecha_ultima_modificacion = GETDATE()
            WHERE id = %s
        """, (mantenimiento["bahia_id"],))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Mantenimiento completado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{mantenimiento_id}/cancelar")
async def cancelar_mantenimiento(
    mantenimiento_id: str,
    motivo: str = Query(..., description="Motivo de la cancelación"),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para cancelar mantenimientos")
        
        # Obtener mantenimiento
        cursor.execute("""
            SELECT id, bahia_id, estado
            FROM mantenimientos 
            WHERE id = %s
        """, (mantenimiento_id,))
        
        mantenimiento = cursor.fetchone()
        if not mantenimiento:
            raise HTTPException(status_code=404, detail="Mantenimiento no encontrado")
        
        # Verificar que no esté completado
        if mantenimiento["estado"] == "completado":
            raise HTTPException(status_code=400, detail="No se puede cancelar un mantenimiento completado")
        
        # Cancelar mantenimiento
        cursor.execute("""
            UPDATE mantenimientos 
            SET estado = 'cancelado', 
                observaciones = CONCAT(ISNULL(observaciones, ''), ' - Cancelado: ', %s)
            WHERE id = %s
        """, (motivo, mantenimiento_id))
        
        # Liberar bahía si no hay otros mantenimientos activos
        cursor.execute("""
            SELECT COUNT(*) as mantenimientos_activos
            FROM mantenimientos 
            WHERE bahia_id = %s 
            AND estado IN ('programado', 'en_progreso')
            AND id != %s
        """, (mantenimiento["bahia_id"], mantenimiento_id))
        
        otros_mantenimientos = cursor.fetchone()["mantenimientos_activos"]
        
        if otros_mantenimientos == 0:
            cursor.execute("""
                UPDATE bahias 
                SET estado_bahia_id = (SELECT id FROM estados_bahia WHERE codigo = 'libre'),
                    fecha_ultima_modificacion = GETDATE()
                WHERE id = %s
            """, (mantenimiento["bahia_id"],))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Mantenimiento cancelado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/bahia/{bahia_id}")
async def obtener_mantenimientos_bahia(
    bahia_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        cursor.execute("""
            SELECT m.id, m.tipo_mantenimiento, m.descripcion, m.fecha_inicio,
                   m.fecha_fin_programada, m.fecha_fin_real, m.estado,
                   m.tecnico_responsable, m.costo, m.observaciones, m.fecha_registro
            FROM mantenimientos m
            WHERE m.bahia_id = %s
            ORDER BY m.fecha_inicio DESC
            OFFSET %s ROWS FETCH NEXT %s ROWS ONLY
        """, (bahia_id, skip, limit))
        
        mantenimientos = cursor.fetchall()
        cursor.close()
        
        return mantenimientos
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
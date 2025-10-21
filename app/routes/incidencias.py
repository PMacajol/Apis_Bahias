from fastapi import APIRouter, HTTPException, Depends, Query
from app.database import get_db,db
from app.models.pydantic_models import (
    IncidenciaResponse, IncidenciaCreate, SeveridadIncidencia, TipoUsuario
)
from app.core.security import get_current_user
import pymssql
import uuid
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/incidencias", tags=["incidencias"])

@router.get("/", response_model=list[IncidenciaResponse])
async def obtener_incidencias(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    estado: Optional[str] = Query(None),
    severidad: Optional[SeveridadIncidencia] = Query(None),
    bahia_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos (solo admin y supervisor pueden ver todas las incidencias)
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        query = """
            SELECT i.id, i.bahia_id, i.reserva_id, i.tipo_incidencia, i.descripcion,
                   i.severidad, i.estado, i.fecha_incidencia, i.fecha_resolucion,
                   i.reportado_por, i.asignado_a, i.resolucion, i.fecha_registro,
                   b.numero as numero_bahia,
                   u1.nombre as reportado_por_nombre,
                   u2.nombre as asignado_a_nombre
            FROM incidencias i
            LEFT JOIN bahias b ON i.bahia_id = b.id
            INNER JOIN usuarios u1 ON i.reportado_por = u1.id
            LEFT JOIN usuarios u2 ON i.asignado_a = u2.id
            WHERE 1=1
        """
        params = []
        
        # Si no es admin o supervisor, solo puede ver sus propias incidencias reportadas
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            query += " AND i.reportado_por = %s"
            params.append(current_user)
        
        if estado:
            query += " AND i.estado = %s"
            params.append(estado)
        
        if severidad:
            query += " AND i.severidad = %s"
            params.append(severidad.value)
        
        if bahia_id:
            query += " AND i.bahia_id = %s"
            params.append(bahia_id)
        
        query += " ORDER BY i.fecha_incidencia DESC OFFSET %s ROWS FETCH NEXT %s ROWS ONLY"
        params.extend([skip, limit])
        
        cursor.execute(query, tuple(params))

        incidencias = cursor.fetchall()
        cursor.close()
        
        return [IncidenciaResponse(**incidencia) for incidencia in incidencias]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/{incidencia_id}", response_model=IncidenciaResponse)
async def obtener_incidencia(
    incidencia_id: str,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        cursor.execute("""
            SELECT i.id, i.bahia_id, i.reserva_id, i.tipo_incidencia, i.descripcion,
                   i.severidad, i.estado, i.fecha_incidencia, i.fecha_resolucion,
                   i.reportado_por, i.asignado_a, i.resolucion, i.fecha_registro,
                   b.numero as numero_bahia,
                   u1.nombre as reportado_por_nombre,
                   u2.nombre as asignado_a_nombre
            FROM incidencias i
            LEFT JOIN bahias b ON i.bahia_id = b.id
            INNER JOIN usuarios u1 ON i.reportado_por = u1.id
            LEFT JOIN usuarios u2 ON i.asignado_a = u2.id
            WHERE i.id = %s
        """, (incidencia_id,))
        
        incidencia = cursor.fetchone()
        cursor.close()
        
        if not incidencia:
            raise HTTPException(status_code=404, detail="Incidencia no encontrada")
        
        # Verificar permisos
        cursor = db.get_cursor(conn)
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        cursor.close()
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI] and incidencia["reportado_por"] != current_user:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver esta incidencia")
        
        return IncidenciaResponse(**incidencia)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/", response_model=IncidenciaResponse)
async def crear_incidencia(
    incidencia: IncidenciaCreate,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Validar referencias
        if incidencia.bahia_id:
            cursor.execute("SELECT id FROM bahias WHERE id = %s", (incidencia.bahia_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Bahía no encontrada")
        
        if incidencia.reserva_id:
            cursor.execute("SELECT id FROM reservas WHERE id = %s", (incidencia.reserva_id,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail="Reserva no encontrada")
        
        # Crear incidencia
        incidencia_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO incidencias (
                id, bahia_id, reserva_id, tipo_incidencia, descripcion,
                severidad, estado, fecha_incidencia, reportado_por, fecha_registro
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, GETDATE())
        """, (incidencia_id, incidencia.bahia_id, incidencia.reserva_id,
              incidencia.tipo_incidencia, incidencia.descripcion, incidencia.severidad.value,
              incidencia.estado, datetime.now(), current_user))
        
        conn.commit()
        
        # Obtener incidencia creada
        cursor.execute("""
            SELECT i.id, i.bahia_id, i.reserva_id, i.tipo_incidencia, i.descripcion,
                   i.severidad, i.estado, i.fecha_incidencia, i.fecha_resolucion,
                   i.reportado_por, i.asignado_a, i.resolucion, i.fecha_registro
            FROM incidencias i
            WHERE i.id = %s
        """, (incidencia_id,))
        
        incidencia_creada = cursor.fetchone()
        cursor.close()
        
        return IncidenciaResponse(**incidencia_creada)
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{incidencia_id}/asignar")
async def asignar_incidencia(
    incidencia_id: str,
    usuario_asignado: str = Query(..., description="ID del usuario a asignar"),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos (solo admin y supervisor pueden asignar)
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para asignar incidencias")
        
        # Verificar que la incidencia existe
        cursor.execute("SELECT id, estado FROM incidencias WHERE id = %s", (incidencia_id,))
        incidencia = cursor.fetchone()
        
        if not incidencia:
            raise HTTPException(status_code=404, detail="Incidencia no encontrada")
        
        # Verificar que el usuario asignado existe
        cursor.execute("SELECT id FROM usuarios WHERE id = %s AND activo = 1", (usuario_asignado,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Usuario asignado no encontrado")
        
        # Asignar incidencia
        cursor.execute("""
            UPDATE incidencias 
            SET asignado_a = %s, estado = 'en_proceso'
            WHERE id = %s
        """, (usuario_asignado, incidencia_id))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Incidencia asignada correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{incidencia_id}/resolver")
async def resolver_incidencia(
    incidencia_id: str,
    resolucion: str = Query(..., description="Descripción de la resolución"),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Obtener incidencia
        cursor.execute("""
            SELECT id, asignado_a, estado 
            FROM incidencias 
            WHERE id = %s
        """, (incidencia_id,))
        
        incidencia = cursor.fetchone()
        if not incidencia:
            raise HTTPException(status_code=404, detail="Incidencia no encontrada")
        
        # Verificar permisos (solo asignado, admin o supervisor pueden resolver)
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        puede_resolver = (
            user_tipo in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI] or
            incidencia["asignado_a"] == current_user
        )
        
        if not puede_resolver:
            raise HTTPException(status_code=403, detail="No tiene permisos para resolver esta incidencia")
        
        # Verificar que esté en proceso
        if incidencia["estado"] != "en_proceso":
            raise HTTPException(status_code=400, detail="Solo se pueden resolver incidencias en proceso")
        
        # Resolver incidencia
        cursor.execute("""
            UPDATE incidencias 
            SET estado = 'resuelta', 
                resolucion = %s,
                fecha_resolucion = GETDATE()
            WHERE id = %s
        """, (resolucion, incidencia_id))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Incidencia resuelta correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{incidencia_id}/cerrar")
async def cerrar_incidencia(
    incidencia_id: str,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos (solo admin y supervisor pueden cerrar)
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para cerrar incidencias")
        
        # Obtener incidencia
        cursor.execute("SELECT id, estado FROM incidencias WHERE id = %s", (incidencia_id,))
        incidencia = cursor.fetchone()
        
        if not incidencia:
            raise HTTPException(status_code=404, detail="Incidencia no encontrada")
        
        # Verificar que esté resuelta
        if incidencia["estado"] != "resuelta":
            raise HTTPException(status_code=400, detail="Solo se pueden cerrar incidencias resueltas")
        
        # Cerrar incidencia
        cursor.execute("""
            UPDATE incidencias 
            SET estado = 'cerrada'
            WHERE id = %s
        """, (incidencia_id,))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Incidencia cerrada correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/estadisticas/resumen")
async def obtener_estadisticas_incidencias(
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver estadísticas")
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total,
                COUNT(CASE WHEN estado = 'abierta' THEN 1 END) as abiertas,
                COUNT(CASE WHEN estado = 'en_proceso' THEN 1 END) as en_proceso,
                COUNT(CASE WHEN estado = 'resuelta' THEN 1 END) as resueltas,
                COUNT(CASE WHEN estado = 'cerrada' THEN 1 END) as cerradas,
                COUNT(CASE WHEN severidad = 'critica' THEN 1 END) as criticas,
                COUNT(CASE WHEN severidad = 'alta' THEN 1 END) as altas,
                COUNT(CASE WHEN severidad = 'media' THEN 1 END) as medias,
                COUNT(CASE WHEN severidad = 'baja' THEN 1 END) as bajas
            FROM incidencias
        """)
        
        estadisticas = cursor.fetchone()
        cursor.close()
        
        return estadisticas
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
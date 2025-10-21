from fastapi import APIRouter, HTTPException, Depends, Query
from app.database import get_db
from app.database import db, get_db
from app.models.pydantic_models import (
    ReservaResponse, ReservaCreate, EstadoReserva, TipoUsuario
)
from app.core.security import get_current_user
import pymssql
import uuid
from datetime import datetime, timedelta
from typing import Optional
from datetime import timezone


router = APIRouter(prefix="/reservas", tags=["reservas"])

@router.get("/", response_model=list[ReservaResponse])
async def obtener_reservas(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    estado: Optional[EstadoReserva] = Query(None),
    bahia_id: Optional[str] = Query(None),
    usuario_id: Optional[str] = Query(None),
    fecha_inicio: Optional[datetime] = Query(None),
    fecha_fin: Optional[datetime] = Query(None),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn) 
        
        # Verificar permisos para ver todas las reservas
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        query = """
            SELECT r.id, r.bahia_id, r.usuario_id, r.fecha_hora_inicio, 
                   r.fecha_hora_fin, r.estado, r.vehiculo_placa, 
                   r.conductor_nombre, r.conductor_telefono, r.conductor_documento,
                   r.mercancia_tipo, r.mercancia_peso, r.mercancia_descripcion,
                   r.observaciones, r.fecha_creacion, r.fecha_cancelacion,
                   r.fecha_completacion, r.cancelado_por, r.motivo_cancelacion,
                   b.numero as numero_bahia,
                   u.nombre as usuario_nombre,
                   u.email as usuario_email
            FROM reservas r
            INNER JOIN bahias b ON r.bahia_id = b.id
            INNER JOIN usuarios u ON r.usuario_id = u.id
            WHERE 1=1
        """
        params = []
        
        # Si no es admin, solo puede ver sus propias reservas
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
            query += " AND r.usuario_id = %s"
            params.append(current_user)
        
        if estado:
            query += " AND r.estado = %s"
            params.append(estado.value)
        
        if bahia_id:
            query += " AND r.bahia_id = %s"
            params.append(bahia_id)
        
        if usuario_id:
            # Solo admin puede filtrar por otros usuarios
            if user_tipo in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI]:
                query += " AND r.usuario_id = %s"
                params.append(usuario_id)
        
        if fecha_inicio:
            query += " AND r.fecha_hora_inicio >= %s"
            params.append(fecha_inicio)
        
        if fecha_fin:
            query += " AND r.fecha_hora_fin <= %s"
            params.append(fecha_fin)
        
        query += " ORDER BY r.fecha_hora_inicio DESC OFFSET %s ROWS FETCH NEXT %s ROWS ONLY"
        params.extend([skip, limit])
        
        cursor.execute(query, tuple(params))

        reservas = cursor.fetchall()
        cursor.close()
        
        return [ReservaResponse(**reserva) for reserva in reservas]
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/{reserva_id}", response_model=ReservaResponse)
async def obtener_reserva(
    reserva_id: str,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn) 
        
        cursor.execute("""
            SELECT r.id, r.bahia_id, r.usuario_id, r.fecha_hora_inicio, 
                   r.fecha_hora_fin, r.estado, r.vehiculo_placa, 
                   r.conductor_nombre, r.conductor_telefono, r.conductor_documento,
                   r.mercancia_tipo, r.mercancia_peso, r.mercancia_descripcion,
                   r.observaciones, r.fecha_creacion, r.fecha_cancelacion,
                   r.fecha_completacion, r.cancelado_por, r.motivo_cancelacion,
                   b.numero as numero_bahia,
                   u.nombre as usuario_nombre,
                   u.email as usuario_email
            FROM reservas r
            INNER JOIN bahias b ON r.bahia_id = b.id
            INNER JOIN usuarios u ON r.usuario_id = u.id
            WHERE r.id = %s
        """, (reserva_id,))
        
        reserva = cursor.fetchone()
        cursor.close()
        
        if not reserva:
            raise HTTPException(status_code=404, detail="Reserva no encontrada")
        
        # Verificar permisos (solo puede ver sus propias reservas a menos que sea admin)
        cursor = db.get_cursor(conn) 
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        cursor.close()
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI] and reserva["usuario_id"] != current_user:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver esta reserva")
        
        return ReservaResponse(**reserva)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/", response_model=ReservaResponse)
async def crear_reserva(
    reserva: ReservaCreate,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn) 
        
         # Normalizar fechas
        if reserva.fecha_hora_inicio.tzinfo is not None:
            reserva.fecha_hora_inicio = reserva.fecha_hora_inicio.astimezone(timezone.utc).replace(tzinfo=None)
        if reserva.fecha_hora_fin.tzinfo is not None:
            reserva.fecha_hora_fin = reserva.fecha_hora_fin.astimezone(timezone.utc).replace(tzinfo=None)

        

        # Verificar que la bahía existe y está activa
        cursor.execute("""
            SELECT id, estado_bahia_id, activo 
            FROM bahias 
            WHERE id = %s AND activo = 1
        """, (reserva.bahia_id,))
        
        bahia = cursor.fetchone()
        if not bahia:
            raise HTTPException(status_code=404, detail="Bahía no encontrada o inactiva")
        
        # Verificar que la bahía no esté en mantenimiento
        cursor.execute("SELECT codigo FROM estados_bahia WHERE id = %s", (bahia["estado_bahia_id"],))
        estado_bahia = cursor.fetchone()["codigo"]
        
        if estado_bahia == "mantenimiento":
            raise HTTPException(status_code=400, detail="No se puede reservar una bahía en mantenimiento")
        
        # Validar fechas
        if reserva.fecha_hora_fin <= reserva.fecha_hora_inicio:
            raise HTTPException(status_code=400, detail="La fecha de fin debe ser posterior a la de inicio")
        
        if reserva.fecha_hora_inicio < datetime.now():
            raise HTTPException(status_code=400, detail="No se pueden crear reservas en el pasado")
        
        # Validar disponibilidad usando el stored procedure
        cursor.execute("""
            DECLARE @disponible BIT;
            DECLARE @mensaje VARCHAR(255);
            EXEC sp_validar_disponibilidad_bahia 
                @bahia_id = %s, 
                @fecha_inicio = %s, 
                @fecha_fin = %s,
                @disponible = @disponible OUTPUT,
                @mensaje = @mensaje OUTPUT;
            SELECT @disponible as disponible, @mensaje as mensaje;
        """, (reserva.bahia_id, reserva.fecha_hora_inicio, reserva.fecha_hora_fin))
        
        resultado = cursor.fetchone()
        if not resultado["disponible"]:
            raise HTTPException(status_code=400, detail=resultado["mensaje"])
        
        # Crear reserva
        reserva_id = str(uuid.uuid4())
        
        cursor.execute("""
            INSERT INTO reservas (
                id, bahia_id, usuario_id, fecha_hora_inicio, fecha_hora_fin,
                estado, vehiculo_placa, conductor_nombre, conductor_telefono,
                conductor_documento, mercancia_tipo, mercancia_peso,
                mercancia_descripcion, observaciones, fecha_creacion
            ) VALUES (%s, %s, %s, %s, %s, 'activa', %s, %s, %s, %s, %s, %s, %s, %s, GETDATE())
        """, (reserva_id, reserva.bahia_id, current_user, reserva.fecha_hora_inicio,
              reserva.fecha_hora_fin, reserva.vehiculo_placa, reserva.conductor_nombre,
              reserva.conductor_telefono, reserva.conductor_documento, reserva.mercancia_tipo,
              reserva.mercancia_peso, reserva.mercancia_descripcion, reserva.observaciones))
        
        # Actualizar estado de la bahía a "reservada"
        cursor.execute("""
            UPDATE bahias 
            SET estado_bahia_id = (SELECT id FROM estados_bahia WHERE codigo = 'reservada'),
                fecha_ultima_modificacion = GETDATE()
            WHERE id = %s
        """, (reserva.bahia_id,))
        
        conn.commit()
        
        # Obtener reserva creada
        cursor.execute("""
            SELECT r.id, r.bahia_id, r.usuario_id, r.fecha_hora_inicio, 
                   r.fecha_hora_fin, r.estado, r.vehiculo_placa, 
                   r.conductor_nombre, r.conductor_telefono, r.conductor_documento,
                   r.mercancia_tipo, r.mercancia_peso, r.mercancia_descripcion,
                   r.observaciones, r.fecha_creacion, r.fecha_cancelacion,
                   r.fecha_completacion, r.cancelado_por, r.motivo_cancelacion,
                   b.numero as numero_bahia,
                   u.nombre as usuario_nombre,
                   u.email as usuario_email
            FROM reservas r
            INNER JOIN bahias b ON r.bahia_id = b.id
            INNER JOIN usuarios u ON r.usuario_id = u.id
            WHERE r.id = %s
        """, (reserva_id,))
        
        reserva_creada = cursor.fetchone()
        cursor.close()
        
        return ReservaResponse(**reserva_creada)
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{reserva_id}/cancelar")
async def cancelar_reserva(
    reserva_id: str,
    motivo: str = Query(..., description="Motivo de la cancelación"),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn) 
        
        # Obtener reserva
        cursor.execute("""
            SELECT id, bahia_id, usuario_id, estado, fecha_hora_inicio
            FROM reservas 
            WHERE id = %s
        """, (reserva_id,))
        
        reserva = cursor.fetchone()
        if not reserva:
            raise HTTPException(status_code=404, detail="Reserva no encontrada")
        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI] and reserva["usuario_id"] != current_user:
            raise HTTPException(status_code=403, detail="No tiene permisos para cancelar esta reserva")
        
        # Verificar que la reserva esté activa
        if reserva["estado"] != "activa":
            raise HTTPException(status_code=400, detail="Solo se pueden cancelar reservas activas")
        
        # Verificar que no haya comenzado
        if reserva["fecha_hora_inicio"] <= datetime.now():
            raise HTTPException(status_code=400, detail="No se puede cancelar una reserva que ya ha comenzado")
        
        # Cancelar reserva
        cursor.execute("""
            UPDATE reservas 
            SET estado = 'cancelada', 
                fecha_cancelacion = GETDATE(),
                cancelado_por = %s,
                motivo_cancelacion = %s
            WHERE id = %s
        """, (current_user, motivo, reserva_id))
        
        # Liberar bahía
        cursor.execute("""
            UPDATE bahias 
            SET estado_bahia_id = (SELECT id FROM estados_bahia WHERE codigo = 'libre'),
                fecha_ultima_modificacion = GETDATE()
            WHERE id = %s
        """, (reserva["bahia_id"],))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Reserva cancelada correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{reserva_id}/completar")
async def completar_reserva(
    reserva_id: str,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn) 
        
        # Obtener reserva
        cursor.execute("""
            SELECT id, bahia_id, usuario_id, estado
            FROM reservas 
            WHERE id = %s
        """, (reserva_id,))
        
        reserva = cursor.fetchone()
        if not reserva:
            raise HTTPException(status_code=404, detail="Reserva no encontrada")
        
        # Verificar permisos (solo admin, supervisor o el propio usuario)
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.ADMINISTRADOR_TI] and reserva["usuario_id"] != current_user:
            raise HTTPException(status_code=403, detail="No tiene permisos para completar esta reserva")
        
        # Verificar que la reserva esté activa
        if reserva["estado"] != "activa":
            raise HTTPException(status_code=400, detail="Solo se pueden completar reservas activas")
        
        # Completar reserva
        cursor.execute("""
            UPDATE reservas 
            SET estado = 'completada', 
                fecha_completacion = GETDATE()
            WHERE id = %s
        """, (reserva_id,))
        
        # Liberar bahía
        cursor.execute("""
            UPDATE bahias 
            SET estado_bahia_id = (SELECT id FROM estados_bahia WHERE codigo = 'libre'),
                fecha_ultima_modificacion = GETDATE()
            WHERE id = %s
        """, (reserva["bahia_id"],))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Reserva completada correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/disponibilidad/verificar")
async def verificar_disponibilidad(
    bahia_id: str = Query(..., description="ID de la bahía"),
    conn = Depends(get_db)
):
    """
    Verifica la disponibilidad actual de una bahía.
    Devuelve si está libre, reservada o en mantenimiento.
    """
    try:
        cursor = db.get_cursor(conn)

        cursor.execute("""
            SELECT 
                b.id,
                b.numero,
                b.activo,
                eb.codigo AS codigo_estado,
                eb.nombre AS estado_nombre
            FROM bahias b
            INNER JOIN estados_bahia eb ON b.estado_bahia_id = eb.id
            WHERE b.id = %s
        """, (bahia_id,))

        bahia = cursor.fetchone()
        cursor.close()

        if not bahia:
            raise HTTPException(status_code=404, detail="Bahía no encontrada")

        # Evaluar estado
        estado = bahia["codigo_estado"].lower()

        if estado == "libre":
            disponible = True
            mensaje = f"La bahía {bahia['numero']} está disponible."
        elif estado == "reservada":
            disponible = False
            mensaje = f"La bahía {bahia['numero']} se encuentra reservada."
        elif estado == "mantenimiento":
            disponible = False
            mensaje = f"La bahía {bahia['numero']} está en mantenimiento."
        else:
            disponible = False
            mensaje = f"Estado desconocido para la bahía {bahia['numero']}."

        return {
            "bahia_id": bahia["id"],
            "numero": bahia["numero"],
            "estado": bahia["estado_nombre"],
            "disponible": disponible,
            "mensaje": mensaje
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

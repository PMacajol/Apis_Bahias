from fastapi import APIRouter, HTTPException, Depends, Query
from app.database import get_db,db
from app.models.pydantic_models import (
    ReporteUsoRequest, EstadisticasBahias, TipoUsuario
)
from app.core.security import get_current_user
import pymssql
from datetime import datetime, date, timedelta
from typing import List, Dict, Any

router = APIRouter(prefix="/reportes", tags=["reportes"])

@router.get("/estadisticas/bahias", response_model=EstadisticasBahias)
async def obtener_estadisticas_bahias(conn = Depends(get_db)):
    try:
        cursor = db.get_cursor(conn)
        
        cursor.execute("""
            SELECT 
                COUNT(*) as total_bahias,
                COUNT(CASE WHEN eb.codigo = 'libre' THEN 1 END) as bahias_libres,
                COUNT(CASE WHEN eb.codigo = 'en_uso' THEN 1 END) as bahias_ocupadas,
                COUNT(CASE WHEN eb.codigo = 'reservada' THEN 1 END) as bahias_reservadas,
                COUNT(CASE WHEN eb.codigo = 'mantenimiento' THEN 1 END) as bahias_mantenimiento
            FROM bahias b
            INNER JOIN estados_bahia eb ON b.estado_bahia_id = eb.id
            WHERE b.activo = 1
        """)
        
        stats = cursor.fetchone()
        
        # Calcular porcentaje de ocupación
        total = stats["total_bahias"]
        ocupadas = stats["bahias_ocupadas"] + stats["bahias_reservadas"]
        porcentaje_ocupacion = (ocupadas / total * 100) if total > 0 else 0
        
        cursor.close()
        
        return EstadisticasBahias(
            total_bahias=total,
            bahias_libres=stats["bahias_libres"],
            bahias_ocupadas=stats["bahias_ocupadas"],
            bahias_reservadas=stats["bahias_reservadas"],
            bahias_mantenimiento=stats["bahias_mantenimiento"],
            porcentaje_ocupacion=round(porcentaje_ocupacion, 2)
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/uso/diario")
async def obtener_reporte_uso_diario(
    fecha: date = Query(..., description="Fecha para el reporte (YYYY-MM-DD)"),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.PLANIFICADOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes")
        
        fecha_inicio = datetime.combine(fecha, datetime.min.time())
        fecha_fin = datetime.combine(fecha, datetime.max.time())
        
        cursor.execute("""
            SELECT 
                b.numero as bahia_numero,
                tb.nombre as tipo_bahia,
                eb.nombre as estado_actual,
                COUNT(r.id) as total_reservas,
                SUM(CASE WHEN r.estado = 'completada' THEN 1 ELSE 0 END) as reservas_completadas,
                AVG(DATEDIFF(MINUTE, r.fecha_hora_inicio, r.fecha_hora_fin)) as duracion_promedio_minutos
            FROM bahias b
            LEFT JOIN tipos_bahia tb ON b.tipo_bahia_id = tb.id
            LEFT JOIN estados_bahia eb ON b.estado_bahia_id = eb.id
            LEFT JOIN reservas r ON b.id = r.bahia_id 
                AND r.fecha_hora_inicio >= %s 
                AND r.fecha_hora_fin <= %s
            WHERE b.activo = 1
            GROUP BY b.numero, tb.nombre, eb.nombre
            ORDER BY b.numero
        """, (fecha_inicio, fecha_fin))
        
        reporte = cursor.fetchall()
        cursor.close()
        
        return {
            "fecha": fecha,
            "total_bahias": len(reporte),
            "detalle_bahias": reporte
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/uso/rango")
async def obtener_reporte_uso_rango(
    reporte_request: ReporteUsoRequest,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.PLANIFICADOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes")
        
        fecha_inicio = datetime.combine(reporte_request.fecha_inicio, datetime.min.time())
        fecha_fin = datetime.combine(reporte_request.fecha_fin, datetime.max.time())
        
        # Estadísticas generales
        cursor.execute("""
            SELECT 
                COUNT(*) as total_reservas,
                COUNT(CASE WHEN estado = 'completada' THEN 1 END) as reservas_completadas,
                COUNT(CASE WHEN estado = 'cancelada' THEN 1 END) as reservas_canceladas,
                AVG(DATEDIFF(MINUTE, fecha_hora_inicio, fecha_hora_fin)) as duracion_promedio_minutos,
                SUM(DATEDIFF(MINUTE, fecha_hora_inicio, fecha_hora_fin)) as tiempo_total_minutos
            FROM reservas
            WHERE fecha_hora_inicio >= %s AND fecha_hora_fin <= %s
        """, (fecha_inicio, fecha_fin))
        
        estadisticas = cursor.fetchone()
        
        # Uso por tipo de bahía
        cursor.execute("""
            SELECT 
                tb.nombre as tipo_bahia,
                COUNT(r.id) as total_reservas,
                COUNT(CASE WHEN r.estado = 'completada' THEN 1 END) as reservas_completadas,
                AVG(DATEDIFF(MINUTE, r.fecha_hora_inicio, r.fecha_hora_fin)) as duracion_promedio
            FROM reservas r
            INNER JOIN bahias b ON r.bahia_id = b.id
            INNER JOIN tipos_bahia tb ON b.tipo_bahia_id = tb.id
            WHERE r.fecha_hora_inicio >= %s AND r.fecha_hora_fin <= %s
            GROUP BY tb.nombre
            ORDER BY total_reservas DESC
        """, (fecha_inicio, fecha_fin))
        
        uso_por_tipo = cursor.fetchall()
        
        # Tendencia diaria
        cursor.execute("""
            SELECT 
                CAST(fecha_hora_inicio AS DATE) as fecha,
                COUNT(*) as reservas,
                COUNT(CASE WHEN estado = 'completada' THEN 1 END) as completadas
            FROM reservas
            WHERE fecha_hora_inicio >= %s AND fecha_hora_fin <= %s
            GROUP BY CAST(fecha_hora_inicio AS DATE)
            ORDER BY fecha
        """, (fecha_inicio, fecha_fin))
        
        tendencia = cursor.fetchall()
        
        cursor.close()
        
        return {
            "periodo": {
                "fecha_inicio": reporte_request.fecha_inicio,
                "fecha_fin": reporte_request.fecha_fin
            },
            "estadisticas_generales": estadisticas,
            "uso_por_tipo_bahia": uso_por_tipo,
            "tendencia_diaria": tendencia
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/reservas/activas")
async def obtener_reservas_activas(
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        cursor.execute("""
            SELECT 
                r.id,
                b.numero as numero_bahia,
                tb.nombre as tipo_bahia,
                u.nombre as usuario_nombre,
                r.fecha_hora_inicio,
                r.fecha_hora_fin,
                r.vehiculo_placa,
                r.conductor_nombre,
                r.mercancia_tipo,
                DATEDIFF(MINUTE, r.fecha_hora_inicio, r.fecha_hora_fin) as duracion_minutos,
                CASE 
                    WHEN GETDATE() < r.fecha_hora_inicio THEN 'pendiente'
                    WHEN GETDATE() BETWEEN r.fecha_hora_inicio AND r.fecha_hora_fin THEN 'en_progreso'
                    ELSE 'vencida'
                END as estado_temporal
            FROM reservas r
            INNER JOIN bahias b ON r.bahia_id = b.id
            INNER JOIN tipos_bahia tb ON b.tipo_bahia_id = tb.id
            INNER JOIN usuarios u ON r.usuario_id = u.id
            WHERE r.estado = 'activa'
            ORDER BY r.fecha_hora_inicio
        """)
        
        reservas_activas = cursor.fetchall()
        cursor.close()
        
        return {
            "total": len(reservas_activas),
            "reservas": reservas_activas
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/mantenimientos/pendientes")
async def obtener_mantenimientos_pendientes(
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = db.get_cursor(conn)
        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.SUPERVISOR, TipoUsuario.OPERADOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver reportes de mantenimiento")
        
        cursor.execute("""
            SELECT 
                m.id,
                b.numero as bahia_numero,
                m.tipo_mantenimiento,
                m.descripcion,
                m.fecha_inicio,
                m.fecha_fin_programada,
                m.estado,
                m.tecnico_responsable,
                DATEDIFF(DAY, GETDATE(), m.fecha_inicio) as dias_restantes
            FROM mantenimientos m
            INNER JOIN bahias b ON m.bahia_id = b.id
            WHERE m.estado IN ('programado', 'en_progreso')
            ORDER BY m.fecha_inicio
        """)
        
        mantenimientos = cursor.fetchall()
        cursor.close()
        
        return {
            "total": len(mantenimientos),
            "mantenimientos": mantenimientos
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/dashboard/indicadores")
async def obtener_indicadores_dashboard(conn = Depends(get_db)):
    try:
        cursor = db.get_cursor(conn)
        
        # Reservas hoy
        hoy = date.today()
        hoy_inicio = datetime.combine(hoy, datetime.min.time())
        hoy_fin = datetime.combine(hoy, datetime.max.time())
        
        cursor.execute("""
            SELECT COUNT(*) as reservas_hoy
            FROM reservas 
            WHERE CAST(fecha_hora_inicio AS DATE) = CAST(GETDATE() AS DATE)
        """)
        reservas_hoy = cursor.fetchone()["reservas_hoy"]
        
        # Reservas esta semana
        inicio_semana = hoy - timedelta(days=hoy.weekday())
        fin_semana = inicio_semana + timedelta(days=6)
        
        cursor.execute("""
            SELECT COUNT(*) as reservas_semana
            FROM reservas 
            WHERE fecha_hora_inicio >= %s AND fecha_hora_fin <= %s
        """, (inicio_semana, fin_semana))
        reservas_semana = cursor.fetchone()["reservas_semana"]
        
        # Bahías en uso crítico (más de 90% de tiempo usado)
        cursor.execute("""
            SELECT COUNT(*) as bahias_criticas
            FROM vista_estadisticas_bahias
            WHERE estado_actual = 'En uso' 
            AND duracion_promedio_minutos > 120  -- Más de 2 horas
        """)
        bahias_criticas = cursor.fetchone()["bahias_criticas"]
        
        # Incidencias abiertas
        cursor.execute("""
            SELECT COUNT(*) as incidencias_abiertas
            FROM incidencias 
            WHERE estado IN ('abierta', 'en_proceso')
        """)
        incidencias_abiertas = cursor.fetchone()["incidencias_abiertas"]
        
        cursor.close()
        
        return {
            "reservas_hoy": reservas_hoy,
            "reservas_semana": reservas_semana,
            "bahias_criticas": bahias_criticas,
            "incidencias_abiertas": incidencias_abiertas,
            "fecha_actual": datetime.now()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
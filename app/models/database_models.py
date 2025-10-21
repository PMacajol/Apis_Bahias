# Este archivo contiene modelos Pydantic para representar las tablas de la base de datos
# Los modelos principales ya están en pydantic_models.py
# Este archivo puede usarse para modelos adicionales específicos de la base de datos

from pydantic import BaseModel
from typing import Optional
from datetime import datetime

# Modelos para respuestas específicas de la base de datos
class BahiaDetalleResponse(BaseModel):
    id: str
    numero: int
    tipo_bahia_id: int
    estado_bahia_id: int
    tipo_bahia_nombre: str
    estado_bahia_nombre: str
    estado_bahia_codigo: str
    capacidad_maxima: Optional[float]
    ubicacion: Optional[str]
    observaciones: Optional[str]
    activo: bool
    fecha_creacion: datetime
    fecha_ultima_modificacion: datetime

class ReservaDetalleResponse(BaseModel):
    id: str
    bahia_id: str
    usuario_id: str
    numero_bahia: int
    usuario_nombre: str
    usuario_email: str
    fecha_hora_inicio: datetime
    fecha_hora_fin: datetime
    estado: str
    vehiculo_placa: Optional[str]
    conductor_nombre: Optional[str]
    conductor_telefono: Optional[str]
    conductor_documento: Optional[str]
    mercancia_tipo: Optional[str]
    mercancia_peso: Optional[float]
    mercancia_descripcion: Optional[str]
    observaciones: Optional[str]
    fecha_creacion: datetime

class MantenimientoDetalleResponse(BaseModel):
    id: str
    bahia_id: str
    numero_bahia: int
    tipo_mantenimiento: str
    descripcion: str
    fecha_inicio: datetime
    fecha_fin_programada: datetime
    fecha_fin_real: Optional[datetime]
    estado: str
    tecnico_responsable: Optional[str]
    costo: Optional[float]
    observaciones: Optional[str]
    usuario_registro: str
    usuario_nombre: str
    fecha_registro: datetime

class IncidenciaDetalleResponse(BaseModel):
    id: str
    bahia_id: Optional[str]
    reserva_id: Optional[str]
    numero_bahia: Optional[int]
    tipo_incidencia: str
    descripcion: str
    severidad: str
    estado: str
    fecha_incidencia: datetime
    fecha_resolucion: Optional[datetime]
    reportado_por: str
    reportado_por_nombre: str
    asignado_a: Optional[str]
    asignado_a_nombre: Optional[str]
    resolucion: Optional[str]
    fecha_registro: datetime
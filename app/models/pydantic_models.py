from pydantic import BaseModel, EmailStr, validator
from typing import Optional, List
from datetime import datetime, date
import re
from enum import Enum

class TipoUsuario(str, Enum):
    ADMINISTRADOR = "administrador"
    OPERADOR = "operador"
    PLANIFICADOR = "planificador"
    SUPERVISOR = "supervisor"
    ADMINISTRADOR_TI = "administrador_ti"

class EstadoReserva(str, Enum):
    ACTIVA = "activa"
    COMPLETADA = "completada"
    CANCELADA = "cancelada"

class TipoMantenimiento(str, Enum):
    PREVENTIVO = "preventivo"
    CORRECTIVO = "correctivo"
    EMERGENCIA = "emergencia"

class EstadoMantenimiento(str, Enum):
    PROGRAMADO = "programado"
    EN_PROGRESO = "en_progreso"
    COMPLETADO = "completado"
    CANCELADO = "cancelado"

class SeveridadIncidencia(str, Enum):
    BAJA = "baja"
    MEDIA = "media"
    ALTA = "alta"
    CRITICA = "critica"

# Modelos de Usuario
class UsuarioBase(BaseModel):
    email: EmailStr
    nombre: str

class UsuarioCreate(UsuarioBase):
    password: str
    tipo_usuario: TipoUsuario

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('La contraseña debe tener al menos 8 caracteres')
        if not re.search(r"[A-Z]", v):
            raise ValueError('La contraseña debe tener al menos una mayúscula')
        if not re.search(r"[a-z]", v):
            raise ValueError('La contraseña debe tener al menos una minúscula')
        if not re.search(r"\d", v):
            raise ValueError('La contraseña debe tener al menos un número')
        return v

class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str

class UsuarioResponse(UsuarioBase):
    id: str
    tipo_usuario: TipoUsuario
    activo: bool
    fecha_registro: datetime
    fecha_ultima_modificacion: datetime

    class Config:
        from_attributes = True

# Modelos de Bahía
class BahiaBase(BaseModel):
    numero: int
    tipo_bahia_id: int
    estado_bahia_id: int
    capacidad_maxima: Optional[float] = None
    ubicacion: Optional[str] = None
    observaciones: Optional[str] = None

class BahiaCreate(BahiaBase):
    pass

class BahiaResponse(BahiaBase):
    id: str
    activo: bool
    fecha_creacion: datetime
    fecha_ultima_modificacion: datetime
    creado_por: Optional[str] = None

    class Config:
        from_attributes = True

# Modelos de Reserva
class ReservaBase(BaseModel):
    bahia_id: str
    fecha_hora_inicio: datetime
    fecha_hora_fin: datetime
    vehiculo_placa: Optional[str] = None
    conductor_nombre: Optional[str] = None
    conductor_telefono: Optional[str] = None
    conductor_documento: Optional[str] = None
    mercancia_tipo: Optional[str] = None
    mercancia_peso: Optional[float] = None
    mercancia_descripcion: Optional[str] = None
    observaciones: Optional[str] = None

class ReservaCreate(ReservaBase):
    pass

class ReservaResponse(ReservaBase):
    id: str
    usuario_id: str
    estado: EstadoReserva
    fecha_creacion: datetime
    fecha_cancelacion: Optional[datetime] = None
    fecha_completacion: Optional[datetime] = None

    class Config:
        from_attributes = True

# Modelos de Mantenimiento
class MantenimientoBase(BaseModel):
    bahia_id: str
    tipo_mantenimiento: TipoMantenimiento
    descripcion: str
    fecha_inicio: datetime
    fecha_fin_programada: datetime
    tecnico_responsable: Optional[str] = None
    costo: Optional[float] = None
    observaciones: Optional[str] = None

class MantenimientoCreate(MantenimientoBase):
    pass

class MantenimientoResponse(MantenimientoBase):
    id: str
    estado: EstadoMantenimiento
    fecha_fin_real: Optional[datetime] = None
    usuario_registro: str
    fecha_registro: datetime

    class Config:
        from_attributes = True

# Modelos de Incidencia
class IncidenciaBase(BaseModel):
    bahia_id: Optional[str] = None
    reserva_id: Optional[str] = None
    tipo_incidencia: str
    descripcion: str
    severidad: SeveridadIncidencia
    estado: str = "abierta"

class IncidenciaCreate(IncidenciaBase):
    pass

class IncidenciaResponse(IncidenciaBase):
    id: str
    fecha_incidencia: datetime
    fecha_resolucion: Optional[datetime] = None
    reportado_por: str
    asignado_a: Optional[str] = None
    resolucion: Optional[str] = None
    fecha_registro: datetime

    class Config:
        from_attributes = True

# Modelos para reportes
class ReporteUsoRequest(BaseModel):
    fecha_inicio: date
    fecha_fin: date

class EstadisticasBahias(BaseModel):
    total_bahias: int
    bahias_libres: int
    bahias_ocupadas: int
    bahias_reservadas: int
    bahias_mantenimiento: int
    porcentaje_ocupacion: float

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    usuario: UsuarioResponse
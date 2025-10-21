from fastapi import APIRouter, HTTPException, Depends, Query
from app.database import get_db
from app.models.pydantic_models import (
    UsuarioResponse, UsuarioCreate, TipoUsuario
)
from app.core.security import get_current_user, get_password_hash
import pymssql
import uuid

router = APIRouter(prefix="/usuarios", tags=["usuarios"])

@router.get("/", response_model=list[UsuarioResponse])
async def obtener_usuarios(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    activo: bool = Query(None),
    tipo_usuario: TipoUsuario = Query(None),
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = conn.cursor(as_dict=True)

        
        # Verificar permisos (solo admin y admin_ti pueden ver todos los usuarios)
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver usuarios")
        
        # Construir query base
        query = """
            SELECT id, email, nombre, tipo_usuario, activo, 
                   fecha_registro, fecha_ultima_modificacion
            FROM usuarios 
            WHERE 1=1
        """
        params = []
        
        if activo is not None:
            query += " AND activo = %s"
            params.append(1 if activo else 0)
        
        if tipo_usuario:
            query += " AND tipo_usuario = %s"
            params.append(tipo_usuario.value)
        
        query += " ORDER BY fecha_registro DESC OFFSET %s ROWS FETCH NEXT %s ROWS ONLY"
        params.extend([skip, limit])
        
        cursor.execute(query, tuple(params))
        usuarios = cursor.fetchall()
        cursor.close()
        
        return [UsuarioResponse(**usuario) for usuario in usuarios]
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/{usuario_id}", response_model=UsuarioResponse)
async def obtener_usuario(
    usuario_id: str,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = conn.cursor(as_dict=True)

        
        # Verificar permisos o si es el propio usuario
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.ADMINISTRADOR_TI] and current_user != usuario_id:
            raise HTTPException(status_code=403, detail="No tiene permisos para ver este usuario")
        
        cursor.execute("""
            SELECT id, email, nombre, tipo_usuario, activo, 
                   fecha_registro, fecha_ultima_modificacion
            FROM usuarios 
            WHERE id = %s
        """, (usuario_id,))
        
        usuario = cursor.fetchone()
        cursor.close()
        
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        return UsuarioResponse(**usuario)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.put("/{usuario_id}", response_model=UsuarioResponse)
async def actualizar_usuario(
    usuario_id: str,
    usuario_update: UsuarioCreate,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = conn.cursor(as_dict=True)

        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.ADMINISTRADOR_TI] and current_user != usuario_id:
            raise HTTPException(status_code=403, detail="No tiene permisos para actualizar este usuario")
        
        # Verificar que el usuario existe
        cursor.execute("SELECT id FROM usuarios WHERE id = %s", (usuario_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Verificar email único
        cursor.execute("SELECT id FROM usuarios WHERE email = %s AND id != %s", (usuario_update.email, usuario_id))
        if cursor.fetchone():
            raise HTTPException(status_code=400, detail="El email ya está en uso")
        
        # Actualizar usuario
        hashed_password = get_password_hash(usuario_update.password)
        
        cursor.execute("""
            UPDATE usuarios 
            SET email = %s, nombre = %s, hash_contrasena = %s, 
                tipo_usuario = %s, fecha_ultima_modificacion = GETDATE()
            WHERE id = %s
        """, (usuario_update.email, usuario_update.nombre, hashed_password, 
              usuario_update.tipo_usuario, usuario_id))
        
        conn.commit()
        
        # Obtener usuario actualizado
        cursor.execute("""
            SELECT id, email, nombre, tipo_usuario, activo, 
                   fecha_registro, fecha_ultima_modificacion
            FROM usuarios 
            WHERE id = %s
        """, (usuario_id,))
        
        usuario = cursor.fetchone()
        cursor.close()
        
        return UsuarioResponse(**usuario)
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.delete("/{usuario_id}")
async def desactivar_usuario(
    usuario_id: str,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = conn.cursor(as_dict=True)

        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para desactivar usuarios")
        
        # No permitir desactivarse a sí mismo
        if current_user == usuario_id:
            raise HTTPException(status_code=400, detail="No puede desactivar su propio usuario")
        
        # Verificar que el usuario existe
        cursor.execute("SELECT id FROM usuarios WHERE id = %s", (usuario_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Desactivar usuario
        cursor.execute("""
            UPDATE usuarios 
            SET activo = 0, fecha_ultima_modificacion = GETDATE()
            WHERE id = %s
        """, (usuario_id,))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Usuario desactivado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/{usuario_id}/activar")
async def activar_usuario(
    usuario_id: str,
    current_user: str = Depends(get_current_user),
    conn = Depends(get_db)
):
    try:
        cursor = conn.cursor(as_dict=True)

        
        # Verificar permisos
        cursor.execute("SELECT tipo_usuario FROM usuarios WHERE id = %s", (current_user,))
        user_tipo = cursor.fetchone()["tipo_usuario"]
        
        if user_tipo not in [TipoUsuario.ADMINISTRADOR, TipoUsuario.ADMINISTRADOR_TI]:
            raise HTTPException(status_code=403, detail="No tiene permisos para activar usuarios")
        
        # Verificar que el usuario existe
        cursor.execute("SELECT id FROM usuarios WHERE id = %s", (usuario_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        
        # Activar usuario
        cursor.execute("""
            UPDATE usuarios 
            SET activo = 1, fecha_ultima_modificacion = GETDATE()
            WHERE id = %s
        """, (usuario_id,))
        
        conn.commit()
        cursor.close()
        
        return {"message": "Usuario activado correctamente"}
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")
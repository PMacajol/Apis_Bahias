from fastapi import APIRouter, HTTPException, Depends
from app.database import get_db, ensure_dict, fetchone_dict
from app.database import get_db, ensure_dict
from app.models.pydantic_models import (
    UsuarioCreate, UsuarioLogin, UsuarioResponse, LoginResponse
)
from app.core.security import (
    get_password_hash, verify_password, create_access_token, verify_token
)
import pymssql
from datetime import timedelta
import uuid

router = APIRouter(prefix="/api/auth", tags=["autenticación"])

@router.post("/registro", response_model=UsuarioResponse)
async def registrar_usuario(usuario: UsuarioCreate, conn = Depends(get_db)):
    try:
        cursor = conn.cursor(as_dict=True)
        
        # Verificar si el usuario ya existe
        cursor.execute(
            "SELECT id FROM usuarios WHERE email = %s", 
            (usuario.email,)
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=400, 
                detail="El email ya está registrado"
            )
        
        # Crear usuario
        user_id = str(uuid.uuid4())
        hashed_password = get_password_hash(usuario.password)
        
        cursor.execute("""
            INSERT INTO usuarios (
                id, email, nombre, hash_contrasena, tipo_usuario, 
                activo, fecha_registro, fecha_ultima_modificacion
            ) VALUES (%s, %s, %s, %s, %s, 1, GETDATE(), GETDATE())
        """, (user_id, usuario.email, usuario.nombre, hashed_password, usuario.tipo_usuario))
        
        conn.commit()
        
        # Obtener usuario creado
        cursor.execute("""
            SELECT id, email, nombre, tipo_usuario, activo, 
                   fecha_registro, fecha_ultima_modificacion
            FROM usuarios WHERE id = %s
        """, (user_id,))
        
        user_data = cursor.fetchone()
        cursor.close()
        
        # CONVERTIR A DICCIONARIO
        user_dict = ensure_dict(user_data)
        print(f"Usuario creado correctamente: {user_dict}")
        
        return UsuarioResponse(**user_dict)
        
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.post("/login", response_model=LoginResponse)
async def login_usuario(usuario: UsuarioLogin, conn = Depends(get_db)):
    try:
        cursor = conn.cursor()
        
        # Buscar usuario
        cursor.execute("""
            SELECT id, email, nombre, hash_contrasena, tipo_usuario, 
                   activo, fecha_registro, fecha_ultima_modificacion
            FROM usuarios 
            WHERE email = %s AND activo = 1
        """, (usuario.email,))
        
        # 🔥 USAR LA NUEVA FUNCIÓN QUE SIEMPRE RETORNA DICT
        user_dict = fetchone_dict(cursor)
        cursor.close()
        
        print(f"🔍 user_dict: {user_dict}")
        
        if not user_dict or not user_dict.get("hash_contrasena"):
            raise HTTPException(
                status_code=401, 
                detail="Credenciales incorrectas"
            )
        
        if not verify_password(usuario.password, user_dict["hash_contrasena"]):
            raise HTTPException(
                status_code=401, 
                detail="Credenciales incorrectas"
            )
        
        # Crear token
        access_token = create_access_token(
            data={"sub": user_dict["id"], "tipo": user_dict["tipo_usuario"]}
        )
        
        user_response = UsuarioResponse(**user_dict)
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            usuario=user_response
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

@router.get("/me", response_model=UsuarioResponse)
async def obtener_usuario_actual(payload: dict = Depends(verify_token), conn = Depends(get_db)):
    try:
        user_id = payload.get("sub")
        cursor = conn.cursor(as_dict=True)  # 👈 esta línea cambia
        cursor.execute("""
            SELECT id, email, nombre, tipo_usuario, activo, 
                   fecha_registro, fecha_ultima_modificacion
            FROM usuarios 
            WHERE id = %s AND activo = 1
        """, (user_id,))
        user_dict = cursor.fetchone()
        cursor.close()

        if not user_dict:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        return UsuarioResponse(**user_dict)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error interno del servidor: {str(e)}")

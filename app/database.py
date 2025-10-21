import pymssql
from fastapi import HTTPException
from app.core.config import settings

class Database:
    def __init__(self):
        self.server = settings.DB_SERVER
        self.user = settings.DB_USER
        self.password = settings.DB_PASSWORD
        self.database = settings.DB_NAME
        self.port = settings.DB_PORT

    def get_connection(self):
        try:
            conn = pymssql.connect(
                server=self.server,
                user=self.user,
                password=self.password,
                database=self.database,
                port=self.port,
                login_timeout=10,
                charset='UTF-8'
            )
            return conn
        except Exception as e:
            print(f"❌ Error conectando a la base de datos: {e}")
            raise HTTPException(
                status_code=500, 
                detail=f"Error de conexión a la base de datos: {str(e)}"
            )

    def get_cursor(self, conn):
        return conn.cursor(as_dict=True)

def ensure_dict(data):
    """Conversión robusta a diccionario"""
    if data is None:
        return {}
    
    # Si ya es dict
    if isinstance(data, dict):
        return data
    
    # Si es tupla - CONVERSIÓN MANUAL
    if isinstance(data, tuple):
        print(f"🔄 Convirtiendo tupla: {data}")
        fields = ['id', 'email', 'nombre', 'hash_contrasena', 'tipo_usuario',
                 'activo', 'fecha_registro', 'fecha_ultima_modificacion']
        return {fields[i]: data[i] for i in range(len(data)) if i < len(fields)}
    
    # Si es objeto pymssql
    try:
        return dict(data)
    except:
        return {}

# Función para obtener datos ya convertidos
def fetchone_dict(cursor):
    """Obtener un resultado ya convertido a diccionario"""
    data = cursor.fetchone()
    return ensure_dict(data)

def fetchall_dict(cursor):
    """Obtener todos los resultados convertidos a diccionario"""
    data = cursor.fetchall()
    return [ensure_dict(row) for row in data] if data else []

# Instancia global de la base de datos
db = Database()

# Dependency para inyectar en los endpoints
def get_db():
    conn = db.get_connection()
    try:
        yield conn
    finally:
        conn.close()
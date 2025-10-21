import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database
    DB_SERVER: str = os.getenv("DB_SERVER", "test_QA.mssql.somee.com")
    DB_USER: str = os.getenv("DB_USER", "cmario_SQLLogin_1")
    DB_PASSWORD: str = os.getenv("DB_PASSWORD", "beilkyl7u5")
    DB_NAME: str = os.getenv("DB_NAME", "test_QA")
    DB_PORT: int = int(os.getenv("DB_PORT", "1433"))
    
    # JWT
    SECRET_KEY: str = os.getenv("SECRET_KEY", "clave_secreta_por_defecto_cambiar_en_produccion")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas
    
    # CORS
    ALLOWED_ORIGINS: list = ["*"]
    
    # App
    APP_NAME: str = "Sistema de Gestión de Bahías"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"

# Instancia global de configuración
settings = Settings()
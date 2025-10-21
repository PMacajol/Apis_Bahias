from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import auth, usuarios, bahias, reservas, mantenimientos, incidencias, reportes
from app.core.config import settings

app = FastAPI(
    title=settings.APP_NAME,
    description="API para el sistema de gestión de bahías de carga",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Incluir rutas
app.include_router(auth.router)
app.include_router(usuarios.router, prefix="/api")
app.include_router(bahias.router, prefix="/api")
app.include_router(reservas.router, prefix="/api")
app.include_router(mantenimientos.router, prefix="/api")
app.include_router(incidencias.router, prefix="/api")
app.include_router(reportes.router, prefix="/api")

@app.get("/")
async def root():
    return {
        "message": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs": "/docs"
    }

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "API funcionando correctamente"}

@app.get("/config")
async def get_config():
    """Endpoint para verificar la configuración (solo en desarrollo)"""
    if settings.DEBUG:
        return {
            "database_server": settings.DB_SERVER,
            "database_name": settings.DB_NAME,
            "debug_mode": settings.DEBUG,
            "token_expire_minutes": settings.ACCESS_TOKEN_EXPIRE_MINUTES
        }
    else:
        return {"message": "Configuración no disponible en producción"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app", 
        host="0.0.0.0", 
        port=8000, 
        reload=settings.DEBUG
    )
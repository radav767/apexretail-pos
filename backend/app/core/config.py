from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_name: str = "ApexRetail POS"
    app_env: str = "production"
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 1440

    class Config:
        env_file = ".env"

def get_settings():
    return Settings()

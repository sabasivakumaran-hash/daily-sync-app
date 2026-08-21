import os
from pathlib import Path

# Absolute path to the directory containing config.py
BASE_DIR = Path(__file__).resolve().parent

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'temple_sync_secret_key_change_in_production')
    
    # Guarantees SQLite always finds daily_sync.db regardless of terminal working directory
    DATABASE = str(BASE_DIR / 'daily_sync.db')
    
    SQLITE_FOREIGN_KEYS = True
    SESSION_PERMANENT = False

class DevelopmentConfig(Config):
    DEBUG = True

class ProductionConfig(Config):
    DEBUG = False
    SECRET_KEY = os.environ.get('SECRET_KEY', 'production_temple_sync_secure_key_2026')

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}
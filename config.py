# -*- coding: utf-8 -*-
import os

# Get the absolute path of the directory where this file is located
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Security key (keep this secret in production)
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'your-secret-key-here'
    
    # Database URI: This creates 'site.db' in the main project directory
    # Using os.path.join guarantees it works on Windows, Mac, and Linux
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(BASE_DIR, 'site.db')
    
    # Disable modification tracking to save memory
    SQLALCHEMY_TRACK_MODIFICATIONS = False
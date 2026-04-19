"""
Tenant Database Manager
Manages dynamic database connections for multi-tenant architecture.
Each organization/user gets their own PostgreSQL database.
"""
import os
import logging
from typing import Dict, Optional
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

logger = logging.getLogger(__name__)


class TenantDatabaseManager:
    """
    Manages tenant-specific database connections.
    Maintains a pool of engines for each tenant database.
    """
    
    def __init__(self):
        # Master database connection (stores tenant registry)
        self.master_db_url = os.getenv("MASTER_DATABASE_URL") or os.getenv("DATABASE_URL")
        if self.master_db_url and self.master_db_url.startswith("postgres://"):
            self.master_db_url = self.master_db_url.replace("postgres://", "postgresql://", 1)
        
        # Database server connection string (for creating new databases)
        self.db_server_url = os.getenv("DATABASE_SERVER_URL")
        if not self.db_server_url:
            # Extract server URL from master DB URL
            if self.master_db_url:
                # postgresql://user:pass@host:port/dbname -> postgresql://user:pass@host:port/postgres
                parts = self.master_db_url.rsplit('/', 1)
                self.db_server_url = parts[0] + "/postgres"
        
        # Master database engine
        self.master_engine = create_engine(
            self.master_db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10
        )
        
        # Cache of tenant engines {tenant_id: engine}
        self._tenant_engines: Dict[str, object] = {}
        
        # Cache of tenant session makers
        self._tenant_session_makers: Dict[str, sessionmaker] = {}
        
        logger.info("TenantDatabaseManager initialized")
    
    def get_master_session(self) -> Session:
        """Get a session for the master database."""
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.master_engine)
        return SessionLocal()
    
    @contextmanager
    def master_db_session(self):
        """Context manager for master database sessions."""
        session = self.get_master_session()
        try:
            yield session
            session.commit()
        except Exception as e:
            logger.error(f"Error in master_db_session: {e}")
            session.rollback()
            raise
        finally:
            session.close()
    
    def create_tenant_database(self, tenant_id: str, db_name: str) -> str:
        """
        Create a new PostgreSQL database for a tenant.
        
        Args:
            tenant_id: Unique tenant identifier
            db_name: Database name (must be PostgreSQL-safe)
        
        Returns:
            Database URL for the new tenant database
        """
        try:
            # Connect to PostgreSQL server (postgres database)
            conn = psycopg2.connect(self.db_server_url)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # Check if database already exists
            cursor.execute(
                "SELECT 1 FROM pg_database WHERE datname = %s",
                (db_name,)
            )
            
            if cursor.fetchone():
                logger.warning(f"Database {db_name} already exists")
            else:
                # Create database
                cursor.execute(f'CREATE DATABASE "{db_name}"')
                logger.info(f"Created database: {db_name}")
            
            cursor.close()
            conn.close()
            
            # Build tenant database URL
            parts = self.db_server_url.rsplit('/', 1)
            tenant_db_url = f"{parts[0]}/{db_name}"
            
            return tenant_db_url
            
        except Exception as e:
            logger.error(f"Failed to create tenant database {db_name}: {e}")
            raise
    
    def get_tenant_engine(self, tenant_id: str, db_url: str):
        """
        Get or create an engine for a tenant database.
        
        Args:
            tenant_id: Unique tenant identifier  
            db_url: Database URL for the tenant
        
        Returns:
            SQLAlchemy engine for the tenant database
        """
        if tenant_id in self._tenant_engines:
            return self._tenant_engines[tenant_id]
        
        # Fix postgres:// to postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        
        # Create new engine for this tenant
        engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=3,  # Smaller pool per tenant
            max_overflow=5,
            pool_recycle=900,
            poolclass=QueuePool
        )
        
        self._tenant_engines[tenant_id] = engine
        logger.info(f"Created engine for tenant: {tenant_id}")
        
        return engine
    
    def get_tenant_session(self, tenant_id: str, db_url: str) -> Session:
        """
        Get a database session for a specific tenant.
        
        Args:
            tenant_id: Unique tenant identifier
            db_url: Database URL for the tenant
        
        Returns:
            SQLAlchemy session for the tenant database
        """
        if tenant_id not in self._tenant_session_makers:
            engine = self.get_tenant_engine(tenant_id, db_url)
            self._tenant_session_makers[tenant_id] = sessionmaker(
                autocommit=False,
                autoflush=False,
                bind=engine
            )
        
        return self._tenant_session_makers[tenant_id]()
    
    @contextmanager
    def tenant_db_session(self, tenant_id: str, db_url: str):
        """Context manager for tenant database sessions."""
        session = self.get_tenant_session(tenant_id, db_url)
        try:
            yield session
            session.commit()
        except Exception as e:
            logger.error(f"Error in tenant_db_session for tenant {tenant_id}: {e}")
            session.rollback()
            raise
        finally:
            session.close()
    
    def run_tenant_migrations(self, tenant_id: str, db_url: str):
        """
        Run Alembic migrations on a tenant database.
        
        Args:
            tenant_id: Unique tenant identifier
            db_url: Database URL for the tenant
        """
        try:
            engine = self.get_tenant_engine(tenant_id, db_url)
            
            # Import Base from your models
            from database import Base
            
            # Create all tables
            Base.metadata.create_all(bind=engine)
            
            logger.info(f"Ran migrations for tenant: {tenant_id}")
            
        except Exception as e:
            logger.error(f"Failed to run migrations for tenant {tenant_id}: {e}")
            raise
    
    def delete_tenant_database(self, tenant_id: str, db_name: str):
        """
        Delete a tenant database (use with caution!).
        
        Args:
            tenant_id: Unique tenant identifier
            db_name: Database name to delete
        """
        try:
            # Remove from cache
            if tenant_id in self._tenant_engines:
                self._tenant_engines[tenant_id].dispose()
                del self._tenant_engines[tenant_id]
            
            if tenant_id in self._tenant_session_makers:
                del self._tenant_session_makers[tenant_id]
            
            # Connect and drop database
            conn = psycopg2.connect(self.db_server_url)
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cursor = conn.cursor()
            
            # Validate db_name matches expected tenant DB pattern
            import re as _re
            if not _re.match(r'^[a-zA-Z0-9_-]+$', db_name):
                raise ValueError(f"Invalid database name: {db_name}")

            from psycopg2 import sql as psql

            # Terminate existing connections
            cursor.execute(
                psql.SQL("""
                    SELECT pg_terminate_backend(pg_stat_activity.pid)
                    FROM pg_stat_activity
                    WHERE pg_stat_activity.datname = {name}
                    AND pid <> pg_backend_pid()
                """).format(name=psql.Literal(db_name))
            )

            # Drop database
            cursor.execute(
                psql.SQL("DROP DATABASE IF EXISTS {}").format(psql.Identifier(db_name))
            )
            
            cursor.close()
            conn.close()
            
            logger.info(f"Deleted tenant database: {db_name}")
            
        except Exception as e:
            logger.error(f"Failed to delete tenant database {db_name}: {e}")
            raise
    
    def close_all(self):
        """Close all database connections."""
        for tenant_id, engine in self._tenant_engines.items():
            engine.dispose()
            logger.info(f"Closed engine for tenant: {tenant_id}")
        
        self._tenant_engines.clear()
        self._tenant_session_makers.clear()
        self.master_engine.dispose()
        logger.info("Closed all database connections")


# Global instance
tenant_db_manager = TenantDatabaseManager()

"""Standalone role-4 API. No app accounts, document search or LLM required."""
from contextlib import asynccontextmanager
import logging
import os
import secrets

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine

from . import role4, role4_agent, role4_calculations

logger = logging.getLogger('role4.audit')
bearer = HTTPBearer(auto_error=False)


class DisabledGateway:
    enabled = False


def create_app(db_url=None, api_token=None):
    load_dotenv('.env.local', override=False)
    url = db_url or os.getenv('DATABASE_URL')
    token = api_token if api_token is not None else os.getenv('ROLE4_API_TOKEN', '')
    if not url or len(token) < 32:
        raise RuntimeError('Set DATABASE_URL and ROLE4_API_TOKEN (at least 32 characters).')
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    options = {'connect_args': {'connect_timeout': 5}} if url.startswith('postgresql') else {}
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True, **options)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title='Sea the Answer — Role 4', version='1.0.0', lifespan=lifespan)
    app.state.engine = engine

    def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None:
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
        if not secrets.compare_digest(credentials.credentials.encode(), token.encode()):
            raise HTTPException(403, 'Invalid API token')

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'scope': 'role4', 'database_checked': False}

    @app.post('/api/role4/query', dependencies=[Depends(authorize)])
    def query(body: role4.Role4Query):
        result = role4.query(engine, body)
        logger.info('role4.query dataset=%s total=%s', body.dataset, result.get('total'))
        return result

    @app.get('/api/role4/factors', dependencies=[Depends(authorize)])
    def factors():
        return role4_calculations.catalog()

    @app.post('/api/role4/calculate', dependencies=[Depends(authorize)])
    def calculate(body: role4_calculations.CalculationRequest):
        result = role4_calculations.calculate(engine, body)
        logger.info('role4.calculate dataset=%s status=%s', body.scope.dataset, result.get('status'))
        return result

    @app.post('/api/role4/ask', dependencies=[Depends(authorize)])
    def ask(body: role4_agent.Ask):
        return role4_agent.run(engine, DisabledGateway(), body)

    return app

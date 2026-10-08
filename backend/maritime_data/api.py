"""Standalone Maritime data API. No app accounts, document search or LLM required."""
from contextlib import asynccontextmanager
import logging
import os
import secrets

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import create_engine

from . import query as maritime_data, agent as maritime_data_agent, calculations as maritime_data_calculations

logger = logging.getLogger('maritime_data.audit')
bearer = HTTPBearer(auto_error=False)


class DisabledGateway:
    enabled = False


def create_app(db_url=None, api_token=None):
    load_dotenv('.env.local', override=False)
    url = db_url or os.getenv('DATABASE_URL')
    token = api_token if api_token is not None else os.getenv('MARITIME_DATA_API_TOKEN', '')
    if not url or len(token) < 32:
        raise RuntimeError('Set DATABASE_URL and MARITIME_DATA_API_TOKEN (at least 32 characters).')
    if url.startswith('postgresql://'):
        url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
    options = {'connect_args': {'connect_timeout': 5}} if url.startswith('postgresql') else {}
    engine = create_engine(url, hide_parameters=True, pool_pre_ping=True, **options)

    @asynccontextmanager
    async def lifespan(app):
        yield
        engine.dispose()

    app = FastAPI(title='Sea the Answer — Maritime data', version='1.0.0', lifespan=lifespan)
    app.state.engine = engine

    def authorize(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
        if credentials is None:
            raise HTTPException(401, 'Bearer token required', headers={'WWW-Authenticate': 'Bearer'})
        if not secrets.compare_digest(credentials.credentials.encode(), token.encode()):
            raise HTTPException(403, 'Invalid API token')

    @app.get('/api/health')
    def health():
        return {'status': 'ok', 'scope': 'maritime_data', 'database_checked': False}

    @app.post('/api/maritime-data/query', dependencies=[Depends(authorize)])
    def query(body: maritime_data.MaritimeDataQuery):
        result = maritime_data.query(engine, body)
        logger.info('maritime_data.query dataset=%s total=%s', body.dataset, result.get('total'))
        return result

    @app.get('/api/maritime-data/factors', dependencies=[Depends(authorize)])
    def factors():
        return maritime_data_calculations.catalog()

    @app.post('/api/maritime-data/calculate', dependencies=[Depends(authorize)])
    def calculate(body: maritime_data_calculations.CalculationRequest):
        result = maritime_data_calculations.calculate(engine, body)
        logger.info('maritime_data.calculate dataset=%s status=%s', body.scope.dataset, result.get('status'))
        return result

    @app.post('/api/maritime-data/ask', dependencies=[Depends(authorize)])
    def ask(body: maritime_data_agent.Ask):
        return maritime_data_agent.run(engine, DisabledGateway(), body)

    return app

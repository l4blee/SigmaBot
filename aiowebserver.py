import logging

from aiohttp.web import RouteTableDef, Application, Request
from dataclasses import dataclass

logger = logging.getLogger('aiohttp.server')

@dataclass
class TaskPayload:
    id: int
    amount: int

@dataclass
class JoinPayload:
    id: int


web_app = Application()
routes = RouteTableDef()


@routes.get('/')
async def index(request: Request):
    # request.app.client -> telegram client
    logger.info('index pinged')


@routes.post('/report_task')
async def task(request: Request):
    payload = TaskPayload(**(await request.json()))
    logger.info(payload)


@routes.post('/report_join')
async def join(request: Request):
    payload = JoinPayload(**(await request.json()))
    logger.info(payload)


web_app.add_routes(routes)
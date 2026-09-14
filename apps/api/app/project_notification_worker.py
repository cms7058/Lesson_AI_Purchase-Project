"""Periodic notification discovery, never automatic external email delivery."""
import logging
import time

from sqlalchemy.exc import SQLAlchemyError

from app.core.database import SessionLocal
from app.services.project_notifications import scan

logger = logging.getLogger(__name__)

if __name__ == '__main__':
    while True:
        try:
            with SessionLocal.begin() as db:
                scan(db)
        except SQLAlchemyError:
            logger.warning('Project notification scan failed; transaction rolled back, retry in 60s')
        time.sleep(60)

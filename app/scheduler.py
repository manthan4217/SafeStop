import os
import logging
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()

def init_scheduler(app):
    """
    Initializes and starts the background task scheduler for periodic compliance checks,
    daily safe-arrival digests, and automated no-show alerts.
    """
    if app.config.get('TESTING') or scheduler.running:
        return

    from app.compliance import check_expiring_driver_credentials
    from app.notifications.service import generate_daily_arrival_digest
    from app.driver.routes import run_no_show_check

    def _run_compliance_check():
        with app.app_context():
            logger.info("Running scheduled driver compliance check...")
            check_expiring_driver_credentials()

    def _run_daily_digest():
        with app.app_context():
            logger.info("Running scheduled daily safe-arrival digest...")
            generate_daily_arrival_digest()

    def _run_no_show_check():
        with app.app_context():
            logger.info("Running scheduled no-show check across active trips...")
            run_no_show_check()

    scheduler.add_job(_run_compliance_check, 'cron', hour=6, minute=0, id='compliance_check', replace_existing=True)
    scheduler.add_job(_run_daily_digest, 'cron', hour=18, minute=0, id='daily_digest', replace_existing=True)
    scheduler.add_job(_run_no_show_check, 'interval', minutes=15, id='no_show_check', replace_existing=True)
    scheduler.start()

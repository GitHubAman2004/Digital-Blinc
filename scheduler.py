from apscheduler.schedulers.background import BackgroundScheduler
from collectors.oneview import OneViewCollector
from collectors.apic import ApicCollector
from config import Config

class AIOpsScheduler:
    def __init__(self):
        self.scheduler = BackgroundScheduler()
        self.oneview_collector = OneViewCollector()
        self.apic_collector = ApicCollector()

    def poll_all(self):
        """Triggers collection loops for all OEM modules."""
        print("Scheduler: Polling background collectors...")
        self.oneview_collector.collect()
        self.apic_collector.collect()

    def start(self):
        """Starts the background scheduler thread."""
        self.scheduler.add_job(
            self.poll_all,
            'interval',
            seconds=Config.COLLECTOR_INTERVAL,
            id='poll_job',
            replace_existing=True
        )
        self.scheduler.start()
        print(f"Scheduler: Background collector jobs active (Interval: {Config.COLLECTOR_INTERVAL}s).")

    def shutdown(self):
        """Gracefully stops the scheduler thread."""
        self.scheduler.shutdown()
        print("Scheduler: Background thread terminated.")

# Export scheduler singleton helper
aiops_scheduler = AIOpsScheduler()

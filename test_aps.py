from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger
import time

s = BackgroundScheduler()
s.start()
job = s.add_job(func=lambda: print("test"), trigger=IntervalTrigger(minutes=15))
print("Job next_run_time:", job.next_run_time)
s.shutdown()

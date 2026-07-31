from storage.db import Database
from storage.config_store import ConfigStore
from pathlib import Path

DB = str(Path(__file__).parent.parent.parent / 'facewatch.db')
db = Database(DB)
config = ConfigStore(db)
print('gaze_alert_sec:', config.get('gaze_alert_sec'))
print('proximity_alert_cm:', config.get('proximity_alert_cm'))
print('notifications_enabled:', config.get('notifications_enabled'))
print('report_times:', config.get('report_times'))
print('eye_strain_alert_sec:', config.get('eye_strain_alert_sec'))
print('work_reminder_break_sec:', config.get('work_reminder_break_sec'))
print('ALL OK')

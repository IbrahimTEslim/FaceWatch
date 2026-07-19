from .connection import Connection
from .faces import FaceQueries
from .demographics import DemographicsQueries
from .stats import StatsQueries
from .config import ConfigQueries
from .calibration import CalibrationQueries
from .audit import AuditQueries


class Database(
    FaceQueries,
    DemographicsQueries,
    StatsQueries,
    ConfigQueries,
    CalibrationQueries,
    AuditQueries,
):
    def __init__(self, db_path: str):
        cx = Connection(db_path)
        self._cx = cx
        FaceQueries.__init__(self, cx)
        DemographicsQueries.__init__(self, cx)
        StatsQueries.__init__(self, cx)
        ConfigQueries.__init__(self, cx)
        CalibrationQueries.__init__(self, cx)
        AuditQueries.__init__(self, cx)
        self.array_to_blob = cx.array_to_blob
        self.blob_to_array = cx.blob_to_array

    def close(self) -> None:
        self._cx.conn.close()

import json
import sqlite3
from datetime import date as date_type
from flask import Flask, render_template, jsonify, request

from storage.db import Database
from storage.config_store import ConfigStore
from .builder import build_report_data, get_known_faces, get_available_dates
from .builder.focus import focus_history

_app: Flask | None = None


def _get_conn(db_path: str):
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def create_app(db_path: str) -> Flask:
    global _app
    template_dir = str(__import__("pathlib").Path(__file__).parent / "templates")
    static_dir   = str(__import__("pathlib").Path(__file__).parent / "static")
    _app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    conn   = _get_conn(db_path)
    db     = Database(db_path)
    config = ConfigStore(db)

    @_app.route("/")
    def index():
        faces = get_known_faces(conn)
        if not faces:
            return render_template("empty.html")
        face_id = request.args.get("face_id", faces[0]["id"], type=int)
        today   = request.args.get("date", str(date_type.today()))
        dates   = get_available_dates(conn, face_id)
        data    = build_report_data(conn, face_id, today, config)
        return render_template("dashboard.html",
                               data=data, faces=faces,
                               selected_face=face_id,
                               selected_date=today,
                               available_dates=dates)

    @_app.route("/history")
    def history():
        faces   = get_known_faces(conn)
        if not faces:
            return render_template("empty.html")
        face_id = request.args.get("face_id", faces[0]["id"], type=int)
        hist    = focus_history(conn, face_id, days=30)
        return render_template("history.html",
                               hist=hist, faces=faces,
                               selected_face=face_id)

    @_app.route("/face/<int:face_id>")
    def face_detail(face_id: int):
        faces = get_known_faces(conn)
        today = str(date_type.today())
        dates = get_available_dates(conn, face_id)
        data  = build_report_data(conn, face_id, today, config)
        face_row = conn.execute(
            "SELECT f.*, d.age_estimate, d.gender, d.race, d.face_width_cm "
            "FROM faces f LEFT JOIN demographics d ON d.face_id=f.id WHERE f.id=?",
            (face_id,)
        ).fetchone()
        return render_template("face.html",
                               data=data, faces=faces,
                               face=dict(face_row) if face_row else {},
                               selected_face=face_id,
                               selected_date=today,
                               available_dates=dates)

    @_app.route("/api/data")
    def api_data():
        faces   = get_known_faces(conn)
        face_id = request.args.get("face_id", faces[0]["id"] if faces else 1, type=int)
        day     = request.args.get("date", str(date_type.today()))
        data    = build_report_data(conn, face_id, day, config)
        return jsonify(data)

    return _app

import traceback
import sys
import sqlite3

conn = sqlite3.connect('facewatch.db')
conn.row_factory = sqlite3.Row

faces = conn.execute("SELECT id, display_name FROM faces").fetchall()
print('Faces in DB:', [(f['id'], f['display_name']) for f in faces])

stats = conn.execute("SELECT COUNT(*) as c, MIN(date(timestamp)) as mn, MAX(date(timestamp)) as mx FROM stats").fetchone()
print('Stats rows:', stats['c'], 'from', stats['mn'], 'to', stats['mx'])

try:
    from reporting.server import create_app
    app = create_app('facewatch.db')
    app.config['TESTING'] = True
    app.config['PROPAGATE_EXCEPTIONS'] = True

    with app.test_client() as client:
        for face in faces:
            url = f'/?face_id={face["id"]}'
            try:
                resp = client.get(url)
                sys.stdout.buffer.write(f'--- {url} STATUS: {resp.status_code}\n'.encode())
                if resp.status_code != 200:
                    sys.stdout.buffer.write(resp.data[:5000])
            except Exception:
                sys.stdout.buffer.write(f'--- {url} EXCEPTION:\n'.encode())
                traceback.print_exc()
except Exception:
    traceback.print_exc()

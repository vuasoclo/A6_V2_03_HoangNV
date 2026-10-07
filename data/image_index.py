from pathlib import Path
import hashlib, sqlite3
from contextlib import closing
import numpy as np
from application.intelligence.common import ROOT, read_json, digest

class ImageIndex:
    def __init__(self,path=None):self.path=Path(path or ROOT/'data/esci/image_index.sqlite3')
    def sync(self,encoder,rows):
        from application.intelligence.image_search import open_image
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with closing(sqlite3.connect(self.path)) as db:
            db.executescript('CREATE TABLE IF NOT EXISTS image_sets (name TEXT PRIMARY KEY,fingerprint TEXT,dimension INTEGER,images_hash TEXT); CREATE TABLE IF NOT EXISTS image_vectors (name TEXT,product_id TEXT,sha256 TEXT,vector BLOB,PRIMARY KEY(name,product_id));')
            old=db.execute('SELECT fingerprint FROM image_sets WHERE name=?',(encoder.alias,)).fetchone()
            cached={pid:(sha,vector) for pid,sha,vector in db.execute('SELECT product_id,sha256,vector FROM image_vectors WHERE name=?',(encoder.alias,))} if old and old[0]==encoder.fingerprint else {}
            prepared=[];pending=[];encoded=0
            for row in rows:
                content=(ROOT/row['path']).read_bytes()
                if hashlib.sha256(content).hexdigest()!=row['sha256']:raise ValueError('Catalog photo changed: '+row['id'])
                if row['id'] in cached and cached[row['id']][0]==row['sha256']:
                    prepared.append((encoder.alias,row['id'],row['sha256'],cached[row['id']][1]));continue
                pending.append((row,open_image(content)))
                if len(pending)>=encoder.batch_size:
                    vectors=encoder.encode([image for _,image in pending])
                    prepared.extend((encoder.alias,r['id'],r['sha256'],v.astype('<f4').tobytes()) for (r,_),v in zip(pending,vectors))
                    encoded+=len(pending);pending=[]
                    if encoded%80==0:print(encoder.alias,'encoded',encoded,'/',len(rows),flush=True)
            if pending:
                vectors=encoder.encode([image for _,image in pending])
                prepared.extend((encoder.alias,r['id'],r['sha256'],v.astype('<f4').tobytes()) for (r,_),v in zip(pending,vectors));encoded+=len(pending)
            with db:
                db.execute('DELETE FROM image_vectors WHERE name=?',(encoder.alias,))
                db.executemany('INSERT INTO image_vectors VALUES(?,?,?,?)',prepared)
                db.execute('INSERT OR REPLACE INTO image_sets VALUES(?,?,?,?)',(encoder.alias,encoder.fingerprint,encoder.dimension,digest(rows)))
        return {'encoded':encoded,'reused':len(rows)-encoded,'total':len(rows)}
    def load(self,encoder,rows):
        if not self.path.is_file():raise FileNotFoundError('Chưa tạo image index.')
        with closing(sqlite3.connect(self.path)) as db:
            meta=db.execute('SELECT fingerprint,dimension,images_hash FROM image_sets WHERE name=?',(encoder.alias,)).fetchone()
            if meta!=(encoder.fingerprint,encoder.dimension,digest(rows)):raise ValueError('Image index không khớp model/catalog. Hãy build lại trước khi chạy web.')
            saved=db.execute('SELECT product_id,vector FROM image_vectors WHERE name=? ORDER BY product_id',(encoder.alias,)).fetchall()
        ids=[pid for pid,_ in saved]
        if ids!=sorted(r['id'] for r in rows):raise ValueError('Image index thiếu/trùng sản phẩm.')
        matrix=np.stack([np.frombuffer(blob,dtype='<f4') for _,blob in saved])
        if matrix.shape!=(len(rows),encoder.dimension) or not np.isfinite(matrix).all() or not np.allclose(np.linalg.norm(matrix,axis=1),1,atol=1e-4):raise ValueError('Vector ảnh không hợp lệ.')
        return ids,matrix


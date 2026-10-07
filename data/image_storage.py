from pathlib import Path
import hashlib, sqlite3
from contextlib import closing
import numpy as np
from application.intelligence.common import ROOT, read_json, digest

def catalog_images():
    source=read_json(ROOT/'data/esci/images.json')
    if source['catalog_hash']!=digest(read_json(ROOT/'data/esci/products.json')):
        raise ValueError('Image manifest belongs to a different catalog.')
    rows=[]
    for pid,record in sorted(source['images'].items()):
        if record.get('status') in {'cached','downloaded'} and record.get('local_path') and record.get('sha256'):
            rows.append({'id':pid,'path':record['local_path'],'sha256':record['sha256']})
    return rows


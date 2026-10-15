import os,random,time
from pathlib import Path

def collect(ctx):
    path=Path(os.path.expanduser(ctx.opts.get('dir','~/Imágenes/widget')))
    if path.is_file(): pool=[str(path)]
    elif path.is_dir(): pool=[str(p) for p in path.rglob('*') if p.is_file() and p.suffix.lower() in ('.jpg','.jpeg','.png','.webp','.gif') and "'" not in str(p)]
    else: pool=[]
    last=ctx.state.get('path')
    choices=[p for p in pool if p!=last] or pool
    chosen=random.choice(choices) if choices else ''
    ctx.state['path']=chosen
    return {'path':chosen}

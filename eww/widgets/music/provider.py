import subprocess

def collect(ctx):
    configured=ctx.opts.get('player','').strip()
    result=subprocess.run(['playerctl','-l'],capture_output=True,text=True,timeout=2)
    players=result.stdout.splitlines()
    if configured: players=[p for p in players if p==configured or p.split('.')[0]==configured]
    candidates=[]
    for p in players[:8]:
        res=subprocess.run(['playerctl','-p',p,'metadata','--format','{{status}}\x1f{{title}}\x1f{{artist}}'],capture_output=True,text=True,timeout=2)
        values=res.stdout.strip().split('\x1f')
        if res.returncode==0 and len(values)==3:
            status,title,artist=values
            candidates.append(dict(player=p,status=status,title=title,artist=artist))
    return next((x for x in candidates if x['status']=='Playing'),candidates[0] if candidates else {'player':'','status':'','title':'','artist':''})

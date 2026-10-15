import time
from randly_widgets.state import read_event

def collect(ctx):
    tick=int(time.time()/.7)
    e=read_event(ctx.widget['id'])
    return {'face':'( -.- )' if tick%6==5 else '( o.o )','tail':['~','/','~','|'][tick%4],
            'says':e.get('says','') if e.get('until',0)>time.time() else ''}

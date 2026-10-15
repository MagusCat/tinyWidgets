import time
from randly_widgets.chest import data as chest_data
from randly_widgets.launchers import entries
from randly_widgets.state import read_event

def collect(ctx):
    data=chest_data(entries(ctx.widget)); e=read_event(ctx.widget['id']); tick=int(time.time()/.6)
    data.update(open=e.get('open',False),hover=e.get('hover',-1),raccoon=str([0,0,1,1,0,0,1,1,2,2,3,3,2,2,3,3,2,0,0,1,1,0,4,4,4,0,0,1,1][tick%29]),rat=str([1,0,1,0,0,0,0,0,2,0,0,1,0][tick%13]))
    for name in ('raccoon','rat'):
        data[name+'_says']=e.get(name+'_says','') if e.get(name+'_until',0)>time.time() else ''
    return data

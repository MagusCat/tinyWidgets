import json,urllib.request,urllib.parse

def collect(ctx):
    city=ctx.opts.get('city','').strip()
    url='https://wttr.in/'+urllib.parse.quote(city)+'?format=j1'
    req=urllib.request.Request(url,headers={'User-Agent':'randly-widgets'})
    with urllib.request.urlopen(req,timeout=4) as resp: data=json.loads(resp.read(500000))
    curr=data.get('current_condition',[{}])[0]
    return {'temp':str(curr.get('temp_C','—'))+'°C','desc':curr.get('weatherDesc',[{}])[0].get('value','Sin datos'),'icon':'󰖙','city':data.get('nearest_area',[{}])[0].get('areaName',[{}])[0].get('value',city or 'Local'),'humidity':str(curr.get('humidity','—'))+'%','wind':str(curr.get('windspeedKmph','—'))+' km/h'}

"""Stable compositor samples; temporary allocations must never resize editor handles."""
import time

class GeometryTracker:
    def __init__(self):self.accepted={};self.candidates={};self.pending={}
    def expect(self,wid,rect,now=None):
        now=time.monotonic() if now is None else now
        self.pending[wid]=(list(rect),now+2)
        self.candidates.pop(wid,None)
    def resolve(self,wid,raw,fallback,now=None):
        now=time.monotonic() if now is None else now
        pending=self.pending.get(wid)
        valid=raw is not None and raw[2]>=40 and raw[3]>=40
        if pending:
            target,deadline=pending
            if valid and all(abs(a-b)<=2 for a,b in zip(raw,target)):
                self.accepted[wid]=list(raw);self.pending.pop(wid,None);return list(raw)
            if now<deadline:return list(target)
            self.pending.pop(wid,None)
        if valid:
            rect=list(raw);previous,count=self.candidates.get(wid,(None,0))
            count=count+1 if previous==rect else 1
            self.candidates[wid]=(rect,count)
            if count>=2:self.accepted[wid]=rect
        else:self.candidates.pop(wid,None)
        return list(self.accepted.get(wid,fallback))
    def prune(self,ids):
        ids=set(ids)
        for mapping in (self.accepted,self.candidates,self.pending):
            for wid in set(mapping)-ids:mapping.pop(wid,None)

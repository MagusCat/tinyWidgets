"""Small reusable paint resources and conservative damage bounds."""
import math

def union(rects):
    rects=[r for r in rects if r is not None]
    if not rects:return None
    x=min(r[0] for r in rects);y=min(r[1] for r in rects)
    right=max(r[0]+r[2] for r in rects);bottom=max(r[1]+r[3] for r in rects)
    return [x,y,right-x,bottom-y]

def intersects(rect,clip):
    x,y,w,h=rect;left,top,right,bottom=clip
    return x<right and x+w>left and y<bottom and y+h>top

def widget_bounds(rect,wa,chip_width=0):
    x,y,w,h=rect
    chip_width=max(chip_width,w)
    chip_x=max(wa['x']+2,min(x+2,wa['x']+wa['width']-chip_width-2))
    # Include chip, resize handles, shadows and the contextual buttons.
    return union(([x-24,y-64,w+48,h+128],[chip_x-12,y-64,chip_width+24,h+128]))

def pixel_bounds(rect):
    x,y,w,h=rect;left=math.floor(x);top=math.floor(y)
    return left,top,max(1,math.ceil(x+w)-left),max(1,math.ceil(y+h)-top)

class GridCache:
    def __init__(self):self.key=None;self.tile=None;self.builds=0
    def get(self,step,color,scale=1):
        import cairo
        step=max(1,int(step));scale=max(1,int(scale));key=(step,tuple(color),scale)
        if key!=self.key:
            tile=cairo.ImageSurface(cairo.FORMAT_ARGB32,step*scale,step*scale)
            tile.set_device_scale(scale,scale);cr=cairo.Context(tile)
            cr.set_source_rgba(*color,.10);cr.set_line_width(1)
            cr.move_to(.5,0);cr.line_to(.5,step);cr.move_to(0,.5);cr.line_to(step,.5);cr.stroke()
            self.key=key;self.tile=tile;self.builds+=1
        return self.tile

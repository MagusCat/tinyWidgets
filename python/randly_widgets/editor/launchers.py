"""Inline app picker; bounded search results and instance-owned launcher editing."""
import json
from gi.repository import Gio
from .common import Gtk, Gdk, GLib, W
from randly_widgets.launchers import entries, parse


def launcher_control(editor, wid, key):
    widget=W.find(editor.widgets,wid)
    targets=entries(widget)
    editing=[None]
    limit=1 if widget['window']=='button' else 27 if widget['window']=='chest' else 100
    stack=Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE,transition_duration=120)
    summary=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6)
    selected=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=4)
    summary.pack_start(selected,False,False,0)
    error=Gtk.Label(xalign=0);error.set_line_wrap(True)
    summary.pack_start(error,False,False,0)
    buttons=Gtk.Box(spacing=4)
    add=Gtk.Button(label='Elegir aplicación')
    custom=Gtk.Button(label='Comando propio')
    buttons.pack_start(add,True,True,0);buttons.pack_start(custom,True,True,0)
    summary.pack_start(buttons,False,False,0)
    stack.add_named(summary,'selected')

    def save():
        editor.set_option(wid,key,json.dumps(targets,ensure_ascii=False))
        refresh()

    def remove(index):
        if widget['window']=='chest':targets[index]=None
        else:targets.pop(index)
        save()

    def move(index,delta):
        destination=index+delta
        if 0<=destination<len(targets):targets[index],targets[destination]=targets[destination],targets[index];save()

    def refresh():
        for child in selected.get_children():selected.remove(child)
        if not any(targets):selected.pack_start(Gtk.Label(label='Sin accesos. Agrega los que quieras.',xalign=0),False,False,0)
        for index,target in enumerate(targets):
            if target is None:continue
            row=Gtk.Box(spacing=3)
            label=Gtk.Label(label=f"{index+1} · {target['name']}",xalign=0,hexpand=True)
            label.set_max_width_chars(22);label.set_ellipsize(3);label.set_tooltip_text(target['desktop_id'] or target['cmd'])
            row.pack_start(label,True,True,0)
            for text,tip,callback in [('document-edit-symbolic','Editar',lambda _,i=index:edit(i)),('go-up-symbolic','Subir',lambda _,i=index:move(i,-1)),('go-down-symbolic','Bajar',lambda _,i=index:move(i,1)),('edit-delete-symbolic','Quitar',lambda _,i=index:remove(i))]:
                button=Gtk.Button.new_from_icon_name(text,Gtk.IconSize.BUTTON);button.set_tooltip_text(tip);button.get_accessible().set_name(tip+' '+target['name']);button.connect('clicked',callback);row.pack_start(button,False,False,0)
            selected.pack_start(row,False,False,0)
        selected.show_all()
        add.set_sensitive(limit==1 or sum(t is not None for t in targets)<limit)
        custom.set_sensitive(add.get_sensitive())

    def choose(target):
        try:target=parse([target])[0]
        except ValueError as exc:form_error.set_text(str(exc));command.grab_focus();return
        if editing[0] is not None:
            targets[editing[0]]=target;editing[0]=None
        elif limit==1:
            targets[:]=[target]
            if W.find(editor.widgets,wid).get('opts',{}).get('title','Acceso')=='Acceso':editor.set_option(wid,'title',target['name'])
        elif None in targets:targets[targets.index(None)]=target
        elif len(targets)<limit:targets.append(target)
        else:error.set_text(f'Máximo {limit} accesos');return
        error.set_text('');save();stack.set_visible_child_name('selected');add.grab_focus()

    picker=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
    search=Gtk.SearchEntry(placeholder_text='Buscar aplicación instalada…')
    picker.pack_start(search,False,False,0)
    results=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
    scroll=Gtk.ScrolledWindow(min_content_height=160,max_content_height=240)
    scroll.set_policy(Gtk.PolicyType.NEVER,Gtk.PolicyType.AUTOMATIC);scroll.add(results)
    picker.pack_start(scroll,True,True,0)
    count=Gtk.Label(xalign=0);picker.pack_start(count,False,False,0)
    back=Gtk.Button(label='Volver');back.connect('clicked',lambda _:stack.set_visible_child_name('selected'));picker.pack_start(back,False,False,0)
    stack.add_named(picker,'picker')
    catalog=[];pending=[None]

    def render_results():
        pending[0]=None
        text=search.get_text().casefold().strip()
        matches=[a for a in catalog if text in (a.get_display_name()+' '+a.get_id()).casefold()]
        for child in results.get_children():results.remove(child)
        for app in matches[:60]:
            row=Gtk.ListBoxRow();row.target={'desktop_id':app.get_id(),'name':app.get_display_name(),'icon':'󰀻'}
            box=Gtk.Box(spacing=8)
            icon=app.get_icon()
            if icon:box.pack_start(Gtk.Image.new_from_gicon(icon,Gtk.IconSize.BUTTON),False,False,0)
            label=Gtk.Label(label=app.get_display_name(),xalign=0);label.set_max_width_chars(28);label.set_ellipsize(3)
            box.pack_start(label,True,True,0);row.add(box);results.add(row)
        count.set_text('Sin resultados' if not matches else f'{min(len(matches),60)} de {len(matches)} aplicaciones')
        results.show_all()
        return False

    def query(_):
        if pending[0]:GLib.source_remove(pending[0])
        pending[0]=GLib.timeout_add(120,render_results)

    def open_picker(_):
        if not catalog:
            catalog.extend(sorted((a for a in Gio.AppInfo.get_all() if a.get_id() and a.should_show()),key=lambda a:a.get_display_name().casefold()))
        render_results();stack.set_visible_child_name('picker');search.grab_focus()

    def cancel_pending(_):
        if pending[0]:GLib.source_remove(pending[0]);pending[0]=None

    add.connect('clicked',lambda button:(editing.__setitem__(0,None),open_picker(button)));search.connect('search-changed',query)
    search.connect('key-press-event',lambda _,event: (results.grab_focus() or True) if Gdk.keyval_name(event.keyval)=='Down' else False)
    search.connect('activate',lambda _:choose(results.get_row_at_index(0).target) if results.get_row_at_index(0) else None)
    results.connect('row-activated',lambda _,row:choose(row.target))
    stack.connect('destroy',cancel_pending)

    form=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=5)
    name=Gtk.Entry(placeholder_text='Nombre del acceso')
    command=Gtk.Entry(placeholder_text='Comando')
    glyph=Gtk.Entry(placeholder_text='Icono (opcional)')
    command_label=None
    for title,entry in (('Nombre',name),('Comando',command),('Icono',glyph)):
        label=Gtk.Label(label=title,xalign=0);form.pack_start(label,False,False,0)
        if entry is command:command_label=label
        entry.get_accessible().set_name(title)
        form.pack_start(entry,False,False,0)
    form_error=Gtk.Label(xalign=0);form_error.set_line_wrap(True);form.pack_start(form_error,False,False,0)
    def save_target(_):
        target={'name':name.get_text(),'icon':glyph.get_text()}
        old=targets[editing[0]] if editing[0] is not None else None
        if old and old.get('desktop_id'):target['desktop_id']=old['desktop_id']
        else:target['cmd']=command.get_text()
        choose(target)
    submit=Gtk.Button(label='Guardar acceso');submit.connect('clicked',save_target);form.pack_start(submit,False,False,0)
    replace=Gtk.Button(label='Elegir otra aplicación');replace.connect('clicked',open_picker);form.pack_start(replace,False,False,0)
    command.connect('activate',lambda _:submit.clicked())
    cancel=Gtk.Button(label='Volver');cancel.connect('clicked',lambda _:stack.set_visible_child_name('selected'));form.pack_start(cancel,False,False,0)
    stack.add_named(form,'command')
    def edit(index):
        editing[0]=index
        target=targets[index] if index is not None else {}
        name.set_text(target.get('name',''));command.set_text(target.get('desktop_id') or target.get('cmd',''));glyph.set_text(target.get('icon',''))
        form_error.set_text('')
        command_label.set_text('Aplicación' if target.get('desktop_id') else 'Comando')
        command.set_sensitive(not bool(target.get('desktop_id')))
        stack.set_visible_child_name('command');name.grab_focus()
    custom.connect('clicked',lambda _:edit(None))

    def escape(_,event):
        if Gdk.keyval_name(event.keyval)=='Escape' and stack.get_visible_child_name()!='selected':
            stack.set_visible_child_name('selected');add.grab_focus();return True
        return False
    stack.connect('key-press-event',escape)
    refresh();stack.show_all();stack.set_visible_child_name('selected')
    return stack

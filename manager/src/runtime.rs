use crate::{
    io::{self, Lock, Paths},
    motion, theme,
};
use anyhow::{bail, ensure, Context, Result};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use std::{
    collections::{BTreeMap, HashSet},
    fs,
    os::unix::fs::MetadataExt,
    process::{Command, Stdio},
    thread,
    time::Duration,
};
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Widget {
    pub id: String,
    pub window: String,
    pub show: bool,
    pub anchor: String,
    pub x: i64,
    pub y: i64,
    #[serde(default)]
    pub opts: Map<String, Value>,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}
fn ident(s: &str) -> bool {
    !s.is_empty()
        && s.bytes()
            .all(|b| b.is_ascii_alphanumeric() || b == b'-' || b == b'_')
        && s.as_bytes()[0].is_ascii_alphanumeric()
}
pub fn widgets(p: &Paths) -> Result<Vec<Widget>> {
    let value: Value = serde_json::from_slice(&fs::read(p.config.join("instances.json"))?)?;
    ensure!(value["version"] == 1, "Versión de instancias desconocida");
    let widgets: Vec<Widget> = serde_json::from_value(value["widgets"].clone())?;
    validate(&widgets)?;
    Ok(widgets)
}
pub fn validate(widgets: &[Widget]) -> Result<()> {
    let mut ids = HashSet::new();
    for w in widgets {
        ensure!(
            ident(&w.id) && ident(&w.window) && ids.insert(w.id.clone()),
            "ID inválido/repetido"
        );
        ensure!(
            [
                "top-left",
                "top-right",
                "bottom-left",
                "bottom-right",
                "center"
            ]
            .contains(&w.anchor.as_str()),
            "Anclaje inválido"
        )
    }
    Ok(())
}
pub fn global(w: &Widget) -> bool {
    let target = w
        .opts
        .get("workspace")
        .and_then(Value::as_str)
        .unwrap_or("Global")
        .trim()
        .trim_matches(['\'', '"']);
    target.is_empty()
        || target.split(',').any(|s| {
            ["global", "todos", "all", "*"]
                .contains(&s.trim().trim_matches(['\'', '"']).to_lowercase().as_str())
        })
}
pub fn matches(w: &Widget, mode: &Value, place: &Value, editing: bool) -> bool {
    if mode == &json!(false) {
        return false;
    }
    if mode == "global" || editing && mode == &json!(true) {
        return global(w);
    }
    if mode == &json!(true) {
        return true;
    }
    if global(w) {
        return true;
    }
    let number = mode.as_i64().unwrap_or_else(|| {
        if place[1] == 2 {
            10
        } else {
            place[3].as_i64().unwrap_or(0) * place[4].as_i64().unwrap_or(3)
                + place[2].as_i64().unwrap_or(0)
                + 1
        }
    });
    let target = w
        .opts
        .get("workspace")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_lowercase();
    target.split(',').any(|s| {
        let s = s.trim();
        s == number.to_string() || s == format!("workspace {number}") || s == format!("ws{number}")
    }) || target.replace(' ', "") == format!("{},{}", place[2], place[3])
}
pub fn spec(w: &Widget) -> Vec<String> {
    vec![
        "open".into(),
        format!("rw-{}", w.window),
        "--id".into(),
        w.id.clone(),
        "--pos".into(),
        format!("{}x{}", w.x, w.y),
        "--anchor".into(),
        w.anchor.replace('-', " "),
        "--arg".into(),
        format!("wid={}", w.id),
    ]
}
pub fn active(p: &Paths) -> Result<BTreeMap<String, String>> {
    let out = p.ew(&["active-windows"])?;
    ensure!(
        out.ok && !out.out.trim().is_empty(),
        "Eww no confirmó active-windows"
    );
    parse_active(&out.out)
}
fn parse_active(text: &str) -> Result<BTreeMap<String, String>> {
    let mut active = BTreeMap::new();
    for line in text.lines().filter(|s| !s.trim().is_empty()) {
        let (id, kind) = line.split_once(':').context("Respuesta Eww inválida")?;
        ensure!(
            ident(id.trim()) && kind.trim().starts_with("rw-"),
            "Ventana ajena al perfil"
        );
        active.insert(id.trim().into(), kind.trim().into());
    }
    Ok(active)
}
// Empty active-windows is legitimate only after a retry; never erase APPLIED on an ambiguous success.
fn list_active(p: &Paths) -> Result<BTreeMap<String, String>> {
    match active(p) {
        Ok(v) => Ok(v),
        Err(first) => {
            let out = p.ew(&["active-windows"])?;
            if !out.ok {
                return Err(first);
            }
            if out.out.trim().is_empty() {
                // Eww 0.5 also returns empty on its 100ms IPC deadline.
                // Confirm actual surfaces rather than reopening every known instance.
                let views = p
                    .wf("window-rules/list-views", json!({}))
                    .and_then(|v| v.as_array().cloned())
                    .context("No se pudo confirmar ventanas vacías")?;
                let known = widgets(p)?;
                let mut result = BTreeMap::new();
                for view in views {
                    let name = view["app-id"]
                        .as_str()
                        .filter(|s| s.starts_with(&p.prefix))
                        .or_else(|| view["title"].as_str().filter(|s| s.starts_with(&p.prefix)));
                    if let Some(id) = name.and_then(|s| s.strip_prefix(&p.prefix)) {
                        if let Some(w) = known.iter().find(|w| w.id == id) {
                            result.insert(id.into(), format!("rw-{}", w.window));
                        }
                    }
                }
                Ok(result)
            } else {
                parse_active(&out.out)
            }
        }
    }
}
fn mailbox_current(p: &Paths, token: &str) -> bool {
    let req = io::read(p.runtime.join("editor-sync-request.json"));
    req["token"] == token
        && req["expires"].as_f64().unwrap_or(0.) > io::now()
        && p.runtime.join("eww-widgets-editing").exists()
}
pub fn guard_ready(p: &Paths, token: &Value) -> bool {
    let guard = io::read(p.runtime.join("workspace-transition.json"));
    guard["token"] == *token && io::now() >= guard["ready_at"].as_f64().unwrap_or(0.)
}
pub fn invalidate(p: &Paths, delay: f64) -> Result<f64> {
    let deadline = io::now() + delay;
    io::write(
        p.runtime.join("workspace-transition.json"),
        &json!({"token":io::token(),"ready_at":deadline}),
    )?;
    Ok(deadline)
}
fn effect(w: &Widget, anim: &Value, out: bool) -> String {
    let key = if out { "anim_out" } else { "anim" };
    let own = w.opts.get(key).and_then(Value::as_str).unwrap_or("global");
    if own == "global" {
        anim[if out { "anim_out" } else { "anim_in" }]
            .as_str()
            .or_else(|| anim["type"].as_str())
            .unwrap_or("fade")
            .into()
    } else {
        own.into()
    }
}
fn disable_close(p: &Paths, ids: &[String]) {
    if let Some(views) = p
        .wf("window-rules/list-views", json!({}))
        .and_then(|v| v.as_array().cloned())
    {
        let ids: HashSet<String> = ids.iter().map(|id| format!("{}{id}", p.prefix)).collect();
        for view in views {
            if ids.contains(view["app-id"].as_str().unwrap_or("")) {
                for (property, value) in [
                    ("close-animation-type", json!("none")),
                    ("close-animation-duration", json!("0ms circle")),
                ] {
                    p.wf(
                        "window-rules/set-view-property",
                        json!({"id":view["id"],"property":property,"value":value}),
                    );
                }
            }
        }
    }
}
fn close(p: &Paths, ids: &[String]) -> Result<()> {
    if ids.is_empty() {
        return Ok(());
    }
    motion::set(p, ids, false, "none", 0)?;
    disable_close(p, ids);
    let mut args = vec!["close".into()];
    args.extend_from_slice(ids);
    ensure!(p.eww(&args)?.ok, "No se pudo cerrar widgets");
    Ok(())
}
pub fn sync(
    p: &Paths,
    mut mode: Value,
    leaving_only: bool,
    reloading: bool,
    request: Option<&str>,
) -> Result<bool> {
    let Some(_lock) = Lock::acquire(p.runtime.join("eww-widgets.lock"))? else {
        return Ok(false);
    };
    let editing = p.runtime.join("eww-widgets-editing").exists();
    let disabled = p.disabled() && !editing;
    let place = p.place();
    if place.is_none() && !disabled && mode != false {
        return Ok(false);
    }
    let place = place.unwrap_or(Value::Null);
    let ws_token = io::read(p.runtime.join("workspace-transition.json"))["token"].clone();
    let widgets = widgets(p)?;
    let revision = io::stamp(p.config.join("instances.json"));
    let valid_place = || {
        !crate::STOP.load(std::sync::atomic::Ordering::Relaxed)
            && guard_ready(p, &ws_token)
            && p.place().as_ref() == Some(&place)
            && !(p.disabled() && !editing)
            && request.is_none_or(|t| mailbox_current(p, t))
    };
    let valid = || revision == io::stamp(p.config.join("instances.json")) && valid_place();
    if request.is_some() && !valid_place() {
        return Ok(false);
    }
    if mode.is_null() && editing {
        let text = fs::read_to_string(p.runtime.join("eww-widgets-editing")).unwrap_or_default();
        mode = text
            .trim()
            .parse::<i64>()
            .map(Value::from)
            .unwrap_or(json!("global"));
    }
    let number = if place[1] == 2 {
        10
    } else {
        place[3].as_i64().unwrap_or(0) * place[4].as_i64().unwrap_or(3)
            + place[2].as_i64().unwrap_or(0)
            + 1
    };
    if editing {
        let home = io::read(p.runtime.join("editor-place.json"));
        if home.is_array() && home != place || mode.as_i64().is_some_and(|n| n != number) {
            mode = json!(false)
        }
    }
    let active = list_active(p)?;
    let mut applied = io::read(p.runtime.join("eww-widgets-applied.json"))
        .as_object()
        .cloned()
        .unwrap_or_default();
    applied.retain(|id, _| active.contains_key(id));
    let wanted: BTreeMap<String, Vec<String>> = widgets
        .iter()
        .filter(|w| {
            w.show
                && !disabled
                && matches(w, &mode, &place, editing)
                && io::read(
                    p.config
                        .join("widgets")
                        .join(&w.window)
                        .join("manifest.json"),
                )["enabled"]
                    != false
        })
        .map(|w| (w.id.clone(), spec(w)))
        .collect();
    let leaving: Vec<_> = active
        .keys()
        .filter(|id| !wanted.contains_key(*id))
        .cloned()
        .collect();
    if !leaving.is_empty() {
        if !valid_place() && request.is_some() {
            return Ok(false);
        }
        close(p, &leaving)?;
        for id in &leaving {
            applied.remove(id);
        }
    }
    let applied_path = p.runtime.join("eww-widgets-applied.json");
    if leaving_only || !valid() {
        io::write(&applied_path, &Value::Object(applied))?;
        return Ok(true);
    }
    let mut opening: Vec<String> = wanted
        .iter()
        .filter(|(id, args)| !active.contains_key(*id) || applied.get(*id) != Some(&json!(args)))
        .map(|(id, _)| id.clone())
        .collect();
    let anim = io::read(p.config.join("animation.json"));
    let policy = p.policy();
    let factor = policy["policy"]["animation_factor"].as_f64().unwrap_or(1.);
    let when = anim["when"].as_str().unwrap_or("workspace");
    let animated =
        !editing && factor > 0. && (when == "workspace" || when == "reload" && reloading);
    match anim["order"].as_str().unwrap_or("config") {
        "config" => opening.sort_by_key(|id| widgets.iter().position(|w| &w.id == id).unwrap_or(0)),
        "top_to_bottom" => opening.sort_by_key(|id| {
            widgets
                .iter()
                .find(|w| &w.id == id)
                .map(|w| (w.y, w.x))
                .unwrap_or_default()
        }),
        _ => opening.sort_by_key(|id| {
            widgets
                .iter()
                .find(|w| &w.id == id)
                .map(|w| (w.x, w.y))
                .unwrap_or_default()
        }),
    };
    let ms = (anim["duration_in"].as_u64().unwrap_or(320) as f64 * factor.clamp(0., 2.)) as u64;
    let stagger = animated && anim["stagger_in"].as_bool().unwrap_or(false);
    let gap = if stagger {
        (anim["stagger"].as_f64().unwrap_or(110.) / 1000.)
            .min(0.3 / opening.len().saturating_sub(1).max(1) as f64)
    } else {
        0.
    };
    let mut groups: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for id in &opening {
        if !active.contains_key(id) {
            let w = widgets.iter().find(|w| &w.id == id).unwrap();
            groups
                .entry(if animated {
                    effect(w, &anim, false)
                } else {
                    "none".into()
                })
                .or_default()
                .push(id.clone());
        }
    }
    for (e, ids) in groups {
        if valid() {
            motion::set(p, &ids, false, &e, if e == "none" { 0 } else { ms })?
        }
    }
    let mut opened = vec![];
    for id in &opening {
        if !valid() {
            break;
        }
        let started = io::now();
        let result = p.eww(&wanted[id])?;
        if !result.ok {
            bail!("No se pudo abrir {id}: {}", result.err)
        }
        let mut mapped = false;
        for _ in 0..25 {
            if !valid_place() {
                break;
            }
            if list_active(p)?.get(id)
                == Some(&format!(
                    "rw-{}",
                    widgets.iter().find(|w| &w.id == id).unwrap().window
                ))
            {
                mapped = true;
                break;
            }
            thread::sleep(Duration::from_millis(20))
        }
        if !mapped || !valid_place() {
            let _ = close(p, &[id.clone()]);
            break;
        }
        applied.insert(id.clone(), json!(wanted[id]));
        io::write(&applied_path, &Value::Object(applied.clone()))?;
        opened.push(id.clone());
        if !active.contains_key(id) {
            let w = widgets.iter().find(|w| &w.id == id).unwrap();
            let e = if animated {
                effect(w, &anim, false)
            } else {
                "none".into()
            };
            motion::set(p, &[id.clone()], true, &e, if e == "none" { 0 } else { ms })?;
        }
        let remaining = gap - (io::now() - started);
        if remaining > 0. && valid() {
            thread::sleep(Duration::from_secs_f64(remaining));
        }
    }
    if !valid_place() {
        let latest = p.place();
        let keep_global = !editing
            && !p.disabled()
            && request.is_none()
            && latest.as_ref().is_some_and(|v| v[0] == place[0]);
        let obsolete = opened
            .iter()
            .filter(|id| !keep_global || !widgets.iter().any(|w| &w.id == *id && global(w)))
            .cloned()
            .collect::<Vec<_>>();
        close(p, &obsolete)?;
        for id in &obsolete {
            applied.remove(id);
        }
    }
    io::write(applied_path, &Value::Object(applied))?;
    Ok(valid() && opened.len() == opening.len())
}
pub fn owned(p: &Paths, watcher: bool) -> Vec<(i32, String)> {
    let mut result = vec![];
    let Ok(entries) = fs::read_dir("/proc") else {
        return result;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        let Some(pid) = entry
            .file_name()
            .to_str()
            .and_then(|x| x.parse::<i32>().ok())
        else {
            continue;
        };
        let Ok(meta) = fs::metadata(&path) else {
            continue;
        };
        if meta.uid() != unsafe { libc::getuid() } || pid == std::process::id() as i32 {
            continue;
        }
        let Ok(bytes) = fs::read(path.join("cmdline")) else {
            continue;
        };
        let args = bytes
            .split(|b| *b == 0)
            .filter(|s| !s.is_empty())
            .map(|s| String::from_utf8_lossy(s).into_owned())
            .collect::<Vec<_>>();
        let config = args.windows(2).any(|w| {
            ["--config", "-c"].contains(&w[0].as_str())
                && std::path::Path::new(&w[1]).canonicalize().ok().as_ref() == Some(&p.config)
        });
        if !config {
            continue;
        }
        let name = args
            .first()
            .and_then(|x| std::path::Path::new(x).file_name())
            .map(|x| x.to_string_lossy().into_owned())
            .unwrap_or_default();
        let matches = if watcher {
            args.last().is_some_and(|s| s == "watch")
                && (name == "randly-widget-manager"
                    || name.starts_with("python")
                        && args.iter().any(|s| {
                            s == p
                                .home
                                .join(".local/bin/widgetctl")
                                .to_string_lossy()
                                .as_ref()
                                || s == p
                                    .home
                                    .join(".local/lib/randly_widgets/entry.py")
                                    .to_string_lossy()
                                    .as_ref()
                        }))
        } else {
            name == "eww"
        };
        if !matches {
            continue;
        }
        if let Ok(stat) = fs::read_to_string(path.join("stat")) {
            if let Some(birth) = stat
                .rsplit_once(')')
                .and_then(|(_, s)| s.split_whitespace().nth(19))
            {
                result.push((pid, birth.into()))
            }
        }
    }
    result
}
pub fn terminate(p: &Paths, watcher: bool) {
    let targets = owned(p, watcher);
    let same = |pid: i32, birth: &str| {
        fs::read_to_string(format!("/proc/{pid}/stat"))
            .ok()
            .is_some_and(|stat| {
                stat.rsplit_once(')')
                    .and_then(|(_, s)| s.split_whitespace().nth(19))
                    == Some(birth)
            })
    };
    for (pid, birth) in &targets {
        if same(*pid, birth) {
            unsafe {
                libc::kill(*pid, libc::SIGTERM);
            }
        }
    }
    let until = io::now() + 1.5;
    while io::now() < until && targets.iter().any(|(pid, birth)| same(*pid, birth)) {
        thread::sleep(Duration::from_millis(30));
    }
    for (pid, birth) in &targets {
        if same(*pid, birth) {
            unsafe {
                libc::kill(*pid, libc::SIGKILL);
            }
        }
    }
}
pub fn stop(p: &Paths) -> Result<()> {
    terminate(p, true);
    let _ = p.ew(&["kill"]);
    thread::sleep(Duration::from_millis(150));
    terminate(p, false);
    Ok(())
}
pub fn start(p: &Paths) -> Result<()> {
    if p.ew(&["ping"]).is_ok_and(|o| o.ok) {
        return Ok(());
    }
    theme::apply(p)?;
    ensure!(p.bridge.exists(), "Falta puente CSS del gestor Rust");
    let log = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(p.runtime.join("daemon.log"))?;
    let mut c = Command::new(std::env::var("RANDLY_EWW_BIN").unwrap_or("eww".into()));
    c.arg("--config")
        .arg(&p.config)
        .arg("daemon")
        .stdin(Stdio::null())
        .stdout(log.try_clone()?)
        .stderr(log)
        .env("RANDLY_WIDGETS_THEME_CSS", p.runtime.join("theme.css"));
    let previous = std::env::var("LD_PRELOAD").unwrap_or_default();
    c.env("LD_PRELOAD", format!("{} {}", p.bridge.display(), previous));
    use std::os::unix::process::CommandExt;
    unsafe {
        c.pre_exec(|| {
            libc::setsid();
            Ok(())
        });
    }
    c.spawn()?;
    for _ in 0..40 {
        if p.ew(&["ping"]).is_ok_and(|o| o.ok) {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(100))
    }
    bail!("Eww no arrancó; consulta daemon.log")
}
pub fn spawn_watcher(p: &Paths) -> Result<()> {
    let log = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(p.runtime.join("manager.log"))?;
    let mut c = Command::new(std::env::current_exe()?);
    c.arg("--config")
        .arg(&p.config)
        .arg("watch")
        .stdin(Stdio::null())
        .stdout(log.try_clone()?)
        .stderr(log);
    use std::os::unix::process::CommandExt;
    unsafe {
        c.pre_exec(|| {
            libc::setsid();
            Ok(())
        });
    }
    c.spawn()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn w(target: &str) -> Widget {
        serde_json::from_value(json!({"id":"a","window":"api","show":true,"anchor":"top-left","x":4,"y":6,"opts":{"workspace":target}})).unwrap()
    }
    #[test]
    fn global_filter_is_exclusive() {
        let place = json!([5, 1, 0, 0, 3]);
        assert!(matches(&w("Todos"), &json!("global"), &place, true));
        assert!(!matches(&w("Workspace 1"), &json!("global"), &place, true));
        assert!(matches(&w("Workspace 1"), &Value::Null, &place, false));
        assert!(!matches(&w("Workspace 2"), &Value::Null, &place, false));
        assert!(!matches(&w("Global"), &json!(false), &place, false));
    }
    #[test]
    fn saved_geometry_is_never_defaulted() {
        let widget = w("Global");
        let args = spec(&widget);
        assert!(args.windows(2).any(|x| x == ["--pos", "4x6"]));
        assert!(args.windows(2).any(|x| x == ["--anchor", "top left"]));
    }
    #[test]
    fn ambiguous_or_foreign_active_response_is_rejected() {
        assert!(parse_active("nonsense").is_err());
        assert!(parse_active("foreign: panel").is_err());
        assert_eq!(
            parse_active("a: rw-api").unwrap().get("a").unwrap(),
            "rw-api"
        );
    }
}

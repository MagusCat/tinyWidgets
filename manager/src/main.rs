mod instances;
mod io;
mod motion;
mod runtime;
mod theme;
mod watch;
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::{
    fs,
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicBool, Ordering},
    thread,
    time::Duration,
};
pub static STOP: AtomicBool = AtomicBool::new(false);
extern "C" fn stop(_: i32) {
    STOP.store(true, Ordering::Relaxed);
}
fn mode(args: &[String]) -> Value {
    match args.first().map(String::as_str) {
        Some("global") => json!("global"),
        Some("on") => json!(true),
        Some("off") => json!(false),
        Some(n) => n.parse::<u64>().map(Value::from).unwrap_or(Value::Null),
        _ => Value::Null,
    }
}
fn legacy(args: &[String]) -> Result<i32> {
    use std::os::unix::process::CommandExt;
    let home = PathBuf::from(std::env::var("HOME")?);
    let binary = std::env::current_exe()?;
    let error = Command::new("python3")
        .arg(home.join(".local/lib/randly_widgets/entry.py"))
        .args(args)
        .env("RANDLY_WIDGETS_MANAGER", binary)
        .exec();
    Err(error.into())
}
fn preview(p: &io::Paths, args: &[String]) -> Result<()> {
    let Some(_lock) = io::Lock::acquire(p.runtime.join("eww-widgets.lock"))? else {
        return Ok(());
    };
    let place = p.place().context("Wayfire no responde")?;
    let token = io::read(p.runtime.join("workspace-transition.json"))["token"].clone();
    let valid = || {
        !STOP.load(Ordering::Relaxed)
            && runtime::guard_ready(p, &token)
            && p.place().as_ref() == Some(&place)
    };
    let ids = runtime::active(p)?.into_keys().collect::<Vec<_>>();
    let anim = io::read(p.config.join("animation.json"));
    let input = args
        .first()
        .map(String::as_str)
        .or_else(|| anim["anim_in"].as_str())
        .unwrap_or("fade");
    let output = args
        .get(1)
        .map(String::as_str)
        .or_else(|| anim["anim_out"].as_str())
        .unwrap_or("fade");
    let factor = p.policy()["policy"]["animation_factor"]
        .as_f64()
        .unwrap_or(1.)
        .clamp(0., 2.);
    let input = if factor == 0. { "none" } else { input };
    let output = if factor == 0. { "none" } else { output };
    let ms_out = if output == "none" {
        0
    } else {
        (anim["duration_out"].as_u64().unwrap_or(240) as f64 * factor) as u64
    };
    if !valid() {
        return Ok(());
    }
    motion::set(p, &ids, false, output, ms_out)?;
    let until = io::now() + ms_out as f64 / 1000. + 0.08;
    while io::now() < until {
        if !valid() {
            return Ok(());
        }
        thread::sleep(Duration::from_millis(20))
    }
    if valid() {
        motion::set(
            p,
            &ids,
            true,
            input,
            if input == "none" {
                0
            } else {
                (anim["duration_in"].as_u64().unwrap_or(320) as f64 * factor) as u64
            },
        )?
    }
    Ok(())
}
fn main() -> std::process::ExitCode {
    unsafe {
        libc::signal(libc::SIGTERM, stop as *const () as usize);
        libc::signal(libc::SIGINT, stop as *const () as usize);
    }
    match run() {
        Ok(code) => std::process::ExitCode::from(code as u8),
        Err(e) => {
            eprintln!("widgetctl: {e:#}");
            std::process::ExitCode::FAILURE
        }
    }
}
fn run() -> Result<i32> {
    let raw = std::env::args().skip(1).collect::<Vec<_>>();
    let mut root = std::env::var_os("RANDLY_WIDGETS_CONFIG")
        .map(PathBuf::from)
        .unwrap_or(PathBuf::from(std::env::var("HOME")?).join(".config/eww"));
    let mut at = 0;
    while at < raw.len() {
        if raw[at] == "--config" || raw[at] == "-c" {
            root = PathBuf::from(raw.get(at + 1).context("Falta directorio --config")?);
            at += 2
        } else {
            break;
        }
    }
    let command = raw.get(at).map(String::as_str).unwrap_or("list");
    let args = raw.get(at + 1..).unwrap_or(&[]);
    if command == "--version" {
        println!("randly-widget-manager 1.0.0 (Rust)");
        return Ok(0);
    }
    if ![
        "start",
        "stop",
        "restart",
        "reload",
        "watch",
        "sync",
        "sync-leaving",
        "sync-out",
        "frames",
        "theme",
        "manager-status",
        "preview-anim",
        "test-anim",
        "compile-css",
        "add",
        "set",
        "remove",
        "duplicate",
        "enable",
        "disable",
        "toggle",
        "toggle-all",
        "toggle-global",
    ]
    .contains(&command)
    {
        return legacy(&raw);
    }
    let p = io::Paths::new(root)?;
    if command == "compile-css" {
        let source = fs::read_to_string(args.first().context("Falta fuente SCSS")?)?;
        let css = grass::from_string(source, &grass::Options::default())
            .map_err(|e| anyhow::anyhow!("SCSS: {e}"))?;
        theme::validate(&css)?;
        io::atomic(args.get(1).context("Falta destino CSS")?, css.as_bytes())?;
        return Ok(0);
    }
    if command == "manager-status" {
        println!(
            "{}",
            json!({"backend":"rust","version":1,"profile":p.config,"runtime":p.runtime,"theme_bridge":p.bridge.exists(),"service":io::read(p.runtime.join("editor-sync-service.json"))})
        );
        return Ok(0);
    }
    if command == "theme" {
        theme::apply(&p)?;
        return Ok(0);
    }
    if command == "frames" {
        motion::stream(&p)?;
        return Ok(0);
    }
    if !p.config.join(".modular-active").exists() && !p.config.join(".preview").exists() {
        bail!("Perfil modular no activado")
    }
    match command {
        "add" | "set" | "remove" | "duplicate" => instances::edit(&p, command, args)?,
        "enable" | "disable" | "toggle" if !args.is_empty() => instances::edit(&p, command, args)?,
        "enable" | "disable" | "toggle" | "toggle-all" | "toggle-global" => {
            instances::visibility(&p, command)?
        }
        "watch" => watch::main(&p)?,
        "sync" | "sync-leaving" | "sync-out" => {
            return Ok(
                if runtime::sync(&p, mode(args), command != "sync", false, None)? {
                    0
                } else {
                    1
                },
            )
        }
        "start" => {
            if p.disabled() && !p.runtime.join("eww-widgets-editing").exists() {
                return Ok(0);
            }
            if let Some(_lock) = io::Lock::acquire(p.runtime.join("eww-widget-editor.lock"))? {
                for name in [
                    "eww-widgets-editing",
                    "editor-place.json",
                    "editor-drag.json",
                    "editor-sync-request.json",
                ] {
                    let _ = fs::remove_file(p.runtime.join(name));
                }
            }
            runtime::start(&p)?;
            runtime::spawn_watcher(&p)?
        }
        "stop" => runtime::stop(&p)?,
        "restart" => {
            runtime::stop(&p)?;
            let _ = fs::remove_file(p.runtime.join("eww-widgets-applied.json"));
            runtime::start(&p)?;
            runtime::invalidate(&p, 0.)?;
            runtime::sync(&p, Value::Null, false, true, None)?;
            runtime::spawn_watcher(&p)?
        }
        "reload" => {
            let result = p.python(&["prepare-manager-reload".into()])?;
            if !result.ok {
                bail!("{}", result.err)
            }
            let prepared: Value =
                serde_json::from_str(result.out.trim()).context("Preparación inválida")?;
            let apply = (|| {
                runtime::stop(&p)?;
                let _ = fs::remove_file(p.runtime.join("eww-widgets-applied.json"));
                runtime::start(&p)?;
                runtime::invalidate(&p, 0.)?;
                runtime::sync(&p, Value::Null, false, true, None)?;
                runtime::spawn_watcher(&p)?;
                Ok::<_, anyhow::Error>(())
            })();
            if let Err(e) = apply {
                let _ = runtime::stop(&p);
                if let Some(old) = prepared["old"].as_str() {
                    let temporary = p.config.join("generated/.native-rollback");
                    let _ = fs::remove_file(&temporary);
                    std::os::unix::fs::symlink(old, &temporary)?;
                    fs::rename(temporary, p.config.join("generated/current"))?;
                    let _ = runtime::start(&p);
                    let _ = runtime::spawn_watcher(&p);
                }
                return Err(e);
            }
        }
        "preview-anim" | "test-anim" => preview(&p, args)?,
        _ => unreachable!(),
    }
    Ok(0)
}

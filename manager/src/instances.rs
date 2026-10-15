//! Atomic CLI edits; the Python editor keeps its three-way merge contract.
use crate::{
    io::{self, Lock, Paths},
    runtime::{self, Widget},
};
use anyhow::{bail, ensure, Context, Result};
use serde_json::{json, Value};
use std::{fs, thread, time::Duration};
fn lock(p: &Paths) -> Result<Lock> {
    let deadline = io::now() + 2.;
    loop {
        if let Some(lock) = Lock::acquire(p.config.join("instances.json.lock"))? {
            return Ok(lock);
        }
        if io::now() > deadline {
            bail!("Configuración ocupada")
        }
        thread::sleep(Duration::from_millis(5));
    }
}
pub fn edit(p: &Paths, command: &str, args: &[String]) -> Result<()> {
    let name = args.first().context("Falta instancia o tipo")?;
    ensure!(
        !name.is_empty()
            && name
                .bytes()
                .all(|b| b.is_ascii_alphanumeric() || b == b'_' || b == b'-'),
        "ID o tipo inválido"
    );
    if command == "add" {
        let meta = io::read(p.config.join("widgets").join(name).join("manifest.json"));
        ensure!(
            meta["id"] == name.as_str() && meta["enabled"] != false,
            "Tipo desconocido o retirado"
        );
        let source = fs::read_to_string(p.config.join("generated/current/view.yuck"))?;
        if !source.contains(&format!("(defwindow rw-{name} ")) {
            let mut c = std::process::Command::new(std::env::current_exe()?);
            c.arg("--config").arg(&p.config).arg("reload");
            let r = io::run(c, Duration::from_secs(120))?;
            ensure!(r.ok, "No se pudo cargar tipo: {}", r.err)
        }
    }
    let _lock = lock(p)?;
    let mut widgets = runtime::widgets(p)?;
    if command == "add" {
        let meta = io::read(p.config.join("widgets").join(name).join("manifest.json"));
        let id = args
            .iter()
            .position(|v| v == "--id")
            .map(|i| args.get(i + 1).cloned().context("Falta ID"))
            .transpose()?
            .unwrap_or_else(|| meta["base_id"].as_str().unwrap_or(name).into());
        ensure!(!widgets.iter().any(|w| w.id == id), "ID ya utilizado");
        widgets.push(Widget {
            id,
            window: name.clone(),
            show: true,
            anchor: "top-left".into(),
            x: 40,
            y: 60,
            opts: Default::default(),
            extra: Default::default(),
        });
    } else {
        let i = widgets
            .iter()
            .position(|w| &w.id == name)
            .context("Instancia desconocida")?;
        match command {
            "remove" => {
                widgets.remove(i);
            }
            "enable" => widgets[i].show = true,
            "disable" => widgets[i].show = false,
            "toggle" => widgets[i].show = !widgets[i].show,
            "duplicate" => {
                let mut n = 2;
                while widgets.iter().any(|w| w.id == format!("{name}{n}")) {
                    n += 1
                }
                let mut w = widgets[i].clone();
                w.id = format!("{name}{n}");
                w.x += 24;
                w.y += 24;
                widgets.push(w)
            }
            "set" => {
                for part in &args[1..] {
                    let (key, value) = part.split_once('=').context("Usa opción=valor")?;
                    match key {
                        "x" => widgets[i].x = value.parse()?,
                        "y" => widgets[i].y = value.parse()?,
                        "anchor" => widgets[i].anchor = value.into(),
                        _ => {
                            widgets[i].opts.insert(key.into(), json!(value));
                        }
                    }
                }
            }
            _ => bail!("Edición desconocida"),
        }
    }
    runtime::validate(&widgets)?;
    let revision = io::read(p.config.join("instances.json"))["revision"]
        .as_u64()
        .unwrap_or(0)
        + 1;
    let mut document = io::read(p.config.join("instances.json"));
    document["revision"] = json!(revision);
    document["widgets"] = json!(widgets);
    io::write(p.config.join("instances.json"), &document)?;
    drop(_lock);
    let _ = runtime::sync(p, Value::Null, false, false, None)?;
    Ok(())
}
pub fn visibility(p: &Paths, command: &str) -> Result<()> {
    let path = p.config.join(".disabled");
    let disable = match command {
        "disable" => true,
        "enable" => false,
        _ => !path.exists(),
    };
    if disable {
        io::atomic(&path, b"1\n")?
    } else if path.exists() {
        fs::remove_file(path)?
    }
    let _ = runtime::sync(p, Value::Null, false, false, None)?;
    Ok(())
}

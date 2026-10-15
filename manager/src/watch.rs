use crate::{
    io::{self, Lock, Paths},
    runtime,
};
use anyhow::{bail, Result};
use serde_json::{json, Value};
use std::{fs, io::Read, os::unix::net::UnixStream, sync::mpsc, thread, time::Duration};
struct Job {
    mode: Value,
    leaving: bool,
    token: Option<String>,
}
fn pending(p: &Paths) -> Option<Value> {
    let req = io::read(p.runtime.join("editor-sync-request.json"));
    let mode = &req["mode"];
    if !p.runtime.join("eww-widgets-editing").exists()
        || req["expires"].as_f64()? <= io::now()
        || req["token"].as_str()?.is_empty()
        || !(mode.is_boolean()
            || mode == "global"
            || mode.as_u64().is_some_and(|n| (1..=100).contains(&n)))
        || io::read(p.runtime.join("editor-sync-ack.json"))["token"] == req["token"]
    {
        None
    } else {
        Some(req)
    }
}
pub fn main(p: &Paths) -> Result<()> {
    let Some(_lock) = Lock::acquire(p.runtime.join("eww-workspace-watch.lock"))? else {
        return Ok(());
    };
    let path = p
        .wf_path()
        .ok_or_else(|| anyhow::anyhow!("No se encontró socket Wayfire"))?;
    let (tx, rx) = mpsc::sync_channel::<Job>(1);
    let (done_tx, done) = mpsc::channel();
    let worker_paths = p.clone();
    let worker = thread::spawn(move || {
        while let Ok(job) = rx.recv() {
            let result = runtime::sync(
                &worker_paths,
                job.mode,
                job.leaving,
                false,
                job.token.as_deref(),
            );
            if let Err(e) = &result {
                eprintln!("widget-manager: {e:#}")
            }
            let _ = done_tx.send((job.token, result.unwrap_or(false)));
        }
    });
    let mut failures = 0;
    let mut busy = false;
    let mut heartbeat = 0.;
    while !crate::STOP.load(std::sync::atomic::Ordering::Relaxed) {
        let connection = (|| {
            let mut s = UnixStream::connect(&path)?;
            s.set_read_timeout(Some(Duration::from_secs(2)))?;
            s.set_write_timeout(Some(Duration::from_secs(2)))?;
            io::send(
                &mut s,
                "window-rules/events/watch",
                json!({"events":["wset-workspace-changed","output-wset-changed"]}),
            )?;
            io::receive(&mut s)?;
            s.set_nonblocking(true)?;
            Ok::<_, anyhow::Error>(s)
        })();
        let mut socket = match connection {
            Ok(s) => {
                failures = 0;
                s
            }
            Err(e) => {
                failures += 1;
                runtime::invalidate(p, crate::animation::workspace_delay(p))?;
                if failures > 15 {
                    return Err(e);
                }
                thread::sleep(Duration::from_secs(2));
                continue;
            }
        };
        let mut deadline = runtime::invalidate(p, crate::animation::workspace_delay(p))?;
        let mut leave = false;
        let mut dirty = true;
        let mut seen = io::stamp(p.config.join("instances.json"));
        let mut audit = io::now() + 2.;
        let mut buffer = Vec::new();
        loop {
            if crate::STOP.load(std::sync::atomic::Ordering::Relaxed) {
                break;
            }
            let now = io::now();
            if now >= heartbeat {
                io::write(
                    p.runtime.join("editor-sync-service.json"),
                    &json!({"version":1,"backend":"rust","expires":now+2.}),
                )?;
                heartbeat = now + 1.
            }
            if let Ok((token, success)) = done.try_recv() {
                busy = false;
                if let Some(token) = token {
                    io::write(
                        p.runtime.join("editor-sync-ack.json"),
                        &json!({"token":token,"success":success}),
                    )?
                }
                if !success {
                    dirty = true;
                    deadline = deadline.max(now + 0.1)
                }
            }
            let stamp = io::stamp(p.config.join("instances.json"));
            if stamp != seen {
                seen = stamp;
                dirty = true
            }
            if now >= audit {
                dirty = true;
                audit = now + 2.
            }
            let request = pending(p);
            if !busy {
                let job = if leave {
                    leave = false;
                    Some(Job {
                        mode: Value::Null,
                        leaving: true,
                        token: None,
                    })
                } else if now >= deadline {
                    if let Some(req) = request {
                        dirty = false;
                        Some(Job {
                            mode: req["mode"].clone(),
                            leaving: false,
                            token: req["token"].as_str().map(String::from),
                        })
                    } else if dirty {
                        dirty = false;
                        Some(Job {
                            mode: Value::Null,
                            leaving: false,
                            token: None,
                        })
                    } else {
                        None
                    }
                } else {
                    None
                };
                if let Some(job) = job {
                    tx.send(job)?;
                    busy = true
                }
            }
            let mut chunk = [0u8; 8192];
            let mut disconnected = false;
            loop {
                match socket.read(&mut chunk) {
                    Ok(0) => {
                        disconnected = true;
                        break;
                    }
                    Ok(n) => {
                        buffer.extend_from_slice(&chunk[..n]);
                        if buffer.len() > 8 * 1024 * 1024 {
                            bail!("Eventos Wayfire demasiado grandes")
                        }
                    }
                    Err(e) if e.kind() == std::io::ErrorKind::WouldBlock => break,
                    Err(_) => {
                        disconnected = true;
                        break;
                    }
                }
            }
            while buffer.len() >= 4 {
                let n = u32::from_le_bytes(buffer[..4].try_into().unwrap()) as usize;
                if n > 8 * 1024 * 1024 {
                    bail!("Evento Wayfire inválido")
                }
                if buffer.len() < 4 + n {
                    break;
                }
                let event: Value = serde_json::from_slice(&buffer[4..4 + n])?;
                buffer.drain(..4 + n);
                if ["wset-workspace-changed", "output-wset-changed"]
                    .contains(&event["event"].as_str().unwrap_or(""))
                {
                    deadline = runtime::invalidate(p, crate::animation::workspace_delay(p))?;
                    leave = true;
                    dirty = true
                }
            }
            if disconnected {
                runtime::invalidate(p, crate::animation::workspace_delay(p))?;
                break;
            }
            thread::sleep(Duration::from_millis(
                if busy || dirty || p.runtime.join("eww-widgets-editing").exists() {
                    20
                } else {
                    80
                },
            ));
        }
    }
    runtime::invalidate(p, 0.)?;
    let _ = fs::remove_file(p.runtime.join("editor-sync-service.json"));
    drop(tx);
    let _ = worker.join();
    Ok(())
}

use anyhow::{anyhow, Context, Result};
use serde_json::{json, Value};
use std::{
    fs::{self, File, OpenOptions},
    io::{Read, Write},
    os::{
        fd::AsRawFd,
        unix::{fs::OpenOptionsExt, net::UnixStream},
    },
    path::{Path, PathBuf},
    process::{Command, Stdio},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
pub fn now() -> f64 {
    unsafe {
        let mut t: libc::timespec = std::mem::zeroed();
        libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut t);
        t.tv_sec as f64 + t.tv_nsec as f64 / 1e9
    }
}
pub fn token() -> String {
    format!(
        "{:x}-{:x}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos(),
        now()
    )
}
pub fn read(path: impl AsRef<Path>) -> Value {
    fs::read(path)
        .ok()
        .and_then(|s| serde_json::from_slice(&s).ok())
        .unwrap_or(Value::Null)
}
pub fn atomic(path: impl AsRef<Path>, data: &[u8]) -> Result<()> {
    let path = path.as_ref();
    let parent = path.parent().context("Ruta sin directorio")?;
    fs::create_dir_all(parent)?;
    let temp = parent.join(format!(".rw-{}", token()));
    let result = (|| {
        let mut f = OpenOptions::new()
            .create_new(true)
            .write(true)
            .mode(0o600)
            .open(&temp)?;
        f.write_all(data)?;
        f.sync_all()?;
        fs::rename(&temp, path)?;
        Ok(())
    })();
    let _ = fs::remove_file(temp);
    result
}
pub fn write(path: impl AsRef<Path>, v: &Value) -> Result<()> {
    let bytes = serde_json::to_vec(v)?;
    if fs::read(path.as_ref()).ok().as_deref() != Some(bytes.as_slice()) {
        atomic(path, &bytes)?;
    }
    Ok(())
}
pub fn stamp(path: impl AsRef<Path>) -> Option<SystemTime> {
    fs::metadata(path).and_then(|m| m.modified()).ok()
}
pub struct Lock(File);
impl Lock {
    pub fn acquire(path: impl AsRef<Path>) -> Result<Option<Self>> {
        let f = OpenOptions::new()
            .create(true)
            .truncate(false)
            .write(true)
            .mode(0o600)
            .open(path)?;
        let n = unsafe { libc::flock(f.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) };
        if n == 0 {
            Ok(Some(Self(f)))
        } else if std::io::Error::last_os_error().kind() == std::io::ErrorKind::WouldBlock {
            Ok(None)
        } else {
            Err(std::io::Error::last_os_error().into())
        }
    }
}
impl Drop for Lock {
    fn drop(&mut self) {
        unsafe {
            libc::flock(self.0.as_raw_fd(), libc::LOCK_UN);
        }
    }
}
pub struct Output {
    pub ok: bool,
    pub out: String,
    pub err: String,
}
pub fn run(mut cmd: Command, timeout: Duration) -> Result<Output> {
    let mut child = cmd
        .stdin(Stdio::null())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()?;
    let stdout = child.stdout.take().unwrap();
    let stderr = child.stderr.take().unwrap();
    let result = thread::scope(|scope| {
        let a = scope.spawn(move || {
            let mut s = String::new();
            stdout
                .take(8 * 1024 * 1024)
                .read_to_string(&mut s)
                .map(|_| s)
        });
        let b = scope.spawn(move || {
            let mut s = String::new();
            stderr.take(1024 * 1024).read_to_string(&mut s).map(|_| s)
        });
        let start = now();
        let status = loop {
            if let Some(s) = child.try_wait()? {
                break Some(s);
            }
            if now() - start > timeout.as_secs_f64() {
                let _ = child.kill();
                let _ = child.wait();
                break None;
            }
            thread::sleep(Duration::from_millis(5));
        };
        let out = a.join().map_err(|_| anyhow!("Error leyendo proceso"))??;
        let err = b.join().map_err(|_| anyhow!("Error leyendo proceso"))??;
        Ok::<_, anyhow::Error>(Output {
            ok: status.is_some_and(|s| s.success()),
            out,
            err,
        })
    });
    result
}
#[derive(Clone)]
pub struct Paths {
    pub config: PathBuf,
    pub runtime: PathBuf,
    pub state: PathBuf,
    pub home: PathBuf,
    pub prefix: String,
    pub palette: PathBuf,
    pub bridge: PathBuf,
}
impl Paths {
    pub fn new(config: PathBuf) -> Result<Self> {
        let config = config.canonicalize()?;
        let home = PathBuf::from(std::env::var("HOME")?);
        let mut c = Command::new("sha256sum")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .spawn()?;
        c.stdin
            .take()
            .unwrap()
            .write_all(config.to_string_lossy().as_bytes())?;
        let h = c.wait_with_output()?;
        if !h.status.success() {
            return Err(anyhow!("No se pudo identificar perfil"));
        }
        let key = String::from_utf8(h.stdout)?[..12].to_string();
        let base = std::env::var("XDG_RUNTIME_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| PathBuf::from(format!("/run/user/{}", unsafe { libc::getuid() })));
        let state_base = std::env::var("XDG_STATE_HOME")
            .map(PathBuf::from)
            .unwrap_or_else(|_| home.join(".local/state"));
        let runtime = base.join("randly-widgets").join(&key);
        let state = state_base.join("randly-widgets").join(&key);
        fs::create_dir_all(&runtime)?;
        fs::create_dir_all(&state)?;
        let palette = if Some(&config) == home.join(".config/eww").canonicalize().ok().as_ref() {
            state_base.join("randly-widgets/palette.scss")
        } else {
            config.join("_colors.scss")
        };
        let bridge = home.join(".local/lib/randly-widgets/librandly_widget_theme.so");
        Ok(Self {
            config,
            runtime,
            state,
            home,
            prefix: format!("rw-{key}-"),
            palette,
            bridge,
        })
    }
    pub fn eww(&self, args: &[String]) -> Result<Output> {
        let mut c = Command::new(std::env::var("RANDLY_EWW_BIN").unwrap_or_else(|_| "eww".into()));
        c.arg("--config")
            .arg(&self.config)
            .arg("--no-daemonize")
            .args(args);
        run(c, Duration::from_secs(5))
    }
    pub fn ew(&self, args: &[&str]) -> Result<Output> {
        self.eww(&args.iter().map(|s| s.to_string()).collect::<Vec<_>>())
    }
    pub fn python(&self, args: &[String]) -> Result<Output> {
        let mut c = Command::new("python3");
        c.arg(self.home.join(".local/lib/randly_widgets/entry.py"))
            .arg("--config")
            .arg(&self.config)
            .args(args);
        run(c, Duration::from_secs(120))
    }
    pub fn policy(&self) -> Value {
        let root = self.state.parent().unwrap().parent().unwrap();
        let mut v = read(root.join("desktop-power/status.json"));
        if !v.is_object() {
            v = json!({"policy":{}})
        }
        v
    }
    pub fn disabled(&self) -> bool {
        self.config.join(".disabled").exists()
            || self.policy()["policy"]["widgets"].as_bool() == Some(false)
    }
    pub fn wf_path(&self) -> Option<PathBuf> {
        if let Some(p) = std::env::var_os("WAYFIRE_SOCKET") {
            return Some(p.into());
        }
        let base = self.runtime.parent()?.parent()?;
        fs::read_dir(base)
            .ok()?
            .flatten()
            .map(|x| x.path())
            .find(|p| {
                p.file_name().is_some_and(|x| {
                    let s = x.to_string_lossy();
                    s.starts_with("wayfire-") && s.ends_with(".socket")
                })
            })
    }
    pub fn wf(&self, method: &str, data: Value) -> Option<Value> {
        #[cfg(feature = "test-transport")]
        if let Some(path) = std::env::var_os("RANDLY_WIDGETS_TEST_WF") {
            let fixture = read(PathBuf::from(path));
            return match method {
                "window-rules/list-outputs" => Some(
                    json!([{"id":5,"wset-index":1,"workspace":{"x":i64::from(Path::new(fixture["switch"].as_str()?).exists()),"y":0,"grid_width":3}}]),
                ),
                "window-rules/list-views" => {
                    let state = read(fixture["state"].as_str()?);
                    let items = state["active"]
                        .as_object()?
                        .keys()
                        .enumerate()
                        .map(|(i, id)| json!({"id":i+1,"app-id":format!("{}{id}",self.prefix)}))
                        .collect::<Vec<_>>();
                    Some(json!(items))
                }
                _ => Some(json!({"result":"ok"})),
            };
        }
        let path = self.wf_path()?;
        let mut s = UnixStream::connect(path).ok()?;
        s.set_read_timeout(Some(Duration::from_secs(2))).ok()?;
        s.set_write_timeout(Some(Duration::from_secs(2))).ok()?;
        send(&mut s, method, data).ok()?;
        receive(&mut s).ok()
    }
    pub fn place(&self) -> Option<Value> {
        let v = self.wf("window-rules/list-outputs", json!({}))?;
        let o = v.as_array()?.first()?;
        let ws = o.get("workspace")?;
        Some(json!([
            o.get("id")?,
            o.get("wset-index")?,
            ws.get("x")?,
            ws.get("y")?,
            ws.get("grid_width").unwrap_or(&json!(3))
        ]))
    }
}
pub fn send<W: Write>(s: &mut W, method: &str, data: Value) -> Result<()> {
    let b = serde_json::to_vec(&json!({"method":method,"data":data}))?;
    s.write_all(&(b.len() as u32).to_le_bytes())?;
    s.write_all(&b)?;
    Ok(())
}
pub fn receive<R: Read>(s: &mut R) -> Result<Value> {
    let mut size = [0; 4];
    s.read_exact(&mut size)?;
    let n = u32::from_le_bytes(size) as usize;
    if n > 8 * 1024 * 1024 {
        return Err(anyhow!("Respuesta Wayfire demasiado grande"));
    }
    let mut b = vec![0; n];
    s.read_exact(&mut b)?;
    Ok(serde_json::from_slice(&b)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fragmented(std::io::Cursor<Vec<u8>>);
    impl Read for Fragmented {
        fn read(&mut self, b: &mut [u8]) -> std::io::Result<usize> {
            let n = b.len().min(1);
            self.0.read(&mut b[..n])
        }
    }
    #[test]
    fn framed_ipc_handles_fragmentation() {
        let expected = json!({"event":"wset-workspace-changed","x":2});
        let payload = serde_json::to_vec(&expected).unwrap();
        let mut bytes = (payload.len() as u32).to_le_bytes().to_vec();
        bytes.extend(payload);
        let mut input = Fragmented(std::io::Cursor::new(bytes));
        assert_eq!(receive(&mut input).unwrap(), expected);
    }
    #[test]
    fn framed_ipc_rejects_oversized_body() {
        let mut input = std::io::Cursor::new((9 * 1024 * 1024u32).to_le_bytes());
        assert!(receive(&mut input).is_err());
    }
    #[test]
    fn outbound_packet_has_exact_length_and_json() {
        let mut output = Vec::new();
        send(&mut output, "test", json!({"x":2})).unwrap();
        let size = u32::from_le_bytes(output[..4].try_into().unwrap()) as usize;
        assert_eq!(size, output.len() - 4);
        let v: Value = serde_json::from_slice(&output[4..]).unwrap();
        assert_eq!(v, json!({"method":"test","data":{"x":2}}));
    }
}

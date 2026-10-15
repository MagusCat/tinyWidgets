use crate::io::{atomic, Paths};
use anyhow::{bail, Context, Result};
use std::{
    ffi::{c_char, c_void, CString},
    fs,
};
#[repr(C)]
struct GError {
    domain: u32,
    code: i32,
    message: *mut c_char,
}
#[link(name = "gtk-3")]
extern "C" {
    fn gtk_css_provider_new() -> *mut c_void;
    fn gtk_css_provider_load_from_data(
        p: *mut c_void,
        data: *const c_char,
        n: isize,
        error: *mut *mut GError,
    ) -> i32;
}
#[link(name = "gobject-2.0")]
extern "C" {
    fn g_object_unref(p: *mut c_void);
}
#[link(name = "glib-2.0")]
extern "C" {
    fn g_error_free(p: *mut GError);
}
pub fn validate(css: &str) -> Result<()> {
    let data = CString::new(css)?;
    unsafe {
        let p = gtk_css_provider_new();
        let mut error = std::ptr::null_mut();
        let ok = gtk_css_provider_load_from_data(p, data.as_ptr(), css.len() as isize, &mut error);
        g_object_unref(p);
        if !error.is_null() {
            let text = std::ffi::CStr::from_ptr((*error).message)
                .to_string_lossy()
                .into_owned();
            g_error_free(error);
            bail!("CSS GTK inválido: {text}")
        }
        if ok == 0 {
            bail!("GTK rechazó la paleta")
        }
    }
    Ok(())
}
pub fn source(p: &Paths) -> Result<String> {
    let text = fs::read_to_string(p.config.join("generated/current/style.scss"))?;
    let body = text
        .find("// RW_PALETTE_END")
        .map(|i| &text[i..])
        .or_else(|| text.find("// Window surface belongs").map(|i| &text[i..]))
        .context("Generación sin separador de paleta; usa widgetctl reload una vez")?;
    let colors = fs::read_to_string(&p.palette)
        .or_else(|_| fs::read_to_string(p.config.join("_colors.scss")))?;
    Ok(format!("{colors}\n{body}"))
}
pub fn apply(p: &Paths) -> Result<()> {
    let deadline = crate::io::now() + 5.;
    let _lock = loop {
        if let Some(lock) = crate::io::Lock::acquire(p.runtime.join("theme.lock"))? {
            break lock;
        }
        if crate::io::now() > deadline {
            bail!("Paleta ocupada")
        }
        std::thread::sleep(std::time::Duration::from_millis(20));
    };
    let css = grass::from_string(source(p)?, &grass::Options::default())
        .map_err(|e| anyhow::anyhow!("SCSS: {e}"))?;
    validate(&css)?;
    let path = p.runtime.join("theme.css");
    if fs::read_to_string(&path).ok().as_deref() != Some(&css) {
        atomic(path, css.as_bytes())?
    }
    Ok(())
}

/// Palette changes animate existing surfaces; never open/close/reload them.
pub fn change(p: &Paths) -> Result<()> {
    use crate::{animation, io, motion, runtime};
    use serde_json::Value;
    let deadline = crate::io::now() + 5.;
    let _theme = loop {
        if let Some(lock) = io::Lock::acquire(p.runtime.join("theme.lock"))? {
            break lock;
        }
        if crate::io::now() > deadline {
            bail!("Paleta ocupada")
        }
        if !animation::wait(20, || true) {
            return Ok(());
        }
    };
    // Validate before hiding anything. A malformed palette leaves windows intact.
    let css = grass::from_string(source(p)?, &grass::Options::default())
        .map_err(|e| anyhow::anyhow!("SCSS: {e}"))?;
    validate(&css)?;
    let path = p.runtime.join("theme.css");
    if fs::read_to_string(&path).ok().as_deref() == Some(&css) {
        return Ok(());
    }
    let anim = io::read(p.config.join("animation.json"));
    let factor = p.policy()["policy"]["animation_factor"]
        .as_f64()
        .unwrap_or(1.);
    let place = p.place();
    let token = io::read(p.runtime.join("workspace-transition.json"))["token"].clone();
    let stable = || {
        place.is_some()
            && p.place() == place
            && runtime::guard_ready(p, &token)
            && !p.disabled()
            && !p.runtime.join("eww-widgets-editing").exists()
    };
    let widget_lock = io::Lock::acquire(p.runtime.join("eww-widgets.lock"))?;
    if widget_lock.is_none()
        || anim["palette_animation"] == false
        || anim["when"] == "never"
        || factor <= 0.
        || !stable()
    {
        atomic(path, css.as_bytes())?;
        return Ok(());
    }
    let widgets = runtime::widgets(p)?;
    let active = runtime::active(p).unwrap_or_default();
    let ids = widgets
        .iter()
        .filter(|w| active.get(&w.id) == Some(&format!("rw-{}", w.window)))
        .map(|w| w.id.clone())
        .collect::<Vec<_>>();
    if ids.is_empty() {
        atomic(path, css.as_bytes())?;
        return Ok(());
    }
    let mut owned = Value::Null;
    let result = (|| {
        let ms = animation::scene(p, &widgets, &ids, &anim, false, factor, true)?;
        owned = io::read(p.runtime.join("motion.json"));
        let complete = ms == 0 || animation::wait(ms + 80, stable);
        atomic(&path, css.as_bytes())?;
        // Give the GTK main-loop provider time to apply new colors while hidden.
        if complete && animation::wait(120, stable) {
            animation::scene(p, &widgets, &ids, &anim, true, factor, true)?;
            owned = Value::Null;
        }
        Ok::<_, anyhow::Error>(())
    })();
    if !owned.is_null() {
        // Cancellation/failure must not strand globals hidden. Never replace a
        // newer motion token or reveal a local on the wrong workspace.
        let latest = p.place();
        let controls = io::read(p.runtime.join("motion.json"));
        let still_active = runtime::active(p).unwrap_or_default();
        let restore = widgets
            .iter()
            .filter(|w| {
                ids.contains(&w.id)
                    && still_active.contains_key(&w.id)
                    && controls[&w.id]["token"] == owned[&w.id]["token"]
                    && (latest == place
                        || runtime::global(w)
                            && latest
                                .as_ref()
                                .zip(place.as_ref())
                                .is_some_and(|(a, b)| a[0] == b[0]))
            })
            .map(|w| w.id.clone())
            .collect::<Vec<_>>();
        motion::set(p, &restore, true, "none", 0)?;
    }
    result
}

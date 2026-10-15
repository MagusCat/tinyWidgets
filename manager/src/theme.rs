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

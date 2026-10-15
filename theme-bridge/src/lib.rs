//! A CSS-only provider inside this profile's Eww GTK process. No window lifecycle calls.
use std::{
    ffi::{c_char, c_void, CStr, CString},
    path::PathBuf,
    sync::{Mutex, OnceLock},
    time::SystemTime,
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
        s: *const c_char,
        n: isize,
        e: *mut *mut GError,
    ) -> i32;
    fn gtk_style_context_add_provider_for_screen(s: *mut c_void, p: *mut c_void, priority: u32);
    fn gtk_style_context_remove_provider_for_screen(s: *mut c_void, p: *mut c_void);
}
#[link(name = "gdk-3")]
extern "C" {
    fn gdk_screen_get_default() -> *mut c_void;
}
#[link(name = "gobject-2.0")]
extern "C" {
    fn g_object_unref(p: *mut c_void);
}
#[link(name = "glib-2.0")]
extern "C" {
    fn g_timeout_add(ms: u32, f: extern "C" fn(*mut c_void) -> i32, data: *mut c_void) -> u32;
    fn g_error_free(e: *mut GError);
}
struct State {
    path: PathBuf,
    stamp: Option<SystemTime>,
    provider: usize,
}
static STATE: OnceLock<Mutex<State>> = OnceLock::new();
extern "C" fn update(_: *mut c_void) -> i32 {
    let _ = std::panic::catch_unwind(|| {
        let Some(lock) = STATE.get() else { return };
        let Ok(mut state) = lock.lock() else { return };
        let stamp = std::fs::metadata(&state.path)
            .and_then(|m| m.modified())
            .ok();
        if stamp.is_none() || stamp == state.stamp {
            return;
        }
        unsafe {
            let screen = gdk_screen_get_default();
            if screen.is_null() {
                return;
            }
            let Ok(css) = std::fs::read_to_string(&state.path) else {
                return;
            };
            let Ok(text) = CString::new(css.as_bytes()) else {
                return;
            };
            let provider = gtk_css_provider_new();
            let mut error = std::ptr::null_mut();
            let ok = gtk_css_provider_load_from_data(
                provider,
                text.as_ptr(),
                css.len() as isize,
                &mut error,
            );
            if ok == 0 || !error.is_null() {
                if !error.is_null() {
                    eprintln!(
                        "randly-theme: {}",
                        CStr::from_ptr((*error).message).to_string_lossy()
                    );
                    g_error_free(error)
                }
                g_object_unref(provider);
                state.stamp = stamp;
                return;
            }
            gtk_style_context_add_provider_for_screen(screen, provider, 601);
            if state.provider != 0 {
                let previous = state.provider as *mut c_void;
                gtk_style_context_remove_provider_for_screen(screen, previous);
                g_object_unref(previous)
            }
            state.provider = provider as usize;
            state.stamp = stamp;
        }
    });
    1
}
extern "C" fn init() {
    let _ = std::panic::catch_unwind(|| {
        if std::env::current_exe()
            .ok()
            .and_then(|p| p.file_name().map(|s| s.to_string_lossy().into_owned()))
            .as_deref()
            != Some("eww")
        {
            return;
        }
        let Some(path) = std::env::var_os("RANDLY_WIDGETS_THEME_CSS") else {
            return;
        };
        if let Some(value) = std::env::var_os("LD_PRELOAD") {
            let filtered = value
                .to_string_lossy()
                .split([' ', ':'])
                .filter(|s| !s.contains("librandly_widget_theme.so"))
                .collect::<Vec<_>>()
                .join(" ");
            if filtered.is_empty() {
                std::env::remove_var("LD_PRELOAD")
            } else {
                std::env::set_var("LD_PRELOAD", filtered)
            }
        }
        let _ = STATE.set(Mutex::new(State {
            path: path.into(),
            stamp: None,
            provider: 0,
        }));
        unsafe {
            g_timeout_add(100, update, std::ptr::null_mut());
        }
    });
}
#[used]
#[cfg_attr(target_os = "linux", link_section = ".init_array")]
static INITIALIZER: extern "C" fn() = init;

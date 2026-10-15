//! Shared scene scheduling: one IPC update, bounded stagger and cancelable waits.
use crate::{
    io::{self, Paths},
    motion,
    runtime::Widget,
};
use anyhow::Result;
use serde_json::Value;
use std::{thread, time::Duration};

pub fn delay(anim: &Value, name: &str, default: u64) -> u64 {
    anim[name].as_u64().unwrap_or(default).min(5000)
}
pub fn enabled(anim: &Value, editing: bool, factor: f64, reloading: bool) -> bool {
    !editing
        && factor > 0.
        && match anim["when"].as_str().unwrap_or("workspace") {
            "never" => false,
            "reload" => reloading,
            _ => true,
        }
}
pub fn workspace_delay(p: &Paths) -> f64 {
    delay(
        &io::read(p.config.join("animation.json")),
        "workspace_delay",
        650,
    ) as f64
        / 1000.
}
pub fn effect(w: &Widget, anim: &Value, out: bool) -> String {
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
pub fn scene(
    p: &Paths,
    widgets: &[Widget],
    ids: &[String],
    anim: &Value,
    reveal: bool,
    factor: f64,
    enabled: bool,
) -> Result<u64> {
    let duration = (delay(
        anim,
        if reveal {
            "duration_in"
        } else {
            "duration_out"
        },
        if reveal { 320 } else { 240 },
    )
    .min(2000) as f64
        * factor.clamp(0., 2.)) as u64;
    let base = if reveal && enabled {
        delay(anim, "delay_in", 180)
    } else {
        0
    };
    let gap = if enabled
        && anim[if reveal { "stagger_in" } else { "stagger_out" }]
            .as_bool()
            .unwrap_or(false)
    {
        delay(anim, "stagger", 20).min(300 / ids.len().saturating_sub(1).max(1) as u64)
    } else {
        0
    };
    let mut lanes = vec![base; anim["max_parallel"].as_u64().unwrap_or(4).clamp(1, 16) as usize];
    let mut requests = Vec::new();
    let mut total = 0;
    for (index, id) in ids.iter().enumerate() {
        let Some(w) = widgets.iter().find(|w| &w.id == id) else {
            continue;
        };
        let effect = if enabled {
            effect(w, anim, !reveal)
        } else {
            "none".into()
        };
        let (ms, delay) = if effect == "none" {
            (0, 0)
        } else {
            let lane = lanes
                .iter()
                .enumerate()
                .min_by_key(|(_, at)| **at)
                .unwrap()
                .0;
            let at = lanes[lane].max(base + index as u64 * gap).min(60000);
            lanes[lane] = at + duration;
            (duration, at)
        };
        total = total.max(ms + delay);
        requests.push(motion::Request {
            ids: vec![id.clone()],
            reveal,
            effect,
            ms,
            delay,
        });
    }
    motion::set_many(p, &requests)?;
    Ok(total)
}
pub fn wait(ms: u64, valid: impl Fn() -> bool) -> bool {
    let until = io::now() + ms as f64 / 1000.;
    while io::now() < until {
        if crate::STOP.load(std::sync::atomic::Ordering::Relaxed) || !valid() {
            return false;
        }
        thread::sleep(Duration::from_millis(40));
    }
    valid()
}

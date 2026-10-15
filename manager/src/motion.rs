use crate::io::{self, Paths};
use anyhow::Result;
use serde_json::{json, Map, Value};
use std::{collections::HashMap, thread, time::Duration};
pub fn set(p: &Paths, ids: &[String], reveal: bool, effect: &str, ms: u64) -> Result<()> {
    let path = p.runtime.join("motion.json");
    let mut state = io::read(&path).as_object().cloned().unwrap_or_default();
    for id in ids {
        state.insert(id.clone(),json!({"token":io::token(),"reveal":reveal,"effect":effect,"ms":ms,"duration":format!("{ms}ms"),"transition":if effect=="none"{"none"}else{"crossfade"}}));
    }
    let v = Value::Object(state);
    let out = p.eww(&["update".into(), format!("wmotion={v}")])?;
    anyhow::ensure!(out.ok, "No se pudo actualizar movimiento: {}", out.err);
    io::write(path, &v)
}
pub fn pose(effect: &str, p: f64) -> Value {
    let p = p.clamp(0., 1.);
    let e = 1. - (1. - p).powi(3);
    let q = 1. - e;
    let (mut sx, mut sy, mut x, mut y, mut rotate) = (1., 1., 0., 0., 0.);
    match effect {
        "zoom" => {
            sx = 0.68 + 0.32 * e;
            sy = sx
        }
        "pop" => {
            sx = if p < 0.62 {
                0.68 + 0.32 * (1. - (1. - p / 0.62).powi(3))
            } else if p < 0.82 {
                1. - 0.025 * ((p - 0.62) / 0.2 * std::f64::consts::FRAC_PI_2).sin()
            } else {
                0.975 + 0.025 * (p - 0.82) / 0.18
            };
            sy = sx
        }
        "vortex" => {
            sx = 0.12 + 0.88 * e;
            sy = sx;
            rotate = -85. * q
        }
        "spin" | "helix" => {
            sx = 0.8 + 0.2 * e;
            sy = sx;
            rotate = -45. * q
        }
        "zap" | "blinds" | "shatter" => {
            sx = 0.025 + 0.975 * ((p - 0.2) / 0.8).max(0.).sqrt();
            sy = 0.025 + 0.975 * (p / 0.4).min(1.)
        }
        "glitch" => {
            x = (p * 73.).sin() * 6. * (1. - p).powi(2);
            y = (p * 43.).sin() * 1.5 * (1. - p).powi(2)
        }
        "float3d" => {
            sx = 0.82 + 0.18 * e;
            sy = 0.6 + 0.4 * e;
            y = 10. * q
        }
        "slide" | "slideup" | "melt" => y = 18. * q,
        "slidedown" => y = -18. * q,
        "slideleft" => x = 18. * q,
        "slideright" => x = -18. * q,
        _ => (),
    };
    if p >= 1. {
        sx = 1.;
        sy = 1.;
        x = 0.;
        y = 0.;
        rotate = 0.
    }
    json!({"sx":format!("{:.0}%",sx*100.),"sy":format!("{:.0}%",sy*100.),"x":format!("{:.0}%",x+(1.-sx)*50.),"y":format!("{:.0}%",y+(1.-sy)*50.),"rotate":(rotate*10000.).round()/10000.})
}
struct State {
    token: Value,
    started: Option<f64>,
    stable: f64,
    signature: Value,
    frozen: Option<Value>,
    shown: bool,
    ready_since: Option<f64>,
}
#[derive(Default)]
pub struct Engine {
    states: HashMap<String, State>,
}
impl Engine {
    pub fn step(
        &mut self,
        controls: &Value,
        data: &Value,
        ready: &Value,
        opts: &Value,
        now: f64,
    ) -> (Value, Value, bool) {
        let mut frames = Map::new();
        let mut freeze = Map::new();
        let mut running = false;
        let Some(items) = data.as_object() else {
            return (json!({}), json!({}), false);
        };
        self.states.retain(|id, _| items.contains_key(id));
        for (id, value) in items {
            let req = &controls[id];
            let token = req["token"].clone();
            let shown = self.states.get(id).is_some_and(|s| s.shown);
            if self.states.get(id).is_none_or(|s| s.token != token) {
                self.states.insert(
                    id.clone(),
                    State {
                        token: token.clone(),
                        started: if !req["reveal"].as_bool().unwrap_or(false) && shown {
                            Some(now)
                        } else {
                            None
                        },
                        stable: now,
                        signature: Value::Null,
                        frozen: None,
                        shown,
                        ready_since: None,
                    },
                );
            }
            let state = self.states.get_mut(id).unwrap();
            let reveal = req["reveal"].as_bool().unwrap_or(false);
            let ms = req["ms"].as_u64().unwrap_or(0);
            let effect = req["effect"].as_str().unwrap_or("none");
            let mode = opts[id]["motion_mode"].as_str().unwrap_or("stable");
            let duration = if effect == "none" {
                0.
            } else {
                ms as f64 / 1000.
            };
            let mut waiting = false;
            if reveal && ready[id].as_bool().unwrap_or(false) {
                if state.started.is_none() {
                    let since = *state.ready_since.get_or_insert(now);
                    if state.signature != *value {
                        state.signature = value.clone();
                        state.stable = now
                    }
                    waiting = duration > 0.
                        && mode == "stable"
                        && now - state.stable < 0.06
                        && now - since < 0.24;
                    if !waiting {
                        state.started = Some(now);
                        state.frozen = Some(value.clone())
                    }
                }
            } else if reveal {
                waiting = true
            }
            let mut frame;
            if (!reveal && state.started.is_none()) || waiting {
                frame = pose(
                    if waiting { "zoom" } else { "none" },
                    if waiting { 0. } else { 1. },
                );
                frame["show"] = json!(false);
                frame["fade_duration"] = json!("0ms");
                running |= waiting && ready[id].as_bool().unwrap_or(false)
            } else {
                let progress = if duration > 0. {
                    ((now - state.started.unwrap_or(now)) / duration).clamp(0., 1.)
                } else {
                    1.
                };
                frame = if reveal {
                    if mode == "staged" && effect != "none" {
                        let expand = ((progress - 0.3) / 0.7).max(0.);
                        if effect == "fade" {
                            pose("zoom", 0.4 + 0.6 * expand)
                        } else {
                            pose(effect, expand)
                        }
                    } else {
                        pose(effect, progress)
                    }
                } else {
                    pose(effect, 1. - progress)
                };
                frame["show"] = json!(reveal);
                frame["fade_duration"] = json!(format!(
                    "{:.0}ms",
                    if duration > 0. {
                        ms as f64 * if mode == "staged" && reveal { 0.3 } else { 1. }
                    } else {
                        0.
                    }
                ));
                state.shown = reveal;
                running |= progress < 1.;
                if progress >= 1. {
                    state.frozen = None
                }
            }
            frame["token"] = token;
            frames.insert(id.clone(), frame);
            if let Some(frozen) = &state.frozen {
                freeze.insert(id.clone(), json!({"token":state.token,"data":frozen}));
            }
        }
        (Value::Object(frames), Value::Object(freeze), running)
    }
}
pub fn stream(p: &Paths) -> Result<()> {
    use std::io::Write;
    let mut engine = Engine::default();
    let (mut stamp, mut control_stamp) = (None, None);
    let (mut snapshot, mut controls) = (json!({}), json!({}));
    let (mut last, mut last_freeze) = (Value::Null, Value::Null);
    let mut running = true;
    loop {
        if crate::STOP.load(std::sync::atomic::Ordering::Relaxed) || unsafe { libc::getppid() } == 1
        {
            return Ok(());
        }
        let a = io::stamp(p.runtime.join("data-snapshot.json"));
        let b = io::stamp(p.runtime.join("motion.json"));
        if a != stamp || b != control_stamp || running {
            if a != stamp {
                snapshot = io::read(p.runtime.join("data-snapshot.json"));
                stamp = a
            }
            if b != control_stamp {
                controls = io::read(p.runtime.join("motion.json"));
                control_stamp = b
            }
            let (frames, freeze, active) = engine.step(
                &controls,
                &snapshot["g"],
                &snapshot["r"],
                &snapshot["o"],
                io::now(),
            );
            running = active;
            if freeze != last_freeze {
                io::write(p.runtime.join("motion-freeze.json"), &freeze)?;
                last_freeze = freeze
            }
            if frames != last {
                let mut out = std::io::stdout().lock();
                if writeln!(out, "{frames}").is_err() {
                    return Ok(());
                }
                out.flush()?;
                last = frames
            }
        }
        thread::sleep(Duration::from_millis(if running { 33 } else { 50 }));
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn idle_identity() {
        for effect in ["zoom", "zap", "vortex", "glitch", "slide"] {
            assert_eq!(
                pose(effect, 1.),
                json!({"sx":"100%","sy":"100%","x":"0%","y":"0%","rotate":0.0})
            )
        }
    }
    #[test]
    fn native_wait_and_freeze() {
        let mut e = Engine::default();
        let control = json!({"a":{"token":"1","effect":"zoom","reveal":true,"ms":400}});
        let ready = json!({"a":true});
        assert_eq!(
            e.step(&control, &json!({"a":{"n":1}}), &ready, &json!({}), 0.)
                .0["a"]["show"],
            false
        );
        assert_eq!(
            e.step(&control, &json!({"a":{"n":1}}), &ready, &json!({}), 0.061)
                .0["a"]["show"],
            true
        );
        assert_eq!(
            e.step(&control, &json!({"a":{"n":2}}), &ready, &json!({}), 0.1)
                .1["a"]["data"]["n"],
            1
        );
        assert_eq!(
            e.step(&control, &json!({"a":{"n":2}}), &ready, &json!({}), 0.6)
                .1,
            json!({})
        );
    }
}

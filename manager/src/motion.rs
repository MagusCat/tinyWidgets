use crate::io::{self, Paths};
use anyhow::Result;
use serde_json::{json, Map, Value};
use std::{collections::HashMap, thread, time::Duration};
pub struct Request {
    pub ids: Vec<String>,
    pub reveal: bool,
    pub effect: String,
    pub ms: u64,
    pub delay: u64,
}
pub fn set(p: &Paths, ids: &[String], reveal: bool, effect: &str, ms: u64) -> Result<()> {
    set_many(
        p,
        &[Request {
            ids: ids.to_vec(),
            reveal,
            effect: effect.into(),
            ms,
            delay: 0,
        }],
    )
}
pub fn set_many(p: &Paths, requests: &[Request]) -> Result<()> {
    if requests.iter().all(|r| r.ids.is_empty()) {
        return Ok(());
    }
    let path = p.runtime.join("motion.json");
    let mut state = io::read(&path).as_object().cloned().unwrap_or_default();
    let config = io::read(p.config.join("instances.json"));
    if let Some(widgets) = config["widgets"].as_array() {
        let ids = widgets
            .iter()
            .filter_map(|w| w["id"].as_str())
            .collect::<std::collections::HashSet<_>>();
        state.retain(|id, _| ids.contains(id.as_str()));
    }
    for req in requests {
        for id in &req.ids {
            state.insert(id.clone(),json!({"token":io::token(),"reveal":req.reveal,"effect":req.effect,"ms":req.ms,"delay_ms":req.delay,"duration":format!("{}ms",req.ms),"transition":if req.effect=="none"{"none"}else{"crossfade"}}));
        }
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
    issued: f64,
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
    max_parallel: Option<usize>,
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
        let limit = self.max_parallel.unwrap_or(4);
        let mut in_flight = self
            .states
            .iter()
            .filter(|(id, state)| {
                let req = &controls[*id];
                state.token == req["token"]
                    && req["reveal"] == true
                    && state.started.is_some_and(|at| {
                        now >= at && now - at < req["ms"].as_u64().unwrap_or(0) as f64 / 1000.
                    })
            })
            .count();
        for (id, value) in items {
            let req = &controls[id];
            let token = req["token"].clone();
            let shown = self.states.get(id).is_some_and(|s| s.shown);
            if self.states.get(id).is_none_or(|s| s.token != token) {
                self.states.insert(
                    id.clone(),
                    State {
                        token: token.clone(),
                        issued: now,
                        started: if !req["reveal"].as_bool().unwrap_or(false) && shown {
                            Some(
                                now + req["delay_ms"].as_u64().unwrap_or(0).min(60000) as f64
                                    / 1000.,
                            )
                        } else {
                            None
                        },
                        stable: now,
                        signature: Value::Null,
                        frozen: if !req["reveal"].as_bool().unwrap_or(false) && shown {
                            Some(value.clone())
                        } else {
                            None
                        },
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
                    waiting = now - state.issued
                        < req["delay_ms"].as_u64().unwrap_or(0).min(60000) as f64 / 1000.
                        || duration > 0.
                            && mode == "stable"
                            && now - state.stable < 0.06
                            && now - since < 0.24;
                    waiting |= duration > 0. && in_flight >= limit;
                    if !waiting {
                        if duration > 0. {
                            in_flight += 1;
                        }
                        state.started = Some(now);
                        state.frozen = Some(value.clone())
                    }
                }
            } else if reveal {
                waiting = true
            }
            if !reveal && state.started.is_some_and(|start| start > now) {
                let mut frame = pose("none", 1.);
                frame["show"] = json!(true);
                frame["fade_duration"] = json!("0ms");
                frame["token"] = token;
                frames.insert(id.clone(), frame);
                if let Some(frozen) = &state.frozen {
                    freeze.insert(id.clone(), json!({"token":state.token,"data":frozen}));
                }
                running = true;
                continue;
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
    let (mut applied_stamp, mut settings_stamp) = (None, None);
    let (mut applied, mut settings) = (Value::Null, Value::Null);
    let mut visible = Value::Null;
    loop {
        if crate::STOP.load(std::sync::atomic::Ordering::Relaxed) || unsafe { libc::getppid() } == 1
        {
            return Ok(());
        }
        let a = io::stamp(p.runtime.join("data-snapshot.json"));
        let b = io::stamp(p.runtime.join("motion.json"));
        let c = io::stamp(p.runtime.join("eww-widgets-applied.json"));
        let d = io::stamp(p.config.join("animation.json"));
        if d != settings_stamp {
            settings = io::read(p.config.join("animation.json"));
            settings_stamp = d;
        }
        if a != stamp || b != control_stamp || c != applied_stamp || running {
            let changed = a != stamp || c != applied_stamp;
            if c != applied_stamp {
                applied = io::read(p.runtime.join("eww-widgets-applied.json"));
                applied_stamp = c;
            }
            if a != stamp {
                snapshot = io::read(p.runtime.join("data-snapshot.json"));
                stamp = a
            }
            if b != control_stamp {
                controls = io::read(p.runtime.join("motion.json"));
                control_stamp = b
            }
            engine.max_parallel =
                Some(settings["max_parallel"].as_u64().unwrap_or(4).clamp(1, 16) as usize);
            if changed {
                visible = snapshot["g"]
                    .as_object()
                    .map(|data| {
                        Value::Object(
                            data.iter()
                                .filter(|(id, _)| {
                                    !applied.is_object() || applied.get(*id).is_some()
                                })
                                .map(|(id, value)| (id.clone(), value.clone()))
                                .collect(),
                        )
                    })
                    .unwrap_or(json!({}));
            }
            let (frames, freeze, active) = engine.step(
                &controls,
                &visible,
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
        thread::sleep(Duration::from_millis(if running {
            1000 / settings["fps"].as_u64().unwrap_or(24).clamp(12, 30)
        } else {
            100
        }));
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
    #[test]
    fn entry_dead_time_and_scheduled_exit_keep_their_frames() {
        let mut e = Engine::default();
        let data = json!({"a":{"value":1}});
        let ready = json!({"a":true});
        let opts = json!({"a":{"motion_mode":"staged"}});
        let enter =
            json!({"a":{"token":"one","reveal":true,"effect":"zoom","ms":120,"delay_ms":180}});
        assert_eq!(
            e.step(&enter, &data, &ready, &opts, 0.).0["a"]["show"],
            false
        );
        assert_eq!(
            e.step(&enter, &data, &ready, &opts, 0.17).0["a"]["show"],
            false
        );
        assert_eq!(
            e.step(&enter, &data, &ready, &opts, 0.18).0["a"]["show"],
            true
        );
        let out =
            json!({"a":{"token":"two","reveal":false,"effect":"zoom","ms":120,"delay_ms":100}});
        assert_eq!(e.step(&out, &data, &ready, &opts, 1.).0["a"]["show"], true);
        assert_eq!(
            e.step(&out, &data, &ready, &opts, 1.08).0["a"]["show"],
            true
        );
        assert_eq!(
            e.step(&out, &data, &ready, &opts, 1.11).0["a"]["show"],
            false
        );
    }
    #[test]
    fn providers_becoming_ready_together_cannot_exceed_motion_budget() {
        let mut e = Engine::default();
        e.max_parallel = Some(3);
        let mut controls = Map::new();
        let mut data = Map::new();
        let mut ready = Map::new();
        let mut opts = Map::new();
        for n in 0..100 {
            let id = format!("w{n}");
            controls.insert(
                id.clone(),
                json!({"token":id,"reveal":true,"effect":"zoom","ms":120,"delay_ms":0}),
            );
            data.insert(id.clone(), json!({}));
            ready.insert(id.clone(), json!(false));
            opts.insert(id, json!({"motion_mode":"staged"}));
        }
        let controls = Value::Object(controls);
        let data = Value::Object(data);
        let opts = Value::Object(opts);
        e.step(&controls, &data, &Value::Object(ready.clone()), &opts, 0.);
        for v in ready.values_mut() {
            *v = json!(true);
        }
        for frame in 0..20 {
            let now = 10. + frame as f64 * 0.04;
            e.step(&controls, &data, &Value::Object(ready.clone()), &opts, now);
            let active = e
                .states
                .values()
                .filter(|s| s.started.is_some_and(|at| now - at < 0.12))
                .count();
            assert!(active <= 3, "{active} simultaneous animations");
        }
    }
}

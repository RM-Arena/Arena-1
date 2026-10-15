use rmuc_sim::{config, Engine};
use serde_json::{json, Value};
use std::io::{self, BufRead, Write};

fn main() {
    let mut engine: Option<Engine> = None;
    let stdin = io::stdin();
    let mut stdout = io::BufWriter::new(io::stdout());
    for line in stdin.lock().lines() {
        let Ok(line) = line else {
            break;
        };
        let response = (|| -> Result<Value, String> {
            let request: Value = serde_json::from_str(&line).map_err(|e| e.to_string())?;
            let op = request["op"].as_str().ok_or("missing op")?;
            if op == "config" {
                let c = config();
                return Ok(
                    json!({"specs":c.specs,"maps":c.maps,"dt":rmuc_sim::DT,"engine":"rust","version":"0.2.0"}),
                );
            }
            if op == "init" {
                engine = Some(Engine::new(
                    request["seed"].as_i64().ok_or("seed must be i64")?,
                    request["duration"].as_f64().ok_or("duration required")?,
                    request["map"].as_str().ok_or("map required")?,
                )?);
                return Ok(engine.as_ref().unwrap().snapshot());
            }
            let e = engine.as_mut().ok_or("engine not initialized")?;
            match op {
                "step" => Ok(e.step(&request["commands"])),
                "snapshot" => Ok(e.snapshot()),
                "digest" => Ok(json!({"digest":e.digest()})),
                "observation" => {
                    let team = request["team"]
                        .as_str()
                        .filter(|t| ["red", "blue"].contains(t))
                        .ok_or("invalid team")?;
                    let slots: Option<Vec<u32>> =
                        request.get("slots").and_then(Value::as_array).map(|s| {
                            s.iter()
                                .filter_map(|n| n.as_u64().map(|n| n as u32))
                                .collect()
                        });
                    Ok(e.observation(team, slots.as_deref()))
                }
                "finish" => {
                    e.finish(
                        request["winner"].as_str().map(str::to_owned),
                        request["reason"].as_str().unwrap_or("stopped"),
                    );
                    Ok(e.snapshot())
                }
                _ => Err("unknown op".into()),
            }
        })();
        let value = response.unwrap_or_else(|error| json!({"error":error}));
        if serde_json::to_writer(&mut stdout, &value).is_err() {
            break;
        }
        if writeln!(&mut stdout).is_err() || stdout.flush().is_err() {
            break;
        }
    }
}

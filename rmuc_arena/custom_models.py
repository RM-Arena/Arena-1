"""User-uploaded robot appearances.

An appearance is a self-contained GLB shown in place of one hardware model. The engine still simulates the base model,
so physics, armour and rules are unchanged; the viewer scales the mesh to the base model's stowed envelope.
"""
import json
import re
import secrets
import struct
import threading
import time
from pathlib import Path

from .models import robot_models

MODEL_LIMIT = 24 * 1024 * 1024
FORWARD_AXES = ("+x", "-x", "+z", "-z")
# Loaders for these need decoders the viewer does not ship.
UNSUPPORTED = {"KHR_draco_mesh_compression", "EXT_meshopt_compression", "KHR_texture_basisu", "EXT_texture_webp", "EXT_texture_avif"}
ID = re.compile(r"^[a-f0-9]{12}$")


def inspect_glb(data):
    """Check a binary glTF 2.0 file is complete and self-contained; return mesh and triangle counts."""
    if len(data) > MODEL_LIMIT:
        raise ValueError(f"Model must be at most {MODEL_LIMIT // (1024 * 1024)} MiB")
    if len(data) < 20 or data[:4] != b"glTF":
        raise ValueError("Upload a binary glTF (.glb) file")
    version, length = struct.unpack_from("<II", data, 4)
    if version != 2 or length != len(data):
        raise ValueError("Only complete glTF 2.0 .glb files are supported")
    chunk_length, chunk_type = struct.unpack_from("<II", data, 12)
    if chunk_type != 0x4E4F534A or 20 + chunk_length > len(data):
        raise ValueError("The .glb file has no JSON chunk")
    try:
        gltf = json.loads(data[20:20 + chunk_length].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError("The .glb JSON chunk is invalid") from error
    if not isinstance(gltf, dict) or str(gltf.get("asset", {}).get("version", "")) != "2.0":
        raise ValueError("Only glTF 2.0 models are supported")
    blocked = UNSUPPORTED & set(gltf.get("extensionsUsed", []) or [])
    if blocked:
        raise ValueError(f"Compressed or unusual extensions are not supported: {', '.join(sorted(blocked))}")
    # Everything must be embedded: an external URI would make the viewer fetch other files.
    for kind in ("buffers", "images"):
        for item in gltf.get(kind, []) or []:
            uri = item.get("uri") if isinstance(item, dict) else None
            if uri is not None and not (kind == "images" and str(uri).startswith("data:image/")):
                raise ValueError("Embed all buffers and textures in the .glb (no external files)")
    meshes = gltf.get("meshes") or []
    if not meshes:
        raise ValueError("The model contains no meshes")
    accessors = gltf.get("accessors") or []
    triangles = 0
    for mesh in meshes:
        for primitive in mesh.get("primitives", []) or []:
            index = primitive.get("indices", primitive.get("attributes", {}).get("POSITION"))
            if isinstance(index, int) and 0 <= index < len(accessors):
                triangles += int(accessors[index].get("count", 0)) // 3
    if triangles > 600_000:
        raise ValueError("Model is too detailed (more than 600k triangles)")
    return {"meshes": len(meshes), "triangles": triangles}


class CustomModels:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.registry = self.directory / "models.json"
        self.lock = threading.RLock()

    def _records(self):
        return json.loads(self.registry.read_text(encoding="utf-8")) if self.registry.exists() else {}

    def _write(self, records):
        from .submissions import write_json
        self.directory.mkdir(parents=True, exist_ok=True)
        write_json(self.registry, records)

    @staticmethod
    def asset(record):
        # The fit envelope and forward axis travel in the URL, so replays render without the registry.
        size = robot_models()[str(record["base_model"])]["stowed_m"]
        fit = ",".join(f"{v:g}" for v in size)
        return f"/api/custom-models/{record['id']}.glb?fit={fit}&fwd={record['forward']}"

    def public(self, record):
        design = robot_models().get(str(record["base_model"]), {})
        return {**record, "asset": self.asset(record), "role": design.get("role"), "base_name": design.get("name")}

    def list(self):
        with self.lock:
            return [self.public(r) for r in sorted(self._records().values(), key=lambda r: -r["created_at"])]

    def get(self, model_id):
        with self.lock:
            record = self._records().get(model_id) if ID.match(model_id or "") else None
            return self.public(record) if record else None

    def path(self, model_id):
        return self.directory / f"{model_id}.glb" if ID.match(model_id or "") else None

    def create(self, name, base_model, forward, data, author=None):
        name = (name or "").strip()
        if not 1 <= len(name) <= 40:
            raise ValueError("Name the model in 1 to 40 characters")
        if str(base_model) not in robot_models():
            raise ValueError("Choose the hardware model this appearance replaces")
        if forward not in FORWARD_AXES:
            raise ValueError("Forward axis must be +x, -x, +z or -z")
        if author is not None and len(author.strip()) > 40:
            raise ValueError("Author must be at most 40 characters")
        info = inspect_glb(data)
        record = {"id": secrets.token_hex(6), "name": name, "base_model": int(base_model), "forward": forward,
                  "bytes": len(data), **info, "created_at": time.time(), **({"author": author.strip()} if author and author.strip() else {})}
        with self.lock:
            self.directory.mkdir(parents=True, exist_ok=True)
            temporary = self.directory / f".{record['id']}.tmp"
            temporary.write_bytes(data)
            temporary.replace(self.directory / f"{record['id']}.glb")
            records = self._records()
            records[record["id"]] = record
            self._write(records)
        return self.public(record)

    def delete(self, model_id):
        with self.lock:
            records = self._records()
            if model_id not in records:
                return False
            del records[model_id]
            self._write(records)
            self.path(model_id).unlink(missing_ok=True)
            return True

    def resolve(self, team, choices, models):
        """Validate {model number: appearance id} for one team; models is the set of hardware models it fields."""
        skins = {}
        with self.lock:
            records = self._records()
        for model, model_id in (choices or {}).items():
            record = records.get(model_id)
            if not record:
                raise ValueError(f"{'红' if team == 'red' else '蓝'}方选择的机器人外观已被删除")
            if str(record["base_model"]) != str(model) or int(model) not in models:
                raise ValueError(f"外观「{record['name']}」只适用于 {record['base_model']} 型，且该型号必须上场")
            skins[str(model)] = {"id": record["id"], "name": record["name"], "base_model": record["base_model"],
                                 "forward": record["forward"], "asset": self.asset(record)}
        return skins

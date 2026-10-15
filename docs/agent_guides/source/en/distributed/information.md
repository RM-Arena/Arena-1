## Information and Control

During development you edit six strategies. During a match each process mounts only its own source (named `strategy.py` in the container). The sources cannot import each other; module globals and `state` are private. Each `controlled_ids` contains just its own slot. Returning another slot disables that process, while the other five continue.

Vision comes only from the controlled robot. `enemies` does not automatically combine teammate vision; the full public state of your six robots, your economy and referee information remain available. A deployed hero, inactive aerial robot or dead robot has no own vision. Teammates may explicitly send intelligence and intentions through `messages`; these are previous-round policy reports, not engine-verified current observations.

Ground cameras have a {{ground_fov_horizontal}}° horizontal and {{ground_fov_vertical}}° vertical field of view following the actual muzzle direction, with existing range and occlusion limits. Aerial coverage is unchanged. All own positions and referee information remain readable.

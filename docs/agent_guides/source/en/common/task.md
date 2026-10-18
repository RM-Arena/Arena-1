## Task and Constraints

### Deliverable

You deliver only {{source_files}}. It must define `act(observation, state)` and return `(actions, new_state)`. See "Interface Reference" for how it is called and what the data looks like.

### Development Time

- The default development time is **90 minutes**, started by the organizer. Reading, planning, coding, practice, waiting for results and submitting all share one continuous window.
- `python3 -B arena.py status` shows the remaining time as recorded by the host. Before the clock starts, the tool tells you to wait for the organizer; you cannot practice or submit yet.
- Until the deadline you may edit, practice and submit as often as you like. **Your last successful submission before the deadline is your entry**; with no successful submission you have no entry.
- After the deadline, new practice runs and submissions are refused and running practice is stopped. Editing files after the deadline does not change what you submitted.
- The 90-minute development clock and the 420 s match clock are unrelated.

### Files and Permissions

**Edit only {{source_files}}.** Every other file in the workspace is a protected reference or tool; changing or deleting one, or adding new files, makes practice and submission fail. The one exception is the `practice/` directory: keep practice scripts, notes, logs and replays there. Those files never reach the match environment, so {{source_files}} must not depend on them.

| File | Purpose |
| --- | --- |
| {{source_files}} | {{^distributed}}Your strategy — the only editable file{{/distributed}}{{#distributed}}Your {{count_sources}} editable strategy source files{{/distributed}} |
| `AGENT_GUIDE.md`, `AGENT_GUIDE.en.md` | This guide in Chinese and in English, with identical content |
| `AGENT_TASK.md` | Task summary |
| `sdk.py` | Helper library you can `import` during a match |
| `arena.json` | Full map, rule parameters and robot designs |
| `agent.json` | Your entry details and practice credentials |
| `arena.py` | Practice and submission tool |
| `practice/` | Free-to-write directory for practice output |

Do not read, or try to obtain, other participants' code, private state, submissions or logs.

### Runtime Environment and Limits

During a match your program runs in its own container, {{^distributed}}which holds only your `strategy.py`{{/distributed}}{{#distributed}}each holding only its own `strategy.py`{{/distributed}}:

- Python 3.12, with the standard library and `sdk.py` only;
- no network, read-only root file system, non-root user; a single process that may not start threads or subprocesses;
- 1 GiB of memory and 1 CPU core;
- source code of at most 512 KiB;
- **200 ms** per decision; importing the module and global initialization do not count toward that limit but must finish within 60 s;
- at most 16 KiB of actions per decision and 1 KiB per robot;
- `new_state` must be JSON-serializable and at most 256 KiB.

A single decision timeout skips that round's actions while retaining the program and its private state. Late actions are discarded; subsequent decisions use fresh observations. Each round still has a 200 ms wall-clock budget, including any wait for the previous response. A successful fresh decision resets the consecutive-timeout count. All policy errors, including recovered timeouts, remain in the replay and exclude the match from Elo rating.

Any of the following **disables your program for the rest of the match** — the match goes on, but the robots controlled by that process receive no further commands:

- three consecutive decision rounds time out, or `act` raises an exception;
- the return value is malformed, or an action contains an unsupported field or a non-finite number (NaN, Infinity);
- you try to control a robot that is not yours;
- you exceed one of the size limits above.

So catch exceptions inside `act` and check your worst-case decision time in practice. Practice games use the same container and limits as real matches. Output from `print` goes to the error log and is returned with practice results only when your program fails.

"""Read-only CLI catalogs and immutable strategy snapshots for parallel jobs."""
from .strategy_sources import bundled_examples, bundled_manifests
import hashlib
import json
from pathlib import Path
import shutil

from .paths import ROOT, data_path
from . import seasons
from .showcase import load_profile, load_showcase
from .strategy_names import canonical_key
from .submissions import load_submission, manifest_season


def strategy_index():
    choices = {}
    locations = [('bundled', bundled_manifests())]
    from .strategy_library import StrategyLibrary
    library = StrategyLibrary(data_path('.arena_data/strategy-library'), enabled=False)
    locations += [('remote', library.paths()), ('local', sorted(data_path('submissions').glob('*/manifest.json')))]
    for source, paths in locations:
        for path in paths:
            try:
                manifest, _ = load_submission(path.parent)
                if manifest.get('api_version') != 3 or manifest.get('rules_profile') not in seasons.profiles():
                    continue
                key = canonical_key(path.parent.name)
                if source == 'local' and key in choices:
                    key = 'submission-' + key
                choices[key] = {'key': key, 'source': source, 'path': path.parent.resolve(),
                                'season': manifest_season(manifest), 'mode': manifest['mode'],
                                'version': manifest['version'], 'robot': manifest.get('robot'),
                                'team_lineup': manifest.get('team_lineup'),
                                'profile': load_profile(path.parent, bundled=source != 'local')}
            except (ValueError, OSError, KeyError):
                continue
    return choices


def resolve_strategy(value, index=None):
    path = Path(value).expanduser()
    if path.is_dir():
        load_submission(path)
        return path.resolve()
    index = strategy_index() if index is None else index
    key = canonical_key(str(value))
    source, separator, name = str(value).partition(':')
    if separator and source in ('bundled', 'remote', 'local'):
        key = canonical_key(name)
        if source == 'bundled':
            path = (ROOT/'examples' if key=='gpt61_sol_max_2027' else bundled_examples())/key
        elif source == 'local':
            path = data_path('submissions')/key
        else:
            found = next((v['path'] for v in index.values() if v['source'] == source and v['path'].name == key), None)
            if found is None:
                raise ValueError(f'Unknown cached strategy: {value}')
            path = found
        load_submission(path)
        return path.resolve()
    if key not in index:
        raise ValueError(f'Unknown strategy: {value}; use strategies list or supply a submission directory')
    return index[key]['path']


def describe_strategy(path):
    manifest, _ = load_submission(path)
    return {'path': str(path), 'manifest': manifest, 'profile': load_profile(path), 'showcase': load_showcase(path)}


class StrategySnapshots:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.entries = {}

    def freeze(self, source):
        source = Path(source).resolve()
        if source in self.entries:
            return self.entries[source]
        manifest, _ = load_submission(source)
        identity = hashlib.sha256((str(source) + ':' + manifest['version']).encode()).hexdigest()[:24]
        target = self.directory/identity/source.name
        target.mkdir(parents=True)
        for name in {'manifest.json', *manifest['entries'].values(), 'profile.json', 'showcase.json'}:
            path = source/name
            if path.is_file():
                if path.is_symlink():
                    raise ValueError(f'Strategy snapshot refuses symlinks: {path}')
                shutil.copyfile(path, target/name)
        load_submission(target)
        self.entries[source] = target
        return target

    def metadata(self):
        return [{'path': str(source), 'name': source.name,
                 'version': load_submission(frozen)[0]['version']}
                for source, frozen in sorted(self.entries.items(), key=lambda item: str(item[0]))]

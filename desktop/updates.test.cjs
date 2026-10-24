const test = require('node:test');
const assert = require('node:assert/strict');
const {AppUpdates, compareVersions, findUpdate, fetchReleases, RELEASES_URL, API_URL, STARTUP_DELAY, CHECK_INTERVAL} = require('./updates.cjs');

function release(version = '0.7.2-beta.10', overrides = {}) {
  const tag = `v${version}`;
  return {tag_name: tag, draft: false, prerelease: true, published_at: '2026-10-24T20:00:00Z',
    assets: ['mac-arm64.dmg', 'mac-x64.dmg', 'win-x64.exe', 'linux-amd64.deb', 'linux-x86_64.AppImage'].map(suffix => {
      const name = `Arena-1-${version}-${suffix}`;
      return {name, state: 'uploaded', size: 1024, browser_download_url: `${RELEASES_URL}/download/${tag}/${name}`};
    }), ...overrides};
}

const response = releases => new Response(JSON.stringify(releases), {status: 200});

function harness(options = {}) {
  const dialogs = [], opened = [], transitions = [], requests = [];
  const updater = new AppUpdates({version: '0.7.2-beta.2', platform: 'darwin', arch: 'arm64',
    fetch: async (...args) => { requests.push(args); return response([release()]); },
    showMessageBox: async options => { dialogs.push(options); return {response: options.cancelId ?? 0}; },
    openExternal: async url => { opened.push(url); },
    onCheckingChange: value => transitions.push(value), ...options});
  return {updater, dialogs, opened, transitions, requests};
}

test('SemVer orders beta numbers, stable releases, identifiers, and build metadata', () => {
  for (const [a, b] of [['0.7.2-beta.2', '0.7.2-beta.10'], ['0.7.2-beta.10', '0.7.2-rc.1'],
    ['0.7.2-rc.1', '0.7.2'], ['0.7.2', '0.8.0-beta.1'], ['0.7.2-beta.1', '0.7.2-beta.1.1'],
    ['0.7.2-1', '0.7.2-beta'], ['0.7.2-beta', '0.7.2-rc']]) {
    assert.equal(compareVersions(a, b), -1, `${a} < ${b}`);
    assert.equal(compareVersions(b, a), 1, `${b} > ${a}`);
  }
  assert.equal(compareVersions('v0.7.2-beta.2+build.1', '0.7.2-beta.2+build.2'), 0);
  for (const value of [null, 'latest', '0.7', '0.07.2', '0.7.2-beta.02', '0.7.2-', '0.7.2+']) {
    assert.throws(() => compareVersions(value, '0.7.2'));
  }
});

test('finds the greatest published version including Beta, ignoring drafts and malformed tags', () => {
  const update = findUpdate([release('0.7.2-beta.3'), release('0.7.2-beta.100', {draft: true}),
    release('0.7.2-beta.10'), release('nightly'), release('0.9.0', {published_at: null})], '0.7.2-beta.2');
  assert.equal(update.version, '0.7.2-beta.10');
  assert.equal(update.releaseUrl, `${RELEASES_URL}/tag/v0.7.2-beta.10`);
  assert.equal(findUpdate([release('0.7.2-beta.2')], '0.7.2-beta.2'), null);
  assert.equal(findUpdate([release('0.7.2-beta.2')], '0.7.2'), null);
  assert.equal(findUpdate([release('0.7.2')], '0.8.0-beta.1'), null);
  assert.throws(() => findUpdate([], '0.7.2-beta.2'));
});

test('download links select the native macOS, Windows, DEB, or AppImage installer', () => {
  for (const [platform, arch, appImage, suffix] of [['darwin', 'arm64', false, 'mac-arm64.dmg'],
    ['darwin', 'x64', false, 'mac-x64.dmg'], ['win32', 'x64', false, 'win-x64.exe'],
    ['linux', 'x64', false, 'linux-amd64.deb'], ['linux', 'x64', true, 'linux-x86_64.AppImage']]) {
    const update = findUpdate([release()], '0.7.2-beta.2', {platform, arch, appImage});
    assert.equal(update.downloadUrl, `${RELEASES_URL}/download/v0.7.2-beta.10/Arena-1-0.7.2-beta.10-${suffix}`);
  }
});

test('missing, unfinished, or untrusted installers fall back to the repository release page', () => {
  for (const assets of [[], [{...release().assets[0], browser_download_url: 'https://example.com/setup.dmg'}],
    [{...release().assets[0], state: 'new'}], [{...release().assets[0], size: 0}]]) {
    const update = findUpdate([release(undefined, {assets, html_url: 'file:///tmp/setup'})], '0.7.2-beta.2', {platform: 'darwin', arch: 'arm64'});
    assert.equal(update.downloadUrl, null);
    assert.equal(update.releaseUrl, `${RELEASES_URL}/tag/v0.7.2-beta.10`);
  }
  assert.equal(findUpdate([release()], '0.7.2-beta.2', {platform: 'win32', arch: 'arm64'}).downloadUrl, null);
});

test('release request includes prereleases, timeout/cancellation, and requires no GitHub credentials', async () => {
  let request;
  const releases = await fetchReleases(async (...args) => { request = args; return response([release()]); }, '0.7.2-beta.2');
  assert.equal(releases[0].tag_name, 'v0.7.2-beta.10');
  assert.equal(request[0], API_URL);
  assert.equal(request[1].headers['User-Agent'], 'Arena-1/0.7.2-beta.2');
  assert.equal(request[1].headers.Authorization, undefined);
  assert.ok(request[1].signal instanceof AbortSignal);
  await assert.rejects(fetchReleases(async () => new Response('', {status: 403}), '0.7.2-beta.2'), /HTTP 403/);
  await assert.rejects(fetchReleases(async () => response({message: 'error'}), '0.7.2-beta.2'), /Invalid release response/);
});

test('automatic checks notify once per version per session while manual checks can reopen the prompt', async () => {
  const {updater, dialogs, transitions} = harness();
  await updater.check();
  await updater.check();
  assert.equal(dialogs.length, 1);
  assert.match(dialogs[0].message, /0.7.2-beta.10/);
  assert.match(dialogs[0].detail, /0.7.2-beta.2/);
  await updater.check({manual: true});
  assert.equal(dialogs.length, 2);
  assert.deepEqual(transitions, [true, false, true, false, true, false]);
});

test('download and release notes buttons open their intended URLs', async () => {
  for (const button of [0, 1, 2]) {
    const {updater, opened} = harness({showMessageBox: async () => ({response: button})});
    await updater.check({manual: true});
    assert.deepEqual(opened, button === 2 ? [] : [button === 0
      ? `${RELEASES_URL}/download/v0.7.2-beta.10/Arena-1-0.7.2-beta.10-mac-arm64.dmg`
      : `${RELEASES_URL}/tag/v0.7.2-beta.10`]);
  }
});

test('unsupported architectures open the release page instead of downloading the wrong binary', async () => {
  const {updater, opened} = harness({arch: 'riscv64', showMessageBox: async () => ({response: 0})});
  await updater.check();
  assert.deepEqual(opened, [`${RELEASES_URL}/tag/v0.7.2-beta.10`]);
});

test('up-to-date automatic checks are quiet and manual checks show the current version', async () => {
  const {updater, dialogs} = harness({fetch: async () => response([release('0.7.2-beta.2')])});
  await updater.check();
  assert.equal(dialogs.length, 0);
  await updater.check({manual: true});
  assert.equal(dialogs.length, 1);
  assert.match(dialogs[0].message, /当前已是最新版本/);
  assert.match(dialogs[0].detail, /0.7.2-beta.2/);
});

test('offline automatic checks are quiet and manual failures offer the downloads page', async () => {
  const dialogs = [];
  const {updater, opened} = harness({fetch: async () => { throw new Error('Network offline'); },
    showMessageBox: async options => { dialogs.push(options); return {response: 0}; }});
  await updater.check();
  assert.equal(dialogs.length, 0);
  await updater.check({manual: true});
  assert.equal(dialogs.length, 1);
  assert.equal(dialogs[0].type, 'warning');
  assert.match(dialogs[0].message, /暂时无法检查更新/);
  assert.deepEqual(opened, [RELEASES_URL]);
  assert.equal(updater.checking, false);
});

test('empty release feeds report an error instead of claiming the app is current', async () => {
  const {updater, dialogs} = harness({fetch: async () => response([])});
  await updater.check({manual: true});
  assert.equal(dialogs[0].type, 'warning');
});

test('overlapping checks share one request and preserve manual feedback', async () => {
  let resolveFetch, requests = 0;
  const {updater, dialogs} = harness({fetch: () => { requests++; return new Promise(resolve => { resolveFetch = resolve; }); }});
  const automatic = updater.check();
  const manual = updater.check({manual: true});
  assert.equal(automatic, manual);
  assert.equal(requests, 1);
  assert.equal(updater.checking, true);
  resolveFetch(response([release('0.7.2-beta.2')]));
  await manual;
  assert.equal(dialogs.length, 1);
  assert.equal(updater.checking, false);
});

test('stopping cancels an in-flight request without showing a dialog', async () => {
  let signal;
  const {updater, dialogs} = harness({fetch: (_url, options) => new Promise((_resolve, reject) => {
    signal = options.signal;
    signal.addEventListener('abort', () => reject(new Error('Aborted')), {once: true});
  })});
  const pending = updater.check({manual: true});
  updater.stop();
  await pending;
  await updater.check({manual: true});
  assert.equal(signal.aborted, true);
  assert.deepEqual(dialogs, []);
});

test('startup and periodic checks are scheduled once and stop with the app', t => {
  t.mock.timers.enable({apis: ['setTimeout', 'setInterval']});
  const {updater} = harness();
  let checks = 0;
  updater.check = () => { checks++; return Promise.resolve(); };
  updater.start();
  updater.start();
  t.mock.timers.tick(STARTUP_DELAY - 1);
  assert.equal(checks, 0);
  t.mock.timers.tick(1);
  assert.equal(checks, 1);
  t.mock.timers.tick(CHECK_INTERVAL - STARTUP_DELAY);
  assert.equal(checks, 2);
  updater.stop();
  t.mock.timers.tick(CHECK_INTERVAL);
  assert.equal(checks, 2);
});

test('browser launch failures leave a usable URL in a dialog', async () => {
  const dialogs = [];
  const {updater} = harness({showMessageBox: async options => { dialogs.push(options); return {response: 0}; },
    openExternal: async () => { throw new Error('No browser'); }});
  await updater.check({manual: true});
  assert.equal(dialogs.length, 2);
  assert.match(dialogs[1].message, /无法打开下载链接/);
  assert.match(dialogs[1].detail, /https:\/\/github.com\/RM-Arena\/Arena-1\/releases\/download\//);
});

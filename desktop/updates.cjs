const RELEASES_URL = 'https://github.com/RM-Arena/Arena-1/releases';
const API_URL = 'https://api.github.com/repos/RM-Arena/Arena-1/releases?per_page=30';
const STARTUP_DELAY = 5000;
const CHECK_INTERVAL = 6 * 60 * 60 * 1000;

function parseVersion(value) {
  if (typeof value !== 'string') return null;
  const match = /^v?(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([\da-zA-Z-]+(?:\.[\da-zA-Z-]+)*))?(?:\+[\da-zA-Z-]+(?:\.[\da-zA-Z-]+)*)?$/.exec(value);
  if (!match) return null;
  const core = match.slice(1, 4).map(Number);
  const prerelease = match[4]?.split('.') || [];
  if (!core.every(Number.isSafeInteger) || prerelease.some(part => /^0\d+$/.test(part))) return null;
  return {core, prerelease};
}

function compareVersions(left, right) {
  const a = parseVersion(left), b = parseVersion(right);
  if (!a || !b) throw new Error('Invalid application version');
  for (let index = 0; index < 3; index++) {
    if (a.core[index] !== b.core[index]) return a.core[index] > b.core[index] ? 1 : -1;
  }
  if (!a.prerelease.length || !b.prerelease.length) return Math.sign(b.prerelease.length) - Math.sign(a.prerelease.length);
  for (let index = 0; index < Math.max(a.prerelease.length, b.prerelease.length); index++) {
    const x = a.prerelease[index], y = b.prerelease[index];
    if (x === y) continue;
    if (x === undefined || y === undefined) return x === undefined ? -1 : 1;
    const numericX = /^\d+$/.test(x), numericY = /^\d+$/.test(y);
    if (numericX !== numericY) return numericX ? -1 : 1;
    return (numericX ? BigInt(x) > BigInt(y) : x > y) ? 1 : -1;
  }
  return 0;
}

function installerNames(version, platform, arch, appImage) {
  const base = `Arena-1-${version}`;
  if (platform === 'darwin') return [`${base}-mac-${arch}.dmg`, `${base}-mac-${arch}.zip`];
  if (platform === 'win32') return [`${base}-win-${arch}.exe`, `${base}-win-${arch}.zip`];
  if (platform === 'linux') {
    const deb = `${base}-linux-${arch === 'x64' ? 'amd64' : arch}.deb`;
    const image = `${base}-linux-${arch === 'x64' ? 'x86_64' : arch}.AppImage`;
    return appImage ? [image, deb] : [deb, image];
  }
  return [];
}

function findUpdate(releases, currentVersion, {platform = process.platform, arch = process.arch, appImage = !!process.env.APPIMAGE} = {}) {
  const published = releases.filter(release => release && !release.draft && release.published_at && parseVersion(release.tag_name));
  if (!published.length) throw new Error('未找到已发布的版本 / No published releases were found.');
  const latest = published.sort((a, b) => compareVersions(b.tag_name, a.tag_name))[0];
  if (compareVersions(latest.tag_name, currentVersion) <= 0) return null;
  const version = latest.tag_name.replace(/^v/, '');
  const releaseUrl = `${RELEASES_URL}/tag/${encodeURIComponent(latest.tag_name)}`;
  // Construct links from this repository and accept only matching uploaded assets.
  // Release metadata must never turn a download button into an arbitrary external URL.
  for (const name of installerNames(version, platform, arch, appImage)) {
    const downloadUrl = `${RELEASES_URL}/download/${encodeURIComponent(latest.tag_name)}/${encodeURIComponent(name)}`;
    if (Array.isArray(latest.assets) && latest.assets.some(asset => asset && asset.name === name && asset.state === 'uploaded' && asset.size > 0 && asset.browser_download_url === downloadUrl)) {
      return {version, releaseUrl, downloadUrl};
    }
  }
  return {version, releaseUrl, downloadUrl: null};
}

async function fetchReleases(fetch, version, signal) {
  const response = await fetch(API_URL, {
    headers: {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': `Arena-1/${version}`},
    signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(15000)]) : AbortSignal.timeout(15000),
  });
  if (!response.ok) throw new Error(`发布服务暂不可用 / Release service unavailable (HTTP ${response.status}).`);
  const releases = await response.json();
  if (!Array.isArray(releases)) throw new Error('发布服务返回了无效数据 / Invalid release response.');
  return releases;
}

class AppUpdates {
  constructor({version, fetch, showMessageBox, openExternal, onCheckingChange = () => {}, platform = process.platform, arch = process.arch, appImage = !!process.env.APPIMAGE}) {
    this.version = version;
    this.fetch = fetch;
    this.showMessageBox = showMessageBox;
    this.openExternal = openExternal;
    this.onCheckingChange = onCheckingChange;
    this.target = {platform, arch, appImage};
    this.checking = false;
    this.stopped = false;
    this.notifiedVersion = null;
  }

  start() {
    if (this.stopped || this.intervalTimer) return;
    this.startupTimer = setTimeout(() => { this.startupTimer = null; void this.check(); }, STARTUP_DELAY);
    this.intervalTimer = setInterval(() => { void this.check(); }, CHECK_INTERVAL);
    this.startupTimer.unref?.();
    this.intervalTimer.unref?.();
  }

  stop() {
    this.stopped = true;
    clearTimeout(this.startupTimer);
    clearInterval(this.intervalTimer);
    this.controller?.abort();
  }

  check({manual = false} = {}) {
    if (this.stopped) return Promise.resolve();
    this.manualRequested ||= manual;
    if (this.pending) return this.pending;
    this.checking = true;
    this.controller = new AbortController();
    this.onCheckingChange(true);
    this.pending = this.run().finally(() => {
      this.pending = null;
      this.manualRequested = false;
      this.checking = false;
      this.onCheckingChange(false);
    });
    return this.pending;
  }

  async run() {
    try {
      const releases = await fetchReleases(this.fetch, this.version, this.controller.signal);
      if (this.stopped) return;
      const update = findUpdate(releases, this.version, this.target);
      if (!update) {
        if (this.manualRequested) await this.showMessageBox({type: 'info', title: 'Arena-1', message: '当前已是最新版本 / You’re up to date', detail: `Arena-1 ${this.version}`, buttons: ['确定 / OK']});
        return;
      }
      if (!this.manualRequested && this.notifiedVersion === update.version) return;
      this.notifiedVersion = update.version;
      const answer = await this.showMessageBox({
        type: 'info', title: 'Arena-1', message: `发现新版本 / Update available: ${update.version}`,
        detail: `当前版本 / Current: ${this.version}\n新版本 / New: ${update.version}\n\n${update.downloadUrl ? '安装包将通过浏览器下载，下载完成后退出 Arena-1 并安装。\nDownload the installer in your browser, then quit Arena-1 and install it.' : '请在发布页选择适用的安装包。\nChoose a compatible installer on the release page.'}`,
        buttons: [update.downloadUrl ? '下载升级 / Download update' : '打开下载页 / Open downloads', '查看版本说明 / Release notes', '稍后 / Later'],
        defaultId: 0, cancelId: 2, noLink: true,
      });
      if (!this.stopped && answer.response < 2) await this.open(answer.response === 0 ? update.downloadUrl || update.releaseUrl : update.releaseUrl);
    } catch (error) {
      if (this.stopped || !this.manualRequested) return;
      const answer = await this.showMessageBox({type: 'warning', title: 'Arena-1', message: '暂时无法检查更新 / Unable to check for updates',
        detail: `请检查网络后重试，也可以打开下载页。\nCheck your connection and try again, or open the downloads page.\n\n${error.message}`,
        buttons: ['打开下载页 / Open downloads', '关闭 / Close'], defaultId: 1, cancelId: 1, noLink: true});
      if (!this.stopped && answer.response === 0) await this.open(RELEASES_URL);
    }
  }

  async open(url) {
    try { await this.openExternal(url); }
    catch {
      if (!this.stopped) await this.showMessageBox({type: 'error', title: 'Arena-1', message: '无法打开下载链接 / Unable to open the download link',
        detail: `请在浏览器中打开 / Open this URL in your browser:\n${url}`, buttons: ['确定 / OK']});
    }
  }
}

module.exports = {AppUpdates, compareVersions, findUpdate, fetchReleases, RELEASES_URL, API_URL, STARTUP_DELAY, CHECK_INTERVAL};

'use strict';
const activeNotifications = new Set();

function showDigestNotification({Notification, payload, onClick = () => {}, timeoutMs = 8000}) {
  if (!payload || !/^\d{4}-\d{2}-\d{2}$/.test(payload.date) || typeof payload.partial !== 'boolean') {
    return Promise.resolve({ok: false, state: 'invalid'});
  }
  if (!Notification.isSupported()) return Promise.resolve({ok: false, state: 'unsupported'});
  return new Promise(resolve => {
    let finished = false;
    const finish = value => {
      if (finished) return;
      finished = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => finish({ok: false, state: 'unconfirmed'}), timeoutMs);
    try {
      const notification = new Notification({
        title: 'SPARK Morning Digest',
        body: payload.partial
          ? 'Your morning digest is ready. Some sources need attention. Open SPARK to review.'
          : 'Your morning digest is ready. Open SPARK to review.',
        silent: true,
      });
      activeNotifications.add(notification);
      notification.once('close', () => activeNotifications.delete(notification));
      notification.once('failed', () => activeNotifications.delete(notification));
      notification.once('show', () => finish({ok: true, state: 'shown', date: payload.date}));
      notification.once('failed', () => finish({ok: false, state: 'failed'}));
      notification.once('click', onClick);
      notification.show();
    } catch {
      finish({ok: false, state: 'failed'});
    }
  });
}

// Electron loads its entry through its bootstrap module, so require.main can
// differ even when this file is the application's actual command-line entry.
const electronEntry = process.versions.electron && process.type === 'browser'
  && process.argv[1] && require('node:path').resolve(process.argv[1]) === __filename;
if (require.main === module || electronEntry) {
  const {app, Notification, shell} = require('electron');
  const path = require('node:path');
  app.setPath('userData', path.join(process.env.LOCALAPPDATA || app.getPath('temp'), 'SPARK', 'digest-notifier'));
  app.setAppUserModelId('com.spark.workstation');
  app.whenReady().then(async () => {
    if (process.platform === 'win32') {
      // Windows associates desktop toasts with a Start Menu shortcut's AUMID.
      // Keep this registration separate from the owner's desktop shortcut.
      const fs = require('node:fs');
      const root = path.resolve(__dirname, '..');
      const shortcut = path.join(app.getPath('appData'), 'Microsoft', 'Windows',
        'Start Menu', 'Programs', 'SPARK Morning Digest.lnk');
      const target = path.join(process.env.SystemRoot || 'C:\\Windows',
        'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
      const args = `-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "${path.join(root, 'scripts', 'launch-desktop.ps1')}"`;
      try {
        if (fs.existsSync(shortcut)) {
          const existing = shell.readShortcutLink(shortcut);
          if (existing.target.toLowerCase() !== target.toLowerCase() || existing.args !== args) {
            throw new Error('Shortcut belongs to another application.');
          }
        }
        if (!shell.writeShortcutLink(shortcut, fs.existsSync(shortcut) ? 'update' : 'create', {
          target, args, cwd: root, appUserModelId: 'com.spark.workstation',
          description: 'SPARK Morning Digest', icon: path.join(root, 'public', 'spark.ico'), iconIndex: 0,
        })) throw new Error('Shortcut registration failed.');
      } catch {
        process.stdout.write(JSON.stringify({ok: false, state: 'registration_failed'}) + '\n');
        app.quit();
        return;
      }
    }
    const receipt = await showDigestNotification({Notification,
      payload: {date: process.argv[2], partial: process.argv[3] === 'partial'}});
    process.stdout.write(JSON.stringify(receipt) + '\n');
    // Keep the native notification alive for the banner's display interval.
    setTimeout(() => app.quit(), receipt.ok ? 10000 : 0);
  });
}

module.exports = {showDigestNotification};

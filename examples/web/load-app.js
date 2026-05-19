/** Load compiled Shàn web app from ?app= (external module for CSP). */
const APP_RE = /^[a-z0-9]+(?:-[a-z0-9]+)*-web$/;
const raw = new URLSearchParams(location.search).get("app") || "hello-web";
const app = APP_RE.test(raw) ? raw : "hello-web";

document.getElementById("app-style").href = `styles/${app}.css`;

try {
  const mod = await import(`/dist/apps/${app}.js`);
  const run = mod.default ?? mod.createApp;
  if (typeof run !== 'function') {
    throw new Error('module has no createApp export');
  }
  run();
} catch (err) {
  console.error("[Shàn]", err);
  const el = document.getElementById("app");
  el.replaceChildren();
  const p = document.createElement("p");
  p.style.cssText = "color:#f85149;padding:2rem";
  p.textContent = `Failed to load app: ${app}. Run: python3 -m shan serve ${app}`;
  el.appendChild(p);
}

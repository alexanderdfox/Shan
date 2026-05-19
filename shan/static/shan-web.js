/**
 * Shàn Web Runtime — Phase 1 (hardened)
 * DOM bindings, declarative events, env state. No eval.
 */

const IDENT_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;
const MOUNT_RE = /^#[A-Za-z][\w-]*$|^\.[A-Za-z][\w-]*$/;
const SAFE_EVENTS = new Set([
  'click', 'dblclick', 'change', 'input', 'submit',
  'keydown', 'keyup', 'keypress',
  'mousedown', 'mouseup', 'mouseover', 'mouseout', 'focus', 'blur',
]);
// Match inline handlers (onclick=), not Shàn data-on=
const UNSAFE_MARKUP = /<script\b|javascript\s*:|data\s*:\s*text\/html|(?:^|[\s"'>\/])(on(?:click|error|load|mouse\w+|focus|blur|change|input|submit)\s*=)/i;

export function range(n) {
  const k = Number(n);
  if (!Number.isFinite(k) || k < 0 || k > 1_000_000) {
    throw new RangeError('range: invalid length');
  }
  return Array.from({ length: k }, (_, i) => i);
}

export function len(x) {
  if (x == null) return 0;
  return x.length !== undefined ? x.length : Object.keys(x).length;
}

function requireIdent(name, what = 'name') {
  if (!name || !IDENT_RE.test(name)) {
    throw new Error(`Shàn: invalid ${what}: ${name}`);
  }
}

function requireMount(selector) {
  const s = String(selector || '#app').trim();
  if (!MOUNT_RE.test(s)) {
    throw new Error(`Shàn: invalid mount selector: ${s}`);
  }
  return s;
}

function assertTrustedMarkup(html) {
  if (typeof html !== 'string' || UNSAFE_MARKUP.test(html)) {
    throw new Error('Shàn: unsafe markup blocked (compile output only)');
  }
}

function installMarkup(root, html) {
  assertTrustedMarkup(html);
  const tpl = document.createElement('template');
  tpl.innerHTML = html;
  root.replaceChildren(...tpl.content.childNodes);
}

/**
 * @param {object} options
 * @param {string} options.mount - CSS selector (#id or .class)
 * @param {string} options.html - App markup (trusted compile output only)
 * @param {string} [options.title]
 * @param {(env: object) => void} [options.init]
 * @param {Record<string, (env: object, api: object, ...args: any[]) => void>} options.handlers
 */
export function mount(options) {
  const { mount: selector, html, title, init, handlers } = options;
  requireMount(selector);
  const root = document.querySelector(selector);
  if (!root) {
    throw new Error(`Shàn mount: element not found: ${selector}`);
  }

  const env = Object.create(null);
  const api = {
    render() {
      syncInputs(root, env);
      bindAll(root, env);
    },
    log(...args) {
      console.log('[Shàn]', ...args);
    },
  };

  if (title) document.title = String(title).slice(0, 200);

  installMarkup(root, html);
  wireEvents(root, env, handlers, api);

  if (init) init(env);
  wireInputs(root, env, api);
  api.render();

  return {
    env,
    api,
    root,
    destroy() {
      root.replaceChildren();
    },
  };
}

function bindAll(container, env) {
  container.querySelectorAll('[data-bind]').forEach((el) => {
    const key = el.getAttribute('data-bind');
    if (!key || !IDENT_RE.test(key)) return;
    const val = env[key];
    el.textContent = val === undefined || val === null ? '' : String(val);
  });
}

function syncInputs(container, env) {
  container.querySelectorAll('[data-input]').forEach((el) => {
    const key = el.getAttribute('data-input');
    if (!key || !IDENT_RE.test(key) || !(key in env)) return;
    if (document.activeElement === el) return;
    const v = env[key];
    el.value = v === undefined || v === null ? '' : String(v);
  });
}

function wireInputs(root, env, api) {
  root.querySelectorAll('[data-input]').forEach((el) => {
    const key = el.getAttribute('data-input');
    if (!key || !IDENT_RE.test(key)) return;
    const sync = () => {
      env[key] = el.value;
      api.render();
    };
    el.addEventListener('input', sync);
    el.addEventListener('change', sync);
  });
  syncInputs(root, env);
}

function wireEvents(root, env, handlers, api) {
  root.querySelectorAll('[data-on]').forEach((el) => {
    const spec = el.getAttribute('data-on');
    if (!spec) return;
    const parts = spec.split(':').map((s) => s.trim());
    if (parts.length !== 2) {
      console.warn('[Shàn] invalid data-on:', spec);
      return;
    }
    const [eventName, handlerName] = parts;
    if (!SAFE_EVENTS.has(eventName)) {
      console.warn('[Shàn] event not allowed:', eventName);
      return;
    }
    if (!IDENT_RE.test(handlerName)) {
      console.warn('[Shàn] invalid handler name:', handlerName);
      return;
    }
    const fn = handlers[handlerName];
    if (typeof fn !== 'function') {
      console.warn('[Shàn] unknown handler:', handlerName);
      return;
    }
    el.addEventListener(eventName, (e) => {
      if (eventName === 'submit' && e.cancelable) e.preventDefault();
      fn(env, api);
      api.render();
    });
  });
}

export default { mount, range, len };

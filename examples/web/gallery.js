/** Gallery nav — external script for CSP (script-src 'self'). */
const APPS = [
  { id: "hello-web", title: "Counter", desc: "+1 / −1 / reset" },
  { id: "greet-web", title: "Greeting", desc: "Text input + hello" },
  { id: "lights-web", title: "Fan lamp", desc: "Toggle on/off" },
  { id: "score-web", title: "Scoreboard", desc: "Home vs away" },
  { id: "todo-web", title: "Todo", desc: "Three toggle items" },
  { id: "calc-web", title: "Calculator", desc: "Digit pad" },
];

const nav = document.getElementById("apps");
for (const { id, title, desc } of APPS) {
  const a = document.createElement("a");
  a.className = "card";
  a.href = `index.html?app=${id}`;
  const h2 = document.createElement("h2");
  h2.textContent = title;
  const p = document.createElement("p");
  p.textContent = desc;
  a.append(h2, p);
  nav.appendChild(a);
}

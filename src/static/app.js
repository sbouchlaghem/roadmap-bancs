"use strict";
const MOIS = ["Janv.", "Févr.", "Mars", "Avr.", "Mai", "Juin", "Juil.", "Août", "Sept.", "Oct.", "Nov.", "Déc."];
const NEXT = ["En cours", "Planifié", "Bloqué", "En retard"];
const MANUELS = ["Terminé", "Bloqué"];   // les autres statuts se déduisent des dates
const $ = (s, el = document) => el.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const RO = !!window.SNAPSHOT;   // page publiée : lecture seule, données figées
const VUE_PROD = RO && window.SNAPSHOT.vue === "prod";   // production.html : seulement la vue production
if (RO) document.documentElement.classList.add("ro");
if (VUE_PROD) document.documentElement.classList.add("ro-prod");
let S = { projets: [], poles: [], statuts: [], jalons: [], today: "", config: null };   // config : titres, pôles, couleurs…
const stc = s => "st-" + String(s || "auto").replace(/\s+/g, "-");   // « En retard » -> classe st-En-retard
let edit = null;      // projet en cours d'édition (copie)
let dirty = false;

// ---------- utilitaires ----------
const poleCfg = nom => S.config.poles.find(p => p.nom === nom);
function color(pole) {
  if (poleCfg(pole)) return poleCfg(pole).couleur;
  const sup = S.config.couleurs.supplementaires;   // pôle absent de la configuration
  const others = [...new Set(S.projets.map(p => p.pole))].filter(p => !poleCfg(p));
  return sup[Math.max(0, others.indexOf(pole)) % sup.length];
}
const court = pole => poleCfg(pole)?.court || pole;
const liste = r => Array.isArray(r) ? r : String(r || "").split(",").map(s => s.trim()).filter(Boolean);
// couleur d'une personne : rang dans l'annuaire, puis les autres noms par ordre alphabétique (10 couleurs, puis on recommence)
const PERSO = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac"];
function persoColor(n) {
  if (S.config.equipe_couleurs?.[n]) return S.config.equipe_couleurs[n];   // choisie dans les paramètres
  const ann = S.config.equipe || [];
  if (ann.includes(n)) return PERSO[ann.indexOf(n) % PERSO.length];
  const autres = [...new Set(S.projets.flatMap(p => [p.ressources, ...p.versions.map(v => v.ressources)].flatMap(liste)))]
    .filter(x => !ann.includes(x)).sort();
  return PERSO[(ann.length + autres.indexOf(n)) % PERSO.length];
}
const pointsEquipe = noms => noms.length && S.config.application.points_equipe ? `<span class="eq-pts" aria-hidden="true">${noms.map(n => `<i style="background:${persoColor(n)}"></i>`).join("")}</span>` : "";
const equipeV = (p, v) => liste(v.ressources).length ? liste(v.ressources) : liste(p.ressources);   // version, sinon projet
const ETATS = { ok: ["✅", "Opérationnel"], maj: ["🔧", "En mise à jour"], degrade: ["⚠", "Dégradé"], panne: ["⛔", "En panne"] };
// postes d'un banc (fiche projet) : chacun son état et sa version installée ; sans poste, le projet est le banc
const postesDe = p => p.postes?.length
  ? p.postes.map((x, i) => ({ ...p, etat: x.etat, etat_note: x.etat_note, etat_date: x.etat_date, poste: x.nom, i,
                              version: x.version || "", version_date: x.version_date || "" })) : [{ ...p, i: 0 }];
const GRAVITE = ["panne", "degrade", "maj", "ok"];
const pire = p => postesDe(p).map(b => b.etat).filter(e => ETATS[e]).sort((a, b) => GRAVITE.indexOf(a) - GRAVITE.indexOf(b))[0] || "";
function infoProd(p) {   // version en production, dernière livrée, à déployer, prochaine : base de la vue production
  // p : un projet, ou un poste (postesDe) qui a sa propre version installée
  const cle = v => vkey(v.version) || [];
  const livrees = p.versions.filter(v => v.statut === "Terminé" && vkey(v.version)).sort((a, b) => cmp(cle(b), cle(a)));
  const vp = p.poste !== undefined && p.versions.find(v => v.version === p.version);
  const enProd = p.poste !== undefined ? vp && { ...vp, prod: p.version_date || vp.prod }
    : p.versions.filter(v => v.prod).sort((a, b) => b.prod.localeCompare(a.prod))[0];
  const derniere = livrees[0], suivante = prochaine(p);
  // « à déployer » seulement si on sait ce qui tourne (une mise en prod saisie) : sinon pas de fausse alerte
  const aDeployer = derniere && enProd && cmp(cle(derniere), cle(enProd)) > 0;
  return { livrees, enProd, derniere, suivante, aDeployer, cibleMaj: aDeployer ? derniere : suivante };   // mise à jour vers…
}
const etatHtml = p => {   // durée seulement pour un problème (dégradé, en panne) ; la date reste au survol
  if (!ETATS[p.etat]) return '<span class="muted">—</span>';
  const duree = p.etat !== "ok" && p.etat_date ? ` · depuis le ${fmtD(p.etat_date)}` : "";   // date du passage en mise à jour, panne…
  const cible = p.etat === "maj" && infoProd(p).cibleMaj ? ` → ${esc(infoProd(p).cibleMaj.version)}` : "";   // relié à la version visée
  return `<span class="etat etat-${p.etat}" title="${p.etat_date ? "depuis le " + fmtD(p.etat_date) : ""}">${ETATS[p.etat].join(" ")}${cible}${duree}</span>` +
    (p.etat_note ? ` <span class="muted">${esc(p.etat_note)}</span>` : "");
};
const equipe = (p, v) => (v ? equipeV(p, v) : liste(p.ressources)).join(", ");
function applyConfig(c) {   // thème, couleurs et titre viennent de la configuration
  const r = document.documentElement;
  r.dataset.theme = c.application.theme;
  r.style.setProperty("--c-today", c.couleurs.aujourdhui);
  r.style.setProperty("--c-jalon", c.couleurs.jalon);
  r.style.setProperty("--c-retard", c.couleurs.retard);
  document.title = $("#titre").textContent = c.application.titre + (VUE_PROD ? " — Production" : "");
}
function vkey(v) {
  const s = String(v).replace(/^[vV]/, "");
  if (!/^\d+(\.\d+)*$/.test(s)) return null;
  const p = s.split(".").map(Number); while (p.length < 3) p.push(0); return p;
}
const cmp = (a, b) => { for (let i = 0; i < Math.max(a.length, b.length); i++) if ((a[i] || 0) !== (b[i] || 0)) return (a[i] || 0) - (b[i] || 0); return 0; };
function actuelle(p) { return p.versions.find(v => v.statut === "Terminé"); }      // versions : plus récente d'abord
function prochaine(p) { return [...p.versions].reverse().find(v => NEXT.includes(v.statut)); }
function toDate(s, end) {          // "2026-09" -> 1er ou dernier jour du mois
  if (!s) return null;
  const [y, m, d] = s.split("-").map(Number);
  return d ? new Date(y, m - 1, d) : end ? new Date(y, m, 0) : new Date(y, m - 1, 1);
}
const isoJour = () => { const d = new Date(); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`; };
function deduire(v, t) {   // même règle que releases.deduce (Python) : Terminé et Bloqué restent, le reste suit les dates
  if (MANUELS.includes(v.statut) || !(v.debut || v.fin)) return v.statut;
  if (v.fin && (v.fin + "-31").slice(0, 10) < t) return "En retard";   // fin « 2026-11 » = fin du mois
  return v.debut ? (v.debut <= t ? "En cours" : "Planifié") : v.statut;
}
function majJour() {   // page publiée : « aujourd'hui » avance et les statuts suivent (Planifié → En cours → En retard)
  S.today = isoJour();
  for (const p of [...S.projets, ...(S.parc || [])]) for (const v of p.versions) v.statut = deduire(v, S.today);
}
const fmtD = s => !s ? "?" : s.split("-").reverse().join("/");
// alerte d'une version (texte) ou "" : ce qui demande une action
function alerte(v) {
  if (v.statut === "En retard") return `Fin dépassée (${fmtD(v.fin)}) sans livraison — livrer, décaler la fin ou marquer Bloqué`;
  if (v.statut === "Bloqué" && !v.motif) return "Bloqué sans motif — indique ce qu'on attend";
  return "";
}
// dérive en jours : fin actuelle - fin prévue initialement (0 si inconnue)
const derive = v => v.prevu && v.fin ? Math.round((toDate(v.fin, true) - toDate(v.prevu, true)) / 864e5) : 0;
const fmtDer = n => n ? ` (${n > 0 ? "+" : ""}${n} j)` : "";
const alertes = p => p.versions.map(v => [v, alerte(v)]).filter(([, a]) => a);
function toast(msg, err = false) {
  const t = $("#toast"); t.textContent = msg; t.className = "toast show" + (err ? " err" : "");
  clearTimeout(t._h); t._h = setTimeout(() => t.className = "toast", err ? 6000 : 3000);
}
async function api(method, url, body) {
  const r = await fetch(url, { method, headers: body ? { "Content-Type": "application/json" } : {},
                               body: body ? JSON.stringify(body) : undefined });
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).erreur || msg; } catch (_) { /* réponse non JSON */ }
    throw new Error(msg);
  }
  return r;
}
const store = { get(k, d) { try { return localStorage.getItem(k) || d; } catch (_) { return d; } },
                set(k, v) { try { localStorage.setItem(k, v); } catch (_) { /* stockage indisponible */ } } };

const isoMois = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
function remplirMois(extra) {   // « septembre 2026 » quelle que soit la langue du navigateur (input type=month ne le permet pas)
  const t = toDate(S.today);
  let a = new Date(t.getFullYear() - 3, t.getMonth(), 1), b = new Date(t.getFullYear() + 3, t.getMonth(), 1);
  for (const d of extra.map(k => toDate(k)).filter(Boolean)) { if (d < a) a = d; if (d > b) b = d; }
  const opts = [];
  for (let m = new Date(a.getFullYear(), a.getMonth(), 1); m <= b; m = new Date(m.getFullYear(), m.getMonth() + 1, 1))
    opts.push(`<option value="${isoMois(m)}">${m.toLocaleDateString("fr-FR", { month: "long", year: "numeric" })}</option>`);
  $("#debut").innerHTML = $("#fin").innerHTML = opts.join("");
}

// ---------- chargement ----------
async function load() {
  const d = RO ? window.SNAPSHOT : await (await api("GET", "/api/projets")).json();
  S = { projets: d.projets, poles: d.poles, statuts: d.statuts, jalons: d.jalons || [], today: d.aujourdhui,
        config: d.config, configChemin: d.config_chemin };
  S.parc = RO ? d.parc || [] : S.projets;   // onglet En production : page publiée = tous les projets (pas seulement la période)
  applyConfig(S.config);
  if (RO) majJour();   // page publiée : date du jour du lecteur, pas celle de la publication
  const nv = S.projets.reduce((n, p) => n + p.versions.length, 0);
  const nav = S.projets.reduce((n, p) => n + p.versions.filter(v => v.statut !== "Terminé").length, 0);
  const souci = S.parc.flatMap(postesDe).filter(p => ["panne", "degrade", "maj"].includes(p.etat)).length;   // production.html : l'essentiel pour la prod
  $("#resume").textContent = VUE_PROD ? `${S.parc.length} bancs / outils${souci ? ` · ${souci} indisponible(s) ou dégradé(s)` : ""} · publié le ${d.publie}`
    : RO ? `${nav} versions à venir · publié le ${d.publie}` : `${S.projets.length} projets · ${nv} versions`;
  if (!$("#debut").length) {   // premier chargement : liste des mois, puis période
    const mois = n => { const d = toDate(S.today); d.setMonth(d.getMonth() + n, 1); return isoMois(d); };
    // par défaut : 2 mois avant -> 4 mois après aujourd'hui ; page publiée : période choisie à la publication
    const [deb, fin] = RO ? d.periode : [store.get("debut", mois(-2)), store.get("fin", mois(4))];
    remplirMois([deb, fin]);
    $("#debut").value = deb; $("#fin").value = fin;
    if ($("#debut").selectedIndex < 0) $("#debut").value = mois(-2);   // valeur mémorisée illisible
    if ($("#fin").selectedIndex < 0) $("#fin").value = mois(4);
  }
  const gp = $("#g-pole");
  gp.length = 1;
  for (const [pole] of grouped(S.projets)) gp.add(new Option(pole, pole));
  for (const id of ["g-pole", "g-statut"]) { const el = $("#" + id); el.value = store.get(id, ""); if (el.selectedIndex < 0) el.value = ""; }
  render();
}
function render() { renderAlerts(); renderGantt(); renderCards(); renderJalons(); renderProd(); }
// versions livrées pas encore installées, regroupées par version (seulement là où la version en production est connue)
function aDeployerListe() {
  return S.projets.filter(p => p.prod_publie !== false).flatMap(p => {
    const par = {};
    for (const b of postesDe(p)) {
      const { aDeployer, derniere } = infoProd(b);
      if (aDeployer) (par[derniere.version] ||= { p, v: derniere, postes: [] }).postes.push(b.poste);
    }
    return Object.values(par);
  });
}
function renderAlerts() {
  const list = S.projets.flatMap(p => alertes(p).map(([v, a]) => ({ p, v, a })));
  const dep = aDeployerListe(), n = list.length + dep.length;
  const box = $("#alerts");
  box.hidden = !n;
  const depuis = d => { const j = Math.round((toDate(S.today) - toDate(d)) / 864e5); return j > 0 ? ` (il y a ${j} j)` : ""; };
  box.innerHTML = `<strong>⚠ ${n} alerte${n > 1 ? "s" : ""}</strong><ul>` +
    list.map(({ p, v, a }) => `<li><button class="link" data-id="${p.id}">${esc(p.nom)} ${esc(v.version)}</button> : ${esc(a)}</li>`).join("") +
    dep.map(({ p, v, postes }) => `<li><button class="link" data-vue="prod">${esc(p.nom)} ${esc(v.version)}</button> : livrée le ${fmtD(v.fin)}${depuis(v.fin)},
      pas encore déployée${postes.some(Boolean) ? " sur " + esc(postes.join(", ")) : ""} — l'installer puis la saisir dans 📦 En production</li>`).join("") +
    "</ul>";
}
$("#alerts").addEventListener("click", e => { if (e.target.closest("[data-vue]")) $('.tabs button[data-view="prod"]').click(); });
const filtres = () => ({ pole: $("#g-pole").value, statut: $("#g-statut").value });
function garde(v, statut) { return !statut || (statut === "alerte" ? ["Bloqué", "En retard"].includes(v.statut) : v.statut === statut); }
function visibles() {   // projets et versions retenus par les filtres du Gantt (même règle que server.ppt_export)
  const { pole, statut } = filtres();
  return S.projets.filter(p => !pole || p.pole === pole).map(p => ({ ...p, versions: p.versions.filter(v => garde(v, statut)) }));
}
function grouped(list) {
  const order = [...S.poles, ...new Set(list.map(p => p.pole).filter(p => !S.poles.includes(p)))];
  return order.map(pole => [pole, list.filter(p => p.pole === pole)]).filter(([, l]) => l.length);
}

// ---------- roadmap ----------
function renderGantt() {
  const t0 = toDate($("#debut").value), t1 = toDate($("#fin").value, true);
  const g = $("#gantt");
  g.classList.toggle("eq", !!S.config.application.points_equipe);   // lignes un peu plus hautes : points sous la version
  if (!t0 || !t1 || t1 < t0) { g.innerHTML = `<p class="empty">Choisis une période valide.</p>`; return; }
  const span = (t1 - t0) / 864e5 + 1;
  const trackPx = g.clientWidth - 34 - (parseFloat(getComputedStyle(g).getPropertyValue("--nom")) || 230);
  const vus = { poles: new Set(), statuts: new Set(), personnes: new Set(), prevu: false };   // pour une légende limitée à ce qui est affiché   // largeur des pistes (colonnes pôle 34 px + nom 230 px)
  const pct = d => Math.min(100, Math.max(0, ((d - t0) / 864e5) / span * 100));
  const today = toDate(S.today);
  let months = "", grid = "";
  for (let m = new Date(t0.getFullYear(), t0.getMonth(), 1); m <= t1; m = new Date(m.getFullYear(), m.getMonth() + 1, 1)) {
    const a = pct(m < t0 ? t0 : m), b = pct(new Date(m.getFullYear(), m.getMonth() + 1, 1));
    const cls = new Date(m.getFullYear(), m.getMonth() + 1, 1) <= today ? "past" : (m <= today ? "now" : "");
    months += `<div class="g-month ${cls}" style="left:${a}%;width:${b - a}%">${MOIS[m.getMonth()]} ${String(m.getFullYear()).slice(2)}</div>`;
    grid += `<div class="g-grid" style="left:${a}%"></div>`;
  }
  const todayLine = today >= t0 && today <= t1 ? `<div class="today" style="left:${pct(today)}%" data-label="Aujourd'hui"></div>` : "";
  let html = `<div class="g-head"><div></div><div></div><div class="g-months">${months}</div></div>`;
  const horsSlide = [];
  for (const [pole, list] of grouped(visibles())) {
    let rows = "";
    for (const p of list) {
      const bars = [];
      for (const v of p.versions) {
        const a = toDate(v.debut), b = toDate(v.fin, true);
        if (!a || !b) { if (v.statut && v.statut !== "Terminé") horsSlide.push({ p, v }); continue; }
        if (b < t0 || a > t1) continue;
        const l = pct(a), w = Math.max(pct(b) - l, 0.6), der = derive(v);
        const txt = (["Bloqué", "En retard"].includes(v.statut) ? "⚠ " : "") + v.version + fmtDer(der);
        const need = (Math.max(txt.length * 7, S.config.application.points_equipe ? equipeV(p, v).length * 9 : 0) + 16) / trackPx * 100;   // points sous le texte      // largeur du texte, en % de la piste
        // barre trop courte : élargie juste assez pour son numéro (vers la gauche au bord droit) ; vraies dates au survol
        const wd = Math.max(w, need), ld = Math.max(0, Math.min(l, 100 - wd));
        bars.push({ v, a, b, l: ld, w: wd, der, txt, need, x0: ld, x1: ld + wd, r0: l, r1: l + w });
      }
      if (!bars.length) continue;
      bars.sort((x, y) => x.x0 - y.x0);
      const lanes = [];                  // barres ou textes qui se chevauchent : sous-lignes
      const fin = lane => lane[lane.length - 1];
      for (const x of bars) {
        let lane = lanes.find(l => fin(l).x1 + 0.3 < x.x0);
        if (!lane) {   // chevauchement dû seulement à l'élargissement : petit décalage plutôt qu'une sous-ligne
          lane = lanes.find(l => fin(l).r1 <= x.r0 && fin(l).x1 + 0.3 - x.x0 <= x.need && fin(l).x1 + 0.3 + x.w <= 100);
          if (lane) { x.l = x.x0 = fin(lane).x1 + 0.3; x.x1 = x.x0 + x.w; }
        }
        lane ? lane.push(x) : lanes.push([x]);
      }
      lanes.forEach((lane, i) => {
        const items = lane.map(({ v, l, w, der, txt }) => {
          const c = color(pole), pv = toDate(v.prevu, true);
          const tip = `${p.nom} ${v.version} — ${v.statut || "?"}${v.motif ? " : " + v.motif : ""} (${fmtD(v.debut)} → ${fmtD(v.fin)})` +
                      (equipe(p, v) ? `\nÉquipe : ${equipe(p, v)}` : "") +
                      (der ? `\nFin prévue initialement : ${fmtD(v.prevu)}${fmtDer(der)}` : "") +
                      (v.notes ? "\n\n" + v.notes.split("\n").slice(0, 8).join("\n") : "");   // contenu prévu
          const ghost = der && pv >= t0 && pv <= t1 ? `<div class="prevu" style="left:${pct(pv)}%" title="${esc(p.nom)} ${esc(v.version)} : fin prévue initialement ${fmtD(v.prevu)}"></div>` : "";
          const pr = toDate(v.prod), prod = pr && pr >= t0 && pr <= t1
            ? `<div class="prod-mark" style="left:${pct(pr)}%" title="${esc(p.nom)} ${esc(v.version)} : en production depuis le ${fmtD(v.prod)}">▲</div>` : "";
          vus.statuts.add(v.statut); if (S.config.application.points_equipe) equipeV(p, v).forEach(n => vus.personnes.add(n)); if (ghost) vus.prevu = true; if (prod) vus.prod = true;
          return `${ghost}${prod}<div class="bar ${stc(v.statut)}" style="left:${l}%;width:${w}%;--c:${c}" title="${esc(tip)}"
                    data-id="${p.id}" data-v="${esc(v.version)}"><span>${esc(txt)}</span>${pointsEquipe(equipeV(p, v))}</div>`;
        }).join("");
        rows += `<div class="g-row"><div class="g-name" data-id="${p.id}" title="${esc(p.nom + (equipe(p) ? "\nÉquipe : " + equipe(p) : ""))}">${i ? "" : esc(p.nom)}</div>
                 <div class="g-track">${grid}${items}</div></div>`;
      });
    }
    if (rows) vus.poles.add(pole);
    if (rows) html += `<div class="g-group"><div class="g-pole" style="background:${color(pole)}">${esc(court(pole))}</div><div>${rows}</div></div>`;
  }
  g.innerHTML = html.includes("g-group") ? html : html + `<p class="empty">Aucune version datée sur cette période${filtres().pole || filtres().statut ? " pour ces filtres" : ""}.</p>`;
  const tr = g.querySelector(".g-months");
  if (tr) {   // lignes « aujourd'hui » et jalons au-dessus des pistes
    const box = tr.getBoundingClientRect(), gb = g.getBoundingClientRect(), x = d => box.left - gb.left + box.width * pct(d) / 100;
    // étiquettes de l'en-tête sans chevauchement : nom complet, sinon « ◆ date », sinon « ◆ » (nom au survol et dans 📍 Jalons)
    const larg = s => s.length * 6.4 + 14, occupe = [];
    const libre = (cx, w) => !occupe.some(([a, b]) => cx - w / 2 < b + 4 && cx + w / 2 > a - 4);
    if (todayLine) occupe.push([x(today) - larg("Aujourd'hui") / 2, x(today) + larg("Aujourd'hui") / 2]);
    for (const j of [...S.jalons].sort((a, b) => a.date.localeCompare(b.date))) {
      const d = toDate(j.date), cx = x(d), dd = fmtD(j.date).slice(0, 5);
      if (d < t0 || d > t1) continue;
      const lbl = [`◆ ${j.label} · ${dd}`, `◆ ${dd}`, "◆"].find(l => libre(cx, larg(l))) || "◆";
      occupe.push([cx - larg(lbl) / 2, cx + larg(lbl) / 2]);
      g.insertAdjacentHTML("beforeend", `<div class="today jalon" style="left:${cx}px" data-label="${esc(lbl)}" title="${esc(j.label)} — ${fmtD(j.date)}"></div>`);
    }   // « Aujourd'hui » en dernier : au-dessus d'un jalon tombant le même jour
    if (todayLine) g.insertAdjacentHTML("beforeend", `<div class="today" style="left:${x(today)}px" data-label="Aujourd'hui"></div>`);
  }
  renderEquipe(t0, t1);
  renderJalonsVue(t0);
  const hs = $("#hors-slide");   // versions sans dates : pastilles cliquables (ouvrent la fiche pour les dater)
  hs.hidden = !horsSlide.length;
  hs.querySelector("summary").innerHTML = `Sans dates <span class="muted">(${horsSlide.length}) — non affichées sur le Gantt, clic pour les dater</span>`;
  hs.querySelector("div").innerHTML = horsSlide.map(({ p, v }) => `<button class="chip ${stc(v.statut)}" style="--c:${color(p.pole)}"
    data-id="${p.id}" data-v="${esc(v.version)}">${esc(p.nom)} <b>${esc(v.version)}</b></button>`).join("");
  const STYLES = { "Terminé": "background:color-mix(in srgb,var(--c) 40%,var(--panel))", "En cours": "background:var(--c)",   // comme .bar.st-*
                   "Planifié": "background:color-mix(in srgb,var(--c) 8%,var(--panel));border:2px dashed var(--c)",
                   "Bloqué": "background:var(--c);border:2px solid var(--text)", "En retard": "background:var(--c);border:2px solid var(--c-retard)" };
  $("#legend").style.setProperty("--c", vus.poles.size ? color([...vus.poles][0]) : "var(--muted)");
  $("#legend").innerHTML = [...vus.poles].map(p => `<span><i style="background:${color(p)}"></i>${esc(p)}</span>`).join("") +
    Object.keys(STYLES).filter(s => vus.statuts.has(s)).map(s => `<span><i style="${STYLES[s]}"></i>${s}</span>`).join("") +
    (vus.prevu ? `<span><i style="width:0;border-left:2px solid var(--text)"></i>Fin prévue initialement</span>` : "") +
    (vus.prod ? `<span><b class="prod-leg">▲</b>Mise en production</span>` : "");
  $("#legend-eq").innerHTML = [...vus.personnes].sort().map(n => `<span><i class="eq-leg" style="background:${persoColor(n)}"></i>${esc(n)}</span>`).join("");
}

// ---------- détail d'une version (page publiée) ----------
const RUBRIQUES = { added: "Nouveautés", changed: "Modifications", fixed: "Corrections", removed: "Suppressions",
                    deprecated: "Bientôt supprimé", security: "Sécurité" };
function notesHtml(notes) {   // markdown simple d'un changelog : « ### Added », « - ligne », texte
  let html = "", ul = false;
  for (const raw of String(notes || "").split("\n")) {
    const l = raw.trim();
    const li = l.match(/^[-*]\s+(.*)/), h = l.match(/^#+\s*(.*)/);
    if (ul && !li) { html += "</ul>"; ul = false; }
    if (li) { if (!ul) { html += "<ul>"; ul = true; } html += `<li>${esc(li[1])}</li>`; }
    else if (h) html += `<h4>${esc(RUBRIQUES[h[1].toLowerCase()] || h[1])}</h4>`;
    else if (l) html += `<p>${esc(l)}</p>`;
  }
  return (html + (ul ? "</ul>" : "")) || `<p class="muted">Contenu non encore détaillé.</p>`;
}
function showDetail(p, v) {
  const der = derive(v);
  $("#detail-body").innerHTML = `
    <h3>${esc(p.nom)} <span class="muted">${esc(v.version)}</span></h3>
    <p><span class="badge ${stc(v.statut)}">${esc(v.statut || "—")}</span> ${fmtD(v.debut)} → ${fmtD(v.fin)}
       ${der ? `<span class="muted">· prévu initialement ${fmtD(v.prevu)}${fmtDer(der)}</span>` : ""}</p>
    ${v.motif ? `<p class="ver-warn">⚠ Bloqué : ${esc(v.motif)}</p>` : ""}
    ${v.statut === "Terminé" ? `<p>${v.prod ? `▲ <b>En production</b> depuis le ${fmtD(v.prod)}` : '<span class="muted">Livrée — pas encore en production</span>'}</p>` : ""}
    ${equipe(p, v) ? `<p>👥 <b>Équipe :</b> ${esc(equipe(p, v))}</p>` : ""}
    <div class="notes">${notesHtml(v.notes)}</div>`;
  $("#detail").showModal();
}
$("#detail").addEventListener("click", e => { if (e.target === e.currentTarget || e.target.closest("[data-close]")) $("#detail").close(); });

// ---------- identifiants Git ----------
const idMsg = (txt, ok) => { const m = $("#id-msg"); m.hidden = !txt; m.textContent = txt; m.classList.toggle("ok", !!ok); };
async function openIdent() {
  const url = $("#f-depot").value.trim(), https = url.startsWith("https://");
  $("#id-hote").textContent = url;
  $("#id-https").hidden = $("#id-ok").hidden = !https;
  $("#id-ssh").hidden = $("#id-copier").hidden = https;
  $("#id-user").required = $("#id-secret").required = https;
  $("#id-secret").value = ""; idMsg("");
  $("#ident").showModal();
  if (!https) {
    try { $("#id-cle").value = (await (await api("GET", "/api/git/cle")).json()).cle; }
    catch (err) { idMsg(err.message); }
  }
}
$("#b-ident").addEventListener("click", openIdent);
$("#id-close").addEventListener("click", () => { $("#id-secret").value = ""; $("#ident").close(); });
$("#id-copier").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("#id-cle").value); idMsg("Clé copiée", true); }
  catch (_) { $("#id-cle").select(); idMsg("Sélectionnée : Ctrl+C pour copier", true); }
});
$("#id-form").addEventListener("submit", e => {
  e.preventDefault();
  busy($("#id-ok"), async () => {
    idMsg("Test de l'accès…", true);
    try {
      const body = { url: $("#f-depot").value.trim(), utilisateur: $("#id-user").value, secret: $("#id-secret").value };
      idMsg((await (await api("POST", "/api/git/identifiants", body)).json()).message, true);
    } catch (err) { idMsg(err.message); }
    finally { $("#id-secret").value = ""; }   // le secret ne reste pas dans la page
  });
});

// ---------- paramètres ----------
let prPoles = [];
const prMsg = (txt, ok) => { const m = $("#pr-msg"); m.hidden = !txt; m.textContent = txt; m.classList.toggle("ok", !!ok); };
function renderPrPoles() {
  $("#pr-poles").innerHTML = prPoles.map((p, i) => `<div class="pr-pole" data-i="${i}">
      <input data-k="nom" value="${esc(p.nom)}" required maxlength="60" aria-label="Nom du pôle" placeholder="Nom">
      <input data-k="court" value="${esc(p.court)}" required maxlength="12" aria-label="Abréviation" placeholder="Abrév.">
      <input type="color" data-k="couleur" value="${esc(p.couleur)}" aria-label="Couleur du pôle">
      <button type="button" class="icon" data-pdel="${i}" aria-label="Supprimer le pôle ${esc(p.nom)}">✕</button></div>`).join("");
}
let prEquipe = [];   // [{ nom, couleur }]
function renderPrEquipe() {
  $("#pr-equipe").innerHTML = prEquipe.map((p, i) => `<div class="pr-pers" data-i="${i}">
      <input data-k="nom" value="${esc(p.nom)}" required maxlength="60" aria-label="Nom" placeholder="Nom">
      <input type="color" data-k="couleur" value="${esc(p.couleur)}" aria-label="Couleur de ${esc(p.nom)}">
      <button type="button" class="icon" data-edel="${i}" aria-label="Retirer ${esc(p.nom)} de l'annuaire">✕</button></div>`).join("");
}
function openParams() {
  for (const el of $("#pr-form").querySelectorAll("[name]")) {
    const [a, b] = el.name.split(".");
    if (el.type === "checkbox") el.checked = !!S.config[a]?.[b];
    else el.value = S.config[a]?.[b] ?? "";
  }
  $("#pr-chemin").textContent = S.configChemin;
  prPoles = structuredClone(S.config.poles); renderPrPoles(); prMsg("");
  prEquipe = annuaire().map(nom => ({ nom, couleur: persoColor(nom) })); renderPrEquipe();
  prSection(0);
  $("#params").showModal();
}
// une rubrique à la fois : onglets construits à partir des <legend>
const prSets = [...document.querySelectorAll("#pr-form fieldset")];
$("#pr-nav").innerHTML = prSets.map((f, i) => `<button type="button" data-sec="${i}">${esc(f.querySelector("legend").firstChild.textContent.trim())}</button>`).join("");
function prSection(i) {
  prSets.forEach((f, j) => f.hidden = j !== i);
  $("#pr-nav").querySelectorAll("button").forEach((b, j) => b.setAttribute("aria-current", j === i));
}
$("#pr-nav").addEventListener("click", e => { const i = e.target.closest("[data-sec]")?.dataset.sec; if (i !== undefined) prSection(+i); });
// champ invalide dans une rubrique cachée : l'afficher pour que le navigateur puisse le signaler
$("#pr-form").addEventListener("invalid", e => { const i = prSets.indexOf(e.target.closest("fieldset")); if (i >= 0 && prSets[i].hidden) prSection(i); }, true);
$("#btn-params").addEventListener("click", openParams);
$("#pr-close").addEventListener("click", () => $("#params").close());
$("#pr-add-pole").addEventListener("click", () => { prPoles.push({ nom: "", court: "", couleur: "#888888" }); renderPrPoles(); });
$("#pr-add-pers").addEventListener("click", () => {
  prEquipe.push({ nom: "", couleur: PERSO[prEquipe.length % PERSO.length] }); renderPrEquipe();
  $("#pr-equipe").lastElementChild.querySelector("input").focus();
});
$("#pr-equipe").addEventListener("input", e => {
  const i = e.target.closest(".pr-pers")?.dataset.i, k = e.target.dataset.k;
  if (i !== undefined && k) prEquipe[+i][k] = e.target.value;
});
$("#pr-equipe").addEventListener("click", e => {
  const i = e.target.closest("[data-edel]")?.dataset.edel;
  if (i !== undefined) { prEquipe.splice(+i, 1); renderPrEquipe(); }
});
$("#pr-poles").addEventListener("input", e => {
  const i = e.target.closest(".pr-pole")?.dataset.i, k = e.target.dataset.k;
  if (i !== undefined && k) prPoles[+i][k] = e.target.value;
});
$("#pr-poles").addEventListener("click", e => {
  const i = e.target.closest("[data-pdel]")?.dataset.pdel;
  if (i !== undefined) { prPoles.splice(+i, 1); renderPrPoles(); }
});
$("#pr-test").addEventListener("click", e => busy(e.target, async () => {
  prMsg("Connexion…", true);
  try { prMsg((await (await api("POST", "/api/config/test-publication", { serveur: $('#pr-form [name="publication.serveur"]').value })).json()).message, true); }
  catch (err) { prMsg(err.message); }
}));
$("#pr-form").addEventListener("submit", async e => {
  e.preventDefault();
  const pers = prEquipe.map(p => ({ ...p, nom: p.nom.trim().replace(/\s+/g, " ") })).filter(p => p.nom);   // espaces comme le serveur
  const data = { poles: prPoles, equipe: pers.map(p => p.nom), equipe_couleurs: Object.fromEntries(pers.map(p => [p.nom, p.couleur])) };
  for (const el of e.target.querySelectorAll("[name]")) {
    const [a, b] = el.name.split(".");
    (data[a] ??= {})[b] = el.type === "number" ? Number(el.value) : el.type === "checkbox" ? el.checked : el.value;
  }
  try { await api("PUT", "/api/config", data); $("#params").close(); await load(); toast("Paramètres enregistrés"); }
  catch (err) { prMsg(err.message); }   // le message reste visible dans la fenêtre (le toast serait caché derrière)
});

// ---------- jalons ----------
function renderJalons() {
  $("#j-count").textContent = `(${S.jalons.length})`;
  $("#j-list").innerHTML = S.jalons.map((j, i) => `<li>${fmtD(j.date)} — ${esc(j.label)}
    <button class="icon" data-jdel="${i}" aria-label="Supprimer le jalon ${esc(j.label)}">✕</button></li>`).join("");
}
async function saveJalons(list) {
  try {
    S.jalons = (await (await api("PUT", "/api/jalons", { jalons: list })).json()).jalons;
    renderJalons(); renderGantt(); return true;
  } catch (e) { toast(e.message, true); return false; }
}

// ---------- jalons à venir (sous le Gantt) ----------
function renderJalonsVue(t0) {
  const today = toDate(S.today);
  const list = S.jalons.filter(j => toDate(j.date) >= t0).sort((a, b) => a.date.localeCompare(b.date));   // période et au-delà
  const box = $("#jalons-vue");
  box.hidden = !list.length;
  if (!list.length) return;
  const dans = d => { const n = Math.round((toDate(d) - today) / 864e5);
    return n === 0 ? "aujourd'hui" : n > 0 ? `dans ${n} j` : `il y a ${-n} j`; };
  box.innerHTML = `<h3>📍 Jalons</h3><div class="jl-list">` + list.map(j => {
    const d = toDate(j.date), passe = d < today;
    return `<div class="jl${passe ? " passe" : ""}${j.date === S.today ? " jour" : ""}">
      <span class="jl-date">${d.getDate()} ${MOIS[d.getMonth()].toLowerCase()} ${d.getFullYear()}</span>
      <b>◆ ${esc(j.label)}</b><span class="jl-dans">${dans(j.date)}</span></div>`;
  }).join("") + "</div>";
}

// ---------- qui travaille sur quoi (sous le Gantt) ----------
function renderEquipe(t0, t1) {
  const par = new Map();   // personne -> versions de la période : terminées (livrées dans la période) puis à faire
  for (const p of S.projets) for (const v of p.versions) {
    const a = toDate(v.debut), b = toDate(v.fin, true), fait = v.statut === "Terminé";
    if (fait ? !b || b < t0 || b > t1 : !a || !b || b < t0 || a > t1) continue;
    for (const n of equipeV(p, v)) par.set(n, [...(par.get(n) || []), { p, v, fait }]);
  }
  const box = $("#equipe-vue");
  box.hidden = !par.size || !S.config.application.qui_travaille;   // option des paramètres ; rien sans équipe renseignée
  if (!par.size) return;
  const per = d => `${MOIS[d.getMonth()]} ${d.getFullYear()}`;
  const chip = ({ p, v, fait }) => `<button class="chip ${stc(v.statut)}" style="--c:${color(p.pole)}" data-id="${p.id}" data-v="${esc(v.version)}"
      title="${esc(`${v.statut} · ${fmtD(v.debut)} → ${fmtD(v.fin)}`)}">${fait ? "✓ " : ["Bloqué", "En retard"].includes(v.statut) ? "⚠ " : ""}${esc(p.nom)} <b>${esc(v.version)}</b></button>`;
  const lignes = [...par].map(([n, l]) => {
    const faits = l.filter(x => x.fait).sort((x, y) => x.v.fin.localeCompare(y.v.fin));
    const afaire = l.filter(x => !x.fait).sort((x, y) => x.v.debut.localeCompare(y.v.debut));
    return { n, faits, afaire };
  }).sort((x, y) => y.afaire.length - x.afaire.length || x.n.localeCompare(y.n));   // les plus chargés d'abord
  box.innerHTML = `<h3>👥 Qui travaille sur quoi <span class="muted">${per(t0)} → ${per(t1)}</span></h3><div class="eq-table">` +
    lignes.map(({ n, faits, afaire }) => `
      <div class="eq-nom"><i class="eq-leg" style="background:${persoColor(n)}"></i>${esc(n)}</div>
      <div class="eq-items">${afaire.map(chip).join("") || '<span class="muted">rien en cours</span>'}
        ${faits.length ? `<span class="eq-faits" hidden><span class="eq-sep" aria-hidden="true"></span>${faits.map(chip).join("")}</span>` : ""}</div>
      <div class="eq-nb">${faits.length ? `<button type="button" class="eq-voir" aria-expanded="false"
          title="Afficher les ${faits.length} version(s) terminée(s) sur la période">${faits.length} ✓</button> · ` : ""}<span
          title="en cours ou à venir sur la période">${afaire.length}</span></div>`).join("") + "</div>";
}

$("#equipe-vue").addEventListener("click", e => {   // « 5 ✓ » : déplie / replie les versions terminées de la personne
  const b = e.target.closest(".eq-voir");
  if (!b) return;
  const faits = b.closest(".eq-nb").previousElementSibling.querySelector(".eq-faits"), ouvert = b.getAttribute("aria-expanded") === "true";
  faits.hidden = ouvert;
  b.setAttribute("aria-expanded", String(!ouvert));
});

// ---------- en production : une ligne par projet ----------
function parcFiltre() {   // onglet En production : filtre par pôle (bancs de dev, de prod…)
  const sel = $("#prod-pole"), poles = grouped(S.parc).map(([p]) => p), val = sel.value || store.get("prod-pole", "");
  sel.innerHTML = `<option value="">Tous les pôles</option>` + poles.map(p => `<option>${esc(p)}</option>`).join("");
  sel.value = poles.includes(val) ? val : "";
  return S.parc.filter(p => !sel.value || p.pole === sel.value);
}
function renderProd() {
  const parc = parcFiltre(), avecPostes = parc.some(p => p.postes?.length);   // colonne « Poste » seulement si utile
  const lignes = grouped(parc).flatMap(([pole, ps]) => ps.map(p => {
    const { livrees, enProd, derniere, suivante } = infoProd(p);
    const etatBloc = b => RO ? etatHtml(b) : `<div class="pe-l">
        <select class="pe" data-k="etat" aria-label="État de ${esc(p.nom)}${b.poste ? " — " + esc(b.poste) : ""}">${["", ...Object.keys(ETATS)].map(k =>
          `<option value="${k}" ${(b.etat || "") === k ? "selected" : ""}>${k ? ETATS[k].join(" ") + (k === "maj" && infoProd(b).cibleMaj ? " → " + esc(infoProd(b).cibleMaj.version) : "") : "—"}</option>`).join("")}</select>
        <input class="pe" type="date" data-k="etat_date" value="${b.etat_date || ""}" title="Depuis le" aria-label="État depuis le" ${b.etat ? "" : "hidden"}></div>
        <input class="pe pe-note" data-k="etat_note" value="${esc(b.etat_note || "")}" maxlength="120" placeholder="commentaire (ex. alim HS)" ${b.etat ? "" : "hidden"}>`;
    const vbtn = (v, html) => `<button class="link vlink" data-id="${p.id}" data-v="${esc(v.version)}" title="Voir ce qu'apporte ${esc(v.version)}">${html}</button>`;
    const prodBloc = b => {   // version en production du banc, ou de chaque poste (deux postes peuvent avoir des versions différentes)
      const { enProd, aDeployer } = infoProd(b);
      const champ = RO ? (enProd ? `▲ ${vbtn(enProd, `<b>${esc(enProd.version)}</b>`)} <span class="muted">· ${fmtD(enProd.prod)}</span>` : livrees.length ? "" : '<span class="muted">—</span>')
        : `<div class="pe-l"><select class="pe" data-k="prod_version" aria-label="Version en production de ${esc(p.nom)}${b.poste ? " — " + esc(b.poste) : ""}"><option value="">—</option>${livrees.map(v =>
            `<option ${enProd && v.version === enProd.version ? "selected" : ""}>${esc(v.version)}</option>`).join("")}</select>
          <input class="pe" type="date" data-k="prod_date" value="${enProd ? enProd.prod : ""}" title="En production depuis le" aria-label="En production depuis le" ${enProd ? "" : "hidden"}></div>`;
      // dernière livrée : seulement si elle apporte quelque chose (plus récente que la prod, ou prod inconnue)
      const info = RO ? "" : aDeployer ? `<div class="a-deployer">${vbtn(derniere, `<span class="badge st-En-retard">⚠ ${esc(derniere.version)} à déployer</span>`)} <span class="muted">livrée le ${fmtD(derniere.fin)}</span></div>`
        : !enProd && derniere ? `<div class="muted">dernière livrée : ${esc(derniere.version)} (${fmtD(derniere.fin)})</div>` : "";
      return champ + info;
    };
    // une ligne par poste (une seule sans poste) ; projet, pôle et prochaine version fusionnés sur les lignes du projet
    const blocs = postesDe(p), rs = blocs.length > 1 ? ` rowspan="${blocs.length}"` : "";
    const lignesP = blocs.map((b, n) => `<tr data-i="${b.i}">${n ? "" : `
      ${RO ? "" : `<td${rs}><input type="checkbox" class="pp" data-pid="${p.id}" ${p.prod_publie !== false ? "checked" : ""}
          aria-label="Afficher ${esc(p.nom)} sur la page publiée" title="Afficher sur la page publiée"></td>`}
      <td${rs}><button class="link" data-id="${p.id}" data-v="${esc((enProd || derniere || suivante || {}).version || "")}">${esc(p.nom)}</button></td>
      <td${rs}><i class="pt" style="background:${color(pole)}"></i>${esc(court(pole))}</td>`}
      ${avecPostes ? `<td class="poste-cell">${esc(b.poste || "")}</td>` : ""}
      <td class="etat-cell">${etatBloc(b)}</td>
      <td>${prodBloc(b)}</td>
      ${n ? "" : `<td${rs}>${suivante ? `${vbtn(suivante, `<b>${esc(suivante.version)}</b>`)} <span class="badge ${stc(suivante.statut)}">${esc(suivante.statut)}</span> <span class="muted">→ ${fmtD(suivante.fin)}</span>` : '<span class="muted">—</span>'}</td>`}
    </tr>`).join("");
    return `<tbody class="${p.prod_publie === false ? "non-publie" : ""}" data-pid="${p.id}">${lignesP}</tbody>`;
  }));
  $("#prod-table").innerHTML = lignes.length ? `<table class="prod"><thead><tr>${RO ? "" : '<th title="Afficher sur la page publiée">Publié</th>'}<th>Projet</th><th>Pôle</th>${avecPostes ? "<th>Poste</th>" : ""}<th>État</th><th>En production</th><th>Prochaine</th></tr></thead>${lignes.join("")}</table>` : '<p class="empty">Aucun projet.</p>';
}

$("#btn-csv").addEventListener("click", () => {   // tableau production -> Excel .xlsx (couleurs, filtres, en-tête figé)
  const etats = [""];   // état de chaque ligne, pour colorer la cellule
  const lignes = [["Projet", "Poste", "Pôle", "État", "Commentaire", "État depuis", "Version en production", "En production depuis",
                   "Version à déployer", "Livrée le", "Prochaine version", "Statut prochaine", "Fin prévue prochaine", "Équipe"]];
  for (const [pole, ps] of grouped(parcFiltre())) for (const p of ps) {
    const { suivante } = infoProd(p);
    for (const b of postesDe(p)) {   // une ligne par poste, avec sa version
      const { enProd, derniere } = infoProd(b), aDeployer = !RO && infoProd(b).aDeployer;   // page publiée : pas de « à déployer »
      lignes.push([p.nom, b.poste || "", pole, ETATS[b.etat]?.[1] || "", b.etat_note, fmtD(b.etat_date || ""), enProd?.version, enProd ? fmtD(enProd.prod) : "",
                   aDeployer ? derniere.version : "", aDeployer ? fmtD(derniere.fin) : "", suivante?.version, suivante?.statut,
                   suivante ? fmtD(suivante.fin) : "", liste(p.ressources).join(", ")]);
      etats.push(b.etat);
    }
  }
  telecharger(xlsx(lignes, (l, i) => i ? [, , color(l[2]), XL_ETATS[etats[i]]] : []),
              `${S.config.application.titre} - En production ${S.today}.xlsx`,
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet");
});
const XL_ETATS = { ok: "#C6EFCE", maj: "#DDEBF7", degrade: "#FFEB9C", panne: "#FFC7CE" };   // fonds clairs fa\u00e7on Excel
// lignes : tableau de lignes (la 1re = en-t\u00eate) ; fonds(ligne, i) -> couleur #rrggbb par colonne (p\u00f4le : texte blanc)
function xlsx(lignes, fonds) {
  const x = s => esc(s).replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g, "");   // caract\u00e8res interdits en XML
  const styles = ["0,0,1"], sid = (fill, font) => {   // style = "fond,police,bordure" ; fonds dynamiques (couleurs des p\u00f4les)
    const k = `${fill},${font},1`, i = styles.indexOf(k); return i >= 0 ? i : styles.push(k) - 1; };
  const fills = [], fid = c => { if (!c) return 0; const i = fills.indexOf(c); return 2 + (i >= 0 ? i : fills.push(c) - 1); };
  const col = j => String.fromCharCode(65 + j), n = lignes.length, m = lignes[0].length;
  const rows = lignes.map((l, i) => `<row r="${i + 1}">${l.map((v, j) => {
    const f = i ? fonds(l, i)[j] : "#1F3864", s = sid(fid(f), !i || j === 2 ? 1 : j === 0 ? 2 : 0);
    return `<c r="${col(j)}${i + 1}" s="${s}" t="inlineStr"><is><t xml:space="preserve">${x(v)}</t></is></c>`; }).join("")}</row>`).join("");
  const larg = lignes[0].map((_, j) => Math.min(60, Math.max(...lignes.map(l => String(l[j] ?? "").length)) + 3));
  const fichiers = {
    "[Content_Types].xml": `<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>`,
    "_rels/.rels": `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>`,
    "xl/workbook.xml": `<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="En production" sheetId="1" r:id="r1"/></sheets><definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'En production'!$A$1:$${col(m - 1)}$${n}</definedName></definedNames></workbook>`,
    "xl/_rels/workbook.xml.rels": `<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/><Relationship Id="r2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>`,
    "xl/worksheets/sheet1.xml": `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><cols>${larg.map((w, j) => `<col min="${j + 1}" max="${j + 1}" width="${w}" customWidth="1"/>`).join("")}</cols><sheetData>${rows}</sheetData><autoFilter ref="A1:${col(m - 1)}${n}"/></worksheet>`,
  };
  fichiers["xl/styles.xml"] = `<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><fonts count="3"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font></fonts><fills count="${2 + fills.length}"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>${fills.map(c => `<fill><patternFill patternType="solid"><fgColor rgb="FF${c.slice(1).toUpperCase()}"/></patternFill></fill>`).join("")}</fills><borders count="2"><border/><border>${["left", "right", "top", "bottom"].map(b => `<${b} style="thin"><color rgb="FFBFBFBF"/></${b}>`).join("")}</border></borders><cellStyleXfs count="1"><xf/></cellStyleXfs><cellXfs count="${styles.length}">${styles.map(k => { const [f, p, b] = k.split(","); return `<xf fillId="${f}" fontId="${p}" borderId="${b}" applyFill="1" applyFont="1" applyBorder="1"><alignment vertical="center" wrapText="1"/></xf>`; }).join("")}</cellXfs></styleSheet>`;
  return zip(fichiers);
}
function zip(fichiers) {   // archive ZIP sans compression (suffit pour Excel)
  const enc = new TextEncoder(), crcT = [...Array(256)].map((_, n) => { for (let k = 0; k < 8; k++) n = n & 1 ? 0xEDB88320 ^ (n >>> 1) : n >>> 1; return n >>> 0; });
  const crc = d => { let c = -1; for (const o of d) c = crcT[(c ^ o) & 255] ^ (c >>> 8); return (c ^ -1) >>> 0; };
  const u = (...v) => { const b = new DataView(new ArrayBuffer(v.length * 4)); let o = 0;   // [taille en octets, valeur]\u2026
    for (let i = 0; i < v.length; i += 2) { v[i] === 2 ? b.setUint16(o, v[i + 1], true) : b.setUint32(o, v[i + 1], true); o += v[i]; }
    return new Uint8Array(b.buffer, 0, o); };
  const parts = [], central = []; let off = 0;
  for (const [nom, txt] of Object.entries(fichiers)) {
    const n = enc.encode(nom), d = enc.encode('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n' + txt), c = crc(d);
    const commun = [2, 20, 2, 0, 2, 0, 2, 0, 2, 33, 4, c, 4, d.length, 4, d.length, 2, n.length, 2, 0];
    parts.push(u(4, 0x04034b50, ...commun), n, d);
    central.push(u(4, 0x02014b50, 2, 20, ...commun, 2, 0, 2, 0, 2, 0, 4, 0, 4, off), n);
    off += 30 + n.length + d.length;
  }
  const taille = central.reduce((s, p) => s + p.length, 0), k = Object.keys(fichiers).length;
  return new Blob([...parts, ...central, u(4, 0x06054b50, 2, 0, 2, 0, 2, k, 2, k, 4, taille, 4, off, 2, 0)]);
}
function telecharger(texte, nom, type) {
  const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([texte], { type })), download: nom });
  document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// 2. export draw.io de la roadmap (période affichée) : fichier .drawio modifiable
function exportDrawio() {
  const t0 = toDate($("#debut").value), t1 = toDate($("#fin").value, true);
  if (!t0 || !t1 || t1 < t0) { toast("Choisis une période valide", true); return; }
  const span = (t1 - t0) / 864e5 + 1, X0 = 290, W = 1300, ROW = 30, TOP = 90;
  const x = d => X0 + Math.min(W, Math.max(0, (d - t0) / 864e5 / span * W));
  const cells = []; let id = 2;
  const box = (val, X, Y, w, h, style) => cells.push(`<mxCell id="c${id++}" value="${esc(val)}" style="${style}" vertex="1" parent="1">` +
    `<mxGeometry x="${Math.round(X)}" y="${Math.round(Y)}" width="${Math.max(1, Math.round(w))}" height="${Math.round(h)}" as="geometry"/></mxCell>`);
  const ligne = (X, y0, y1, style) => cells.push(`<mxCell id="c${id++}" style="endArrow=none;html=1;${style}" edge="1" parent="1"><mxGeometry relative="1" as="geometry">` +
    `<mxPoint x="${Math.round(X)}" y="${y0}" as="sourcePoint"/><mxPoint x="${Math.round(X)}" y="${y1}" as="targetPoint"/></mxGeometry></mxCell>`);
  const per = d => `${MOIS[d.getMonth()]} ${d.getFullYear()}`;
  box(`${S.config.application.titre} (${per(t0)} – ${per(t1)})`, 40, 20, X0 + W - 40, 36, "text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=middle;fontColor=#da1f3d;");
  for (let m = new Date(t0.getFullYear(), t0.getMonth(), 1), k = 0; m <= t1; m = new Date(m.getFullYear(), m.getMonth() + 1, 1), k++) {
    const a = x(m < t0 ? t0 : m), b = x(new Date(m.getFullYear(), m.getMonth() + 1, 1));
    box(`${MOIS[m.getMonth()]} ${String(m.getFullYear()).slice(2)}`, a, TOP - 30, b - a, 26,
        `rounded=0;html=1;fillColor=${k % 2 ? "#7f7f7f" : "#595959"};strokeColor=#ffffff;fontColor=#ffffff;fontStyle=1;fontSize=12;`);
  }
  let y = TOP;
  const STY = { "Terminé": "opacity=45;strokeColor=none;", "Planifié": "fillColor=#ffffff;dashed=1;strokeWidth=2;",
                "Bloqué": "strokeColor=#000000;strokeWidth=2;", "En retard": `strokeColor=${S.config.couleurs.retard};strokeWidth=3;` };
  for (const [pole, list] of grouped(visibles())) {
    const y0 = y, c = color(pole);
    for (const p of list) {
      const bars = p.versions.map(v => ({ v, a: toDate(v.debut), b: toDate(v.fin, true) }))
        .filter(o => o.a && o.b && o.b >= t0 && o.a <= t1).sort((m, n) => m.a - n.a)
        .map(o => { const txt = (["Bloqué", "En retard"].includes(o.v.statut) ? "⚠ " : "") + o.v.version + fmtDer(derive(o.v));
          const l = x(o.a), w = Math.max(x(o.b) - l, txt.length * 7 + 14); return { ...o, txt, l: Math.min(l, X0 + W - w), w }; });
      if (!bars.length) continue;
      const lanes = [];
      for (const o of bars) { const ln = lanes.find(ln => ln[ln.length - 1].l + ln[ln.length - 1].w + 4 < o.l); ln ? ln.push(o) : lanes.push([o]); }
      box(p.nom, 80, y, X0 - 90, ROW * lanes.length, "text;html=1;align=left;verticalAlign=middle;fontSize=12;whiteSpace=wrap;");   // après la colonne des pôles
      lanes.forEach(ln => {
        for (const o of ln) box(o.txt, o.l, y + 4, o.w, ROW - 8, `rounded=1;whiteSpace=wrap;html=1;fillColor=${c};strokeColor=${c};` +
          `fontColor=${o.v.statut === "Planifié" ? c : "#ffffff"};fontStyle=1;fontSize=11;${STY[o.v.statut] || ""}`);
        y += ROW;
      });
    }
    if (y > y0) box(court(pole), 40, y0, 30, y - y0, `rounded=0;html=1;horizontal=0;fillColor=${c};strokeColor=none;fontColor=#ffffff;fontStyle=1;fontSize=11;`);
    y += 6;
  }
  const today = toDate(S.today);
  if (today >= t0 && today <= t1) {
    ligne(x(today), TOP - 4, y, `dashed=1;strokeWidth=2;strokeColor=${S.config.couleurs.aujourdhui};`);
    box(`Aujourd'hui (${fmtD(S.today).slice(0, 5)})`, x(today) - 60, y + 4, 120, 20, `text;html=1;align=center;fontSize=11;fontStyle=1;fontColor=${S.config.couleurs.aujourdhui};`);
  }
  for (const j of S.jalons) {
    const d = toDate(j.date);
    if (d < t0 || d > t1) continue;
    ligne(x(d), TOP - 4, y, `strokeWidth=2;strokeColor=${S.config.couleurs.jalon};`);
    box(`◆ ${j.label} (${fmtD(j.date).slice(0, 5)})`, x(d) - 80, y + 24, 160, 20, `text;html=1;align=center;fontSize=11;fontStyle=1;fontColor=${S.config.couleurs.jalon};`);
  }
  const xml = `<mxfile host="roadmap-bancs"><diagram name="Roadmap" id="roadmap"><mxGraphModel grid="0" page="1" pageWidth="${X0 + W + 40}" ` +
    `pageHeight="${y + 70}" background="#ffffff"><root><mxCell id="0"/><mxCell id="1" parent="0"/>${cells.join("")}</root></mxGraphModel></diagram></mxfile>`;
  telecharger(xml, `${S.config.application.titre} - Roadmap ${$("#debut").value} a ${$("#fin").value}.drawio`, "application/xml");
  toast("Fichier draw.io généré (à ouvrir dans draw.io / diagrams.net)");
}
$("#btn-drawio").addEventListener("click", exportDrawio);

$("#prod-table").addEventListener("change", async e => {   // état / version en production : enregistrés tout de suite
  const c = e.target.closest(".pe");
  if (!c) return;
  const tr = c.closest("tbody"), p = S.projets.find(x => x.id === tr.dataset.pid);   // les lignes du projet
  const blocs = postesDe(p), i = +c.closest("[data-i]").dataset.i;   // un bloc par poste (un seul sans poste)
  const champ = (k, j = i) => tr.querySelector(`[data-i="${j}"] [data-k="${k}"]`);
  const versions = p.versions.map(v => ({ ...v }));
  const actuelle = infoProd(blocs[i]).enProd;   // version qui tourne sur ce poste (ou ce banc)
  const livraison = v => v?.fin?.length === 10 ? v.fin : S.today;   // date « Terminé » de la version (sinon aujourd'hui)
  // dates proposées, modifiables : opérationnel depuis la mise en prod ; mise en prod = date de livraison de la version
  // opérationnel : depuis la mise en prod, sinon la livraison de la dernière version, sinon aujourd'hui
  if (c.dataset.k === "etat") champ("etat_date").value = !c.value ? "" : c.value !== "ok" ? S.today
    : actuelle ? actuelle.prod : livraison(infoProd(p).derniere);
  if (c.dataset.k === "prod_version" && c.value)
    champ("prod_date").value = c.value === actuelle?.version ? actuelle.prod : livraison(versions.find(v => v.version === c.value));
  const choix = champ("prod_version").value, quand = champ("prod_date").value || S.today;
  let fini = "";   // mise à jour terminée : nouvelle version installée sur un banc / poste « en mise à jour » → opérationnel
  if (c.dataset.k === "prod_version" && choix && choix !== actuelle?.version && champ("etat").value === "maj") {
    champ("etat").value = "ok"; champ("etat_date").value = quand; champ("etat_note").value = "";
    fini = ` — mise à jour terminée : ${choix} installée${blocs[i].poste ? " sur " + blocs[i].poste : ""}, ✅ opérationnel`;
  }
  const lire = j => ({ etat: champ("etat", j).value, etat_note: champ("etat_note", j).value,
                       etat_date: champ("etat", j).value ? champ("etat_date", j).value : "" });
  let corps;
  if (p.postes?.length) {   // chaque poste garde sa version
    const postes = p.postes.map((x, j) => { const v = champ("prod_version", j).value;
      return { nom: x.nom, ...lire(j), version: v, version_date: v ? champ("prod_date", j).value || S.today : "" }; });
    for (const x of postes) {   // ▲ du Gantt : première mise en production de la version, tous postes confondus
      const v = versions.find(w => w.version === x.version);
      if (v && (!v.prod || x.version_date < v.prod)) v.prod = x.version_date;
    }
    corps = { ...p, versions, postes };
  } else {
    if (!choix) { if (actuelle) versions.find(v => v.version === actuelle.version).prod = ""; }   // « — » : plus rien en production
    else versions.find(v => v.version === choix).prod = quand;   // l'historique des autres est gardé
    corps = { ...p, versions, ...lire(0) };
  }
  try {
    await api("PUT", `/api/projets/${p.id}`, corps);
    await load(); toast(`${p.nom} : enregistré${fini}`);
  } catch (err) { toast(err.message, true); renderProd(); }
});
$("#prod-table").addEventListener("change", async e => {   // case « Publié » : enregistrée tout de suite
  const c = e.target.closest(".pp");
  if (!c) return;
  const p = S.projets.find(x => x.id === c.dataset.pid);
  try {
    await api("PUT", `/api/projets/${p.id}`, { ...p, prod_publie: c.checked });
    p.prod_publie = c.checked; c.closest("tbody").classList.toggle("non-publie", !c.checked);
    toast(`${p.nom} : ${c.checked ? "affiché" : "masqué"} sur la page publiée (à la prochaine publication)`);
  } catch (err) { c.checked = !c.checked; toast(err.message, true); }
});

// conformité au standard (constatée au dernier import) : liste de ce qui manque, null = pas encore importé
function manques(p) {
  if (!p.depot) return ["dépôt"];
  const c = p.conformite;
  return c ? [["roadmap", "ROADMAP.md"], ["changelog", "CHANGELOG.md"], ["tags", "tags Git"]].filter(([k]) => !c[k]).map(([, n]) => n) : null;
}

// ---------- cartes ----------
function renderCards() {
  const q = $("#search").value.trim().toLowerCase();
  const poles = grouped(S.projets);
  let sel = store.get("pole", "");
  if (!poles.some(([p]) => p === sel)) sel = "";   // pôle disparu : retour à « Tous »
  $("#pole-tabs").innerHTML = [["", S.projets], ...poles].map(([p, ps]) =>
    `<button data-pole="${esc(p)}" aria-pressed="${p === sel}" aria-selected="${p === sel}">` +
    (p ? `<i style="background:${color(p)}"></i>${esc(court(p))}` : "Tous") + ` <span class="muted">${ps.length}</span></button>`).join("");
  const nc = $("#f-nc").checked;
  const list = S.projets.filter(p => (!sel || p.pole === sel) && (!nc || manques(p)?.length) &&
    (!q || [p.nom, p.pole, ...(p.ressources || [])].join(" ").toLowerCase().includes(q)));   // recherche aussi par personne
  $("#cards").innerHTML = grouped(list).map(([pole, ps]) => `
    <div class="pole-title"><i style="background:${color(pole)}"></i>${esc(pole)} · ${ps.length}</div>
    <div class="cards">${ps.map(p => {
      const a = actuelle(p), n = prochaine(p), al = alertes(p);
      const warn = al.length ? `<span class="warn" title="${esc(al.map(([v, t]) => `${v.version} : ${t}`).join("\n"))}"
                                     aria-label="${al.length} alerte(s)">⚠ ${al.length}</span>` : "";
      return `<button class="card" style="--c:${color(pole)}" data-id="${p.id}">
        <h4>${esc(p.nom)} ${warn}${pire(p) ? ` <span title="${esc(postesDe(p).map(b => (b.poste ? b.poste + " : " : "") + (ETATS[b.etat]?.[1] || "—") + (b.etat_note ? " (" + b.etat_note + ")" : "")).join("\n"))}">${ETATS[pire(p)][0]}</span>` : ""}</h4>
        <div class="kv"><span class="muted">Actuelle</span><b>${a ? esc(a.version) : "—"}</b></div>
        <div class="kv"><span class="muted">Prochaine</span><span>${n ? `<b>${esc(n.version)}</b> <span class="badge ${stc(n.statut)}">${esc(n.statut)}</span>` : "—"}</span></div>
        ${n && n.motif ? `<div class="kv"><span class="muted">Attend</span><span>${esc(n.motif)}</span></div>` : ""}
        ${n && derive(n) ? `<div class="kv"><span class="muted">Dérive</span><span>${fmtDer(derive(n)).trim()}</span></div>` : ""}
        <div class="kv"><span class="muted">Versions</span><span>${p.versions.length}</span></div>
        ${equipe(p) ? `<div class="kv"><span class="muted">Équipe</span><span class="equipe">${esc(equipe(p))}</span></div>` : ""}
        ${(m => m === null || !p.depot ? "" : m.length ? `<div class="kv"><span class="muted">Standard</span><span class="nc-txt" title="Manque : ${esc(m.join(", "))} (voir modeles/GUIDE.md)">✗ ${esc(m.map(x => x.replace(".md", "")).join(" · "))}</span></div>`
          : `<div class="kv"><span class="muted">Standard</span><span class="ok" title="Vérifié à l'import du ${fmtD(p.conformite.date)}">✓ conforme</span></div>`)(manques(p))}
        <div class="repo">${p.depot ? "⎇ " + esc(p.depot.split(/[/:]/).pop()) + (p.branche ? ` (${esc(p.branche)})` : "") : "pas de dépôt"}</div>
      </button>`;
    }).join("")}</div>`).join("") || `<p class="empty">Aucun projet.</p>`;
}

// ---------- choix de l'équipe : étiquettes + saisie avec suggestions de l'annuaire ----------
const annuaire = () => S.config.equipe || [];
const majAnnuaireDl = () => { $("#annuaire-dl").innerHTML = annuaire().map(n => `<option value="${esc(n)}">`).join(""); };
function pickerHtml(scope, choisis) {
  return `<div class="picker" data-scope="${scope}">` +
    choisis.map(n => `<span class="tag"><i class="eq-leg" style="background:${persoColor(n)}"></i>${esc(n)}<button type="button"
      class="tag-x" data-nom="${esc(n)}" aria-label="Retirer ${esc(n)}" title="Retirer">✕</button></span>`).join("") +
    `<input class="pick-add" list="annuaire-dl" maxlength="60" placeholder="${choisis.length ? "+ ajouter" : "Ajouter une personne…"}"
      aria-label="Ajouter une personne à l'équipe : nom de l'annuaire ou nouveau nom (Entrée)"></div>`;
}
const cibleEquipe = scope => scope === "projet" ? edit : edit.versions[+scope.slice(2)];
function majEquipe(picker, noms) {   // remplace l'équipe de la cible, redessine, garde le curseur dans la saisie
  const scope = picker.dataset.scope;
  cibleEquipe(scope).ressources = noms;
  setDirty(true);
  if (scope === "projet") renderVersions();   // le rappel « équipe du projet » des versions suit
  picker.outerHTML = pickerHtml(scope, noms);
  $(`#drawer .picker[data-scope="${scope}"] .pick-add`)?.focus();
}
async function ajouterPersonnes(input) {   // « A, B » collé : plusieurs personnes d'un coup
  const picker = input.closest(".picker"), l = liste(cibleEquipe(picker.dataset.scope).ressources);
  const saisis = input.value.split(",").map(n => n.replace(/\s+/g, " ").trim()).filter(Boolean);
  if (!saisis.length) return;
  const nouveaux = saisis.filter(n => !annuaire().some(x => x.toLowerCase() === n.toLowerCase()));
  try {
    if (nouveaux.length) {   // nouvelle personne : rangée dans l'annuaire
      S.config = (await (await api("PUT", "/api/config", { equipe: [...annuaire(), ...nouveaux] })).json()).config;
      majAnnuaireDl();
    }
  } catch (err) { return toast(err.message, true); }
  const noms = saisis.map(n => annuaire().find(x => x.toLowerCase() === n.toLowerCase()) || n);   // orthographe de l'annuaire
  majEquipe(picker, [...new Set([...l, ...noms])]);
}
$("#drawer").addEventListener("click", e => {
  const x = e.target.closest(".tag-x");
  if (x) { const picker = x.closest(".picker"); majEquipe(picker, liste(cibleEquipe(picker.dataset.scope).ressources).filter(n => n !== x.dataset.nom)); }
  else if (e.target.matches(".picker")) e.target.querySelector(".pick-add").focus();   // clic dans le cadre : on peut taper
});
$("#drawer").addEventListener("keydown", e => {
  if (!e.target.matches(".pick-add")) return;
  if (e.key === "Enter" || e.key === ",") { e.preventDefault(); ajouterPersonnes(e.target); }
  else if (e.key === "Backspace" && !e.target.value) {   // effacer dans une saisie vide : retire la dernière personne
    const picker = e.target.closest(".picker"), l = liste(cibleEquipe(picker.dataset.scope).ressources);
    if (l.length) { e.preventDefault(); majEquipe(picker, l.slice(0, -1)); }
  }
});
$("#drawer").addEventListener("input", e => {   // nom choisi dans les suggestions : ajouté tout de suite
  if (e.target.matches(".pick-add") && (!e.inputType || e.inputType === "insertReplacementText") && annuaire().includes(e.target.value))
    ajouterPersonnes(e.target);
});

// ---------- éditeur ----------
const estUrl = d => /^((https?|ssh|file):\/\/|git@)/.test(d || "");
function setBranches(list, defaut, choisie) {
  $("#f-branche").innerHTML = `<option value="">branche par défaut${defaut ? ` (${esc(defaut)})` : ""}</option>` +
    [...new Set([...list, choisie].filter(Boolean))].map(b => `<option ${b === choisie ? "selected" : ""}>${esc(b)}</option>`).join("");
}
function majDepot() {   // lien Git : choix de la branche ; écriture dans le dépôt seulement pour un dossier local
  const url = estUrl($("#f-depot").value.trim());
  $("#branche-row").hidden = !url;
  for (const id of ["#b-exp-rel", "#b-exp-chg"]) {
    $(id).dataset.title ??= $(id).title;   // infobulle d'origine, rétablie pour un dossier local
    $(id).disabled = url;
    $(id).title = url ? "Dépôt distant : l'écriture demande un dossier local (clone du dépôt)" : $(id).dataset.title;
  }
}
function openEditor(p) {
  edit = p ? structuredClone(p) : { id: null, nom: "", pole: S.poles[0], depot: "", ressources: [], versions: [] };
  $("#d-title").textContent = p ? p.nom : "Nouveau projet";
  $("#f-nom").value = edit.nom;
  $("#f-pole").innerHTML = [...new Set([...S.poles, edit.pole])].map(x => `<option ${x === edit.pole ? "selected" : ""}>${esc(x)}</option>`).join("");
  $("#f-depot").value = edit.depot || "";
  $("#f-postes").value = (edit.postes || []).map(x => x.nom).join(", ");
  majAnnuaireDl();
  $("#f-ressources").innerHTML = pickerHtml("projet", liste(edit.ressources));
  setBranches(edit.branche ? [edit.branche] : [], "", edit.branche || "");
  majDepot();
  $("#b-del").hidden = !p;
  $("#depot-btns").hidden = !p;
  if (p) {
    $("#b-dl-rel").href = `/api/projets/${p.id}/release`;
    $("#b-dl-chg").href = `/api/projets/${p.id}/changelog`;
  }
  renderVersions(); setDirty(false);
  if (RO) $("#drawer").querySelectorAll("input, select, textarea").forEach(el => el.disabled = true);
  $("#drawer-bg").hidden = false; $("#drawer").classList.add("open"); $("#drawer").setAttribute("aria-hidden", "false");
  setTimeout(() => $("#f-nom").focus(), 50);
}
function closeEditor(force) {
  if (!force && dirty && !confirm("Des modifications ne sont pas enregistrées. Fermer quand même ?")) return;
  $("#drawer").classList.remove("open"); $("#drawer").setAttribute("aria-hidden", "true"); $("#drawer-bg").hidden = true; edit = null;
}
function setDirty(v) { dirty = v; $("#dirty").hidden = !v; }
// date de version : texte libre (AAAA-MM-JJ, AAAA-MM ou ? venant des dépôts) + calendrier 📅 pour choisir un jour
const champDate = (f, val) => `<span class="date-l"><input data-f="${f}" value="${esc(val)}" placeholder="AAAA-MM-JJ">` +
  `<button type="button" class="icon" data-cal title="Choisir dans le calendrier" aria-label="Calendrier">📅</button>` +
  `<input type="date" class="cal-in" tabindex="-1" aria-hidden="true"></span>`;
function renderVersions() {
  $("#v-count").textContent = `(${edit.versions.length})`;
  const stColor = { "Terminé": "#16a34a", "En cours": "#0d9488", "Planifié": "#6366f1", "Bloqué": "#ea580c", "En retard": "#dc2626" };
  const peutLivrer = edit.id && edit.depot && !estUrl(edit.depot);   // livrer = écrire + commit : dossier local seulement
  $("#versions").innerHTML = edit.versions.map((v, i) => `
    <div class="ver" style="--sc:${stColor[v.statut] || "var(--line)"}" data-i="${i}">
      <div class="ver-top">
        <label>Version<input data-f="version" value="${esc(v.version)}" placeholder="v1.0.0"></label>
        <label>Statut<select data-f="statut"><option value="">auto (${MANUELS.includes(v.statut) || !v.statut ? "dates" : esc(v.statut)})</option>${MANUELS.map(s => `<option ${s === v.statut ? "selected" : ""}>${s}</option>`).join("")}</select></label>
        <label>Début${champDate("debut", v.debut)}</label>
        <label>Fin / livraison${champDate("fin", v.fin)}</label>
        <button class="icon" data-del="${i}" title="Supprimer cette version" aria-label="Supprimer la version ${esc(v.version)}">🗑</button>
      </div>
      ${alerte(v) ? `<p class="ver-warn">⚠ ${esc(alerte(v))}</p>` : ""}
      <div class="ver-meta">
        ${v.statut === "Bloqué" ? `<label>Motif du blocage<input data-f="motif" value="${esc(v.motif)}" maxlength="80" placeholder="ex. attente cartes"></label>` : ""}
        <div class="ver-eq">Équipe de la version <span class="muted">(rien de choisi = équipe du projet${equipe(edit) ? " : " + esc(equipe(edit)) : ""})</span>
          ${pickerHtml("v:" + i, liste(v.ressources))}</div>
        ${v.prevu && v.prevu !== v.fin ? `<span class="muted">Fin prévue initialement : ${fmtD(v.prevu)}${fmtDer(derive(v))}
          <button type="button" class="icon" data-efface="${i}" title="Erreur de saisie : oublier cette date prévue (plus de dérive)"
            aria-label="Effacer la date prévue de ${esc(v.version)}">✕</button></span>` : ""}
        <span class="spacer"></span>
        ${v.statut !== "Terminé" && vkey(v.version) ? `<button class="btn" data-livrer="${i}" ${peutLivrer ? "" : "disabled"}
            title="${peutLivrer ? "Terminé + fin aujourd'hui, ROADMAP.md / CHANGELOG.md écrits, commit et tag Git (sans push)" : "Renseigne et enregistre le dossier du dépôt d'abord"}">🚀 Livrer</button>` : ""}
      </div>
      <textarea data-f="notes" placeholder="Fonctionnalités / changements (markdown : - item, ### Added…)">${esc(v.notes)}</textarea>
    </div>`).join("") || `<p class="muted">Aucune version. Ajoute-en une, ou importe le ROADMAP.md / CHANGELOG.md du dépôt.</p>`;
}
function readForm() {
  edit.nom = $("#f-nom").value.trim(); edit.pole = $("#f-pole").value; edit.depot = $("#f-depot").value.trim();
  edit.branche = estUrl(edit.depot) ? $("#f-branche").value : "";
}
// date de fin modifiée sans date prévue : demander si c'est un décalage du planning ou une correction de saisie
const cleV = v => (vkey(v.version) || [v.version]).join(".");
function finsModifiees() {
  const orig = edit.id && S.projets.find(p => p.id === edit.id);
  if (!orig) return [];
  return edit.versions.map(v => ({ v, o: orig.versions.find(x => cleV(x) === cleV(v)) }))
    .filter(({ v, o }) => o && o.fin && v.fin !== o.fin && (!v.prevu || v.prevu_efface));
}
function demanderDecalage(changes) {
  return new Promise(resolve => {
    $("#dc-liste").innerHTML = changes.map(({ v, o }, i) => {
      const n = v.fin ? Math.round((toDate(v.fin, true) - toDate(o.fin, true)) / 864e5) : 0;
      return `<fieldset class="dc"><legend><b>${esc(v.version)}</b> : fin ${fmtD(o.fin)} → ${fmtD(v.fin)}${fmtDer(n)}</legend>
        <label><input type="radio" name="dc${i}" value="1" required> 📅 Décalage du planning — ${fmtD(o.fin)} reste la date prévue, la dérive est affichée</label>
        <label><input type="radio" name="dc${i}" value="0"> ✏️ Correction d'une erreur de saisie — pas de dérive</label></fieldset>`;
    }).join("");
    const dlg = $("#decalage"), fin = ok => { if (dlg.open) dlg.close(); resolve(ok); };
    $("#dc-form").onsubmit = e => {
      e.preventDefault();
      changes.forEach(({ v }, i) => { v.decalage = e.target.elements["dc" + i].value === "1"; });
      fin(true);
    };
    $("#dc-annuler").onclick = () => fin(false);
    dlg.oncancel = () => resolve(false);   // Échap
    dlg.showModal();
  });
}
async function save() {
  if (RO) return false;
  readForm();
  if (!edit.nom) { toast("Le nom du projet est obligatoire", true); return false; }
  const changes = finsModifiees();
  if (changes.length && !(await demanderDecalage(changes))) return false;   // annulé : rien n'est enregistré
  try {
    const body = { nom: edit.nom, pole: edit.pole, depot: edit.depot, branche: edit.branche, ressources: edit.ressources,
                   etat: edit.etat, etat_note: edit.etat_note, etat_date: edit.etat_date, prod_publie: edit.prod_publie,
                   postes: liste($("#f-postes").value).map(n => (edit.postes || []).find(x => x.nom.toLowerCase() === n.toLowerCase()) || { nom: n }),   // état gardé par nom   // gérés dans 📦 En production
                   versions: edit.versions };
    const r = edit.id ? await api("PUT", `/api/projets/${edit.id}`, body) : await api("POST", "/api/projets", body);
    const p = await r.json();
    await load(); setDirty(false); toast("Enregistré"); openEditor(p); return true;
  } catch (e) { toast(e.message, true); return false; }
}
async function busy(btn, fn) { btn.disabled = true; try { await fn(); } finally { btn.disabled = false; } }

// ---------- événements ----------
// menu ☰ : se referme après un choix, un clic ailleurs ou Échap
document.addEventListener("click", e => { if (!e.target.closest("#menu summary") && (e.target.closest(".menu-pop button") || !e.target.closest("#menu"))) $("#menu").open = false; });
document.addEventListener("keydown", e => { if (e.key === "Escape" && $("#menu").open) { $("#menu").open = false; $("#menu summary").focus(); } });
document.querySelectorAll(".top .tabs button").forEach(b => b.addEventListener("click", () => {
  document.querySelectorAll(".top .tabs button").forEach(x => x.setAttribute("aria-selected", x === b));
  for (const v of ["roadmap", "projets", "prod"]) $("#view-" + v).hidden = b.dataset.view !== v;
  store.set("vue", b.dataset.view);
}));
["debut", "fin", "g-pole", "g-statut"].forEach(id => $("#" + id).addEventListener("change", e => { store.set(id, e.target.value); renderGantt(); }));
window.addEventListener("resize", () => renderGantt());
// période : 📅 ouvre un calendrier des mois (navigateurs qui savent afficher input type=month ; sinon bouton masqué)
document.querySelectorAll("[data-calm]").forEach(b => {
  const sel = b.previousElementSibling, cal = b.nextElementSibling;
  if (cal.type !== "month") { b.hidden = true; return; }
  b.addEventListener("click", e => { e.preventDefault(); cal.value = sel.value; try { cal.showPicker(); } catch (_) { cal.focus(); } });
  cal.addEventListener("change", () => {
    if (!cal.value) return;
    if (![...sel.options].some(o => o.value === cal.value)) {   // mois hors de la liste : on l'élargit
      const [d, f] = [$("#debut").value, $("#fin").value];
      remplirMois([d, f, cal.value]); $("#debut").value = d; $("#fin").value = f;
    }
    sel.value = cal.value;
    sel.dispatchEvent(new Event("change"));   // même chemin que la liste : mémorisé, Gantt redessiné
  });
});
$("#search").addEventListener("input", renderCards);
$("#f-nc").addEventListener("change", renderCards);
$("#prod-pole").addEventListener("change", e => { store.set("prod-pole", e.target.value); renderProd(); });
$("#pole-tabs").addEventListener("click", e => {
  const b = e.target.closest("button[data-pole]");
  if (b) { store.set("pole", b.dataset.pole); renderCards(); }
});
document.addEventListener("click", e => {
  const el = e.target.closest("[data-id]");
  if (!el || e.target.closest(".drawer")) return;
  const trouve = l => l.find(p => p.id === el.dataset.id);   // vue production : historique complet (parc)
  const p = (e.target.closest(".vlink") && trouve(S.parc)) || trouve(S.projets) || trouve(S.parc);
  if (!p) return;
  const vl = e.target.closest(".vlink") && p.versions.find(v => v.version === el.dataset.v);
  if (vl) return showDetail(p, vl);   // vue production : ce qu'apporte la version
  if (!RO) return openEditor(S.projets.find(x => x.id === p.id));
  const v = el.dataset.v && p.versions.find(v => v.version === el.dataset.v);   // page publiée : ce qu'apporte la version
  if (v) showDetail(p, v);
});
$("#btn-new").addEventListener("click", () => openEditor(null));
$("#btn-import-tout").addEventListener("click", e => busy(e.currentTarget, async () => {
  if (edit) return toast("Fermer d'abord la fiche du projet", true);
  const list = S.projets.filter(p => p.depot), erreurs = [];
  if (!list.length) return toast("Aucun projet n'a de dépôt", true);
  for (const [i, p] of list.entries()) {   // un par un : le serveur écrit un projet à la fois
    toast(`Import ${i + 1}/${list.length} : ${p.nom}…`);
    try { await api("POST", `/api/projets/${p.id}/import`); } catch (err) { erreurs.push(`${p.nom} : ${err.message}`); }
  }
  await load();
  toast(`${list.length - erreurs.length}/${list.length} dépôt(s) importé(s)` + (erreurs.length ? ` — échec : ${erreurs.join(" ; ")}` : ""), erreurs.length > 0);
}));
$("#j-form").addEventListener("submit", async e => {
  e.preventDefault();
  if (await saveJalons([...S.jalons, { date: $("#j-date").value, label: $("#j-label").value }])) e.target.reset();
});
$("#j-list").addEventListener("click", e => {
  const i = e.target.closest("[data-jdel]")?.dataset.jdel;
  if (i !== undefined) saveJalons(S.jalons.filter((_, k) => k !== +i));
});
$("#d-close").addEventListener("click", () => closeEditor());
$("#b-cancel").addEventListener("click", () => closeEditor());
if (RO) $("#b-cancel").textContent = "Fermer";
if (!RO) $("#prod-aide").textContent += " Sous la version installée : « ⚠ à déployer » si une version plus récente est livrée (visible ici seulement, pas sur la page publiée).";
$("#drawer-bg").addEventListener("click", () => closeEditor());
document.addEventListener("keydown", e => {
  if (e.key === "Escape" && edit) closeEditor();
  if ((e.ctrlKey || e.metaKey) && e.key === "s" && edit) { e.preventDefault(); save(); }
});
$("#b-save").addEventListener("click", e => busy(e.target, save));
["f-nom", "f-pole", "f-depot", "f-branche", "f-postes"].forEach(id => $("#" + id).addEventListener("input", () => setDirty(true)));
$("#f-depot").addEventListener("input", majDepot);
$("#b-branches").addEventListener("click", e => busy(e.target, async () => {
  try {
    const d = await (await api("GET", "/api/branches?url=" + encodeURIComponent($("#f-depot").value.trim()))).json();
    setBranches(d.branches, d.defaut, $("#f-branche").value);
    toast(`${d.branches.length} branche(s)` + (d.defaut ? ` — par défaut : ${d.defaut}` : ""));
  } catch (err) { toast(err.message, true); }
}));
$("#versions").addEventListener("click", e => {   // 📅 : ouvre le calendrier, pré-rempli avec la date du champ
  const b = e.target.closest("[data-cal]"); if (!b) return;
  e.preventDefault();
  const cal = b.nextElementSibling, txt = b.previousElementSibling;
  cal.value = /^\d{4}-\d{2}-\d{2}$/.test(txt.value) ? txt.value : "";
  try { cal.showPicker(); } catch (_) { cal.focus(); }   // navigateur trop ancien : focus sur le champ date
});
$("#versions").addEventListener("change", e => {   // jour choisi : recopié dans le champ texte (même chemin qu'une saisie)
  if (!e.target.classList.contains("cal-in") || !e.target.value) return;
  const txt = e.target.parentElement.querySelector("[data-f]");
  txt.value = e.target.value;
  txt.dispatchEvent(new Event("input", { bubbles: true }));
});
$("#versions").addEventListener("input", e => {
  const f = e.target.dataset.f; if (!f) return;
  const i = +e.target.closest(".ver").dataset.i;
  edit.versions[i][f] = e.target.value; setDirty(true);
  if (f === "statut") renderVersions();
});
$("#versions").addEventListener("click", e => {
  const ie = e.target.closest("[data-efface]")?.dataset.efface;
  if (ie !== undefined) {   // date prévue saisie à tort : effacée à l'enregistrement
    Object.assign(edit.versions[+ie], { prevu: "", prevu_efface: true });
    renderVersions(); setDirty(true); return;
  }
  const i = e.target.closest("[data-del]")?.dataset.del; if (i === undefined) return;
  const v = edit.versions[+i];
  if (confirm(`Supprimer la version ${v.version || "(sans numéro)"} ?`)) { edit.versions.splice(+i, 1); renderVersions(); setDirty(true); }
});
$("#b-add-v").addEventListener("click", () => {
  const top = edit.versions.map(v => vkey(v.version)).filter(Boolean).sort(cmp).pop();
  const next = top ? `v${top[0]}.${top[1] + 1}.0` : "v1.0.0";
  edit.versions.unshift({ version: next, statut: "", debut: "", fin: "", notes: "- " });
  renderVersions(); setDirty(true); $("#versions input").focus();
});
$("#versions").addEventListener("click", e => {
  const b = e.target.closest("[data-livrer]"); if (!b) return;
  const v = edit.versions[+b.dataset.livrer];
  if (!confirm(`Livrer ${v.version} aujourd'hui ?\n\n• statut Terminé, fin = aujourd'hui\n• ROADMAP.md et CHANGELOG.md écrits dans ${edit.depot}\n` +
               `• commit « Release v${vkey(v.version).join(".")} » + tag\n\nRien n'est poussé : à faire ensuite (git push && git push --tags).`)) return;
  const version = v.version;
  busy(b, async () => {
    if (dirty && !(await save())) return;
    try {
      const d = await (await api("POST", `/api/projets/${edit.id}/livrer`, { version })).json();
      await load(); openEditor(d.projet); toast(d.message);
    } catch (err) { toast(err.message, true); }
  });
});
$("#b-del").addEventListener("click", async () => {
  if (!confirm(`Supprimer le projet « ${edit.nom} » ? (son ROADMAP.md est gardé en .supprime dans les données)`)) return;
  try { await api("DELETE", `/api/projets/${edit.id}`); closeEditor(true); await load(); toast("Projet supprimé"); }
  catch (e) { toast(e.message, true); }
});
$("#b-import").addEventListener("click", e => busy(e.target, async () => {
  if (dirty && !(await save())) return;
  let choix = "fusion";
  if (edit.versions.length) {   // versions déjà là : fusionner ou écraser, au choix
    const dlg = $("#import-choix");
    dlg.returnValue = "";
    dlg.showModal();
    choix = await new Promise(r => dlg.addEventListener("close", () => r(dlg.returnValue), { once: true }));
    if (!choix) return;
    if (choix === "remplacer" && !confirm(`Remplacer les ${edit.versions.length} version(s) de « ${edit.nom} » par celles du dépôt ?`)) return;
  }
  try {
    const d = await (await api("POST", `/api/projets/${edit.id}/import`, { remplacer: choix === "remplacer" })).json();
    await load(); openEditor(d.projet); toast(d.message);
  } catch (err) { toast(err.message, true); }
}));
for (const [id, cible] of [["b-exp-rel", "ROADMAP.md"], ["b-exp-chg", "CHANGELOG.md"]]) {
  $("#" + id).addEventListener("click", e => busy(e.target, async () => {
    if (dirty && !(await save())) return;
    if (!confirm(`Écrire ${cible} dans le dépôt ${edit.depot} ?\n(le fichier existant est remplacé ; Git garde l'ancienne version)`)) return;
    try { const d = await (await api("POST", `/api/projets/${edit.id}/export`, { cible })).json(); toast(`Écrit : ${d.chemin}`); }
    catch (err) { toast(err.message, true); }
  }));
}
$("#btn-pub").addEventListener("click", e => {
  e.preventDefault();
  const periode = { debut: $("#debut").value, fin: $("#fin").value };   // la même période que le Gantt / le PPT
  if (!S.config.publication?.serveur) { location.href = "/api/publier?" + new URLSearchParams(periode); return; }   // téléchargement
  busy(e.currentTarget, async () => {
    try { toast((await (await api("POST", "/api/publier", periode)).json()).message); }
    catch (err) { toast(err.message, true); }
  });
});
$("#btn-ppt").addEventListener("click", e => busy(e.currentTarget, async () => {
  try {
    toast("Génération du PowerPoint…");
    const r = await api("POST", "/api/export/ppt", { debut: $("#debut").value, fin: $("#fin").value, ...filtres() });
    const blob = await r.blob();
    const name = decodeURIComponent((r.headers.get("Content-Disposition") || "").split("''")[1] || "roadmap.pptx");
    const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(blob), download: name });
    a.click(); URL.revokeObjectURL(a.href); toast(`PPT généré : ${name} (copie dans exports/)`);
  } catch (err) { toast(err.message, true); }
}));
window.addEventListener("beforeunload", e => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });

// liens directs : #projets (onglet) ou #p=<id> (fiche d'un projet)
{ const vue = location.hash.slice(1) || store.get("vue", "roadmap");   // #projets, #prod (page publiée : roadmap ou prod)
  if (VUE_PROD || vue === "prod" || (vue === "projets" && !RO)) $(`.tabs button[data-view="${VUE_PROD ? "prod" : vue}"]`).click(); }
// page publiée laissée ouverte (écran au mur) : au changement de jour, « aujourd'hui » et les statuts avancent
if (RO) setInterval(() => { if (isoJour() !== S.today) { majJour(); render(); } }, 600000);
// page publiée sur la Raspberry : se recharge seule (vérif. chaque minute) quand une nouvelle publication arrive
if (RO && location.protocol.startsWith("http")) {
  const empreinte = async () => {
    try { const r = await fetch(location.href, { method: "HEAD", cache: "no-store" }); return r.headers.get("ETag") || r.headers.get("Last-Modified"); }
    catch (_) { return null; }   // Raspberry injoignable un instant : on réessaie à la minute suivante
  };
  empreinte().then(v0 => v0 && setInterval(async () => {
    const v = await empreinte();
    if (v && v !== v0 && !$("#detail").open) location.reload();   // pas pendant la lecture d'un détail
  }, 60000));
}
load().then(() => {
  const m = location.hash.match(/^#p=([a-z0-9-]+)$/);
  if (m && !RO) { const p = S.projets.find(x => x.id === m[1]); if (p) openEditor(p); }
}).catch(e => toast("Chargement impossible : " + e.message, true));

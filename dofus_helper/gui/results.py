"""Résultats, résumé de fin de Ctrl+F3, zones affichées."""
from __future__ import annotations

import time
import tkinter as tk

import customtkinter as ctk

from dofus_helper import core
from dofus_helper.gui.style import P

from .common import CARD, fmt, LEVEL_COLORS, MUTED, POINT_COLORS, ZONE_COLORS, ZONE_LABELS
from .helpers import duration_text, MAX_RUNS, reading_quality, save_runs, validate_reminder
from .tray import brand


class ResultsMixin:
    """Résultats, résumé de fin de Ctrl+F3, zones affichées. (partie de App)"""

    # ------------------------------------------------------------- results
    def _on_result(self, res: core.Result):
        self._show_screen(res.screen)
        self._count_stats(res)
        tag = {"warn": "WARN", "error": "ERROR"}.get(res.level) or (
            "OPT" if res.message.startswith("[OPT]") else "OK")
        self._log(res.message, tag, res.new_price)
        if res.message.startswith("[MAJ TOUT]"):
            self._relist_summary(res)
        if self._loop is None or res.level != "ok":
            core.beep(res.level, self.cfg)       # fin d'une boucle réussie : son « fin de parcours »
        head = (f"Lot {res.lot} → {fmt(res.new_price)}" if res.new_price is not None
                else "Liste mise à jour" if res.message.startswith("[MAJ TOUT]") else "Pas de prix")
        self.last_action = (head, res.hint or res.level, LEVEL_COLORS[res.level])
        self._last_action_t = time.time()
        if res.new_price is not None:                # le HUD fait défiler le prix jusqu'à sa valeur
            start = res.old_price if res.old_price and res.old_price != res.new_price else 0
            self._hud_ticker = {"head": head, "tpl": f"Lot {res.lot} → {{}}", "from": start,
                                "to": res.new_price, "t0": time.time()}
        remind = validate_reminder(res, self.cfg)
        if remind:                                   # prix prêt mais pas mis en vente : à toi de valider
            self.last_action = (head, remind, P["gold"])
        self._add_activity(res)
        self._push_history(res, refresh=False)
        if res.level == "ok" and res.message.startswith(("[VENTE]", "[OPT]", "[TOUT]", "[MAJ]")) \
                and ("mis en vente" in res.message or "modifié" in res.message or res.message.startswith("[TOUT]")):
            self._mark_step("sell")
        self._refresh_hud()
        self._hud_flash(P["gold"] if remind else LEVEL_COLORS[res.level])   # le HUD remplace l'ancien popup

    # ---- résumé de fin de Ctrl+F3
    def _relist_summary(self, res: core.Result):
        """Journal : une ligne par prix modifié / ligne à revoir. Historique (onglet Mes ventes) et
        fenêtre : la même chose avec l'image du nom de chaque objet (le nom n'est pas lu en texte)."""
        ids = []                                     # lignes du journal : clic dans le récap = y aller
        for c in res.changes:
            self._log("   " + c.text(), "OK" if c.modified else "WARN", c.new if c.modified else None)
            ids.append(self._log_seq)
        run = {"time": time.time(), "changes": list(res.changes), "summary": dict(res.summary), "log_ids": ids}
        if res.changes:
            self.runs = (self.runs + [run])[-MAX_RUNS:]
            try:
                save_runs(self.runs)
            except OSError as e:
                self._log(f"[Résumé] Historique non enregistré : {e}", "WARN")
            self._refresh_runs()
        if self.cfg.relist_summary and (res.changes or res.summary):
            self._summary_window(run)

    def _summary_window(self, run: dict):
        changes = run["changes"]
        mod = [c for c in changes if c.modified]
        bad = [c for c in changes if not c.modified]
        w = getattr(self, "_summary_win", None)
        if w is not None and w.winfo_exists():
            w.destroy()
        w = ctk.CTkToplevel(self)
        brand(w)
        self._summary_win = w
        w.title("Résumé de la mise à jour (Ctrl+F3) · "
                + time.strftime("%d/%m %H:%M", time.localtime(run["time"])))
        w.geometry("560x560")
        w.attributes("-topmost", True)
        summary = run.get("summary") or {}
        if summary:
            self._summary_tiles(w, summary, len(mod), len(bad))
        else:                                        # ancien parcours (avant le récap)
            ctk.CTkLabel(w, text=f"{len(mod)} prix modifié{'s' if len(mod) > 1 else ''}"
                                 + (f"  ·  {len(bad)} ligne{'s' if len(bad) > 1 else ''} à revoir avec "
                                    f"{self.cfg.hotkeys['relist'].upper()}" if bad else ""),
                         font=ctk.CTkFont(size=15, weight="bold")).pack(anchor="w", padx=14, pady=(12, 4))
        ids = dict(zip(map(id, changes), run.get("log_ids") or []))
        hint = ctk.CTkLabel(w, text="Clic sur une ligne = la retrouver dans le journal" if ids else "",
                            text_color=MUTED, font=ctk.CTkFont(size=11))
        if ids:
            hint.pack(anchor="w", padx=14)
        body = ctk.CTkScrollableFrame(w, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=8, pady=4)
        if not changes:
            ctk.CTkLabel(body, text="Rien à modifier : tes ventes sont déjà au bon prix.",
                         text_color=MUTED).pack(anchor="w", padx=8, pady=8)
        self._summary_imgs = []                     # garder les images (sinon effacées par Tk)
        for c in bad + mod:                          # à revoir en premier
            r = ctk.CTkFrame(body, fg_color=CARD)
            r.pack(fill="x", pady=2)
            img = self._name_thumb(c.img)
            if img is not None:
                self._summary_imgs.append(img)
                ctk.CTkLabel(r, text="", image=img).pack(side="left", padx=6, pady=4)
            if id(c) in ids:
                self._clickable(r, lambda k=ids[id(c)]: self._jump_to_log(k, w, hint))
            lot = f"lot {c.lot}" if c.lot else "lot ?"
            if c.modified:
                txt = f"{lot}   {fmt(c.old)} → {fmt(c.new)}"
                if c.old and c.new:
                    txt += f"   ({(c.new - c.old) / c.old:+.1%})"
                color = P["green"]
            else:
                txt = f"{lot}   NON modifiée : {c.note}"
                color = P["orange"]
            ctk.CTkLabel(r, text=txt, text_color=color, anchor="w", justify="left",
                         wraplength=300).pack(side="left", padx=6)
            ctk.CTkLabel(r, text=f"ligne {c.row}", text_color=MUTED).pack(side="right", padx=8)
        ctk.CTkButton(w, text="Fermer", width=100, command=w.destroy).pack(pady=(4, 12))
        w.bind("<Escape>", lambda _e: w.destroy())

    def _summary_tiles(self, w, s: dict, mod: int, bad: int):
        """Récap en tête du résumé : modifiés, à revoir, déjà au bon prix, durée, et pourquoi ça s'est arrêté."""
        row = ctk.CTkFrame(w, fg_color="transparent")
        row.pack(fill="x", padx=10, pady=(12, 2))
        tiles = ((mod, "modifiés" if mod > 1 else "modifié", P["green"] if mod else MUTED),
                 (bad, "à revoir", P["orange"] if bad else MUTED),
                 (s.get("same", 0), "déjà au bon prix", P["text"]),
                 (duration_text(s.get("seconds")), "durée", P["text"]))
        for i, (value, label, color) in enumerate(tiles):
            row.grid_columnconfigure(i, weight=1, uniform="tile")
            t = ctk.CTkFrame(row, fg_color=CARD, corner_radius=10)
            t.grid(row=0, column=i, sticky="ew", padx=4)
            ctk.CTkLabel(t, text=str(value), text_color=color,
                         font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(6, 0))
            ctk.CTkLabel(t, text=label, text_color=MUTED, font=ctk.CTkFont(size=11)).pack(pady=(0, 6))
        seen = s.get("seen", 0)
        if s.get("complete", True):
            end, color = f"{seen} ligne{'s' if seen > 1 else ''} vue{'s' if seen > 1 else ''} · toute la liste", MUTED
        else:
            end, color = f"{seen} ligne{'s' if seen > 1 else ''} vue{'s' if seen > 1 else ''} · arrêté : " \
                         f"{s.get('stop', '?')}", P["orange"]
        if bad:
            end += f"  ·  lignes à revoir : {self.cfg.hotkeys['relist'].upper()} une par une"
        ctk.CTkLabel(w, text=end, text_color=color, anchor="w", justify="left",
                     wraplength=520).pack(anchor="w", padx=14, pady=(4, 2))

    @staticmethod
    def _clickable(frame, command):
        """Tout le cadre (et ce qu'il contient) réagit au clic."""
        for wdg in [frame] + list(frame.winfo_children()):
            try:
                wdg.configure(cursor="hand2")
            except (tk.TclError, ValueError):
                pass
            wdg.bind("<Button-1>", lambda _e: command())

    def _jump_to_log(self, entry_id: int, win=None, hint=None) -> bool:
        """Résumé -> journal : la ligne est affichée (bloc déplié, filtre « Tout » si besoin) et surlignée."""
        entry = next((e for e in self.log_entries if e.get("id") == entry_id), None)
        if entry is None:
            if hint is not None:
                hint.configure(text="Cette ligne n'est plus dans le journal (effacé).", text_color=P["orange"])
            return False
        b = self.log_blocks.get(entry["block"]) if entry["block"] is not None else None
        if b is not None:
            b["collapsed"] = False
        if not self._entry_visible(entry):
            self.log_filter.set("Tout")
        self._render_log()
        t = self.log_text
        rng = t.tag_ranges(f"e{entry_id}")
        if not rng:
            return False
        t.tag_remove("FOCUS", "1.0", "end")
        t.tag_add("FOCUS", f"{rng[0]} linestart", f"{rng[-1]} lineend")
        t.tag_raise("FOCUS")
        t.see(rng[0])
        if getattr(self, "_focus_after", None):
            self.after_cancel(self._focus_after)
        self._focus_after = self.after(3000, lambda: t.tag_remove("FOCUS", "1.0", "end"))
        if win is not None:
            try:
                win.attributes("-topmost", False)      # le journal passe devant le résumé
            except tk.TclError:
                pass
        self._show_main()
        self.lift()
        return True

    @staticmethod
    def _name_thumb(img):
        """Image du nom (BGR) -> vignette pour l'interface, ou None."""
        if img is None or getattr(img, "size", 0) == 0:
            return None
        try:
            from PIL import Image
            pil = Image.fromarray(img[:, :, ::-1].copy())
            h = 36
            w = max(1, int(pil.width * h / pil.height))
            return ctk.CTkImage(light_image=pil, dark_image=pil, size=(w, h))
        except Exception:
            return None

    def _count_stats(self, res: core.Result):
        m = res.message
        if "SUSPECT" in m:
            self.stats["suspects"] += 1
        if m.startswith("[TOUT]"):
            for seg in m.split("] ", 1)[1].split(" | ")[0].split(" + "):
                n = seg.split("×")[0]
                if n.isdigit():
                    self.stats["ventes"] += int(n)
        elif "mis en vente" in m:
            self.stats["ventes"] += 1
        if m.startswith("[MAJ TOUT]"):
            try:
                self.stats["modifs"] += int(m.split(" modifiées")[0].split(": ")[-1])
            except ValueError:
                pass
        elif m.startswith("[MAJ]") and "| modifié" in m:
            self.stats["modifs"] += 1
        self._refresh_status()

    def _show_screen(self, sr: core.ScreenRead):
        if not sr.prices and sr.selected is None:
            return
        if any(v is not None for v in sr.values.values()):
            self._set_hud_selected(sr)
        if any(r and r.value is not None for r in sr.prices.values()):
            self._set_hdv("ok")
            self._mark_step("read")
            # winfo_manager (placé ?) et non winfo_ismapped (visible ?) : fenêtre réduite pendant
            # Tout vendre, le tableau déjà placé était « non visible » -> pack(before=…) sur un
            # widget retiré -> TclError, et toute l'interface se figeait (« Arrêt… » bloqué).
            if not self.read_grid.winfo_manager():
                if self.read_empty.winfo_manager():
                    self.read_grid.pack(fill="x", padx=12, pady=6, before=self.read_empty)
                    self.read_empty.pack_forget()
                else:
                    self.read_grid.pack(fill="x", padx=12, pady=6)
        self.qty_var.set(str(sr.selected) if sr.selected else "?")
        qcolors = {"good": P["green"], "doubt": P["orange"], "bad": P["red"]}
        for lot, var in self.read_vars.items():
            r = sr.prices.get(lot)
            level, why = reading_quality(r, self.cfg.min_confidence)
            if sr.engine and level:
                why += " · " + {"chiffres": "lecture rapide", "tesseract": "Tesseract"}.get(sr.engine, sr.engine)
            self.read_dots[lot].configure(text="●" if level else "", text_color=qcolors.get(level, MUTED))
            for tip in self.read_tips[lot]:
                tip.text = why
            if r and r.value is not None:
                var.set(fmt(r.value))
                self.unit_vars[lot].set(f"{r.value / lot:,.1f}/u".replace(",", " ") if lot > 1 else "")
            else:
                var.set("—")
                self.unit_vars[lot].set("")
        self.avg_var.set(f"{fmt(sr.avg)} /u" if sr.avg else "—")
        mine = sr.mine if sr.mine is not None else (sr.mine_r.value if sr.mine_r else None)
        self.mine_var.set(fmt(mine) if mine else "—")
        self.engine_var.set({"chiffres": "lecture rapide", "tesseract": "Tesseract"}.get(sr.engine, "—"))
        info = [f"quantité {sr.selected}" if sr.selected else "quantité ?"]
        if sr.avg:
            info.append(f"moyen {fmt(sr.avg)}/u")
        if mine:
            info.append(f"ton prix {fmt(mine)}")
        self.read_info.configure(text=" · ".join(info))

    # ------------------------------------------------------------- overlays
    def _overlay(self, x, y, w, h, color, alpha, ms, label=""):
        t = tk.Toplevel(self)
        t.overrideredirect(True)
        t.attributes("-topmost", True)
        try:
            t.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        t.configure(bg=color)
        if label:
            tk.Label(t, text=label, bg=color, fg="black", font=("Segoe UI", 8, "bold")).place(x=2, y=0)
        t.geometry(f"{w}x{h}+{x}+{y}")
        t.after(ms, t.destroy)

    def _show_zones(self, ms: int = 2500):
        c = self.cfg
        shown = False
        for name, label in ZONE_LABELS.items():
            r = getattr(c, f"{name}_region")
            if r:
                self._overlay(*r, ZONE_COLORS[name], 0.35, ms, label)
                shown = True
        for name in POINT_COLORS:
            p = getattr(c, name)
            if p:
                self._overlay(p[0] - 6, p[1] - 6, 12, 12, POINT_COLORS[name], 0.9, ms)
                shown = True
        if not shown:
            self._log("[Zones] Rien n'est calibré.", "WARN")


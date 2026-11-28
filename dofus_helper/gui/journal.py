"""Journal : filtres, blocs Ctrl+F3 repliables, copie."""
from __future__ import annotations

import time
from typing import Optional

from dofus_helper import core
from dofus_helper.gui import icons as dofus_icons
from dofus_helper.gui import style
from dofus_helper.gui.style import P

from .common import fmt, MUTED, TAG_COLORS
from .helpers import log_category, LOG_FILTERS, LOG_ICONS, log_kind, log_visible


class JournalMixin:
    """Journal : filtres, blocs Ctrl+F3 repliables, copie. (partie de App)"""

    # ---- journal : filtres, blocs Ctrl+F3 repliables, copie
    MAX_LOG = 1500

    def _log_font_size(self) -> int:
        return max(8, round(10 * (self.cfg.ui_scale or 1.0)))

    def _clear_log(self):
        self.log_entries.clear()
        self.log_blocks = {k: b for k, b in self.log_blocks.items() if k == self._block}
        if self._block is not None:       # parcours en cours : son en-tête reste
            self.log_entries.append({"t": time.strftime("%H:%M:%S"), "msg": "", "tag": "INFO",
                                     "cat": "sale", "block": self._block, "header": True})
        self._render_log()

    def _log_plain(self) -> str:
        """Lignes affichées du journal, en texte simple (pour « Copier »)."""
        lines = []
        for e in self.log_entries:
            if not self._entry_visible(e):
                continue
            if e["header"]:
                b = self.log_blocks.get(e["block"])
                if b:
                    lines.append(b["title"])
                continue
            ind = "   " if e["block"] is not None else ""
            lines.append(f"{e['t']}  {ind}{LOG_ICONS[e.get('kind', 'info')]} {e['msg'].lstrip()}")
        return "\n".join(lines)

    def _copy_log(self):
        self.clipboard_clear()
        self.clipboard_append(self._log_plain())
        self.copy_btn.configure(text="Copié ✓")
        self.after(1500, lambda: self.copy_btn.configure(text="Copier"))

    ICON_COLORS = {"sale": "gold", "update": "cyan", "warn": "orange", "error": "red", "cal": "cyan",
                   "ok": "green", "info": "log_time"}

    LOG_BARS = {"sale": "gold", "update": "cyan", "warn": "orange", "error": "red", "cal": "violet",
                "ok": "green", "info": "track"}
    LOG_ICON_NAMES = {"sale": "tag", "update": "edit", "warn": "warn", "error": "error", "cal": "target",
                      "ok": "check", "info": "dot"}

    def _log_fonts(self):
        size = self._log_font_size()
        t = self.log_text
        t.tag_configure("CARD", font=(style.FONT, size))
        t.tag_configure("TIME", font=(style.MONO, max(7, size - 1)))
        t.tag_configure("HDR", font=(style.FONT, size, "bold"))
        t.tag_configure("EMPTY", font=(style.FONT, size + 1))
        t.tag_configure("EMPTY_HINT", font=(style.FONT, size))
        self._log_icon_imgs = {}

    def _log_icon(self, kind: str):
        """Icône d'une ligne du journal (image Tk, à la taille du texte)."""
        imgs = self._log_icon_imgs
        if kind not in imgs:
            from PIL import Image, ImageTk
            px = self._log_font_size() + 5
            img = dofus_icons.icon_image(self.LOG_ICON_NAMES.get(kind, "dot"),
                                         P[self.ICON_COLORS.get(kind, "log_time")], px)
            imgs[kind] = ImageTk.PhotoImage(img.resize((px, px), Image.LANCZOS))
        return imgs[kind]

    def _setup_log_tags(self):
        t = self.log_text
        # chaque ligne est une « carte » : fond légèrement plus clair, barre de couleur à gauche
        t.tag_configure("CARD", background=P["card"] if style.is_dark() else P["card2"],
                        spacing1=2, spacing3=2, rmargin=6)
        for kind, color in self.LOG_BARS.items():
            t.tag_configure(f"B_{kind}", lmargincolor=P[color], lmargin1=4, lmargin2=4)
        t.tag_configure("B_hdr", lmargincolor=P["cyan"], lmargin1=4, lmargin2=4)
        t.tag_configure("GAP", font=(style.MONO, 2))
        t.tag_configure("EMPTY", foreground=P["text"], justify="center", spacing1=26)
        t.tag_configure("EMPTY_HINT", foreground=MUTED, justify="center", spacing1=4)
        self._log_fonts()
        for tag, color in TAG_COLORS.items():
            t.tag_configure(tag, foreground=color)
        for kind, color in self.ICON_COLORS.items():
            t.tag_configure(f"I_{kind}", foreground=P[color])
        t.tag_configure("HDR", foreground=P["cyan"])
        t.tag_configure("FOCUS", background=P["track"])
        t.tag_bind("PRICE", "<Button-1>", self._on_log_click)
        t.tag_bind("PRICE", "<Enter>", lambda _e: t.configure(cursor="hand2"))
        t.tag_bind("PRICE", "<Leave>", lambda _e: t.configure(cursor=""))

    def _on_log_click(self, e):
        """Clic sur une ligne qui contient un prix : le prix est copié (à coller dans le jeu)."""
        t = self.log_text
        ids = [n for n in t.tag_names(t.index(f"@{e.x},{e.y}")) if n[:1] == "e" and n[1:].isdigit()]
        if not ids:
            return
        k = int(ids[0][1:])
        entry = next((x for x in reversed(self.log_entries) if x.get("id") == k), None)
        if entry is None or entry.get("price") is None:
            return
        self.clipboard_clear()
        self.clipboard_append(str(entry["price"]))
        self.log_hint.configure(text=f"{fmt(entry['price'])} copié ✓", text_color=P["green"])
        if getattr(self, "_hint_after", None):
            self.after_cancel(self._hint_after)
        self._hint_after = self.after(1800, lambda: self.log_hint.configure(
            text="Clic sur une ligne avec un prix = le copier", text_color=MUTED))

    def _log(self, msg: str, tag: str = "INFO", price: Optional[int] = None):
        core.log_line(msg, tag)
        self._log_seq += 1
        e = {"t": time.strftime("%H:%M:%S"), "msg": msg, "tag": tag, "cat": log_category(msg, tag),
             "block": self._block, "header": False, "id": self._log_seq, "price": price,
             "kind": log_kind(msg, tag)}
        self.log_entries.append(e)
        if self._block is not None and e["cat"] == "problem":
            self.log_blocks[self._block]["problems"] += 1
        if len(self.log_entries) > self.MAX_LOG:
            del self.log_entries[:300]
            self._render_log()
        elif self._entry_visible(e):
            self._insert_entries([e])

    def _entry_visible(self, e: dict) -> bool:
        flt = LOG_FILTERS.get(self.log_filter.get(), "all")
        b = self.log_blocks.get(e["block"]) if e["block"] is not None else None
        if e["header"]:
            return flt != "problem" or bool(b and b["problems"])
        if b is not None and b["collapsed"]:
            return False
        return log_visible(e["cat"], flt, in_block=b is not None)

    def _insert_entries(self, entries: list):
        t = self.log_text
        t.configure(state="normal")
        if getattr(self, "_log_empty", False) and entries:      # le message « journal vide » s'efface
            t.delete("1.0", "end")
            self._log_empty = False
        for e in entries:
            if e["header"]:
                b = self.log_blocks.get(e["block"])
                if b is None:
                    continue
                htag = f"hdr{e['block']}"
                t.insert("end", " " + ("▶ " if b["collapsed"] else "▼ ") + b["title"] + "\n",
                         ("CARD", "B_hdr", "HDR", htag))
                t.insert("end", "\n", ("GAP",))
                t.tag_bind(htag, "<Button-1>", lambda _e, k=e["block"]: self._toggle_block(k))
                t.tag_bind(htag, "<Enter>", lambda _e: t.configure(cursor="hand2"))
                t.tag_bind(htag, "<Leave>", lambda _e: t.configure(cursor=""))
                continue
            kind = e.get("kind", "info")
            card = ("CARD", f"B_{kind}") + ((f"e{e['id']}",) if e.get("id") else ())
            t.insert("end", " " + ("      " if e["block"] is not None else "") + e["t"] + "  ", card + ("TIME",))
            at = t.index("end-1c")
            t.image_create("end", image=self._log_icon(kind), padx=1)
            for tag in card:
                t.tag_add(tag, at)
            tags = card + (e["tag"],) + (("PRICE",) if e.get("price") is not None else ())
            t.insert("end", "  " + e["msg"].lstrip() + "\n", tags)
            t.insert("end", "\n", ("GAP",))
        t.see("end")
        t.configure(state="disabled")

    def _render_log(self):
        t = self.log_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.configure(state="disabled")
        shown = [e for e in self.log_entries if self._entry_visible(e)]
        self._log_empty = False
        if shown:
            self._insert_entries(shown)
            return
        filtered = bool(self.log_entries) and LOG_FILTERS.get(self.log_filter.get(), "all") != "all"
        t.configure(state="normal")
        t.insert("end", ("Rien avec ce filtre" if filtered else "Le journal est vide") + "\n", ("EMPTY",))
        t.insert("end", ("Choisis « Tout » pour revoir toutes les lignes." if filtered else
                         "Chaque action de l'outil s'affiche ici, la plus récente en bas.") + "\n",
                 ("EMPTY_HINT",))
        t.configure(state="disabled")
        self._log_empty = True

    def _toggle_block(self, key: int):
        b = self.log_blocks.get(key)
        if b:
            b["collapsed"] = not b["collapsed"]
            y = self.log_text.yview()[0]
            self._render_log()
            self.log_text.yview_moveto(y)

    def _block_start(self, kind: str = "relist_all"):
        """Début d'un parcours (Ctrl+F3, F2) : ses lignes vont dans un bloc repliable du journal."""
        self._block_seq += 1
        self._block = self._block_seq
        key = self.cfg.hotkeys.get(kind, "").upper()
        self.log_blocks[self._block] = {
            "title": f"{key} · {self.LOOP_NAMES.get(kind, 'Parcours')} · {time.strftime('%H:%M:%S')} · en cours…",
            "collapsed": False, "problems": 0}
        e = {"t": "", "msg": "", "tag": "INFO", "cat": "sale", "block": self._block, "header": True}
        self.log_entries.append(e)
        self._insert_entries([e])

    def _block_end(self, res: Optional[core.Result]):
        key, self._block = self._block, None
        b = self.log_blocks.get(key)
        if b is None:
            return
        title = b["title"].replace(" · en cours…", "")
        if res is not None and res.changes:
            mod = sum(1 for c in res.changes if c.modified)
            bad = len(res.changes) - mod
            title += f" · {mod} prix modifié{'s' if mod > 1 else ''}" + (f" · {bad} à revoir" if bad else "")
        elif res is not None:
            title += f" · {res.hint or res.level}"
        else:
            title += " · interrompu (erreur)"
        b["title"] = title + "   (clic = déplier / replier)"
        b["collapsed"] = True
        self._render_log()


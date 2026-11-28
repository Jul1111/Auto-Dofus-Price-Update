"""Alerte « calibration décalée » dans le HUD."""
from dofus_helper import gui


def test_no_alert_when_fine_or_not_calibrated():
    assert gui.hud_calib_alert(None, "ok", True) is None
    assert gui.hud_calib_alert(None, None, True) is None
    # pas encore calibré : le HUD dit déjà « Calibration à faire »
    assert gui.hud_calib_alert("La calibration semble décalée : x.", "lost", False) is None


def test_drift_reason_is_shortened():
    head, sub = gui.hud_calib_alert(
        "La calibration semble décalée : la fenêtre du jeu a changé de taille (1600×900 → 1920×1080).",
        "ok", True)
    assert head == "Calibration décalée"
    assert sub == "la fenêtre du jeu a changé de taille (1600×900 → 1920×1080)"
    _, sub = gui.hud_calib_alert("Calibration à refaire : des zones sont hors de l'écran (Tableau). "
                                 "Écran débranché ou résolution changée ?", None, True)
    assert sub == "des zones sont hors de l'écran (Tableau)"


def test_long_reason_is_cut():
    _, sub = gui.hud_calib_alert(
        "La calibration semble décalée : la fenêtre du jeu a bougé de (+100, +50) px et il n'y a pas de "
        "repère « Hôtel de vente » pour que les zones suivent.", None, True)
    assert len(sub) <= gui.HUD_ALERT_LEN and sub.endswith("…")


def test_drift_wins_over_lost_hdv():
    assert gui.hud_calib_alert("A : b.", "lost", True)[0] == "Calibration décalée"
    assert gui.hud_calib_alert(None, "lost", True)[0] == "HDV introuvable"

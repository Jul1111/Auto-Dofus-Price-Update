import pytest

from dofus_helper import core
import dofus_price_helper_cli as cli


def test_no_args_changes_nothing():
    cfg = core.Config()
    assert cli.apply_args(cfg, cli.parse_args([])) is False
    assert cfg.floor_ratio == 0.7 and cfg.floor_mode == "floor" and cfg.smart_f1 is True


def test_floor_options():
    cfg = core.Config()
    assert cli.apply_args(cfg, cli.parse_args(["--plancher", "80", "--sous-plancher", "garder"]))
    assert cfg.floor_ratio == pytest.approx(0.8)
    assert cfg.floor_mode == "keep"


def test_floor_zero_disables():
    cfg = core.Config()
    cli.apply_args(cfg, cli.parse_args(["--plancher", "0"]))
    assert cfg.floor_ratio == 0
    assert "Plancher : désactivé" in cli.describe(cfg)


def test_negative_floor_rejected():
    with pytest.raises(ValueError):
        cli.apply_args(core.Config(), cli.parse_args(["--plancher", "-5"]))


def test_f1_modes():
    cfg = core.Config()
    cli.apply_args(cfg, cli.parse_args(["--f1-simple"]))
    assert cfg.smart_f1 is False
    assert "F1 : vendre\n" in cli.describe(cfg)
    cli.apply_args(cfg, cli.parse_args(["--f1-intelligent"]))
    assert cfg.smart_f1 is True
    with pytest.raises(SystemExit):
        cli.parse_args(["--f1-simple", "--f1-intelligent"])


def test_describe_flags_missing_zones():
    cfg = core.Config()
    out = cli.describe(cfg)
    assert "Ctrl+Alt+F8" in out and "Ctrl+Alt+F5" in out
    cfg.modify_button, cfg.avg_region = [1, 2], [0, 0, 10, 10]
    out = cli.describe(cfg)
    assert "à calibrer" not in out
    assert "70% du prix moyen" in out


def test_profile_option():
    cfg = core.Config(table_region=[1, 1, 5, 5])
    cfg.new_profile("Runes")
    cfg.table_region = [9, 9, 5, 5]
    cfg.switch_profile("Principal")
    assert cli.apply_args(cfg, cli.parse_args(["--profil", "Runes"]))
    assert cfg.profile == "Runes" and cfg.table_region == [9, 9, 5, 5]
    with pytest.raises(ValueError):
        cli.apply_args(cfg, cli.parse_args(["--profil", "Inconnu"]))

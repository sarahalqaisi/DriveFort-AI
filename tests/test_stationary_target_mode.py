from pathlib import Path


def test_visible_impact_loop_does_not_move_targets():
    src = Path('src/carla_bridge.py').read_text()
    start = src.index('def _tick_for_visible_impact')
    end = src.index('def _configure_attack_impact')
    block = src[start:end]
    assert '_place_actor_relative_to_vehicle(' not in block
    assert 'set_transform(' not in block
    assert 'Stationary target mode' in src


def test_adopted_attack_targets_have_forward_clearance():
    src = Path('src/carla_bridge.py').read_text()
    # Guard against the old bug where targets were spawned 5-7m away and then nudged onto the hood.
    assert '("pedestrian", 5.3, 0.0)' not in src
    assert '("vehicle", 6.0, 0.0)' not in src
    assert '"target": ("vehicle", 14.0, 0.0)' in src
    assert '"target": ("pedestrian", 13.0, 0.0)' in src

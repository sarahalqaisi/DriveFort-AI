from app import app, engine


def test_rejects_unknown_preset():
    client = app.test_client()
    res = client.post('/api/preset/not_real')
    assert res.status_code == 400


def test_new_attack_preset_available():
    client = app.test_client()
    res = client.post('/api/preset/gps_spoofing')
    assert res.status_code == 200
    data = res.get_json()
    assert data['attack']['attack_name'] == 'gps_spoofing'
    assert data['attack']['active'] is True


def test_attack_update_validation_clamps_values():
    client = app.test_client()
    res = client.post('/api/update_attack', json={
        'attack_name': 'totally_unknown',
        'intensity': 99,
        'duration_sec': -4,
        'target_ecu': 'evil_ecu',
        'mode': 'unknown',
    })
    data = res.get_json()
    assert data['attack']['attack_name'] == 'normal'
    assert data['attack']['intensity'] == 1.0
    assert data['attack']['duration_sec'] == 1
    assert data['attack']['target_ecu'] in {'steering_ecu', 'brake_ecu', 'gateway_ecu', 'battery_ecu', 'telematics_ecu', 'powertrain_ecu', 'perception_ecu'}

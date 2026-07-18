from app import app


def test_home():
    client = app.test_client()
    res = client.get('/')
    assert res.status_code == 200


def test_api_state():
    client = app.test_client()
    data = client.get('/api/state').get_json()
    assert data['vehicle']['vehicle_brand'] == 'Tesla'
    assert 'risks' in data


def test_attack_changes_risks():
    client = app.test_client()
    normal = client.get('/api/state').get_json()
    attack = client.post('/api/preset/steering_manipulation').get_json()
    assert attack['risks']['cyber_physical'] > normal['risks']['cyber_physical']
    assert attack['risks']['overall'] > normal['risks']['overall']

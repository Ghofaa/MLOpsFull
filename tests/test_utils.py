from madewithml import utils
from madewithml.predict import local_path_from_uri


def test_save_and_load_dict_roundtrip(tmp_path):
    path = tmp_path / "nested" / "results.json"
    payload = {"run_id": "abc123", "metrics": {"f1": 0.75}}

    utils.save_dict(payload, str(path))

    assert utils.load_dict(str(path)) == payload


def test_parse_config_json_handles_powershell_mangled_json():
    parsed = utils.parse_config_json("{dropout_p:0.5,lr:1e-4,lr_factor:0.8,lr_patience:3}")

    assert parsed["dropout_p"] == 0.5
    assert parsed["lr"] == 1e-4
    assert parsed["lr_patience"] == 3


def test_parse_config_json_returns_defaults_when_empty():
    parsed = utils.parse_config_json(None)

    assert parsed == utils.DEFAULT_TRAIN_LOOP_CONFIG


def test_local_path_from_windows_mlflow_uri():
    uri = r"file://C:\Users\ayoub\workspace\.mlops-storage\mlflow/123/run/artifacts"

    path = local_path_from_uri(uri)

    assert str(path) == r"C:\Users\ayoub\workspace\.mlops-storage\mlflow\123\run\artifacts"

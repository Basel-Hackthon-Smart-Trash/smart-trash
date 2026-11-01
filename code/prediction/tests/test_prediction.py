from smartbins import predict


def test_fill_band_uses_observed_level_thresholds():
    assert predict.fill_band(54.9) == "green"
    assert predict.fill_band(55.0) == "orange"
    assert predict.fill_band(79.9) == "orange"
    assert predict.fill_band(80.0) == "red"


def test_status_uses_the_same_green_boundary():
    assert predict.status_for(predict.Prediction(54.9, None, None, 0)) == "green"
    assert predict.status_for(predict.Prediction(55.0, None, None, 0)) == "orange"
    assert predict.status_for(predict.Prediction(80.0, None, None, 0)) == "red"

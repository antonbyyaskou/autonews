from autonews.pipeline.cluster import normalize_tokens, similarity


def test_same_launch_clusters():
    a = normalize_tokens("BYD launches Sealion 08 with 1,000 km range")
    b = normalize_tokens("BYD Sealion 08 revealed: 1,000 km CLTC range and 800V")
    assert similarity(a, b) >= 0.42


def test_unrelated_models_stay_apart():
    a = normalize_tokens("Toyota patents low nose electric sports car layout")
    b = normalize_tokens("Hyundai invests 500 million in Alabama Tucson plant")
    assert similarity(a, b) < 0.2


def test_stopwords_removed():
    tokens = normalize_tokens("The new car is a model for the year")
    assert "the" not in tokens
    assert "new" not in tokens
    assert "model" not in tokens

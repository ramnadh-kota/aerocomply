"""H2: HUMS Advanced Signal Processing & Feature Engine.

    HUMS ingestion (app.services.hums_service)
          |
          v
    SignalProcessor (signal_processing.py) -- validate, preprocess, window
          |
          v
    FeatureExtractor (feature_extractors.py) -- time-domain, frequency-domain,
          |                                      domain-specific
          v
    FeatureRepository (feature_service.py) -- persists HUMSFeature rows
          |
          v
    Existing H1 health/exceedance evaluator (app.services.hums_service)

This package is pure signal processing/statistics — it has no knowledge of
Finding/Evidence/ProactiveSignalRecord. hums_service.py remains the only
place that turns a feature into an exceedance/finding/signal, so H2 does not
introduce a second alerting system.
"""

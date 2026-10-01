"""aurora-forecaster — pure inference kernel for the AURORA SIC forecaster.

Public API (nothing else is part of the interface):

    from forecaster import predict, ForecastOutput
    output = predict(input_tensor)      # [5, 10, 101, 361] -> ForecastOutput
"""

from .predict import predict, ForecastOutput
from .model import ConvLSTMForecaster, ConvLSTMCell

__all__ = ["predict", "ForecastOutput", "ConvLSTMForecaster", "ConvLSTMCell"]

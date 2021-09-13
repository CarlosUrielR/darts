"""
Ensemble Model Base Class
"""

from abc import abstractmethod
from typing import List, Optional, Union, Sequence, Tuple
from functools import reduce

from ..timeseries import TimeSeries
from ..logging import get_logger, raise_if_not, raise_if
from ..models.forecasting_model import ForecastingModel, GlobalForecastingModel

logger = get_logger(__name__)


class EnsembleModel(GlobalForecastingModel):
    """
    Abstract base class for ensemble models.
    Ensemble models take in a list of forecasting models and ensemble their predictions
    to make a single one according to the rule defined by their `ensemble()` method.

    Parameters
    ----------
    models
        List of forecasting models whose predictions to ensemble
    """
    def __init__(self, models: Union[List[ForecastingModel], List[GlobalForecastingModel]]):
        raise_if_not(isinstance(models, list) and models,
                     "Cannot instantiate EnsembleModel with an empty list of models",
                     logger)

        is_local_ensemble = all(isinstance(model, ForecastingModel) and not isinstance(model, GlobalForecastingModel)
                                for model in models)
        self.is_global_ensemble = all(isinstance(model, GlobalForecastingModel) for model in models)

        raise_if_not(is_local_ensemble or self.is_global_ensemble,
                     "All models must either be GlobalForecastingModel instances, or none of them should be.",
                     logger)
        super().__init__()
        self.models = models
        self.is_single_series = None
        self.is_single_series_covariate = None

    def fit(self,
            series: Union[TimeSeries, Sequence[TimeSeries]],
            past_covariates: Optional[Union[TimeSeries, Sequence[TimeSeries]]] = None,
            future_covariates: Optional[Union[TimeSeries, Sequence[TimeSeries]]] = None) -> None:
        """
        Fits the model on the provided series.
        Note that `EnsembleModel.fit()` does NOT call `fit()` on each of its constituent forecasting models.
        It is left to classes inheriting from EnsembleModel to do so appropriately when overriding `fit()`
        """
        raise_if(not self.is_global_ensemble and not isinstance(series, TimeSeries),
                 "The models are not GlobalForecastingModel's and do not support training on multiple series.",
                 logger
                 )
        raise_if(not self.is_global_ensemble and past_covariates is not None,
                 "The models are not GlobalForecastingModel's and do not support past covariates.",
                 logger
                 )

        self.is_single_series = isinstance(series, TimeSeries)
        if past_covariates is not None:
            self.is_single_series_covariate = isinstance(past_covariates, TimeSeries)

        raise_if(past_covariates is not None and (self.is_single_series != self.is_single_series_covariate),
                 "Both series and covariates have to be either univariate or multivariate.",
                 logger
                 )

        super().fit(series, past_covariates, future_covariates)

    def _stack_ts_seq(self, seq1, seq2):
        # stacks two sequences of timeseries elementwise
        return [ts1.stack(ts2) for ts1, ts2 in zip(seq1, seq2)]

    def predict(self,
                n: int,
                series: Optional[Union[TimeSeries, Sequence[TimeSeries]]] = None,
                past_covariates: Optional[Union[TimeSeries, Sequence[TimeSeries]]] = None,
                future_covariates: Optional[Union[TimeSeries, Sequence[TimeSeries]]] = None,
                num_samples: int = 1,
                ) -> Union[TimeSeries, Sequence[TimeSeries]]:

        super().predict(n=n, series=series,
                        past_covariates=past_covariates, future_covariates=future_covariates, num_samples=num_samples)

        if self.is_global_ensemble and not self.is_single_series:
            predictions = self.models[0].predict(n=n, series=series,
                        past_covariates=past_covariates, future_covariates=future_covariates, num_samples=num_samples)
        else:
            predictions = self.models[0].predict(n=n, num_samples=num_samples)

        if len(self.models) > 1:
            for model in self.models[1:]:
                if self.is_global_ensemble and not self.is_single_series:
                    prediction = model.predict(n=n, series=series,
                        past_covariates=past_covariates, future_covariates=future_covariates, num_samples=num_samples)
                    predictions = self._stack_ts_seq(predictions, prediction)
                else:
                    prediction = model.predict(n=n, num_samples=num_samples)
                    predictions = predictions.stack(prediction)

        if self.is_single_series:
            return self.ensemble(predictions)
        else:
            return self.ensemble(predictions, series)

    @abstractmethod
    def ensemble(self,
                 predictions: Union[TimeSeries, Sequence[TimeSeries]],
                 series: Optional[Sequence[TimeSeries]] = None) -> Union[TimeSeries, Sequence[TimeSeries]]:
        """
        Defines how to ensemble the individual models' predictions to produce a single prediction.

        Parameters
        ----------
        predictions
            Individual predictions to ensemble
        series
            Sequence of timeseries to predict on. Optional, since it only makes sense for sequences of timeseries -
            local models retain timeseries for prediction.

        Returns
        -------
        TimeSeries or Sequence[TimeSeries]
            The predicted ``TimeSeries`` or sequence of ``TimeSeries`` obtained by ensembling the individual predictions
        """
        pass

    @property
    def min_train_series_length(self) -> int:
        return max(model.min_train_series_length for model in self.models)

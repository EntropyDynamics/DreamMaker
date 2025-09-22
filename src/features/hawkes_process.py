"""
Hawkes Process Implementation for High-Frequency Trading.
Models self-exciting point processes in order flow dynamics.
"""

import numpy as np
import pandas as pd
from typing import List, Tuple, Optional, Dict, Callable, Union
from dataclasses import dataclass, field
from scipy.optimize import minimize
from scipy.special import gamma
import numba
from loguru import logger


@dataclass
class HawkesEvent:
    """Single event in Hawkes process"""
    timestamp: float
    mark: Optional[float] = None
    event_type: Optional[str] = None


@dataclass
class HawkesParameters:
    """Parameters for Hawkes process"""
    baseline_intensity: float  # μ (mu)
    alpha: float  # Excitation parameter
    beta: float  # Decay parameter

    def branching_ratio(self) -> float:
        """Calculate branching ratio α/β (stability condition: must be < 1)"""
        return self.alpha / self.beta

    def is_stable(self) -> bool:
        """Check if process is stable (non-explosive)"""
        return self.branching_ratio() < 1


class HawkesKernel:
    """Different kernel functions for Hawkes processes"""

    @staticmethod
    def exponential(t: Union[float, np.ndarray], alpha: float, beta: float) -> Union[float, np.ndarray]:
        """
        Exponential kernel: φ(t) = α * exp(-β * t)
        Most common kernel for financial applications.
        """
        return alpha * np.exp(-beta * t)

    @staticmethod
    def power_law(t: Union[float, np.ndarray], alpha: float, beta: float, p: float = 1.1) -> Union[float, np.ndarray]:
        """
        Power-law kernel: φ(t) = α / (1 + β * t)^p
        Captures long memory effects.
        """
        return alpha / np.power(1 + beta * t, p)

    @staticmethod
    def sum_exponentials(t: Union[float, np.ndarray],
                         alphas: List[float],
                         betas: List[float]) -> Union[float, np.ndarray]:
        """
        Sum of exponentials: φ(t) = Σ α_i * exp(-β_i * t)
        Captures multiple timescales.
        """
        result = np.zeros_like(t, dtype=float)
        for alpha, beta in zip(alphas, betas):
            result += alpha * np.exp(-beta * t)
        return result


class UnivariateHawkes:
    """
    Univariate Hawkes process for modeling single event stream.
    Used for individual order types (e.g., market buys, limit sells).
    """

    def __init__(self,
                 baseline_intensity: float = 0.1,
                 alpha: float = 0.5,
                 beta: float = 1.0,
                 kernel: str = "exponential"):
        """
        Initialize univariate Hawkes process.

        Args:
            baseline_intensity: Background intensity μ
            alpha: Excitation parameter
            beta: Decay parameter
            kernel: Kernel type ("exponential", "power_law")
        """
        self.params = HawkesParameters(baseline_intensity, alpha, beta)
        self.kernel_type = kernel
        self.events: List[float] = []

        # Select kernel function
        if kernel == "exponential":
            self.kernel = lambda t: HawkesKernel.exponential(t, alpha, beta)
        elif kernel == "power_law":
            self.kernel = lambda t: HawkesKernel.power_law(t, alpha, beta)
        else:
            raise ValueError(f"Unknown kernel type: {kernel}")

    def intensity(self, t: float) -> float:
        """
        Calculate conditional intensity at time t.
        λ(t) = μ + Σ φ(t - t_i) for t_i < t
        """
        if not self.events:
            return self.params.baseline_intensity

        # Filter past events
        past_events = [ti for ti in self.events if ti < t]
        if not past_events:
            return self.params.baseline_intensity

        # Calculate excitation from past events
        excitation = sum(self.kernel(t - ti) for ti in past_events)

        return self.params.baseline_intensity + excitation

    @numba.jit(nopython=True)
    def _fast_intensity(self, t: float, events: np.ndarray,
                       mu: float, alpha: float, beta: float) -> float:
        """Numba-accelerated intensity calculation"""
        intensity = mu
        for ti in events:
            if ti < t:
                intensity += alpha * np.exp(-beta * (t - ti))
        return intensity

    def simulate(self, T: float, max_events: int = 10000) -> List[float]:
        """
        Simulate Hawkes process using Ogata's thinning algorithm.

        Args:
            T: Time horizon
            max_events: Maximum number of events to generate

        Returns:
            List of event times
        """
        if not self.params.is_stable():
            logger.warning("Process is unstable (branching ratio >= 1)")

        events = []
        t = 0

        # Upper bound for thinning
        lambda_bar = self.params.baseline_intensity

        while t < T and len(events) < max_events:
            # Update upper bound
            if events:
                lambda_bar = self.intensity(t) + self.params.alpha

            # Generate next candidate time
            t += np.random.exponential(1 / lambda_bar)

            if t >= T:
                break

            # Accept/reject based on thinning
            lambda_t = self.intensity(t)
            if np.random.uniform() <= lambda_t / lambda_bar:
                events.append(t)

        self.events = events
        return events

    def log_likelihood(self, events: List[float], T: float) -> float:
        """
        Calculate log-likelihood of observed events.

        LL = Σ log(λ(t_i)) - ∫₀ᵀ λ(s)ds
        """
        if not events:
            return -self.params.baseline_intensity * T

        events = sorted(events)

        # First term: sum of log intensities
        log_sum = 0
        for i, t in enumerate(events):
            past_events = events[:i]
            intensity = self.params.baseline_intensity

            for tj in past_events:
                intensity += self.kernel(t - tj)

            if intensity > 0:
                log_sum += np.log(intensity)
            else:
                log_sum -= 1e10  # Penalty for negative intensity

        # Second term: integral of intensity (analytical for exponential kernel)
        if self.kernel_type == "exponential":
            integral = self.params.baseline_intensity * T
            for ti in events:
                integral += self.params.alpha / self.params.beta * \
                           (1 - np.exp(-self.params.beta * (T - ti)))
        else:
            # Numerical integration for other kernels
            integral = self._numerical_integral(events, T)

        return log_sum - integral

    def _numerical_integral(self, events: List[float], T: float,
                           n_points: int = 1000) -> float:
        """Numerical integration of intensity function"""
        times = np.linspace(0, T, n_points)
        intensities = [self.intensity(t) for t in times]
        return np.trapz(intensities, times)

    def fit(self, events: List[float], T: float,
            method: str = "MLE") -> HawkesParameters:
        """
        Fit Hawkes process parameters to observed events.

        Args:
            events: List of event times
            T: Observation period
            method: Fitting method ("MLE" or "EM")

        Returns:
            Fitted parameters
        """
        events = sorted(events)

        if method == "MLE":
            return self._fit_mle(events, T)
        elif method == "EM":
            return self._fit_em(events, T)
        else:
            raise ValueError(f"Unknown fitting method: {method}")

    def _fit_mle(self, events: List[float], T: float) -> HawkesParameters:
        """Maximum likelihood estimation"""

        def neg_log_likelihood(params):
            mu, alpha, beta = params
            if mu <= 0 or alpha <= 0 or beta <= 0:
                return 1e10
            if alpha >= beta:  # Ensure stability
                return 1e10

            self.params = HawkesParameters(mu, alpha, beta)
            self.kernel = lambda t: HawkesKernel.exponential(t, alpha, beta)

            return -self.log_likelihood(events, T)

        # Initial guess
        n_events = len(events)
        mu_init = n_events / T * 0.5
        alpha_init = 0.5
        beta_init = 1.0

        # Optimize
        result = minimize(
            neg_log_likelihood,
            [mu_init, alpha_init, beta_init],
            method='L-BFGS-B',
            bounds=[(1e-6, None), (1e-6, None), (1e-6, None)]
        )

        if result.success:
            mu_opt, alpha_opt, beta_opt = result.x
            self.params = HawkesParameters(mu_opt, alpha_opt, beta_opt)
            logger.info(f"MLE fit successful: μ={mu_opt:.4f}, α={alpha_opt:.4f}, β={beta_opt:.4f}")
        else:
            logger.warning(f"MLE fit failed: {result.message}")

        return self.params

    def _fit_em(self, events: List[float], T: float,
                max_iter: int = 100, tol: float = 1e-6) -> HawkesParameters:
        """Expectation-Maximization algorithm"""

        n = len(events)
        if n == 0:
            return self.params

        # Initialize
        mu = n / T * 0.5
        alpha = 0.5
        beta = 1.0

        for iteration in range(max_iter):
            # E-step: Calculate branching structure probabilities
            p_matrix = np.zeros((n, n))

            for i in range(n):
                intensity = mu
                for j in range(i):
                    kern = alpha * np.exp(-beta * (events[i] - events[j]))
                    p_matrix[i, j] = kern
                    intensity += kern

                if intensity > 0:
                    p_matrix[i, :] /= intensity

            # M-step: Update parameters
            mu_new = np.sum(1 - np.sum(p_matrix, axis=1)) / T

            if np.sum(p_matrix) > 0:
                alpha_new = np.sum(p_matrix) / n

                # Update beta using Newton-Raphson
                beta_new = self._update_beta_em(events, p_matrix, beta)
            else:
                alpha_new = alpha
                beta_new = beta

            # Check convergence
            if (abs(mu_new - mu) < tol and
                abs(alpha_new - alpha) < tol and
                abs(beta_new - beta) < tol):
                break

            mu, alpha, beta = mu_new, alpha_new, beta_new

        self.params = HawkesParameters(mu, alpha, beta)
        return self.params

    def _update_beta_em(self, events: List[float], p_matrix: np.ndarray,
                       beta_init: float) -> float:
        """Newton-Raphson update for beta in EM algorithm"""
        n = len(events)
        beta = beta_init

        for _ in range(10):  # Newton iterations
            grad = 0
            hess = 0

            for i in range(n):
                for j in range(i):
                    dt = events[i] - events[j]
                    grad += p_matrix[i, j] * (1 - beta * dt)
                    hess += p_matrix[i, j] * dt * dt

            if abs(hess) > 1e-10:
                beta_new = beta + grad / hess
                if abs(beta_new - beta) < 1e-8:
                    break
                beta = max(beta_new, 1e-6)  # Ensure positivity

        return beta


class MultivariateHawkes:
    """
    Multivariate Hawkes process for modeling multiple interacting event streams.
    Used for modeling cross-excitation between different order types.
    """

    def __init__(self, n_dimensions: int,
                 baseline_intensities: Optional[np.ndarray] = None,
                 interaction_matrix: Optional[np.ndarray] = None,
                 decay_matrix: Optional[np.ndarray] = None):
        """
        Initialize multivariate Hawkes process.

        Args:
            n_dimensions: Number of event types
            baseline_intensities: Background intensities μ_i
            interaction_matrix: Cross-excitation matrix α_ij
            decay_matrix: Decay parameters β_ij
        """
        self.n_dims = n_dimensions

        # Initialize parameters
        if baseline_intensities is None:
            self.mu = np.ones(n_dimensions) * 0.1
        else:
            self.mu = baseline_intensities

        if interaction_matrix is None:
            # Default: diagonal dominance with weak cross-excitation
            self.alpha = np.eye(n_dimensions) * 0.5 + np.ones((n_dimensions, n_dimensions)) * 0.05
        else:
            self.alpha = interaction_matrix

        if decay_matrix is None:
            self.beta = np.ones((n_dimensions, n_dimensions))
        else:
            self.beta = decay_matrix

        self.events: Dict[int, List[float]] = {i: [] for i in range(n_dimensions)}

    def intensity(self, t: float, dimension: int) -> float:
        """
        Calculate conditional intensity for specific dimension.
        λ_i(t) = μ_i + Σ_j Σ_{t_k^j < t} α_ij * exp(-β_ij * (t - t_k^j))
        """
        intensity = self.mu[dimension]

        for j in range(self.n_dims):
            for event_time in self.events[j]:
                if event_time < t:
                    intensity += self.alpha[dimension, j] * \
                                np.exp(-self.beta[dimension, j] * (t - event_time))

        return intensity

    def simulate(self, T: float, max_events_per_dim: int = 1000) -> Dict[int, List[float]]:
        """
        Simulate multivariate Hawkes process.

        Returns:
            Dictionary mapping dimension to list of event times
        """
        events = {i: [] for i in range(self.n_dims)}
        all_events = []  # (time, dimension) tuples

        t = 0
        total_events = 0

        while t < T and total_events < max_events_per_dim * self.n_dims:
            # Calculate intensities for all dimensions
            intensities = np.array([self.intensity(t, i) for i in range(self.n_dims)])
            lambda_sum = np.sum(intensities)

            if lambda_sum == 0:
                lambda_sum = np.sum(self.mu)

            # Generate next event time
            t += np.random.exponential(1 / lambda_sum)

            if t >= T:
                break

            # Determine which dimension fires
            intensities = np.array([self.intensity(t, i) for i in range(self.n_dims)])

            if np.sum(intensities) > 0:
                probs = intensities / np.sum(intensities)
                dimension = np.random.choice(self.n_dims, p=probs)

                events[dimension].append(t)
                all_events.append((t, dimension))
                total_events += 1

                # Update for next iteration
                self.events = events

        self.events = events
        return events


class OrderFlowHawkes:
    """
    Specialized Hawkes process for order flow modeling in HFT.
    Models different order types and their interactions.
    """

    def __init__(self):
        """Initialize order flow Hawkes model"""
        # Define order types
        self.order_types = [
            "market_buy",
            "market_sell",
            "limit_buy",
            "limit_sell",
            "cancel_buy",
            "cancel_sell"
        ]

        self.n_types = len(self.order_types)
        self.type_to_idx = {t: i for i, t in enumerate(self.order_types)}

        # Initialize multivariate Hawkes
        self.hawkes = MultivariateHawkes(self.n_types)

        # Storage for computed features
        self.intensity_history = []
        self.excitation_matrix_history = []

    def fit_from_orders(self, orders: pd.DataFrame,
                        time_column: str = "timestamp",
                        type_column: str = "order_type") -> None:
        """
        Fit Hawkes model from order data.

        Args:
            orders: DataFrame with order data
            time_column: Name of timestamp column
            type_column: Name of order type column
        """
        # Group orders by type
        events_by_type = {i: [] for i in range(self.n_types)}

        for _, order in orders.iterrows():
            order_type = order[type_column]
            if order_type in self.type_to_idx:
                idx = self.type_to_idx[order_type]
                timestamp = order[time_column]

                if isinstance(timestamp, pd.Timestamp):
                    timestamp = timestamp.timestamp()

                events_by_type[idx].append(timestamp)

        # Normalize timestamps to start from 0
        min_time = min(min(times) for times in events_by_type.values() if times)
        max_time = max(max(times) for times in events_by_type.values() if times)

        for idx in events_by_type:
            events_by_type[idx] = [t - min_time for t in events_by_type[idx]]

        T = max_time - min_time

        # Fit each dimension separately (simplified approach)
        for i in range(self.n_types):
            if events_by_type[i]:
                univariate = UnivariateHawkes()
                params = univariate.fit(events_by_type[i], T)

                self.hawkes.mu[i] = params.baseline_intensity
                self.hawkes.alpha[i, i] = params.alpha
                self.hawkes.beta[i, i] = params.beta

        logger.info("Hawkes model fitted to order data")

    def get_excitation_features(self, current_time: float) -> Dict[str, float]:
        """
        Extract Hawkes-based features for current market state.

        Returns:
            Dictionary of features including intensities and excitation measures
        """
        features = {}

        # Current intensities for each order type
        for i, order_type in enumerate(self.order_types):
            intensity = self.hawkes.intensity(current_time, i)
            features[f"hawkes_intensity_{order_type}"] = intensity

        # Buy vs Sell pressure
        buy_intensity = (features["hawkes_intensity_market_buy"] +
                        features["hawkes_intensity_limit_buy"])
        sell_intensity = (features["hawkes_intensity_market_sell"] +
                         features["hawkes_intensity_limit_sell"])

        total_intensity = buy_intensity + sell_intensity
        if total_intensity > 0:
            features["hawkes_buy_sell_ratio"] = buy_intensity / total_intensity
        else:
            features["hawkes_buy_sell_ratio"] = 0.5

        # Market vs Limit intensity
        market_intensity = (features["hawkes_intensity_market_buy"] +
                           features["hawkes_intensity_market_sell"])
        limit_intensity = (features["hawkes_intensity_limit_buy"] +
                          features["hawkes_intensity_limit_sell"])

        features["hawkes_market_limit_ratio"] = (
            market_intensity / (market_intensity + limit_intensity + 1e-10)
        )

        # Cancellation intensity
        cancel_intensity = (features["hawkes_intensity_cancel_buy"] +
                           features["hawkes_intensity_cancel_sell"])
        features["hawkes_cancel_ratio"] = cancel_intensity / (total_intensity + 1e-10)

        # Self-excitation strength (diagonal dominance)
        self_excitation = np.mean(np.diag(self.hawkes.alpha))
        cross_excitation = (np.sum(self.hawkes.alpha) - np.sum(np.diag(self.hawkes.alpha))) / (self.n_types * (self.n_types - 1))
        features["hawkes_self_excitation"] = self_excitation
        features["hawkes_cross_excitation"] = cross_excitation

        # Branching ratio (stability measure)
        branching_ratios = self.hawkes.alpha / self.hawkes.beta
        features["hawkes_max_branching"] = np.max(branching_ratios)
        features["hawkes_avg_branching"] = np.mean(branching_ratios)

        return features

    def predict_next_intensity(self, horizon: float,
                               n_samples: int = 100) -> Dict[str, np.ndarray]:
        """
        Predict future intensities using simulation.

        Args:
            horizon: Prediction horizon
            n_samples: Number of Monte Carlo samples

        Returns:
            Dictionary with mean and std predictions for each order type
        """
        predictions = {order_type: [] for order_type in self.order_types}

        # Current time
        t0 = max(max(times) if times else 0 for times in self.hawkes.events.values())

        # Monte Carlo simulation
        for _ in range(n_samples):
            future_events = self.hawkes.simulate(t0 + horizon)

            for i, order_type in enumerate(self.order_types):
                # Count events in prediction window
                future_count = sum(1 for t in future_events[i] if t > t0)
                predictions[order_type].append(future_count / horizon)

        # Compute statistics
        results = {}
        for order_type in self.order_types:
            preds = np.array(predictions[order_type])
            results[f"{order_type}_mean"] = np.mean(preds)
            results[f"{order_type}_std"] = np.std(preds)

        return results
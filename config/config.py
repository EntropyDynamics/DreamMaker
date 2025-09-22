"""
Configuration module for the HFT system.
Contains all system parameters, thresholds, and settings.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

@dataclass
class MT5Config:
    """MetaTrader 5 connection configuration"""
    account: int = int(os.getenv("MT5_ACCOUNT", "0"))
    password: str = os.getenv("MT5_PASSWORD", "")
    server: str = os.getenv("MT5_SERVER", "")
    symbol: str = "WINc1"  # Mini Index futures
    timeout: int = 60000  # milliseconds
    path: Optional[str] = os.getenv("MT5_PATH", None)

@dataclass
class DataConfig:
    """Data processing configuration"""
    tick_bar_size: int = 100  # Number of ticks per bar
    volume_bar_size: float = 1000.0  # Volume per bar
    dollar_bar_size: float = 100000.0  # Dollar value per bar
    lookback_window: int = 1000  # Historical data points to keep
    buffer_size: int = 10000  # Data buffer size
    data_path: Path = Path("data")
    raw_data_path: Path = Path("data/raw")
    processed_data_path: Path = Path("data/processed")
    features_path: Path = Path("data/features")

@dataclass
class FeatureConfig:
    """Feature engineering configuration"""
    ofi_levels: List[int] = field(default_factory=lambda: [1, 2, 3, 5])
    microprice_weights: str = "volume"  # "volume" or "equal"
    spread_type: str = "relative"  # "absolute" or "relative"
    volatility_window: int = 20
    hawkes_kernel: str = "exponential"  # "exponential", "power_law"
    hawkes_decay: float = 0.1
    fractional_diff_d: float = 0.4
    feature_window: int = 50

@dataclass
class ModelConfig:
    """Machine Learning model configuration"""
    model_type: str = "lightgbm"  # "lightgbm", "xgboost", "random_forest"

    # LightGBM parameters
    lgb_params: Dict[str, Any] = field(default_factory=lambda: {
        "objective": "multiclass",
        "num_class": 3,
        "metric": "multi_logloss",
        "boosting_type": "gbdt",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_fraction": 0.9,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "num_threads": -1,
        "lambda_l1": 0.1,
        "lambda_l2": 0.1,
    })

    # Training parameters
    n_estimators: int = 100
    early_stopping_rounds: int = 10
    validation_fraction: float = 0.2

    # Triple Barrier labeling
    pt_sl: List[float] = field(default_factory=lambda: [1.5, 1.5])  # profit/stop-loss
    vertical_barrier: int = 100  # bars

    # Meta-labeling
    use_meta_labeling: bool = True
    meta_model_type: str = "lightgbm"

@dataclass
class ExecutionConfig:
    """Order execution configuration"""
    execution_style: str = "adaptive"  # "aggressive", "passive", "adaptive"
    max_order_size: float = 10.0  # Maximum contracts per order
    slice_size: float = 1.0  # Size of child orders
    price_improvement: float = 0.0001  # Minimum price improvement
    max_spread_cross: float = 2.0  # Maximum spreads to cross
    urgency_threshold: float = 0.7  # Urgency score threshold
    execution_timeout: int = 5000  # milliseconds

@dataclass
class RiskConfig:
    """Risk management configuration"""
    max_position: float = 10.0  # Maximum position size
    max_daily_loss: float = 10000.0  # Maximum daily loss in currency
    max_drawdown: float = 0.2  # Maximum drawdown percentage
    position_limit_per_signal: float = 1.0  # Max position per signal
    stop_loss_multiplier: float = 2.0  # Stop loss as multiple of ATR
    take_profit_multiplier: float = 3.0  # Take profit as multiple of ATR
    risk_per_trade: float = 0.01  # Risk 1% per trade

@dataclass
class BacktestConfig:
    """Backtesting configuration"""
    initial_capital: float = 100000.0
    commission: float = 5.0  # Per contract
    slippage: float = 1.0  # Points

    # CPCV parameters
    n_splits: int = 6
    purge_window: int = 10
    embargo_window: int = 5

    # Performance thresholds
    min_sharpe: float = 1.0
    min_win_rate: float = 0.45
    max_drawdown: float = 0.3
    min_profit_factor: float = 1.2

@dataclass
class SystemConfig:
    """Main system configuration"""
    mt5: MT5Config = field(default_factory=MT5Config)
    data: DataConfig = field(default_factory=DataConfig)
    features: FeatureConfig = field(default_factory=FeatureConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    backtest: BacktestConfig = field(default_factory=BacktestConfig)

    # System parameters
    mode: str = "paper"  # "live", "paper", "backtest"
    log_level: str = "INFO"
    enable_notifications: bool = True
    heartbeat_interval: int = 1000  # milliseconds

    def validate(self) -> bool:
        """Validate configuration parameters"""
        # Add validation logic
        if self.mt5.account == 0:
            raise ValueError("MT5 account not configured")
        if not self.mt5.password:
            raise ValueError("MT5 password not configured")
        if not self.mt5.server:
            raise ValueError("MT5 server not configured")
        return True

# Global configuration instance
config = SystemConfig()
# DreamMaker HFT System

## High-Frequency Trading System with Advanced ML and Microstructure Analysis

### Overview

DreamMaker is a sophisticated High-Frequency Trading (HFT) system designed for Mini Index futures trading. It implements state-of-the-art microstructure analysis, machine learning models, and agent-based architecture for automated trading.

### System Architecture

The system uses a hierarchical agent-based architecture with specialized components:

- **Coordinator Agent**: Central orchestration and consensus management
- **Data Agent**: Real-time data ingestion from MetaTrader 5
- **Feature Agent**: Advanced feature engineering including OFI and Hawkes processes
- **ML Agent**: Machine learning decision making (in development)
- **Execution Agent**: Smart order routing and execution (in development)
- **Risk Agent**: Real-time risk management (in development)

### Key Features

#### Mathematical Models
- **Order Flow Imbalance (OFI)**: Multi-level order book analysis
- **Hawkes Processes**: Self-exciting point processes for order flow dynamics
- **Micro-Price**: Volume-weighted and depth-weighted price estimates
- **Fractional Differentiation**: Maintaining memory while achieving stationarity

#### Feature Engineering (27 Features)
- Price features (mid, micro, weighted)
- Order flow features (OFI at multiple levels)
- Book imbalance metrics
- Spread calculations
- Volatility measures (realized, velocity, acceleration)
- Hawkes intensities and excitation
- Liquidity metrics (Kyle's lambda, Amihud illiquidity)
- Technical indicators (RSI, MACD, Bollinger Bands)

### Installation

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install dependencies
uv sync

# For Windows with MT5 support
uv sync --extra windows
```

### Project Structure

```
DreamMaker/
├── src/
│   ├── agents/         # Agent implementations
│   ├── features/       # Feature engineering
│   ├── models/         # ML models
│   ├── execution/      # Order execution
│   ├── risk/          # Risk management
│   └── backtest/      # Backtesting framework
├── tests/             # Unit and integration tests
├── config/            # Configuration files
├── docs/              # Documentation
│   └── reports/       # Stage documentation
├── data/              # Data storage
├── models/            # Trained models
└── scripts/           # Utility scripts
```

### Current Status

**Stage 1 - COMPLETED ✅**
- [x] Project structure and dependencies
- [x] Base agent framework
- [x] Data connection module (MT5)
- [x] Feature engineering (OFI, Micro-price, Hawkes)
- [x] Unit tests (27 tests)
- [x] Documentation

**Stage 2 - IN PROGRESS**
- [ ] ML Decision Module (LightGBM/Random Forest)
- [ ] Triple Barrier labeling
- [ ] Meta-labeling implementation

**Stage 3 - PENDING**
- [ ] Order Execution Module
- [ ] Risk Management Module

**Stage 4 - PENDING**
- [ ] Backtesting Framework (CPCV)
- [ ] Hyperparameter Optimization

**Stage 5 - PENDING**
- [ ] GitHub Actions CI/CD
- [ ] Production deployment

### Testing

```bash
# Run all tests
uv run pytest tests/

# Run with coverage
uv run pytest tests/ --cov=src --cov-report=term-missing

# Run specific test file
uv run pytest tests/unit/test_microstructure.py -v
```

### Configuration

Edit `config/config.py` to configure:
- MT5 connection parameters
- Feature engineering settings
- Model hyperparameters
- Risk limits
- Execution parameters

### Documentation

Comprehensive documentation for each stage is available in `docs/reports/`:
- [Stage 1 Documentation](docs/reports/Stage_1_Documentation.md) - Foundation and architecture

### Mathematical Foundation

The system is built on rigorous mathematical principles:

1. **Stochastic Calculus**: Geometric Brownian Motion, Itô's Formula
2. **Optimal Control**: Hamilton-Jacobi-Bellman equation
3. **Point Processes**: Hawkes processes for order flow
4. **Microstructure Theory**: Price impact, spread decomposition
5. **Machine Learning**: Ensemble methods, meta-labeling

### Requirements

- Python 3.10+
- MetaTrader 5 (Windows only for live trading)
- 8GB+ RAM recommended
- Multi-core CPU for parallel processing

### License

Proprietary - DreamMaker Team

### Contact

For questions or issues, please contact the development team.

---

*Version: 0.1.0*
*Status: Development*
*Last Updated: Stage 1 Complete*
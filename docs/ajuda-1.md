# Ajuda para Configuração do MetaTrader 5 no WSL

## Status da Implementação

### ✅ Concluído:

1. **Mock MT5 Module**: Criado um módulo mock (`src/utils/mock_mt5.py`) que simula a API do MetaTrader5 para permitir testes sem Wine/MT5 real.

2. **MT5 Bridge**: Criado um bridge (`src/utils/mt5_bridge.py`) que detecta automaticamente o ambiente e usa:
   - Mock MT5 em WSL/Linux sem Wine
   - MT5 real no Windows
   - pymt5linux via Wine (quando disponível)

3. **Data Agent Atualizado**: Modificado `src/agents/data_agent.py` para usar o bridge MT5 ao invés de importar diretamente.

4. **Microstructure Features**: Implementado módulo completo com:
   - Order Flow Imbalance (OFI)
   - Micro-Price (volume-weighted, depth-weighted, imbalance-adjusted)
   - Book Imbalance Metrics
   - Spread Metrics
   - Volatility Features
   - Liquidity Metrics

5. **Testes Unitários**: Criados 27 testes em `tests/unit/test_microstructure.py`

### ⚠️ Limitações no WSL:

1. **pymt5linux requer Python 3.13**: O pacote pymt5linux requer Python >=3.13, mas estamos usando Python 3.12.3. Isso significa que não podemos usar a ponte Wine atualmente.

2. **Wine não instalado**: O Wine não está instalado no WSL. Para instalar seria necessário:
   ```bash
   sudo apt update
   sudo apt install wine xvfb
   ```

3. **MetaTrader5 Real**: O pacote MetaTrader5 só funciona no Windows, não pode ser instalado diretamente no Linux/WSL.

## Solução Atual

O sistema está configurado para usar automaticamente o **Mock MT5** quando:
- Variável de ambiente `USE_MOCK_MT5=true` está definida
- Rodando em Linux/WSL sem Wine
- MetaTrader5 não está disponível

## Para Testar o Sistema

### 1. Rodar testes com Mock MT5:
```bash
USE_MOCK_MT5=true uv run pytest tests/
```

### 2. Testar importação do módulo:
```bash
USE_MOCK_MT5=true uv run python -c "from src.agents.data_agent import DataAgent; print('Success')"
```

### 3. Rodar um script de teste:
```python
import os
os.environ['USE_MOCK_MT5'] = 'true'

from src.agents.data_agent import DataAgent
from config.config import MT5Config, DataConfig

# Configuração mock
mt5_config = MT5Config(
    account=12345,
    password="test",
    server="MockServer",
    symbol="WIN$N"
)

data_config = DataConfig(
    buffer_size=1000,
    tick_bar_size=100,
    volume_bar_size=1000,
    dollar_bar_size=10000
)

# Criar e inicializar o agent
agent = DataAgent(mt5_config, data_config)
```

## Opções para MT5 Real no WSL

### Opção 1: Usar Windows nativo
Execute o sistema diretamente no Windows onde o MT5 pode ser instalado nativamente.

### Opção 2: Docker com Wine (Documentado)
Criar um container Docker com Wine+MT5 conforme documentado no arquivo "Metatrader 5 no WSL e GitHub Actions.md".

### Opção 3: Atualizar Python para 3.13
```bash
# Instalar Python 3.13 quando disponível
uv python install 3.13
uv venv --python 3.13
uv add pymt5linux
```

### Opção 4: Usar VM Windows
Rodar uma máquina virtual Windows para desenvolvimento/testes com MT5 real.

## Componentes Testáveis sem MT5

✅ **Podem ser testados agora:**
- Microstructure features (OFI, Micro-price, etc.)
- Hawkes Process
- Feature engineering
- Agent coordination
- Message passing
- Configuration system

❌ **Precisam do MT5 real:**
- Conexão real com broker
- Dados de mercado em tempo real
- Execução de ordens reais
- Histórico de dados real do MT5

## Próximos Passos Recomendados

1. **Continuar desenvolvimento com Mock MT5**: O mock permite desenvolver e testar toda a lógica do sistema sem depender do MT5 real.

2. **Testes de integração**: Criar testes de integração que validem o comportamento do sistema com dados simulados.

3. **Preparar para produção**: Quando for para produção, executar em ambiente Windows ou container Docker com Wine.

## Preciso de Informações

Para prosseguir com a configuração completa, preciso saber:

1. **Ambiente de produção pretendido**: Windows, Docker, ou Cloud?

2. **Credenciais MT5**: Você tem conta demo/real do MT5 para testes?

3. **Preferência de solução**: Prefere continuar com mock ou configurar Wine/Docker agora?

4. **Python 3.13**: Podemos atualizar para Python 3.13 para usar pymt5linux?

5. **Senha sudo**: Para instalar Wine, precisaria da senha sudo ou rodar com permissões elevadas.

## Comandos Úteis

```bash
# Verificar versão Python
python3 --version

# Listar pacotes instalados
uv pip list

# Rodar todos os testes
USE_MOCK_MT5=true uv run pytest tests/ -v

# Verificar importações
USE_MOCK_MT5=true uv run python -c "import src.utils.mock_mt5; print('Mock OK')"
USE_MOCK_MT5=true uv run python -c "from src.utils.mt5_bridge import get_mt5_module; print('Bridge OK')"

# Rodar testes específicos
USE_MOCK_MT5=true uv run pytest tests/unit/test_microstructure.py::TestOrderFlowImbalance -v
```